"""Offline checks (no MongoDB needed): query shapes, index definitions, input patterns, version, error logging."""
import logging
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from conftest import offline_client
from app.config import Settings
from app.main import create_app
from app.models import AccountCreate, AccountEdit, AmountRequest, UserCreate
from app.repositories import CustomerRepository, TransactionRepository
from app.services import AccountService, BankError, CustomerService

SETTINGS = Settings("mongodb://unused", "paper_maker_test_offline", low_cents=10_000, premium_cents=1_000_000)


def _repo(cls):
    collection = MagicMock()
    return cls(SimpleNamespace(customers=collection, transactions=collection)), collection


def test_page_adds_plain_cursor_lower_bound():
    repo, collection = _repo(TransactionRepository)
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    oid = ObjectId()
    repo.page({"customerId": oid}, (t, oid), 5)
    query = collection.find.call_args.args[0]
    assert query["createdAt"] == {"$gte": t}
    assert query["$or"] == [{"createdAt": {"$gt": t}}, {"createdAt": t, "_id": {"$gt": oid}}]


def test_page_lower_bound_is_max_of_from_and_cursor():
    repo, collection = _repo(TransactionRepository)
    early, late = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc)
    repo.page({"createdAt": {"$gte": early, "$lt": late}}, (late.replace(day=2), ObjectId()), 5)
    assert collection.find.call_args.args[0]["createdAt"] == {"$gte": late.replace(day=2), "$lt": late}
    repo.page({"createdAt": {"$gte": late}}, (early, ObjectId()), 5)
    assert collection.find.call_args.args[0]["createdAt"] == {"$gte": late}


def test_page_without_cursor_is_unchanged():
    repo, collection = _repo(TransactionRepository)
    repo.page({"customerId": 1}, None, 5)
    assert collection.find.call_args.args[0] == {"customerId": 1}


def _stages(total_cond):
    repo, collection = _repo(CustomerRepository)
    repo.search(None, None, total_cond, 7)
    return [next(iter(s)) for s in collection.aggregate.call_args.args[0]]


def test_search_limits_before_lookup_without_balance_condition():
    stages = _stages({})
    assert stages.index("$limit") < stages.index("$lookup")


def test_search_limits_after_balance_match_with_condition():
    stages = _stages({"$gte": 1})
    assert stages.index("$limit") > stages.index("$lookup")


@pytest.mark.parametrize("bad", ["a\x00b", "a\nb", "a\x7fb"])
def test_names_and_types_reject_control_characters(bad):
    with pytest.raises(ValidationError):
        UserCreate(name=bad, email="a@example.com")
    with pytest.raises(ValidationError):
        AccountEdit(account_type=bad)
    with pytest.raises(ValidationError):
        AccountCreate(user_id="a" * 24, account_type=bad)
    assert UserCreate(name="Ann O'Neil", email="a@example.com").name == "Ann O'Neil"


def test_idempotency_key_rejects_leading_space():
    client = offline_client(SETTINGS)  # no lifespan: validation fails before any handler runs
    path = f"/api/accounts/{'a' * 24}/deposit"
    for key in (" leading", "  "):
        assert client.post(path, json={"amount": "1.00"}, headers={"Idempotency-Key": key}).status_code == 422


def test_api_version():
    assert create_app(SETTINGS).version == "2.1.0"


def test_missing_owner_is_logged_at_error_level(caplog, monkeypatch):
    service = AccountService.__new__(AccountService)
    service.settings = SETTINGS
    service.db = MagicMock()
    service.customers = MagicMock(touch=MagicMock(return_value=None))
    service.accounts = MagicMock(get=MagicMock(return_value={"_id": ObjectId(), "customerId": ObjectId()}))
    service.transactions = MagicMock(by_key=MagicMock(return_value=None))
    monkeypatch.setattr("app.services._in_transaction", lambda db, work: work(MagicMock()))
    with caplog.at_level(logging.ERROR), pytest.raises(BankError):
        service._transact(ObjectId(), MagicMock(amount=Decimal("1.00")), "DEPOSIT", None)
    assert any(r.levelno == logging.ERROR and "no owner record" in r.getMessage() for r in caplog.records)


def test_email_key_ignores_letter_case_with_lower():
    repo, collection = _repo(CustomerRepository)
    repo.insert("Ann", "Ann@Example.COM")
    assert collection.insert_one.call_args.args[0]["emailKey"] == "ann@example.com"
    repo.insert("Strasse", "Straße@x.com")  # casefold() would give "strasse@x.com"
    assert collection.insert_one.call_args.args[0]["emailKey"] == "straße@x.com"


