import marshmallow
import pytest

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

    def test_default_factory_not_evaluated_at_schema_build(self):
        from dataclasses import dataclass, field
        from dataclasses_json import dataclass_json

        calls = []

        def factory():
            calls.append(len(calls) + 1)
            return calls[-1]

        @dataclass_json
        @dataclass
        class WithFactory:
            value: int = field(default_factory=factory)

        schema_ = WithFactory.schema(infer_missing=True)
        assert calls == []
        assert schema_.load({}).value == 1
        assert schema_.load({}).value == 2
        assert calls == [1, 2]

    def test_default_factory_many_and_explicit_values(self):
        from dataclasses import dataclass, field
        from dataclasses_json import dataclass_json

        calls = []

        def factory():
            calls.append(len(calls) + 1)
            return calls[-1]

        @dataclass_json
        @dataclass
        class WithFactory:
            value: int = field(default_factory=factory)

        schema_ = WithFactory.schema(infer_missing=True, many=True)
        records = schema_.load([{}, {"value": 41}, {}])
        assert [record.value for record in records] == [1, 41, 2]
        assert calls == [1, 2]

    def test_default_factory_mutable_container_not_shared(self):
        from dataclasses import dataclass, field
        from typing import List
        from dataclasses_json import dataclass_json

        @dataclass_json
        @dataclass
        class WithListFactory:
            values: List[int] = field(default_factory=list)

        schema_ = WithListFactory.schema(infer_missing=True)
        first = schema_.load({})
        second = schema_.load({})
        first.values.append(1)
        assert second.values == []

        records = WithListFactory.schema(infer_missing=True, many=True).load([{}, {}])
        records[0].values.append(1)
        assert records[1].values == []

    def test_default_factory_nested_dataclass(self):
        from dataclasses import dataclass, field
        from typing import List
        from dataclasses_json import dataclass_json

        calls = []

        def factory():
            calls.append(len(calls) + 1)
            return calls[-1]

        @dataclass_json
        @dataclass
        class Inner:
            value: int = field(default_factory=factory)

        @dataclass_json
        @dataclass
        class Outer:
            inner: Inner = field(default_factory=Inner)

        schema_ = Outer.schema(infer_missing=True)
        first = schema_.load({})
        second = schema_.load({})
        assert (first.inner.value, second.inner.value) == (1, 2)
        assert first.inner is not second.inner

        records = Outer.schema(infer_missing=True, many=True).load([{}, {}])
        assert [record.inner.value for record in records] == [3, 4]

        @dataclass_json
        @dataclass
        class Holder:
            inner_items: List[Inner] = field(default_factory=list)

        holder = Holder.schema(infer_missing=True).load(
            {"inner_items": [{}, {"value": 99}, {}]})
        assert [item.value for item in holder.inner_items] == [5, 99, 6]
        assert calls == [1, 2, 3, 4, 5, 6]

    def test_default_factory_exception_raised_on_load(self):
        from dataclasses import dataclass, field
        from dataclasses_json import dataclass_json

        def factory():
            raise RuntimeError("boom")

        @dataclass_json
        @dataclass
        class WithFailingFactory:
            value: int = field(default_factory=factory)

        schema_ = WithFailingFactory.schema(infer_missing=True)
        with pytest.raises(Exception):
            schema_.load({})

    def test_constant_default_still_compatible(self):
        from dataclasses import dataclass, field
        from dataclasses_json import dataclass_json

        @dataclass_json
        @dataclass
        class WithConstantDefault:
            value: int = 7

        schema_ = WithConstantDefault.schema(infer_missing=True)
        assert schema_.load({}).value == 7
        assert schema_.load({"value": 8}).value == 8
        records = schema_.load([{}, {"value": 3}], many=True)
        assert [record.value for record in records] == [7, 3]
