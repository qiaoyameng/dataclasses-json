from dataclasses import dataclass, field
from typing import List

import marshmallow
import pytest

from dataclasses_json import dataclass_json

from .entities import (DataClassDefaultListStr, DataClassDefaultOptionalList, DataClassList, DataClassOptional,
                       DataClassWithNestedOptional, DataClassWithNestedOptionalAny, DataClassWithNestedAny,
                       DataClassDifferentTypeDecode)
from .test_letter_case import CamelCasePerson, KebabCasePerson, SnakeCasePerson, FieldNamePerson

test_do_list = """[{}, {"children": [{"name": "a"}, {"name": "b"}]}]"""
test_list = '[{"children": [{"name": "a"}, {"name": "b"}]}]'
nested_optional_data = '{"a": {"test": null}}'


class TestSchema:
    def test_default_list_str(self):
        DataClassDefaultListStr.schema().dumps(DataClassDefaultListStr())
        assert True

    def test_default_optional_list(self):
        DataClassDefaultOptionalList.schema().loads(test_do_list, many=True)
        assert True

    def test_list(self):
        DataClassList.schema().loads(test_list, many=True)
        assert True

    def test_optional(self):
        DataClassOptional.schema().loads('{"a": 4, "b": null}')
        assert True

    def test_not_providing_required_field(self):
        with pytest.raises(marshmallow.ValidationError):
            DataClassOptional.schema().loads('{"b": null}')

    def test_letter_case(self):
        for cls in (CamelCasePerson, KebabCasePerson, SnakeCasePerson, FieldNamePerson):
            p = cls('Alice')
            assert p.to_dict() == cls.schema().dump(p)

    def test_nested_optional(self):
        DataClassWithNestedOptional.schema().loads(nested_optional_data)
        assert True

    def test_nested_optional_any(self):
        DataClassWithNestedOptionalAny.schema().loads(nested_optional_data)
        assert True

    def test_nested_any_accepts_optional(self):
        DataClassWithNestedAny.schema().loads(nested_optional_data)
        assert True

    def test_accounts_for_decode(self):
        assert DataClassDifferentTypeDecode.schema().load({'lst': '1,2,3'}) == \
               DataClassDifferentTypeDecode(lst=['1', '2', '3'])


def _make_counter_factory():
    calls = []

    def factory():
        calls.append(1)
        return len(calls)

    return factory, calls


def _record_with_factory(factory):
    @dataclass_json
    @dataclass
    class Record:
        n: int = field(default_factory=factory)

    return Record


class TestDefaultFactoryEvaluation:
    def test_factory_not_called_when_building_schema(self):
        factory, calls = _make_counter_factory()
        record = _record_with_factory(factory)

        record.schema(infer_missing=True)
        record.schema(infer_missing=True)
        assert calls == []

    def test_factory_called_once_per_load_with_distinct_values(self):
        factory, calls = _make_counter_factory()
        record = _record_with_factory(factory)
        schema = record.schema(infer_missing=True)

        assert schema.load({}) == record(n=1)
        assert schema.load({}) == record(n=2)
        assert len(calls) == 2

    def test_explicit_value_does_not_consume_factory(self):
        factory, calls = _make_counter_factory()
        record = _record_with_factory(factory)
        schema = record.schema(infer_missing=True)

        assert schema.load({"n": 100}) == record(n=100)
        assert calls == []
        assert schema.load([{"n": 100}, {}, {"n": 200}], many=True) == [
            record(n=100), record(n=1), record(n=200)]
        assert len(calls) == 1

    def test_many_uses_fresh_factory_value_per_record(self):
        factory, calls = _make_counter_factory()
        record = _record_with_factory(factory)

        records = record.schema(infer_missing=True).load(
            [{}, {"n": 41}, {}], many=True)
        assert records == [record(n=1), record(n=41), record(n=2)]
        assert len(calls) == 2

    def test_mutable_factory_not_shared_between_records(self):
        @dataclass_json
        @dataclass
        class MutableDefaults:
            xs: List[int] = field(default_factory=list)

        records = MutableDefaults.schema().load([{}, {}], many=True)
        records[0].xs.append(1)
        assert records[0].xs == [1]
        assert records[1].xs == []
        assert records[0].xs is not records[1].xs

    def test_nested_factory_called_per_nested_record(self):
        factory, calls = _make_counter_factory()

        @dataclass_json
        @dataclass
        class Child:
            n: int = field(default_factory=factory)

        @dataclass_json
        @dataclass
        class Parent:
            child: Child = field(default_factory=Child)
            children: List[Child] = field(default_factory=list)

        schema = Parent.schema(infer_missing=True)
        assert calls == []

        parents = schema.load(
            [{"children": [{}]}, {"children": [{}]}], many=True)
        assert parents[0].child.n != parents[1].child.n
        assert parents[0].children[0].n != parents[1].children[0].n
        assert len(calls) == 4

        one = schema.load({"child": {"n": 99}, "children": [{"n": 98}]})
        assert one.child == Child(n=99)
        assert one.children == [Child(n=98)]
        assert len(calls) == 4

    def test_partial_load_does_not_use_stale_schema_default(self):
        factory, calls = _make_counter_factory()
        schema = _record_with_factory(factory).schema(infer_missing=True)

        first = schema.load({}, partial=True)
        second = schema.load({}, partial=True)
        assert first.n == 1 and second.n == 2
        assert len(calls) == 2

    def test_factory_exception_raised_at_load_time(self):
        def broken_factory():
            raise ValueError("factory boom")

        schema = _record_with_factory(broken_factory).schema(infer_missing=True)
        with pytest.raises(ValueError, match="factory boom"):
            schema.load({})

    def test_constant_default_still_works(self):
        @dataclass_json
        @dataclass
        class Record:
            name: str = "student"

        assert Record.schema(infer_missing=True).load({}) == Record(name="student")
        assert Record.schema().load({"name": "x"}) == Record(name="x")

    def test_infer_missing_false_applies_factory_lazily(self):
        factory, calls = _make_counter_factory()
        record = _record_with_factory(factory)
        schema = record.schema()

        assert calls == []
        assert schema.load({}) == record(n=1)
        assert schema.load({"n": 77}) == record(n=77)
        assert len(calls) == 1