def test_stored_legacy_name_with_control_character_still_serializes():
    from app.services import _customer
    doc = {"_id": ObjectId(), "name": "Ann\tO'Neil", "email": "a@example.com",
           "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    assert _customer(doc).name == "Ann\tO'Neil"
    service = CustomerService.__new__(CustomerService)
    service.customers = MagicMock(insert=MagicMock(return_value=doc))
    assert service.create_user(UserCreate(name="Ann", email="a@example.com")).name == "Ann\tO'Neil"


def _dup(index_key):
    return DuplicateKeyError("E11000 duplicate key", 11000, {"keyPattern": index_key})


def _transact_service(monkeypatch, notification_error=None, transaction_error=None, prior=None):
    service = AccountService.__new__(AccountService)
    service.settings = SETTINGS
    service.db = MagicMock()
    owner, account_oid = ObjectId(), ObjectId()
    after = {"_id": account_oid, "customerId": owner, "customerName": "Ann", "accountType": "SAVINGS",
             "balanceCents": 5_000, "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    service.customers = MagicMock(touch=MagicMock(return_value={"_id": owner}),
                                  next_category_version=MagicMock(return_value=1))
    service.accounts = MagicMock(get=MagicMock(return_value=after), inc=MagicMock(return_value=after),
                                 customer_total=MagicMock(return_value=9_950))  # a 1.00 withdraw drops the total from 100.50 to LOW
    service.transactions = MagicMock(by_key=MagicMock(side_effect=[None, prior]),
                                     insert=MagicMock(return_value={"_id": ObjectId(), **after},
                                                      side_effect=transaction_error))
    service.notifications = MagicMock(insert=MagicMock(side_effect=notification_error))
    monkeypatch.setattr("app.services._in_transaction", lambda db, work: work(MagicMock()))
    return service


def test_duplicate_notification_is_not_treated_as_an_idempotency_replay(monkeypatch, caplog):
    key = {"customerId": 1, "categoryVersion": 1, "kind": 1}
    service = _transact_service(monkeypatch, notification_error=_dup(key), prior={"never": "used"})
    with caplog.at_level(logging.ERROR), pytest.raises(BankError) as raised:
        service._transact(ObjectId(), AmountRequest(amount=Decimal("1.00")), "WITHDRAW", "k1")
    assert (raised.value.status, raised.value.detail) == (500, "Notification state is inconsistent for this customer")
    assert any(r.levelno == logging.ERROR and "categoryVersion" in r.getMessage() for r in caplog.records)
    assert service.transactions.by_key.call_count == 1  # no replay lookup after the failure


def test_duplicate_idempotency_key_replays_the_committed_result(monkeypatch):
    prior = {"_id": ObjectId(), "type": "WITHDRAW", "amountCents": 100, "accountId": ObjectId(),
             "customerId": ObjectId(), "balanceAfterCents": 4_900,
             "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    service = _transact_service(monkeypatch, transaction_error=_dup({"accountId": 1, "idempotencyKey": 1}),
                                prior=prior)
    service.accounts.get = MagicMock(side_effect=[{"_id": ObjectId(), "customerId": ObjectId()}, None])
    result = service._transact(ObjectId(), AmountRequest(amount=Decimal("1.00")), "WITHDRAW", "k1")
    assert result.txn_id == str(prior["_id"])


def test_load_settings_reads_file_without_touching_environ(monkeypatch, tmp_path):
    from app.config import load_settings
    for name in ("MONGODB_URI", "MONGODB_DB"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text("MONGODB_URI=mongodb://from-file\nMONGODB_DB=filedb\n")
    settings = load_settings(env_file=env_file)
    assert (settings.mongodb_uri, settings.mongodb_db) == ("mongodb://from-file", "filedb")
    import os
    assert "MONGODB_URI" not in os.environ and "MONGODB_DB" not in os.environ


def test_bare_threshold_key_in_env_file_uses_the_default(monkeypatch, tmp_path):
    from app.config import load_settings
    for name in ("MONGODB_URI", "LOW_BALANCE_THRESHOLD", "PREMIUM_BALANCE_THRESHOLD", "MONGODB_DB"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text("MONGODB_URI=mongodb://from-file\nLOW_BALANCE_THRESHOLD\nMONGODB_DB\n")
    settings = load_settings(env_file=env_file)
    assert (settings.low_cents, settings.mongodb_db) == (10_000, "paper_maker")


def test_real_environment_beats_the_env_file(monkeypatch, tmp_path):
    from app.config import load_settings
    monkeypatch.setenv("MONGODB_URI", "mongodb://from-env")
    env_file = tmp_path / "test.env"
    env_file.write_text("MONGODB_URI=mongodb://from-file\n")
    assert load_settings(env_file=env_file).mongodb_uri == "mongodb://from-env"


@pytest.mark.parametrize("repo_cls, method", [(CustomerRepository, "list")])
def test_list_limit_caps_the_cursor(repo_cls, method):
    repo, collection = _repo(repo_cls)
    getattr(repo, method)(limit=5)
    collection.find.return_value.sort.return_value.limit.assert_called_with(5)
    getattr(repo, method)()
    collection.find.return_value.sort.return_value.limit.assert_called_with(0)  # 0 means no cap in MongoDB


@pytest.mark.parametrize("path", ["/api/customers", "/api/accounts", f"/api/accounts/{'a' * 24}/transactions"])
@pytest.mark.parametrize("bad", ["0", "201", "-1", "abc"])
def test_list_endpoints_reject_a_bad_limit(path, bad):
    assert offline_client(SETTINGS).get(path, params={"limit": bad}).status_code == 422


def test_limit_caps_lists_and_omitting_it_returns_everything(client):  # needs MongoDB
    owner = client.post("/api/customers", json={"name": "Lim", "email": "lim@example.com"}).json()["customerId"]
    for _ in range(3):
        client.post("/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
    accounts = client.get("/api/accounts").json()
    assert len(accounts) == 3
    assert client.get("/api/accounts", params={"limit": 2}).json() == accounts[:2]
    assert len(client.get("/api/customers", params={"limit": 1}).json()) == 1
    aid = accounts[0]["accountId"]
    client.post(f"/api/accounts/{aid}/deposit", json={"amount": "5.00"})
    client.post(f"/api/accounts/{aid}/deposit", json={"amount": "6.00"})
    assert len(client.get(f"/api/accounts/{aid}/transactions", params={"limit": 1}).json()) == 1
    assert len(client.get(f"/api/accounts/{aid}/transactions").json()) == 2
