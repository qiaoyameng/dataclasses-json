import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest
from marshmallow import ValidationError, fields

from dataclasses_json import DatetimeFormat, config, dataclass_json
from dataclasses_json._datetime import IsoDatetimeError


@dataclass_json(datetime_format=DatetimeFormat.ISO)
@dataclass
class IsoDatetimeContainer:
    scalar: datetime
    values: List[datetime]
    by_key: Dict[str, datetime]
    maybe: Optional[datetime] = None


@dataclass_json
@dataclass
class FieldOverrideContainer:
    iso_value: datetime = field(
        metadata=config(datetime_format=DatetimeFormat.ISO)
    )
    timestamp_value: datetime


@dataclass_json(datetime_format=DatetimeFormat.ISO)
@dataclass
class FieldTimestampOverride:
    iso_value: datetime
    timestamp_value: datetime = field(
        metadata=config(datetime_format=DatetimeFormat.TIMESTAMP)
    )


@dataclass_json(datetime_format=DatetimeFormat.ISO)
@dataclass
class FieldCustomCodec:
    value: datetime = field(metadata=config(
        encoder=lambda value: "custom",
        decoder=lambda value: datetime(2024, 1, 1, tzinfo=timezone.utc),
    ))


@dataclass_json(datetime_format=DatetimeFormat.ISO)
@dataclass
class FieldCustomMarshmallowField:
    value: datetime = field(metadata=config(mm_field=fields.String()))


def test_iso_datetime_class_config_round_trip():
    data = {
        "scalar": "2024-01-01T12:00:00.123456+05:30",
        "values": [
            "2024-11-03T01:30:00-04:00",
            "2024-11-03T01:30:00-05:00",
        ],
        "by_key": {"utc": "2024-01-01T00:00:00Z"},
        "maybe": "2024-01-01T00:00:00+00:00",
    }

    obj = IsoDatetimeContainer.from_dict(data)

    assert obj.scalar.utcoffset().total_seconds() == 5.5 * 3600
    assert [value.utcoffset().total_seconds() for value in obj.values] == [
        -4 * 3600, -5 * 3600
    ]
    assert obj.to_dict() == {
        "scalar": "2024-01-01T12:00:00.123456+05:30",
        "values": [
            "2024-11-03T01:30:00-04:00",
            "2024-11-03T01:30:00-05:00",
        ],
        "by_key": {"utc": "2024-01-01T00:00:00Z"},
        "maybe": "2024-01-01T00:00:00Z",
    }


def test_field_datetime_format_overrides_class_default():
    iso = "2024-01-01T00:00:00Z"
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    payload = {"iso_value": iso, "timestamp_value": timestamp}

    obj = FieldOverrideContainer.from_dict(payload)

    assert obj.iso_value == datetime.fromisoformat(iso)
    encoded = json.loads(obj.to_json())

    assert encoded == {
        "iso_value": iso,
        "timestamp_value": timestamp,
    }


