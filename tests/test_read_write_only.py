import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest
from marshmallow import ValidationError

from dataclasses_json import CatchAll, Undefined, config, dataclass_json


def make_account_class():
    @dataclass_json(undefined=Undefined.INCLUDE)
    @dataclass
    class Account:
        name: str
        password: str = field(
            metadata=config(field_name="passcode", write_only=True)
        )
        audit_id: str = field(
            default_factory=lambda: "server-audit",
            metadata=config(field_name="auditId", read_only=True)
        )
        catch_all: CatchAll = None

    return Account


def test_write_only_password_is_loaded_but_not_exported():
    Account = make_account_class()
    raw = {"name": "alice", "passcode": "secret"}

    account = Account.from_dict(raw)

    assert account.password == "secret"
    assert account.audit_id == "server-audit"
    exported = account.to_dict()
    assert exported == {"name": "alice", "auditId": "server-audit"}
    assert "secret" not in account.to_json()
    assert json.loads(account.to_json()) == exported


def test_schema_load_uses_default_for_missing_read_only_and_omits_write_only():
    Account = make_account_class()
    raw = {"name": "alice", "passcode": "secret"}

    account = Account.schema().load(raw)

    assert account.password == "secret"
    assert account.audit_id == "server-audit"
    dumped = Account.schema().dump(account)
    assert dumped == {"name": "alice", "auditId": "server-audit"}
    assert "secret" not in Account.schema().dumps(account)


@pytest.mark.parametrize("loader", ["dict", "json", "schema"])
def test_read_only_alias_and_canonical_name_are_rejected(loader):
    Account = make_account_class()

    for key in ("auditId", "audit_id"):
        raw = {"name": "alice", "passcode": "secret", key: "forged"}
        with pytest.raises(ValidationError) as error:
            if loader == "dict":
                Account.from_dict(raw)
            elif loader == "json":
                Account.from_json(json.dumps(raw))
            else:
                Account.schema().load(raw)

        assert error.value.messages == {
            key: ["Read-only field cannot be provided when loading."]
        }


def test_read_only_value_cannot_reach_catch_all_through_alias():
    Account = make_account_class()

    with pytest.raises(ValidationError):
        Account.from_dict({
            "name": "alice",
            "passcode": "secret",
            "auditId": "forged",
            "extra": "kept",
        })


def test_write_only_value_is_removed_from_catch_all_on_export():
    Account = make_account_class()
    account = Account(
        name="alice",
        password="secret",
        catch_all={"passcode": "forged-password", "extra": True},
    )

    assert account.to_dict() == {
        "name": "alice",
        "auditId": "server-audit",
        "extra": True,
    }
    assert Account.schema().dump(account) == {
        "name": "alice",
        "auditId": "server-audit",
        "extra": True,
    }


def test_nested_collections_enforce_field_directions():
    @dataclass_json(undefined=Undefined.INCLUDE)
    @dataclass
    class NestedAccount:
        name: str
        password: str = field(
            metadata=config(field_name="passcode", write_only=True)
        )
        audit_id: str = field(
            default_factory=lambda: "nested-audit",
            metadata=config(field_name="auditId", read_only=True)
        )
        catch_all: CatchAll = None

    @dataclass_json
    @dataclass
    class Organization:
        accounts: List[NestedAccount]
        by_name: Dict[str, NestedAccount]

    raw = {
        "accounts": [{"name": "a", "passcode": "pw-a"}],
        "by_name": {"b": {"name": "b", "passcode": "pw-b"}},
    }

    organization = Organization.from_dict(raw)

    assert Organization.schema().load(raw) == organization
    assert Organization.schema().dump(organization) == {
        "accounts": [{"name": "a", "auditId": "nested-audit"}],
        "by_name": {"b": {"name": "b", "auditId": "nested-audit"}},
    }

    with pytest.raises(ValidationError) as error:
        Organization.from_dict({
            "accounts": [{"name": "a", "auditId": "forged"}]
        })
    assert error.value.messages == {
        "auditId": ["Read-only field cannot be provided when loading."]
    }


def test_inherited_field_directions_remain_in_effect():
    Account = make_account_class()

    @dataclass_json
    @dataclass
    class AdminAccount(Account):
        permissions: List[str] = field(default_factory=list)

    raw = {
        "name": "admin",
        "passcode": "secret",
        "permissions": ["users"],
    }

    account = AdminAccount.from_dict(raw)

    assert account.password == "secret"
    assert account.audit_id == "server-audit"
    assert account.to_dict() == {
        "name": "admin",
        "auditId": "server-audit",
        "permissions": ["users"],
    }

    with pytest.raises(ValidationError):
        AdminAccount.from_dict({"name": "admin", "auditId": "forged"})


def test_read_only_and_write_only_cannot_be_enabled_together():
    with pytest.raises(ValueError, match="both read-only and write-only"):
        config(read_only=True, write_only=True)

    invalid_metadata = {
        "dataclasses_json": {"read_only": True, "write_only": True}
    }

    @dataclass_json
    @dataclass
    class InvalidAccount:
        name: str = field(metadata=invalid_metadata)

    with pytest.raises(ValueError, match="both read-only and write-only"):
        InvalidAccount.from_dict({"name": "alice"})


def test_optional_nested_read_only_input_is_rejected_when_present():
    @dataclass_json
    @dataclass
    class Audit:
        value: str = field(
            default_factory=lambda: "server",
            metadata=config(field_name="valueId", read_only=True)
        )

    @dataclass_json
    @dataclass
    class Container:
        audit: Optional[Audit] = None

    assert Container.from_dict({}).audit is None

    with pytest.raises(ValidationError):
        Container.from_dict({"audit": {"valueId": "forged"}})


def test_directions_apply_to_the_catch_all_field_itself():
    @dataclass_json(undefined=Undefined.INCLUDE)
    @dataclass
    class ReadOnlyCatchAll:
        name: str
        extras: CatchAll = field(
            default=None,
            metadata=config(read_only=True),
        )

    with pytest.raises(ValidationError) as error:
        ReadOnlyCatchAll.from_dict({"name": "alice", "extra": True})
    assert error.value.messages == {
        "extra": ["Read-only field cannot be provided when loading."]
    }

    @dataclass_json(undefined=Undefined.INCLUDE)
    @dataclass
    class WriteOnlyCatchAll:
        name: str
        extras: CatchAll = field(
            default=None,
            metadata=config(write_only=True),
        )

    value = WriteOnlyCatchAll.from_dict({"name": "alice", "extra": True})

    assert value.to_dict() == {"name": "alice"}
    assert WriteOnlyCatchAll.schema().dump(value) == {"name": "alice"}
