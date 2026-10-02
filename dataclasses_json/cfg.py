import contextlib
import functools
import re
from enum import Enum
from typing import Callable, Dict, Iterator, Optional, TypeVar, Union

from marshmallow.fields import Field as MarshmallowField  # type: ignore

from dataclasses_json.stringcase import (camelcase, pascalcase, snakecase,
                                         spinalcase)  # type: ignore
from dataclasses_json.undefined import Undefined, UndefinedParameterError

T = TypeVar("T")


# JavaScript Number.MAX_SAFE_INTEGER: integers with an absolute value
# strictly greater than this cannot be represented exactly as a JSON number
# once parsed by JavaScript.
MAX_SAFE_INTEGER = 2 ** 53 - 1

# Largest integer accepted when restoring an integer-encoded string. 64-bit
# signed IDs fit in this range.
MAX_COMPAT_INTEGER = 2 ** 63 - 1

# A plain decimal (base 10) integer literal, as produced by ``str(int)``:
# an optional minus sign, "0" on its own, or a non-zero leading digit
# followed by more digits. Whitespace, a positive sign, leading zeroes,
# decimal points and exponent notation are rejected.
_DECIMAL_INTEGER_RE = re.compile(r'^-?(0|[1-9]\d*)$')


class Exclude:
    """
    Pre-defined constants for exclusion. By default, fields are configured to
    be included.
    """
    ALWAYS: Callable[[object], bool] = lambda _: True
    NEVER: Callable[[object], bool] = lambda _: False


# TODO: add warnings?
class _GlobalConfig:

    def __init__(self):
        self.encoders: Dict[Union[type, Optional[type]], Callable] = {}
        self.decoders: Dict[Union[type, Optional[type]], Callable] = {}
        self.mm_fields: Dict[
            Union[type, Optional[type]],
            MarshmallowField
        ] = {}
        self.int_compat_enabled: bool = False
        self.int_compat_safe_range: int = MAX_SAFE_INTEGER
        self.int_compat_max_string_int: int = MAX_COMPAT_INTEGER
        # self._json_module = json

    @contextlib.contextmanager
    def int_compat_mode(self,
                        *,
                        enabled: bool = True,
                        safe_range: Optional[int] = None,
                        max_string_int: Optional[int] = None,
                        ) -> Iterator[None]:
        """
        Temporarily configure the integer compatibility mode.

        Integers with an absolute value greater than ``safe_range`` are
        emitted as decimal strings (so they survive a JavaScript
        ``JSON.parse`` round trip). When decoding, decimal strings are
        restored to ``int`` only at positions declared as integers, and only
        when the restored value fits in ``max_string_int``.

        :param enabled: turn the mode on or off.
        :param safe_range: inclusive encoding boundary. Defaults to
            ``2 ** 53 - 1`` (JavaScript's ``Number.MAX_SAFE_INTEGER``).
        :param max_string_int: inclusive maximum absolute value accepted
            when restoring an integer string. Defaults to ``2 ** 63 - 1``
            (the 64-bit signed integer range).
        """
        previous = (self.int_compat_enabled, self.int_compat_safe_range,
                    self.int_compat_max_string_int)
        self.int_compat_enabled = enabled
        self.int_compat_safe_range = (MAX_SAFE_INTEGER
                                      if safe_range is None
                                      else safe_range)
        self.int_compat_max_string_int = (MAX_COMPAT_INTEGER
                                          if max_string_int is None
                                          else max_string_int)
        try:
            yield
        finally:
            (self.int_compat_enabled, self.int_compat_safe_range,
             self.int_compat_max_string_int) = previous

    # TODO: #180
    # @property
    # def json_module(self):
    #     return self._json_module
    #
    # @json_module.setter
    # def json_module(self, value):
    #     warnings.warn(f"Now using {value.__name__} module to handle JSON. "
    #                   f"{self._disable_msg}")
    #     self._json_module = value


global_config = _GlobalConfig()


class LetterCase(Enum):
    CAMEL = camelcase
    KEBAB = spinalcase
    SNAKE = snakecase
    PASCAL = pascalcase


def config(metadata: Optional[dict] = None, *,
           # TODO: these can be typed more precisely
           # Specifically, a Callable[A, B], where `B` is bound as a JSON type
           encoder: Optional[Callable] = None,
           decoder: Optional[Callable] = None,
           mm_field: Optional[MarshmallowField] = None,
           letter_case: Union[Callable[[str], str], LetterCase, None] = None,
           undefined: Optional[Union[str, Undefined]] = None,
           field_name: Optional[str] = None,
           exclude: Optional[Callable[[T], bool]] = None,
           ) -> Dict[str, dict]:
    if metadata is None:
        metadata = {}

    lib_metadata = metadata.setdefault('dataclasses_json', {})

    if encoder is not None:
        lib_metadata['encoder'] = encoder

    if decoder is not None:
        lib_metadata['decoder'] = decoder

    if mm_field is not None:
        lib_metadata['mm_field'] = mm_field

    if field_name is not None:
        if letter_case is not None:
            @functools.wraps(letter_case)  # type:ignore
            def override(_, _letter_case=letter_case, _field_name=field_name):
                return _letter_case(_field_name)
        else:
            def override(_, _field_name=field_name):  # type:ignore
                return _field_name
        letter_case = override

    if letter_case is not None:
        lib_metadata['letter_case'] = letter_case

    if undefined is not None:
        # Get the corresponding action for undefined parameters
        if isinstance(undefined, str):
            if not hasattr(Undefined, undefined.upper()):
                valid_actions = list(action.name for action in Undefined)
                raise UndefinedParameterError(
                    f"Invalid undefined parameter action, "
                    f"must be one of {valid_actions}")
            undefined = Undefined[undefined.upper()]

        lib_metadata['undefined'] = undefined

    if exclude is not None:
        lib_metadata['exclude'] = exclude

    return metadata


def encode_int_compat(value):
    """
    Encode an integer for JSON output under the integer compatibility mode.

    Integers outside the configured safe range are returned as decimal
    strings; safe integers are returned unchanged. ``bool`` is never
    converted (``True``/``False`` stay JSON booleans).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    if not global_config.int_compat_enabled:
        return value
    safe_range = global_config.int_compat_safe_range
    if -safe_range <= value <= safe_range:
        return value
    return str(value)


def decode_int_compat(value):
    """
    Decode a value at a position that is explicitly declared as ``int``.

    ``bool`` and ``float`` are never accepted as integers. Decimal strings
    are restored to ``int``, but fractional numbers, exponent notation and
    values outside the configured integer range are rejected.
    """
    if not global_config.int_compat_enabled:
        return value

    if isinstance(value, bool):
        raise TypeError(
            f"bool is not a valid integer value in integer compatibility "
            f"mode: {value!r}")

    if isinstance(value, int):
        restored = value
    elif isinstance(value, str):
        if not _DECIMAL_INTEGER_RE.match(value):
            raise ValueError(
                f"{value!r} is not a plain decimal integer string; "
                f"fractional numbers and exponent notation are not allowed")
        restored = int(value)
    else:
        raise TypeError(
            f"expected an integer or a decimal integer string, got "
            f"{type(value).__name__}: {value!r}")

    max_string_int = global_config.int_compat_max_string_int
    if not -max_string_int <= restored <= max_string_int:
        raise ValueError(
            f"integer {restored} is outside the configured integer "
            f"compatibility range (+/-{max_string_int})")
    return restored
