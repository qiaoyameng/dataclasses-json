"""
Explicit ISO 8601 datetime codec for dataclasses-json.

This module implements an opt-in, machine-timezone-independent datetime
encoding/decoding policy. It never consults the host's local timezone:
offsets are taken from the value itself (encoding) or from the string
(decoding). Naive datetimes / offset-less strings are handled strictly
according to the configured ``NaivePolicy``.

Unrepresentable input (leap seconds, out-of-range dates, sub-microsecond
precision) raises ``Iso8601Error`` instead of being silently corrected.
"""
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Union

_ISO8601_SHORTHAND = 'iso8601'


class Iso8601Error(ValueError):
    """Raised when a value cannot be represented as / parsed from an
    ISO 8601 datetime string under the configured policy."""


class NaivePolicy(Enum):
    """Policy for datetimes without UTC offset information.

    REJECT:      raise ``Iso8601Error`` -- never borrow the machine's
                 local timezone.
    ASSUME_UTC:  interpret the naive value as UTC (documented, explicit).
    """
    REJECT = 'reject'
    ASSUME_UTC = 'assume_utc'


class Iso8601DateTime:
    """
    Specification for explicit ISO 8601 datetime encoding/decoding.

    Parameters
    ----------
    fraction_digits:
        Number of fractional-second digits emitted on encode.
        ``6`` (default) keeps microsecond precision, ``0`` omits the
        fraction entirely, ``None`` omits trailing zeros (and the
        fraction altogether when the microsecond is zero).
        Values outside ``0..6`` are rejected.
    naive:
        ``NaivePolicy`` for values without UTC offset information.
        Defaults to ``NaivePolicy.REJECT`` so the machine's local
        timezone is never silently borrowed.
    use_z:
        Emit ``Z`` instead of ``+00:00`` for the UTC offset on encode.
        Defaults to ``True``. Decoding always accepts both ``Z``/``z``
        and numeric ``+-HH:MM`` offsets.
    """

    def __init__(self,
                 fraction_digits: Optional[int] = 6,
                 naive: NaivePolicy = NaivePolicy.REJECT,
                 use_z: bool = True):
        if fraction_digits is not None:
            if not isinstance(fraction_digits, int) \
                    or isinstance(fraction_digits, bool) \
                    or not 0 <= fraction_digits <= 6:
                raise ValueError(
                    "fraction_digits must be None or an int in 0..6, "
                    f"got {fraction_digits!r}")
        if not isinstance(naive, NaivePolicy):
            raise ValueError(
                f"naive must be a NaivePolicy, got {naive!r}")
        self.fraction_digits = fraction_digits
        self.naive = naive
        self.use_z = bool(use_z)

    def __eq__(self, other):
        if not isinstance(other, Iso8601DateTime):
            return NotImplemented
        return (self.fraction_digits == other.fraction_digits
                and self.naive == other.naive
                and self.use_z == other.use_z)

    def __repr__(self):
        return (f"Iso8601DateTime(fraction_digits={self.fraction_digits!r}, "
                f"naive={self.naive!r}, use_z={self.use_z!r})")


def normalize_datetime_format(value) -> Optional[Iso8601DateTime]:
    """Normalize a ``datetime_format`` config value.

    Accepts an ``Iso8601DateTime`` instance or the shorthand string
    ``'iso8601'`` (default spec). Anything else is a configuration error.
    """
    if value is None:
        return None
    if isinstance(value, Iso8601DateTime):
        return value
    if isinstance(value, str) and value.lower() == _ISO8601_SHORTHAND:
        return Iso8601DateTime()
    raise ValueError(
        "datetime_format must be an Iso8601DateTime instance or the "
        f"string {_ISO8601_SHORTHAND!r}, got {value!r}")


