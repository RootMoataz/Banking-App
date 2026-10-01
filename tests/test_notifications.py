"""Customer notifications: stored when a deposit or withdrawal changes the customer's category, with marketing only
for customers who opted in. Nothing is emailed or pushed."""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.config import Settings
from app.db import ensure_indexes
from app.main import create_app
from app.models import AmountRequest, Preferences
from app.notifications import messages
from app.repositories import AccountRepository, NotificationRepository, TransactionRepository
from app.services import AccountService
from test_search_alerts import account, customer, money, post

DEFAULTS = Settings("mongodb://unused", "paper_maker_test_offline")  # the approved example thresholds
LOAN_DISCLAIMER = "Eligibility and approval depend on assessment."


def opt_in(client, owner, enabled=True):
    response = client.patch(f"/api/customers/{owner}/preferences", json={"marketingEnabled": enabled})
    assert response.status_code == 200, response.text
    return response.json()


def notifications(client, owner, **params):
    response = client.get(f"/api/customers/{owner}/notifications", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def kinds(client, owner):
    """Oldest first, which reads more naturally in assertions than the API's newest-first order."""
    return [n["kind"] for n in reversed(notifications(client, owner))]


# ---- offline: templates, validation, indexes and the category-change decision -------------------------------------

@pytest.mark.parametrize("entered, opted_in, expected", [
    ("LOW", False, ["LOW_BALANCE_ALERT"]),
    ("LOW", True, ["LOW_BALANCE_ALERT", "LOW_BALANCE_MARKETING"]),
    ("STANDARD", False, []), ("STANDARD", True, []),
    ("PREMIUM", False, []),
    ("PREMIUM", True, ["PREMIUM_MARKETING"]),
])
def test_messages_respect_marketing_opt_in(entered, opted_in, expected):
    assert [m["kind"] for m in messages(entered, opted_in, DEFAULTS)] == expected


def test_message_texts_and_templates():
    low = messages("LOW", True, DEFAULTS)
    [premium] = messages("PREMIUM", True, DEFAULTS)
    assert [(m["templateId"], m["message"]) for m in low] == [
        ("low-balance-v1", "Your combined account balance is below 100.00."),
        ("loan-options-v1", "Explore available loan options and learn how to apply. " + LOAN_DISCLAIMER)]
    assert (premium["templateId"], premium["message"]) == (
        "premium-v1", "Your combined balance has reached 10,000.00. Explore available premium banking benefits.")


def test_low_balance_marketing_makes_no_loan_promise():
    [_, marketing] = messages("LOW", True, DEFAULTS)
    text = marketing["message"].lower()
    assert LOAN_DISCLAIMER.lower() in text
    for claim in ("approved", "pre-approved", "prequalif", "pre-qualif", "you are eligible", "you qualify",
                  "guarantee"):
        assert claim not in text


def test_messages_use_configured_thresholds():
    settings = Settings("mongodb://unused", "paper_maker_test_offline", low_cents=25_050, premium_cents=123_456_789)
    assert messages("LOW", False, settings)[0]["message"] == "Your combined account balance is below 250.50."
    assert messages("PREMIUM", True, settings)[0]["message"].startswith(
        "Your combined balance has reached 1,234,567.89.")


@pytest.mark.parametrize("value", ["true", 1, 0, None, "yes"])
def test_preferences_need_a_real_boolean(value):
    with pytest.raises(ValidationError):
        Preferences(marketing_enabled=value)


def test_preferences_reject_extra_fields_and_accept_false():
    with pytest.raises(ValidationError):
        Preferences.model_validate({"marketingEnabled": True, "extra": 1})
    assert Preferences.model_validate({"marketingEnabled": False}).marketing_enabled is False


OFFLINE = TestClient(create_app(DEFAULTS))  # no lifespan: these requests fail validation before any handler runs


@pytest.mark.parametrize("method, path, kwargs", [
    ("PATCH", "/api/customers/abc/preferences", {"json": {"marketingEnabled": True}}),
    ("PATCH", f"/api/customers/{'a' * 24}/preferences", {"json": {"marketingEnabled": "true"}}),
    ("PATCH", f"/api/customers/{'a' * 24}/preferences", {"json": {}}),
    ("GET", "/api/customers/abc/notifications", {}),
    ("GET", f"/api/customers/{'a' * 24}/notifications", {"params": {"kind": "HIGH_BALANCE"}}),
    ("GET", f"/api/customers/{'a' * 24}/notifications", {"params": {"limit": 0}}),
    ("GET", f"/api/customers/{'a' * 24}/notifications", {"params": {"limit": 201}}),
])
def test_bad_requests_are_rejected(method, path, kwargs):
    assert OFFLINE.request(method, path, **kwargs).status_code == 422


def test_old_alerts_route_is_gone():
    assert all(r.path != "/api/alerts" for r in create_app(DEFAULTS).routes)


def test_notification_indexes():
    db = MagicMock()
    ensure_indexes(db)
    calls = {tuple(c.args[0]): c.kwargs for c in db.notifications.create_index.call_args_list}
    assert calls[(("customerId", 1), ("categoryVersion", 1), ("kind", 1))]["unique"] is True
    assert (("customerId", 1), ("createdAt", -1), ("_id", -1)) in calls
    assert not db.alerts.create_index.called


def _offline_service(total_after, marketing):
    service = AccountService.__new__(AccountService)
    service.settings = DEFAULTS
    service.db = MagicMock()
    owner, account_oid = ObjectId(), ObjectId()
    after = {"_id": account_oid, "customerId": owner, "customerName": "Moataz Hikal", "accountType": "SAVINGS",
             "balanceCents": total_after, "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    service.customers = MagicMock(touch=MagicMock(return_value={"_id": owner, "marketingEnabled": marketing}),
                                  next_category_version=MagicMock(return_value=4))
    service.accounts = MagicMock(get=MagicMock(return_value=after), inc=MagicMock(return_value=after),
                                 customer_total=MagicMock(return_value=total_after))
    service.transactions = MagicMock(by_key=MagicMock(return_value=None),
                                     insert=MagicMock(return_value={"_id": ObjectId(), **after}))
    service.notifications = MagicMock()
    return service


@pytest.mark.parametrize("kind, cents, total_after, marketing, entered, expected", [
    ("DEPOSIT", 1, 10_000, True, "STANDARD", []),  # LOW -> STANDARD: new version, no message
    ("WITHDRAW", 1, 9_999, False, "LOW", ["LOW_BALANCE_ALERT"]),
    ("WITHDRAW", 1, 9_999, True, "LOW", ["LOW_BALANCE_ALERT", "LOW_BALANCE_MARKETING"]),
    ("DEPOSIT", 1, 1_000_000, True, "PREMIUM", ["PREMIUM_MARKETING"]),
    ("DEPOSIT", 1, 1_000_000, False, "PREMIUM", []),
    ("DEPOSIT", 2_000_000, 2_000_000, False, "PREMIUM", []),  # LOW straight to PREMIUM
    ("WITHDRAW", 2_000_000, 0, False, "LOW", ["LOW_BALANCE_ALERT"]),  # PREMIUM straight to LOW
    ("WITHDRAW", 1_000_000, 1_000_000, True, "PREMIUM", None),  # stays PREMIUM
    ("WITHDRAW", 1, 9_998, True, "LOW", None),  # stays LOW
    ("DEPOSIT", 1, 500_000, True, "STANDARD", None),  # stays STANDARD
])
def test_messages_only_on_category_change(monkeypatch, kind, cents, total_after, marketing, entered, expected):
    service = _offline_service(total_after, marketing)
    session = MagicMock()
    monkeypatch.setattr("app.services._in_transaction", lambda db, work: work(session))
    service._transact(ObjectId(), AmountRequest(amount=Decimal(cents) / 100), kind, None)
    calls = service.notifications.insert.call_args_list
    if expected is None:
        assert not service.customers.next_category_version.called and calls == []
        return
    service.customers.next_category_version.assert_called_once()
    assert [c.args[3]["kind"] for c in calls] == expected
    record = service.transactions.insert.return_value
    assert all(c.args[:3] == (record, entered, 4) and c.args[4] is session for c in calls)


# ---- Atlas -------------------------------------------------------------------------------------------------------

def test_crossings_and_opt_out(client, settings):
    owner = customer(client)
    first, second = account(client, owner), account(client, owner)
    assert opt_in(client, owner)["marketingEnabled"] is True
    assert notifications(client, owner) == []  # opening accounts at zero is not a category change
    assert post(client, first, "deposit", money(settings.low_cents - 1)).status_code == 200  # still LOW
    assert post(client, second, "deposit", money(1)).status_code == 200  # STANDARD: no message
    assert notifications(client, owner) == []
    assert post(client, second, "deposit", money(settings.premium_cents - settings.low_cents)).status_code == 200
    assert kinds(client, owner) == ["PREMIUM_MARKETING"]
    assert post(client, second, "deposit", money(1)).status_code == 200  # still PREMIUM
    assert kinds(client, owner) == ["PREMIUM_MARKETING"]
    assert opt_in(client, owner, False)["marketingEnabled"] is False
    assert post(client, second, "withdraw", money(settings.premium_cents - settings.low_cents + 2)).status_code == 200
    assert kinds(client, owner) == ["PREMIUM_MARKETING", "LOW_BALANCE_ALERT"]  # opted out: no loan marketing
    assert post(client, first, "withdraw", money(1)).status_code == 200  # still LOW
    assert kinds(client, owner) == ["PREMIUM_MARKETING", "LOW_BALANCE_ALERT"]


def test_notification_fields(client, settings):
    owner = customer(client)
    id = account(client, owner)
    opt_in(client, owner)
    assert post(client, id, "deposit", money(settings.low_cents)).status_code == 200  # version 1, STANDARD
    assert post(client, id, "withdraw", money(1)).status_code == 200  # version 2, LOW
    txn = client.get(f"/api/accounts/{id}/transactions").json()[-1]
    found = notifications(client, owner)
    assert {n["kind"] for n in found} == {"LOW_BALANCE_ALERT", "LOW_BALANCE_MARKETING"}
    for n in found:
        assert len(n.pop("notificationId")) == 24
        assert n.pop("createdAt") == txn["date"]
        n.pop("kind"), n.pop("templateId"), n.pop("message")
        assert n == {"customerId": owner, "categoryVersion": 2, "category": "LOW", "transactionId": txn["txnId"]}


def test_preferences_persist_and_survive_edits(client):
    created = client.post("/api/customers", json={"name": "Moataz Hikal", "email": "pref@example.com"}).json()
    assert created["marketingEnabled"] is False  # marketing is off until the customer opts in
    owner = created["customerId"]
    changed = opt_in(client, owner)
    assert changed == {**created, "marketingEnabled": True}
    edited = client.put(f"/api/customers/{owner}", json={"name": "M. Hikal", "email": "pref2@example.com"}).json()
    assert edited["marketingEnabled"] is True
    assert client.get(f"/api/customers/{owner}").json()["marketingEnabled"] is True
    assert client.get("/api/customers").json()[0]["marketingEnabled"] is True


def test_unknown_customer_is_404(client):
    missing = str(ObjectId())
    assert client.patch(f"/api/customers/{missing}/preferences", json={"marketingEnabled": True}).status_code == 404
    assert client.get(f"/api/customers/{missing}/notifications").status_code == 404


def test_list_newest_first_kind_filter_and_limit(client, settings):
    owner = customer(client)
    id = account(client, owner, settings.low_cents)
    opt_in(client, owner)
    for _ in range(2):
        assert post(client, id, "withdraw", money(1)).status_code == 200  # into LOW
        assert post(client, id, "deposit", money(1)).status_code == 200  # back to STANDARD
    everything = notifications(client, owner)
    assert [n["categoryVersion"] for n in everything] == [4, 4, 2, 2]  # newest first
    assert [n["createdAt"] for n in everything] == sorted((n["createdAt"] for n in everything), reverse=True)
    alerts = notifications(client, owner, kind="LOW_BALANCE_ALERT")
    assert [n["categoryVersion"] for n in alerts] == [4, 2]
    assert notifications(client, owner, limit=1) == everything[:1]
    other = customer(client, "Other", "other@example.com")
    assert notifications(client, other) == []


def test_notification_is_dated_with_its_transaction(client, db, settings, monkeypatch):
    """The transaction's date can be pushed past the clock to keep history in order; its message carries that date."""
    ticks = itertools.count()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.repositories._now", lambda: start + timedelta(seconds=next(ticks)))
    owner = customer(client, "Dated", "dated@example.com")
    id = account(client, owner, settings.low_cents)
    assert post(client, id, "withdraw", money(1)).status_code == 200
    notice = db.notifications.find_one({})
    assert notice["createdAt"] == db.transactions.find_one({"_id": notice["transactionId"]})["createdAt"]


def test_replay_creates_no_second_notification(client, db, settings):
    id = account(client, customer(client), settings.low_cents)
    first = post(client, id, "withdraw", money(1), "key-1")
    replay = post(client, id, "withdraw", money(1), "key-1")
    assert (first.status_code, replay.status_code) == (200, 200)
    assert replay.json() == first.json()
    assert [n["kind"] for n in db.notifications.find()] == ["LOW_BALANCE_ALERT"]


def test_failed_notification_insert_rolls_back_all(client, db, settings, monkeypatch):
    owner = customer(client)
    id = account(client, owner, settings.low_cents)
    version = db.customers.find_one({"_id": ObjectId(owner)})["categoryVersion"]

    def broken(self, *args, **kwargs):
        raise RuntimeError("notification insert failed")
    monkeypatch.setattr(NotificationRepository, "insert", broken)
    with pytest.raises(RuntimeError, match="notification insert failed"):
        post(client, id, "withdraw", money(1))
    assert db.accounts.find_one({"_id": ObjectId(id)})["balanceCents"] == settings.low_cents
    assert db.transactions.count_documents({}) == 1  # only the setup deposit
    assert db.notifications.count_documents({}) == 0
    assert db.customers.find_one({"_id": ObjectId(owner)})["categoryVersion"] == version


def test_transaction_retry_does_not_duplicate_history_or_messages(client, db, settings, monkeypatch):
    owner = customer(client)
    id = account(client, owner, settings.low_cents)
    opt_in(client, owner)
    insert, attempts = NotificationRepository.insert, []

    def retry_once(self, *args, **kwargs):
        insert(self, *args, **kwargs)
        attempts.append(1)
        if len(attempts) == 1:  # the driver reruns the whole transaction after a transient error
            raise OperationFailure("retry", code=112, details={"errorLabels": ["TransientTransactionError"]})
    monkeypatch.setattr(NotificationRepository, "insert", retry_once)
    assert post(client, id, "withdraw", money(1)).status_code == 200
    assert len(attempts) == 3  # one message on the aborted attempt, two on the committed one
    assert len(client.get(f"/api/accounts/{id}/transactions").json()) == 2
    assert sorted(kinds(client, owner)) == ["LOW_BALANCE_ALERT", "LOW_BALANCE_MARKETING"]
    assert db.customers.find_one({"_id": ObjectId(owner)})["categoryVersion"] == 2


def test_unique_key_rejects_a_duplicate_message(client, db, settings):
    owner = customer(client)
    id = account(client, owner, settings.low_cents)
    assert post(client, id, "withdraw", money(1)).status_code == 200
    stored = db.notifications.find_one({}, {"_id": 0})
    with pytest.raises(DuplicateKeyError):
        db.notifications.insert_one(dict(stored))


def test_two_accounts_crossing_concurrently_one_message(client, db, settings, monkeypatch):
    """Two withdrawals on two accounts of one customer, each enough on its own to drop the total below the low
    threshold. The first is held after its writes until the second has started its transaction. Without the customer
    write both would see the old total and there would be two low-balance alerts."""
    owner = customer(client)
    first = account(client, owner, settings.low_cents)
    second = account(client, owner, 1)
    insert, get = TransactionRepository.insert, AccountRepository.get
    entered, release = threading.Event(), threading.Event()
    holder = []

    def held_insert(self, *args, **kwargs):
        if not holder:
            holder.append(threading.get_ident())
            entered.set()
            assert release.wait(timeout=8), "the second withdrawal never started its transaction"
        return insert(self, *args, **kwargs)

    def signalling_get(self, oid, session=None):
        doc = get(self, oid, session)
        if session is not None and entered.is_set() and threading.get_ident() != holder[0]:
            release.set()
        return doc

    monkeypatch.setattr(TransactionRepository, "insert", held_insert)
    monkeypatch.setattr(AccountRepository, "get", signalling_get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(post, client, first, "withdraw", money(2))
        assert entered.wait(timeout=8)
        other = pool.submit(post, client, second, "withdraw", money(1))
        assert (held.result().status_code, other.result().status_code) == (200, 200)
    assert [(n["kind"], n["categoryVersion"]) for n in db.notifications.find()] == [("LOW_BALANCE_ALERT", 2)]


def test_opt_out_during_a_deposit_is_respected(client, monkeypatch, settings):
    """The deposit reads the account, then the customer opts out and commits. The deposit's customer write conflicts,
    the driver reruns it, and the rerun sees the opt-out: no premium marketing."""
    owner = customer(client)
    id = account(client, owner)
    opt_in(client, owner)
    account_read, resume = threading.Event(), threading.Event()
    get = AccountRepository.get

    def pause_first_read(self, oid, session=None):
        doc = get(self, oid, session)
        if session is not None and not account_read.is_set():
            account_read.set()
            assert resume.wait(timeout=10), "timed out waiting for the opt-out"
        return doc

    monkeypatch.setattr(AccountRepository, "get", pause_first_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        deposit = pool.submit(post, client, id, "deposit", money(settings.premium_cents))
        try:
            assert account_read.wait(timeout=10), "the deposit never read the account"
            assert opt_in(client, owner, False)["marketingEnabled"] is False
        finally:
            resume.set()
        assert deposit.result(timeout=20).status_code == 200
    assert notifications(client, owner, kind="PREMIUM_MARKETING") == []
    assert len(client.get(f"/api/accounts/{id}/transactions").json()) == 1
