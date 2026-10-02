import json
from dataclasses import dataclass, field
from typing import List, Optional

import pytest
from marshmallow import ValidationError

from dataclasses_json import (CatchAll, DataClassJsonMixin,
                              Undefined, config, dataclass_json)


def _generate_audit_id():
    return "server-generated-audit-id"


@dataclass_json(undefined=Undefined.INCLUDE)
@dataclass
class Account(DataClassJsonMixin):
    username: str
    password: str = field(
        metadata=config(field_name="passwordHash", write_only=True))
    audit_id: str = field(
        default_factory=_generate_audit_id,
        metadata=config(field_name="auditId", read_only=True))
    catch_all: Optional[CatchAll] = None


@dataclass
class Credential(DataClassJsonMixin):
    value: str = field(metadata=config(write_only=True))
    issued_at: str = field(default_factory=lambda: "server-issued",
                           metadata=config(read_only=True))


@dataclass
class Vault(DataClassJsonMixin):
    credentials: List[Credential]


@dataclass
class BaseToken(DataClassJsonMixin):
    token: str = field(metadata=config(write_only=True))


@dataclass
class NamedToken(BaseToken):
    name: str = ""


account_schema = Account.schema()
vault_schema = Vault.schema()


class TestWriteOnly:
    def test_to_dict_excludes_write_only(self):
        account = Account(username="alice", password="secret")
        assert account.to_dict() == {
            'username': 'alice',
            'auditId': 'server-generated-audit-id'}

    def test_to_json_excludes_write_only(self):
        account = Account(username="alice", password="secret")
        encoded = json.loads(account.to_json())
        assert 'passwordHash' not in encoded
        assert 'password' not in encoded
        assert encoded['username'] == 'alice'

    def test_schema_dump_excludes_write_only(self):
        account = Account(username="alice", password="secret")
        dumped = account_schema.dump(account)
        assert 'passwordHash' not in dumped
        assert 'password' not in dumped

    def test_schema_dumps_excludes_write_only(self):
        account = Account(username="alice", password="secret")
        encoded = json.loads(account_schema.dumps(account))
        assert 'passwordHash' not in encoded
        assert 'password' not in encoded

    def test_from_dict_accepts_write_only(self):
        account = Account.from_dict(
            {'username': 'alice', 'passwordHash': 'secret'})
        assert account.password == 'secret'

    def test_from_json_accepts_write_only(self):
        account = Account.from_json(
            '{"username": "alice", "passwordHash": "secret"}')
        assert account.password == 'secret'

    def test_schema_load_accepts_write_only(self):
        account = account_schema.load(
            {'username': 'alice', 'passwordHash': 'secret'})
        assert account.password == 'secret'


class TestReadOnly:
    def test_from_dict_rejects_read_only(self):
        with pytest.raises(ValidationError):
            Account.from_dict({'username': 'alice',
                               'passwordHash': 'secret',
                               'auditId': 'forged'})

    def test_from_dict_rejects_read_only_under_field_name(self):
        with pytest.raises(ValidationError):
            Account.from_dict({'username': 'alice',
                               'passwordHash': 'secret',
                               'audit_id': 'forged'})

    def test_from_json_rejects_read_only(self):
        with pytest.raises(ValidationError):
            Account.from_json('{"username": "alice", '
                              '"passwordHash": "secret", '
                              '"auditId": "forged"}')

    def test_schema_load_rejects_read_only(self):
        with pytest.raises(ValidationError):
            account_schema.load({'username': 'alice',
                                 'passwordHash': 'secret',
                                 'auditId': 'forged'})

    def test_missing_read_only_uses_default_factory(self):
        account = Account.from_dict(
            {'username': 'alice', 'passwordHash': 'secret'})
        assert account.audit_id == 'server-generated-audit-id'
        account = account_schema.load(
            {'username': 'alice', 'passwordHash': 'secret'})
        assert account.audit_id == 'server-generated-audit-id'

    def test_read_only_included_in_output(self):
        account = Account(username="alice", password="secret")
        assert account.to_dict()['auditId'] == 'server-generated-audit-id'
        assert account_schema.dump(account)['auditId'] == \
            'server-generated-audit-id'

    def test_forged_read_only_not_captured_by_catch_all(self):
        forged = {'username': 'alice',
                  'passwordHash': 'secret',
                  'auditId': 'forged'}
        with pytest.raises(ValidationError):
            Account.from_dict(forged)
        with pytest.raises(ValidationError):
            account_schema.load(forged)

    def test_unknown_fields_still_captured_by_catch_all(self):
        account = Account.from_dict({'username': 'alice',
                                     'passwordHash': 'secret',
                                     'extra': 42})
        assert account.catch_all == {'extra': 42}
        account = account_schema.load({'username': 'alice',
                                       'passwordHash': 'secret',
                                       'extra': 42})
        assert account.catch_all == {'extra': 42}


class TestConfigValidation:
    def test_read_only_and_write_only_are_mutually_exclusive(self):
        with pytest.raises(ValueError):
            config(read_only=True, write_only=True)


class TestInheritance:
    def test_write_only_inherited(self):
        token = NamedToken(token="secret", name="n")
        assert token.to_dict() == {'name': 'n'}

    def test_inherited_write_only_accepted_on_load(self):
        token = NamedToken.from_dict({'token': 'secret', 'name': 'n'})
        assert token.token == 'secret'


class TestNestedCollections:
    def test_write_only_excluded_in_nested_collection(self):
        vault = Vault([Credential("a"), Credential("b")])
        assert vault.to_dict() == {
            'credentials': [{'issued_at': 'server-issued'},
                            {'issued_at': 'server-issued'}]}
        assert vault_schema.dump(vault) == {
            'credentials': [{'issued_at': 'server-issued'},
                            {'issued_at': 'server-issued'}]}

    def test_read_only_rejected_in_nested_collection(self):
        forged = {'credentials': [{'value': 'a', 'issued_at': 'forged'}]}
        with pytest.raises(ValidationError):
            Vault.from_dict(forged)
        with pytest.raises(ValidationError):
            vault_schema.load(forged)

    def test_nested_collection_round_trip(self):
        vault = Vault.from_dict({'credentials': [{'value': 'a'}]})
        assert vault.credentials[0].value == 'a'
        assert vault.credentials[0].issued_at == 'server-issued'