def test_timestamp_field_override_uses_legacy_format():
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    obj = FieldTimestampOverride(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    encoded = obj.to_dict()

    assert encoded["iso_value"] == "2024-01-01T00:00:00Z"
    assert encoded["timestamp_value"] == timestamp


def test_timestamp_field_override_uses_legacy_schema_format():
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    schema = FieldTimestampOverride.schema()
    obj = schema.load({
        "iso_value": "2024-01-01T00:00:00Z",
        "timestamp_value": timestamp,
    })

    assert schema.dump(obj) == {
        "iso_value": "2024-01-01T00:00:00Z",
        "timestamp_value": timestamp,
    }


def test_schema_load_and_dump_share_iso_semantics():
    data = {
        "scalar": "2024-01-01T00:00:00+02:00",
        "values": [
            "2024-11-03T01:30:00-04:00",
            "2024-11-03T01:30:00-05:00",
        ],
        "by_key": {"utc": "2024-01-01T00:00:00Z"},
        "maybe": None,
    }
    schema = IsoDatetimeContainer.schema()

    obj = schema.load(data)

    assert schema.dump(obj) == data


@pytest.mark.parametrize("value", [
    "2024-01-01T00:00:00",
    "2024-01-01T00:00:60Z",
    "2024-01-32T00:00:00Z",
    "2024-01-01T24:00:00Z",
    "2024-01-01T00:00:00.1234567Z",
])
def test_invalid_iso_datetime_direct_load(value):
    with pytest.raises(IsoDatetimeError):
        IsoDatetimeContainer.from_dict({
            "scalar": value,
            "values": [],
            "by_key": {},
        })


@pytest.mark.parametrize("value", [
    "2024-01-01T00:00:00",
    "2024-01-01T00:00:60Z",
    "2024-01-32T00:00:00Z",
    "2024-01-01T00:00:00.1234567Z",
])
def test_invalid_iso_datetime_schema_load_is_field_error(value):
    with pytest.raises(ValidationError) as exc_info:
        IsoDatetimeContainer.schema().load({
            "scalar": value,
            "values": [],
            "by_key": {},
        })

    assert "scalar" in exc_info.value.messages


def test_invalid_iso_datetime_in_nested_container_is_field_error():
    with pytest.raises(ValidationError) as exc_info:
        IsoDatetimeContainer.schema().load({
            "scalar": "2024-01-01T00:00:00Z",
            "values": ["2024-01-01T00:00:60Z"],
            "by_key": {"bad": "2024-01-32T00:00:00Z"},
        })

    assert "Leap second" in exc_info.value.messages["values"][0][0]
    assert "representable" in exc_info.value.messages["by_key"]["bad"]["value"][0]


def test_naive_datetime_encode_is_rejected():
    obj = IsoDatetimeContainer(datetime(2024, 1, 1), [], {})

    with pytest.raises(IsoDatetimeError):
        obj.to_dict()


def test_explicit_field_codec_takes_precedence_over_built_in_iso():
    obj = FieldCustomCodec(datetime(2024, 1, 1))

    assert obj.to_dict() == {"value": "custom"}
    assert FieldCustomCodec.from_dict({"value": "ignored"}).value == datetime(
        2024, 1, 1, tzinfo=timezone.utc
    )


def test_explicit_mm_field_takes_precedence_in_schema():
    schema = FieldCustomMarshmallowField.schema()

    assert schema.dump(FieldCustomMarshmallowField("custom")) == {"value": "custom"}
    assert schema.load({"value": "custom"}).value == "custom"


def test_iso_datetime_is_stable_across_process_timezones():
    script = """
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List

from dataclasses_json import DatetimeFormat, dataclass_json


@dataclass_json(datetime_format=DatetimeFormat.ISO)
@dataclass
class Sample:
    repeated_dst_wall_time: List[datetime]


data = {
    "repeated_dst_wall_time": [
        "2024-11-03T01:30:00-04:00",
        "2024-11-03T01:30:00-05:00",
    ]
}
obj = Sample.from_dict(data)
result = {
    "loaded": obj.to_dict(),
    "timestamps": [value.timestamp() for value in obj.repeated_dst_wall_time],
    "schema": Sample.schema().dump(Sample.schema().load(data)),
}
print(json.dumps(result, sort_keys=True))
"""
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    outputs = []

    for tz in ("UTC0", "UTC5"):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            env=dict(env, TZ=tz),
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(json.loads(completed.stdout))

    assert outputs[0] == outputs[1]
    assert outputs[0] == {
        "loaded": {
            "repeated_dst_wall_time": [
                "2024-11-03T01:30:00-04:00",
                "2024-11-03T01:30:00-05:00",
            ]
        },
        "timestamps": [1730611800.0, 1730615400.0],
        "schema": {
            "repeated_dst_wall_time": [
                "2024-11-03T01:30:00-04:00",
                "2024-11-03T01:30:00-05:00",
            ]
        },
    }
