import functools
from enum import Enum
from typing import Callable, Dict, Optional, TypeVar, Union

from marshmallow.fields import Field as MarshmallowField  # type: ignore

from dataclasses_json.stringcase import (camelcase, pascalcase, snakecase,
                                         spinalcase)  # type: ignore
from dataclasses_json.undefined import Undefined, UndefinedParameterError

T = TypeVar("T")

#: The largest integer that can be represented exactly as a JavaScript
#: number (IEEE 754 double precision), i.e. ``Number.MAX_SAFE_INTEGER``.
MAX_SAFE_INTEGER = 2 ** 53 - 1

#: Largest magnitude accepted when restoring an integer from a string by
#: default. Signed 64 bit identifiers stay within this range.
MAX_SIGNED_64BIT = 2 ** 63 - 1

_UNSET = object()


class IntMode(Enum):
    """Controls how plain :class:`int` values are encoded to and decoded
    from JSON.

    ``LEGACY`` keeps the historical behavior: integers are always emitted as
    JSON numbers and decoding never accepts strings at integer positions.

    ``SAFE`` enables the JavaScript integer compatibility mode: integers
    outside the configured safe range are emitted as decimal strings and,
    when decoding, only positions explicitly annotated as ``int`` restore
    such strings back to integers.
    """
    LEGACY = "legacy"
    SAFE = "safe"


def _check_positive_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int, got {value!r}")


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
        self.int_mode: IntMode = IntMode.LEGACY
        self.int_safe_limit: int = MAX_SAFE_INTEGER
        self.int_max_abs: Optional[int] = MAX_SIGNED_64BIT
        # self._json_module = json

    def set_int_compatibility(self,
                              *,
                              enabled: bool = True,
                              safe_limit: Optional[int] = None,
                              max_abs: Optional[int] = _UNSET) -> None:
        """Configure the integer compatibility mode.

        :param enabled: turn the safe-integer mode on (``IntMode.SAFE``) or
            off (``IntMode.LEGACY``).
        :param safe_limit: integers with ``abs(value)`` strictly greater than
            this limit are emitted as decimal strings. Defaults to
            ``2 ** 53 - 1``.
        :param max_abs: maximum magnitude accepted when restoring an integer
            from a string. Defaults to ``2 ** 63 - 1`` (signed 64 bit ids).
            Pass ``None`` to remove the upper bound.
        """
        self.int_mode = IntMode.SAFE if enabled else IntMode.LEGACY
        if safe_limit is not None:
            _check_positive_int(safe_limit, "safe_limit")
            self.int_safe_limit = safe_limit
        if max_abs is not _UNSET:
            if max_abs is not None:
                _check_positive_int(max_abs, "max_abs")
            self.int_max_abs = max_abs

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
