import re
from datetime import datetime, timedelta, timezone
from enum import Enum


class DatetimeFormat(Enum):
    TIMESTAMP = "timestamp"
    ISO = "iso"


class IsoDatetimeError(ValueError):
    pass


_ISO_DATETIME_RE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"[Tt ](?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?"
    r"(?P<tz>Z|[+-]\d{2}(?::?\d{2})?(?::?\d{2})?)?$"
)


def coerce_datetime_format(value, default=DatetimeFormat.TIMESTAMP):
    if value is None:
        return default
    if isinstance(value, DatetimeFormat):
        return value
    if isinstance(value, str):
        try:
            return DatetimeFormat(value.lower())
        except ValueError:
            pass
    raise ValueError(
        "datetime_format must be one of: "
        f"{DatetimeFormat.TIMESTAMP.value!r}, {DatetimeFormat.ISO.value!r}"
    )


def _parse_offset(value):
    sign = 1 if value[0] == "+" else -1
    parts = value[1:].split(":")
    if len(parts) == 1:
        width = len(parts[0])
        if width == 2:
            hours = parts[0]
            minutes = "00"
            seconds = "00"
        elif width in (4, 6):
            hours = parts[0][:2]
            minutes = parts[0][2:4]
            seconds = parts[0][4:6]
        else:
            raise IsoDatetimeError(f"Invalid UTC offset: {value!r}")
    elif len(parts) in (2, 3):
        hours, minutes = parts[0], parts[1]
        seconds = parts[2] if len(parts) == 3 else "00"
    else:
        raise IsoDatetimeError(f"Invalid UTC offset: {value!r}")

    if not (len(hours) == len(minutes) == len(seconds) == 2):
        raise IsoDatetimeError(f"Invalid UTC offset: {value!r}")
    if not (0 <= int(hours) <= 23
            and 0 <= int(minutes) <= 59
            and 0 <= int(seconds) <= 59):
        raise IsoDatetimeError(f"Invalid UTC offset: {value!r}")

    return timezone(sign * timedelta(
        hours=int(hours), minutes=int(minutes), seconds=int(seconds)
    ))


def decode_iso_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise IsoDatetimeError(
                "Naive datetimes are not accepted by the ISO datetime "
                "codec; include 'Z' or a numeric UTC offset"
            )
        return value

    if not isinstance(value, str):
        raise IsoDatetimeError(
            f"Expected an ISO 8601 datetime string, got {type(value).__name__}"
        )

    match = _ISO_DATETIME_RE.match(value)
    if match is None:
        raise IsoDatetimeError(f"Not a valid ISO 8601 datetime: {value!r}")

    timezone_text = match.group("tz")
    if timezone_text is None:
        raise IsoDatetimeError(
            f"Naive datetime {value!r} is not accepted; include 'Z' or a "
            "numeric UTC offset"
        )

    fraction = match.group("fraction")
    if fraction is not None and len(fraction) > 6:
        raise IsoDatetimeError(
            f"Datetime {value!r} has {len(fraction)} fractional-second "
            "digits; at most 6 digits (microsecond precision) are "
            "supported"
        )

    second = int(match.group("second") or 0)
    if second == 60:
        raise IsoDatetimeError(
            f"Leap second in {value!r} cannot be represented by datetime"
        )

    microsecond = int(fraction.ljust(6, "0")) if fraction is not None else 0
    try:
        tzinfo = (timezone.utc if timezone_text == "Z"
                  else _parse_offset(timezone_text))
    except ValueError as exc:
        raise IsoDatetimeError(
            f"Not a representable ISO 8601 datetime: {value!r}"
        ) from exc

    try:
        return datetime(
            year=int(match.group("year")),
            month=int(match.group("month")),
            day=int(match.group("day")),
            hour=int(match.group("hour")),
            minute=int(match.group("minute")),
            second=second,
            microsecond=microsecond,
            tzinfo=tzinfo,
        )
    except ValueError as exc:
        raise IsoDatetimeError(
            f"Not a representable ISO 8601 datetime: {value!r}"
        ) from exc


def encode_iso_datetime(value):
    if not isinstance(value, datetime):
        raise TypeError(
            f"Expected a datetime instance, got {type(value).__name__}"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise IsoDatetimeError(
            "Naive datetimes are not accepted by the ISO datetime codec; "
            "attach an explicit timezone before encoding"
        )

    if value.utcoffset() == timedelta(0):
        value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return value.isoformat()
