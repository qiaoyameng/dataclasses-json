"""
Tests for the integer compatibility mode.

Integers larger than JavaScript's ``Number.MAX_SAFE_INTEGER`` (2**53-1)
would lose precision after a ``JSON.parse`` round trip in the browser, so
the mode emits them as decimal strings and restores them only at positions
declared as integers.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, NewType, Optional, Tuple

import pytest
from marshmallow.exceptions import ValidationError

from dataclasses_json import (MAX_COMPAT_INTEGER, MAX_SAFE_INTEGER,
                              config, dataclass_json, global_config)

M = MAX_SAFE_INTEGER
BIG = M + 1          # 2**53: first unsafe integer
BIG_NEG = -BIG
ID64 = 2 ** 63 - 1   # largest signed 64 bit integer
UserID = NewType("UserID", int)


@pytest.fixture(autouse=True)
def _int_compat_mode():
    with global_config.int_compat_mode():
        yield


@dataclass_json
@dataclass
class IntHolder:
    x: int


@dataclass_json
@dataclass
class NestedHolder:
    value: int
    maybe: Optional[int]
    values: List[Optional[int]]
    table: Dict[str, List[int]]
    keys: Dict[int, str]
    pair: Tuple[int, int, Optional[int]]
    flags: List[bool]
    raw: Any
    label: int = field(metadata=config(field_name="labelId"))


@dataclass_json
@dataclass
class Child:
    uid: int
    values: List[int]


@dataclass_json
@dataclass
class Parent:
    child: Child
    children: List[Child]


@dataclass_json
@dataclass
class NewTypeHolder:
    uid: UserID


def _sample():
    return NestedHolder(
        value=BIG,
        maybe=BIG_NEG,
        values=[BIG, None, 7, M],
        table={"a": [BIG], "b": [M]},
        keys={BIG: "big", 3: "small"},
        pair=(BIG, BIG_NEG, None),
        flags=[True, False],
        raw={"id": BIG, "phone": "9007199254740992"},
        label=M,
    )


ENCODED = {
    "value": str(BIG),
    "maybe": str(BIG_NEG),
    "values": [str(BIG), None, 7, M],
    "table": {"a": [str(BIG)], "b": [M]},
    # dict keys keep their Python type in to_dict(); only JSON text forces
    # them to strings, and _decode_dict_keys converts them back to int
    "keys": {BIG: "big", 3: "small"},
    "pair": [str(BIG), str(BIG_NEG), None],
    "flags": [True, False],
    "raw": {"id": str(BIG), "phone": "9007199254740992"},
    "labelId": M,
}


class TestEncoding:
    def test_safe_boundary_inclusive(self):
        assert IntHolder(M).to_json() == '{"x": 9007199254740991}'
        assert IntHolder(-M).to_json() == '{"x": -9007199254740991}'

    def test_outside_boundary_becomes_string(self):
        assert IntHolder(BIG).to_json() == '{"x": "9007199254740992"}'
        assert IntHolder(BIG_NEG).to_json() == \
               '{"x": "-9007199254740992"}'

    def test_bool_is_never_stringified(self):
        @dataclass_json
        @dataclass
        class BoolHolder:
            flag: bool

        assert BoolHolder(True).to_json() == '{"flag": true}'
        assert BoolHolder(False).to_json() == '{"flag": false}'

    def test_nested_containers_optional_and_alias(self):
        obj = _sample()
        assert obj.to_dict() == ENCODED
        dumped = obj.schema().dump(obj)
        # marshmallow serializes fixed-length tuples as tuples and mapping
        # keys as strings; every other position matches the direct API
        assert list(dumped.pop("pair")) == ENCODED["pair"]
        assert {int(k): v for k, v in dumped.pop("keys").items()} == \
               ENCODED["keys"]
        assert dumped == {k: v for k, v in ENCODED.items()
                          if k not in ("pair", "keys")}

    def test_nested_dataclasses(self):
        obj = Parent(Child(BIG, [BIG, None]), [Child(ID64, [])])
        encoded = {
            "child": {"uid": str(BIG), "values": [str(BIG), None]},
            "children": [{"uid": str(ID64), "values": []}],
        }
        assert obj.to_dict() == encoded
        assert obj.schema().dump(obj) == encoded

    def test_plain_string_fields_stay_strings(self):
        @dataclass_json
        @dataclass
        class StrHolder:
            code: str

        obj = StrHolder("9007199254740992")
        assert obj.to_json() == '{"code": "9007199254740992"}'
        assert obj.schema().dumps(obj) == '{"code": "9007199254740992"}'

    def test_any_positions_are_not_restored(self):
        restored = NestedHolder.from_dict(ENCODED)
        assert restored.raw["id"] == str(BIG)
        assert isinstance(restored.raw["id"], str)
        assert restored.raw["phone"] == "9007199254740992"


class TestRoundTrip:
    def test_boundary_values_round_trip(self):
        for value in (M, -M, BIG, BIG_NEG, ID64, -ID64, 0, 1, -1):
            js = IntHolder(value).to_json()
            direct = IntHolder.from_json(js)
            via_schema = IntHolder.schema().loads(js)
            assert direct == IntHolder(value)
            assert via_schema == IntHolder(value)
            assert isinstance(direct.x, int)
            assert not isinstance(direct.x, bool)

    def test_nested_round_trip(self):
        obj = _sample()
        js = obj.to_json()
        direct = NestedHolder.from_json(js)
        via_schema = NestedHolder.schema().loads(js)
        for restored in (direct, via_schema):
            assert restored.value == obj.value
            assert restored.maybe == obj.maybe
            assert restored.values == obj.values
            assert restored.table == obj.table
            assert restored.keys == obj.keys
            assert restored.pair == obj.pair
            assert restored.flags == obj.flags
            assert restored.label == obj.label
            # Any positions never restore strings by content
            assert restored.raw["id"] == str(BIG)
            assert isinstance(restored.raw["id"], str)
        assert direct == via_schema

    def test_nested_dataclasses_round_trip(self):
        obj = Parent(Child(BIG, [BIG]), [Child(BIG_NEG, [ID64])])
        js = obj.to_json()
        assert Parent.from_json(js) == obj
        assert Parent.schema().loads(js) == obj

    def test_nulls_in_collections_are_preserved(self):
        @dataclass_json
        @dataclass
        class WithNulls:
            xs: List[Optional[int]]

        obj = WithNulls([BIG, None, BIG_NEG, None])
        js = '{"xs": ["9007199254740992", null, ' \
             '"-9007199254740992", null]}'
        assert obj.to_json() == js
        assert WithNulls.from_json(js) == obj
        assert WithNulls.schema().loads(js) == obj

    def test_new_type_round_trip(self):
        obj = NewTypeHolder(UserID(BIG))
        js = '{"uid": "9007199254740992"}'
        assert obj.to_json() == js
        assert NewTypeHolder.from_json(js) == obj
        assert NewTypeHolder.schema().loads(js) == obj
        assert isinstance(NewTypeHolder.from_json(js).uid, int)


class TestDirectAndSchemaParity:
    def test_dump_string_and_object_are_identical(self):
        obj = _sample()
        # JSON text is the actual JavaScript-facing contract
        assert obj.to_json() == obj.schema().dumps(obj)

    def test_loaded_values_have_identical_types(self):
        js = _sample().to_json()
        direct = NestedHolder.from_json(js)
        via_schema = NestedHolder.schema().loads(js)
        assert isinstance(direct.value, int)
        assert isinstance(direct.maybe, int)
        assert [type(v) for v in direct.values] == \
               [int, type(None), int, int]
        assert isinstance(direct.table["a"][0], int)
        assert isinstance(direct.pair[0], int)
        assert direct.pair[2] is None
        assert direct.flags == [True, False]
        # all declared-integer positions carry identical values and types
        assert direct.value == via_schema.value
        assert direct.maybe == via_schema.maybe
        assert direct.values == via_schema.values
        assert direct.table == via_schema.table
        assert direct.keys == via_schema.keys == _sample().keys
        assert direct.pair == via_schema.pair == _sample().pair
        assert direct.flags == via_schema.flags
        assert direct.label == via_schema.label == _sample().label
        # Any content is never restored on either path
        assert isinstance(direct.raw["id"], str)
        assert isinstance(via_schema.raw["id"], str)


class TestInvalidInput:
    @pytest.mark.parametrize("bad", [
        "1.5",          # fractional number
        '"1.5"',        # decimal string
        '"1e3"',        # exponent notation
        '" 1 "',        # surrounding whitespace
        'true',         # bool masquerading as int
        '"01"',         # leading zeroes
    ])
    def test_direct_api_rejects(self, bad):
        with pytest.raises((ValueError, TypeError)):
            IntHolder.from_json('{"x": ' + bad + '}')

    @pytest.mark.parametrize("bad", [
        "1.5", '"1.5"', '"1e3"', '" 1 "', 'true', '"01"',
    ])
    def test_schema_api_rejects(self, bad):
        with pytest.raises(ValidationError):
            IntHolder.schema().loads('{"x": ' + bad + '}')

    @pytest.mark.parametrize("bad", [str(ID64 + 1), str(-ID64 - 1)])
    def test_strings_outside_configured_range_rejected(self, bad):
        with pytest.raises(ValueError):
            IntHolder.from_json('{"x": "' + bad + '"}')
        with pytest.raises(ValidationError):
            IntHolder.schema().loads('{"x": "' + bad + '"}')

    def test_int_outside_configured_range_rejected(self):
        payload = '{"x": ' + str(ID64 + 1) + '}'
        with pytest.raises(ValueError):
            IntHolder.from_json(payload)
        with pytest.raises(ValidationError):
            IntHolder.schema().loads(payload)

    def test_bool_inside_int_container_rejected(self):
        @dataclass_json
        @dataclass
        class ListHolder:
            xs: List[int]

        with pytest.raises((ValueError, TypeError)):
            ListHolder.from_json('{"xs": [true]}')
        with pytest.raises(ValidationError):
            ListHolder.schema().loads('{"xs": [true]}')

    def test_exponent_inside_nested_container_rejected(self):
        @dataclass_json
        @dataclass
        class TableHolder:
            table: Dict[str, List[int]]

        with pytest.raises((ValueError, TypeError)):
            TableHolder.from_json('{"table": {"a": ["1e3"]}}')
        with pytest.raises(ValidationError):
            TableHolder.schema().loads(
                '{"table": {"a": ["1e3"]}}')


class TestCustomEncoderDecoderPriority:
    def test_field_encoder_decoder_take_precedence(self):
        @dataclass_json
        @dataclass
        class CustomHolder:
            x: int = field(metadata=config(
                encoder=lambda v: f"<{v}>",
                decoder=lambda v: int(v.strip("<>"))))

        obj = CustomHolder(BIG)
        assert obj.to_json() == '{"x": "<9007199254740992>"}'
        assert CustomHolder.from_json(
            '{"x": "<9007199254740992>"}') == obj
        assert CustomHolder.schema().loads(
            '{"x": "<9007199254740992>"}') == obj

    def test_global_encoder_takes_precedence(self):
        global_config.encoders[int] = lambda v: f"g{v}"
        try:
            assert IntHolder(BIG).to_json() == \
                   '{"x": "g9007199254740992"}'
        finally:
            del global_config.encoders[int]


class TestConfiguration:
    def test_disabled_by_default(self):
        with global_config.int_compat_mode(enabled=False):
            assert not global_config.int_compat_enabled
            assert IntHolder(BIG).to_json() == '{"x": 9007199254740992}'
            assert IntHolder(BIG).schema().dumps(
                IntHolder(BIG)) == '{"x": 9007199254740992}'

    def test_custom_safe_range_and_max_string(self):
        with global_config.int_compat_mode(safe_range=100,
                                           max_string_int=1000):
            assert IntHolder(100).to_json() == '{"x": 100}'
            assert IntHolder(101).to_json() == '{"x": "101"}'
            assert IntHolder.from_json('{"x": "999"}').x == 999
            with pytest.raises(ValueError):
                IntHolder.from_json('{"x": "1001"}')
            with pytest.raises(ValidationError):
                IntHolder.schema().loads('{"x": 1001}')

    def test_context_restores_previous_state(self):
        previous = (global_config.int_compat_enabled,
                    global_config.int_compat_safe_range,
                    global_config.int_compat_max_string_int)
        assert previous == (True, M, MAX_COMPAT_INTEGER)
        with global_config.int_compat_mode(safe_range=10):
            assert global_config.int_compat_safe_range == 10
            with global_config.int_compat_mode(enabled=False):
                assert not global_config.int_compat_enabled
            assert global_config.int_compat_enabled
            assert global_config.int_compat_safe_range == 10
        assert (global_config.int_compat_enabled,
                global_config.int_compat_safe_range,
                global_config.int_compat_max_string_int) == previous