def _require_aware(dt: datetime, spec: Iso8601DateTime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        if spec.naive is NaivePolicy.ASSUME_UTC:
            return dt.replace(tzinfo=timezone.utc)
        raise Iso8601Error(
            f"cannot ISO 8601-encode naive datetime {dt!r}: no UTC offset "
            "information and naive=NaivePolicy.REJECT. The local machine "
            "timezone is never assumed implicitly; pass an aware datetime "
            "or configure naive=NaivePolicy.ASSUME_UTC.")
    return dt


def encode_iso8601(dt: datetime, spec: Iso8601DateTime) -> str:
    """Encode an aware datetime as an ISO 8601 string.

    The encoded string always carries an explicit UTC offset (``Z`` or
    ``+-HH:MM[:SS]``), so the represented instant is preserved exactly and
    does not depend on the machine's timezone.
    """
    if not isinstance(dt, datetime):
        raise Iso8601Error(
            f"expected a datetime instance, got {type(dt).__name__}")
    dt = _require_aware(dt, spec)

    digits = spec.fraction_digits
    if digits is None:
        frac = f'.{dt.microsecond:06d}'.rstrip('0') if dt.microsecond else ''
    elif digits == 0:
        frac = ''
    else:
        truncated = dt.microsecond // (10 ** (6 - digits))
        frac = f'.{truncated:0{digits}d}'

    offset = dt.utcoffset()
    if offset is None:
        raise Iso8601Error(f"datetime {dt!r} has no UTC offset")
    if offset == timedelta(0) and spec.use_z:
        offset_str = 'Z'
    else:
        total_seconds = offset.days * 86400 + offset.seconds
        sign = '+' if total_seconds >= 0 else '-'
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        offset_str = f'{sign}{hours:02d}:{minutes:02d}'
        if seconds:
            offset_str += f':{seconds:02d}'

    return (f'{dt.year:04d}-{dt.month:02d}-{dt.day:02d}'
            f'T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}'
            f'{frac}{offset_str}')


_ISO8601_RE = re.compile(
    r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})'
    r'[T ](?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})'
    r'(?:\.(?P<fraction>\d+))?'
    r'(?P<offset>[Zz]|[+-]\d{2}:\d{2}(?::\d{2})?)?$')


def decode_iso8601(value: Union[str, datetime],
                   spec: Iso8601DateTime) -> datetime:
    """Decode an ISO 8601 string to a timezone-aware datetime.

    The result always carries explicit tzinfo; the local machine timezone
    is never consulted. Strings without an offset follow ``spec.naive``.
    Leap seconds, out-of-range dates and sub-microsecond precision raise
    ``Iso8601Error`` -- they are never silently corrected to another
    instant. ``datetime`` instances pass through the naive policy
    unchanged in instant terms.
    """
    if isinstance(value, datetime):
        return _require_aware(value, spec)
    if not isinstance(value, str):
        raise Iso8601Error(
            f"expected an ISO 8601 string, got {type(value).__name__}: "
            f"{value!r}")

    match = _ISO8601_RE.match(value)
    if match is None:
        raise Iso8601Error(f"not a valid ISO 8601 datetime: {value!r}")

    parts = match.groupdict()

    fraction = parts['fraction']
    if fraction is None:
        microsecond = 0
    else:
        if len(fraction) > 6:
            raise Iso8601Error(
                f"sub-microsecond precision is not representable: {value!r}")
        microsecond = int(fraction.ljust(6, '0'))

    second = int(parts['second'])
    if second == 60:
        raise Iso8601Error(
            f"leap seconds are not representable as datetime: {value!r}")

    offset = parts['offset']
    if offset is None:
        tzinfo = None
    elif offset in ('Z', 'z'):
        tzinfo = timezone.utc
    else:
        sign = -1 if offset[0] == '-' else 1
        offset_parts = offset[1:].split(':')
        hours = int(offset_parts[0])
        minutes = int(offset_parts[1])
        seconds = int(offset_parts[2]) if len(offset_parts) > 2 else 0
        if hours > 23 or minutes > 59 or seconds > 59:
            raise Iso8601Error(
                f"invalid UTC offset in ISO 8601 datetime: {value!r}")
        delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        if delta >= timedelta(hours=24):
            raise Iso8601Error(
                f"UTC offset out of range in ISO 8601 datetime: {value!r}")
        tzinfo = timezone(sign * delta)

    try:
        result = datetime(int(parts['year']), int(parts['month']),
                          int(parts['day']), int(parts['hour']),
                          int(parts['minute']), second, microsecond,
                          tzinfo=tzinfo)
    except ValueError as exc:
        raise Iso8601Error(
            f"date/time out of range in ISO 8601 datetime {value!r}: "
            f"{exc}") from exc

    return _require_aware(result, spec)
