"""Tests for the explicit ISO 8601 datetime codec.

These tests must pass under any machine timezone (they are exercised
under multiple TZ settings); the codec never consults the local
timezone.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pytest
from marshmallow import ValidationError, fields

from dataclasses_json import (DataClassJsonMixin, Iso8601DateTime,
                              Iso8601Error, NaivePolicy, config,
                              dataclass_json)

UTC = timezone.utc
EST5 = timezone(-timedelta(hours=5))       # fixed -05:00
IST530 = timezone(timedelta(hours=5, minutes=30))  # fixed +05:30

DT = datetime(2018, 11, 17, 16, 55, 28, 456753, tzinfo=UTC)
ISO_Z = '2018-11-17T16:55:28.456753Z'


@dataclass_json(datetime_format='iso8601')
@dataclass
class ClassLevelIso:
    at: datetime


@dataclass_json
@dataclass
class FieldLevelIso:
    at: datetime = field(metadata=config(
        datetime_format=Iso8601DateTime()))


@dataclass_json(datetime_format=Iso8601DateTime(fraction_digits=0))
@dataclass
class ClassAndFieldSpec:
    whole: datetime
    millis: datetime = field(metadata=config(
        datetime_format=Iso8601DateTime(fraction_digits=3)))


@dataclass_json(datetime_format='iso8601')
@dataclass
class NestedIso:
    stamps: List[datetime]
    lookup: Dict[str, datetime]
    pair: Tuple[datetime, datetime]
    maybe: Optional[datetime] = None


@dataclass_json(datetime_format='iso8601')
@dataclass
class CustomCodecWins:
    at: datetime = field(metadata=config(
        encoder=lambda d: d.strftime('%Y/%m/%d %H:%M'),
        decoder=lambda s: datetime.strptime(s, '%Y/%m/%d %H:%M').replace(
            tzinfo=UTC),
        datetime_format='iso8601'))


@dataclass_json(datetime_format='iso8601')
@dataclass
class CustomMmFieldWins:
    at: datetime = field(metadata=config(
        mm_field=fields.DateTime(format='iso'),
        datetime_format='iso8601'))


@dataclass_json
@dataclass
class LegacyDefault:
    at: datetime


@dataclass_json(datetime_format=Iso8601DateTime(naive=NaivePolicy.ASSUME_UTC))
@dataclass
class NaiveAssumeUtc:
    at: datetime


class TestIso8601Codec:
    def test_encode_z(self):
        assert ClassLevelIso(DT).to_json() == f'{{"at": "{ISO_Z}"}}'

    def test_decode_z(self):
        assert ClassLevelIso.from_json(f'{{"at": "{ISO_Z}"}}') \
            == ClassLevelIso(DT)

    def test_roundtrip_preserves_instant(self):
        obj = ClassLevelIso(DT)
        assert ClassLevelIso.from_json(obj.to_json()) == obj

    def test_encode_numeric_offset(self):
        dt = datetime(2018, 11, 17, 16, 55, 28, tzinfo=EST5)
        assert ClassLevelIso(dt).to_json() \
            == '{"at": "2018-11-17T16:55:28.000000-05:00"}'

    def test_decode_numeric_offset(self):
        obj = ClassLevelIso.from_json(
            '{"at": "2018-11-17T16:55:28+05:30"}')
        assert obj.at == datetime(2018, 11, 17, 16, 55, 28, tzinfo=IST530)
        # the instant is preserved exactly
        assert obj.at == datetime(2018, 11, 17, 11, 25, 28, tzinfo=UTC)

    def test_decode_lowercase_z_and_space_separator(self):
        obj = ClassLevelIso.from_json(
            '{"at": "2018-11-17 16:55:28z"}')
        assert obj.at == datetime(2018, 11, 17, 16, 55, 28, tzinfo=UTC)

    def test_field_level_config(self):
        obj = FieldLevelIso(DT)
        assert obj.to_json() == f'{{"at": "{ISO_Z}"}}'
        assert FieldLevelIso.from_json(f'{{"at": "{ISO_Z}"}}') == obj

    def test_field_overrides_class(self):
        obj = ClassAndFieldSpec(whole=DT, millis=DT)
        assert obj.to_json() == (
            '{"whole": "2018-11-17T16:55:28Z", '
            '"millis": "2018-11-17T16:55:28.456Z"}')

    def test_fraction_digits_none_strips_trailing_zeros(self):
        spec = Iso8601DateTime(fraction_digits=None)

        @dataclass_json(datetime_format=spec)
        @dataclass
        class Auto:
            at: datetime

        assert Auto(datetime(2018, 11, 17, 16, 55, 28, 500000,
                             tzinfo=UTC)).to_json() \
            == '{"at": "2018-11-17T16:55:28.5Z"}'
        assert Auto(datetime(2018, 11, 17, 16, 55, 28,
                             tzinfo=UTC)).to_json() \
            == '{"at": "2018-11-17T16:55:28Z"}'

    def test_use_z_false(self):
        spec = Iso8601DateTime(use_z=False)

        @dataclass_json(datetime_format=spec)
        @dataclass
        class PlusZero:
            at: datetime

        assert PlusZero(DT).to_json() \
            == '{"at": "2018-11-17T16:55:28.456753+00:00"}'

    def test_invalid_fraction_digits(self):
        with pytest.raises(ValueError):
            Iso8601DateTime(fraction_digits=7)

    def test_invalid_datetime_format_config(self):
        with pytest.raises(ValueError):
            config(datetime_format='unix')

    def test_naive_encode_rejected(self):
        with pytest.raises(Iso8601Error):
            ClassLevelIso(datetime(2018, 11, 17, 16, 55, 28)).to_json()

    def test_offsetless_decode_rejected(self):
        with pytest.raises(Iso8601Error):
            ClassLevelIso.from_json('{"at": "2018-11-17T16:55:28"}')

    def test_naive_assume_utc(self):
        obj = NaiveAssumeUtc(datetime(2018, 11, 17, 16, 55, 28))
        assert obj.to_json() == '{"at": "2018-11-17T16:55:28.000000Z"}'
        back = NaiveAssumeUtc.from_json('{"at": "2018-11-17T16:55:28"}')
        assert back.at == datetime(2018, 11, 17, 16, 55, 28, tzinfo=UTC)

    def test_leap_second_rejected(self):
        with pytest.raises(Iso8601Error):
            ClassLevelIso.from_json('{"at": "2016-12-31T23:59:60Z"}')

    @pytest.mark.parametrize('bad', [
        '2023-13-01T00:00:00Z',   # month out of range
        '2023-02-30T00:00:00Z',   # day out of range
        '0000-01-01T00:00:00Z',   # year out of range
        '2018-11-17T25:00:00Z',   # hour out of range
        '2018-11-17T16:55:28.4567531Z',  # sub-microsecond precision
        '2018-11-17T16:55:28+24:00',     # offset out of range
        '2018-11-17T16:55:28+05:60',     # offset minutes out of range
        'not-a-datetime',
        '2018-11-17',             # date only
    ])
    def test_unrepresentable_rejected(self, bad):
        with pytest.raises(Iso8601Error):
            ClassLevelIso.from_json(f'{{"at": "{bad}"}}')

    def test_schema_dump_load(self):
        obj = ClassLevelIso(DT)
        assert ClassLevelIso.schema().dumps(obj) == f'{{"at": "{ISO_Z}"}}'
        assert ClassLevelIso.schema().loads(f'{{"at": "{ISO_Z}"}}') == obj

    def test_schema_load_leap_second_is_field_error(self):
        with pytest.raises(ValidationError):
            ClassLevelIso.schema().loads('{"at": "2016-12-31T23:59:60Z"}')

    def test_schema_load_out_of_range_is_field_error(self):
        with pytest.raises(ValidationError):
            ClassLevelIso.schema().loads('{"at": "2023-13-01T00:00:00Z"}')

    def test_schema_dump_naive_is_field_error(self):
        with pytest.raises(ValidationError):
            ClassLevelIso.schema().dumps(
                ClassLevelIso(datetime(2018, 11, 17, 16, 55, 28)))

    def test_nested_containers(self):
        dt2 = datetime(2020, 1, 2, 3, 4, 5, tzinfo=EST5)
        obj = NestedIso(stamps=[DT, dt2],
                        lookup={'a': DT},
                        pair=(DT, dt2),
                        maybe=DT)
        expected = (
            '{"stamps": ["2018-11-17T16:55:28.456753Z", '
            '"2020-01-02T03:04:05.000000-05:00"], '
            '"lookup": {"a": "2018-11-17T16:55:28.456753Z"}, '
            '"pair": ["2018-11-17T16:55:28.456753Z", '
            '"2020-01-02T03:04:05.000000-05:00"], '
            '"maybe": "2018-11-17T16:55:28.456753Z"}')
        assert obj.to_json() == expected
        assert NestedIso.from_json(expected) == obj

    def test_nested_containers_schema(self):
        dt2 = datetime(2020, 1, 2, 3, 4, 5, tzinfo=EST5)
        obj = NestedIso(stamps=[DT, dt2], lookup={'a': DT},
                        pair=(DT, dt2), maybe=None)
        dumped = NestedIso.schema().dumps(obj)
        assert dumped == (
            '{"stamps": ["2018-11-17T16:55:28.456753Z", '
            '"2020-01-02T03:04:05.000000-05:00"], '
            '"lookup": {"a": "2018-11-17T16:55:28.456753Z"}, '
            '"pair": ["2018-11-17T16:55:28.456753Z", '
            '"2020-01-02T03:04:05.000000-05:00"], '
            '"maybe": null}')
        loaded = NestedIso.schema().loads(dumped)
        assert loaded == obj

    def test_custom_encoder_decoder_take_precedence(self):
        obj = CustomCodecWins(DT)
        assert obj.to_json() == '{"at": "2018/11/17 16:55"}'
        assert CustomCodecWins.from_json('{"at": "2018/11/17 16:55"}') \
            == CustomCodecWins(
                datetime(2018, 11, 17, 16, 55, tzinfo=UTC))

    def test_custom_mm_field_takes_precedence_in_schema(self):
        obj = CustomMmFieldWins(DT)
        dumped = CustomMmFieldWins.schema().dumps(obj)
        # marshmallow DateTime(format='iso') renders +00:00, not Z
        assert dumped == '{"at": "2018-11-17T16:55:28.456753+00:00"}'
        # to_dict/from_dict still honor the ISO 8601 spec
        assert obj.to_json() == f'{{"at": "{ISO_Z}"}}'

    def test_legacy_default_unchanged(self):
        obj = LegacyDefault(DT)
        assert obj.to_json() == f'{{"at": {DT.timestamp()}}}'
        assert LegacyDefault.from_json(obj.to_json()).at == DT

    def test_mixin_api(self):
        @dataclass
        class MixinStyle(DataClassJsonMixin):
            at: datetime

        MixinStyle.dataclass_json_config = config(
            datetime_format='iso8601')['dataclasses_json']
        obj = MixinStyle(DT)
        assert obj.to_json() == f'{{"at": "{ISO_Z}"}}'
        assert MixinStyle.from_json(f'{{"at": "{ISO_Z}"}}') == obj


class TestDstRepeatedMoment:
    """The 2023-11-05 01:30 local time happens twice in America/New_York.
    Both occurrences must round-trip as distinct instants, identically on
    any host timezone."""

    EDT_OCCURRENCE = '2023-11-05T01:30:00.000000-04:00'
    EST_OCCURRENCE = '2023-11-05T01:30:00.000000-05:00'

    def test_distinct_instants_one_hour_apart(self):
        first = ClassLevelIso.from_json(
            f'{{"at": "{self.EDT_OCCURRENCE}"}}').at
        second = ClassLevelIso.from_json(
            f'{{"at": "{self.EST_OCCURRENCE}"}}').at
        assert second - first == timedelta(hours=1)
        assert first == datetime(2023, 11, 5, 5, 30, tzinfo=UTC)
        assert second == datetime(2023, 11, 5, 6, 30, tzinfo=UTC)

    def test_zoneinfo_fold_encodes_distinct_offsets(self):
        ny = ZoneInfo('America/New_York')
        first = datetime(2023, 11, 5, 1, 30, tzinfo=ny, fold=0)
        second = datetime(2023, 11, 5, 1, 30, tzinfo=ny, fold=1)
        assert ClassLevelIso(first).to_json() \
            == f'{{"at": "{self.EDT_OCCURRENCE}"}}'
        assert ClassLevelIso(second).to_json() \
            == f'{{"at": "{self.EST_OCCURRENCE}"}}'

    def test_utc_encode_is_host_tz_independent(self):
        instant = datetime(2023, 11, 5, 6, 30, tzinfo=UTC)
        assert ClassLevelIso(instant).to_json() \
            == '{"at": "2023-11-05T06:30:00.000000Z"}'

    def test_decode_result_offset_is_literal_not_local(self):
        obj = ClassLevelIso.from_json(
            f'{{"at": "{self.EST_OCCURRENCE}"}}')
        assert obj.at.utcoffset() == timedelta(hours=-5)
