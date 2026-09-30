"""Customer search by name, email and total balance; categories; alerts written only when the total crosses a threshold."""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from bson import ObjectId

from app.config import Settings
from app.money import from_cents, to_cents
from app.repositories import AccountRepository, AlertRepository, TransactionRepository
from app.services import category, crossing


def money(cents):
    return str(from_cents(cents))


def customer(client, name="Moataz Hikal", email="moataz@example.com"):
    response = client.post("/api/customers", json={"name": name, "email": email})
    assert response.status_code == 201
    return response.json()["customerId"]


def account(client, owner, deposit_cents=0):
    response = client.post("/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
    assert response.status_code == 201
    id = response.json()["accountId"]
    if deposit_cents:
        assert post(client, id, "deposit", money(deposit_cents)).status_code == 200
    return id


def post(client, id, operation, amount, key=None):
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(f"/api/accounts/{id}/{operation}", json={"amount": amount}, headers=headers)


def search(client, **params):
    response = client.get("/api/customers/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def alert_types(db):
    return [a["type"] for a in db.alerts.find().sort([("createdAt", 1), ("_id", 1)])]


DEFAULTS = Settings("unused", "unused")  # the approved example thresholds: 100.00 and 10000.00


@pytest.mark.parametrize("total, expected", [("0.00", "LOW"), ("99.99", "LOW"), ("100.00", "STANDARD"),
                                             ("9999.99", "STANDARD"), ("10000.00", "PREMIUM")])
def test_category_boundaries(total, expected):
    assert category(to_cents(Decimal(total)), DEFAULTS) == expected


@pytest.mark.parametrize("before, after, expected", [
    (10_000, 9_999, "LOW_BALANCE"), (20_000, 0, "LOW_BALANCE"), (9_999, 9_998, None), (9_999, 10_000, None),
    (10_000, 10_000, None), (999_999, 1_000_000, "HIGH_BALANCE"), (0, 2_000_000, "HIGH_BALANCE"),
    (1_000_000, 1_000_001, None), (1_000_000, 999_999, None), (500_000, 600_000, None)])
def test_crossing(before, after, expected):
    assert crossing(before, after, DEFAULTS) == expected


def test_search_boundary_categories(client, settings):
    low, premium = settings.low_cents, settings.premium_cents
    totals = {"a": low - 1, "b": low, "c": premium - 1, "d": premium}
    for name, cents in totals.items():
        account(client, customer(client, f"Boundary {name}", f"{name}@example.com"), cents)
    found = {c["name"]: (c["totalBalance"], c["category"]) for c in search(client)}
    assert found == {"Boundary a": (money(low - 1), "LOW"), "Boundary b": (money(low), "STANDARD"),
                     "Boundary c": (money(premium - 1), "STANDARD"), "Boundary d": (money(premium), "PREMIUM")}
    assert [c["name"] for c in search(client, category="LOW")] == ["Boundary a"]
    assert [c["name"] for c in search(client, category="STANDARD")] == ["Boundary b", "Boundary c"]
    assert [c["name"] for c in search(client, category="PREMIUM")] == ["Boundary d"]


def test_customer_without_accounts_is_low_with_zero_total(client):
    owner = customer(client)
    assert search(client) == [{"customerId": owner, "name": "Moataz Hikal", "email": "moataz@example.com",
                               "totalBalance": "0.00", "category": "LOW"}]


def test_total_sums_all_accounts(client, settings):
    owner = customer(client)
    account(client, owner, settings.premium_cents - 1)
    account(client, owner, 1)
    [found] = search(client)
    assert (found["totalBalance"], found["category"]) == (money(settings.premium_cents), "PREMIUM")


def test_search_by_name_and_email(client):
    alice = customer(client, "Alice Smith", "alice@example.com")
    bob = customer(client, "Bob Stone", "bob@TEST.org")
    assert [c["customerId"] for c in search(client, name="SMITH")] == [alice]
    assert [c["customerId"] for c in search(client, name="s")] == [alice, bob]  # substring, any letter case
    assert [c["customerId"] for c in search(client, email="test.ORG")] == [bob]
    assert search(client, name="alice", email="test.org") == []  # filters combine
    assert search(client, name="nobody") == []


def test_search_escapes_regex_characters(client):
    dotted = customer(client, "Dr. Who", "dr@example.com")
    customer(client, "Drx Who", "drx@example.com")
    assert [c["customerId"] for c in search(client, name="Dr.")] == [dotted]  # "." is a dot, not any character
    assert search(client, name=".*") == []
    assert search(client, name="(") == []
    assert search(client, email="[") == []


def test_search_by_min_and_max_balance(client):
    for name, cents in [("Low", 5_000), ("Mid", 50_000), ("High", 500_000)]:
        account(client, customer(client, name, f"{name.lower()}@example.com"), cents)
    names = lambda **params: [c["name"] for c in search(client, **params)]  # noqa: E731
    assert names(minBalance="500.00") == ["Mid", "High"]  # inclusive
    assert names(maxBalance="500.00") == ["Low", "Mid"]  # inclusive
    assert names(minBalance="50.01", maxBalance="4999.99") == ["Mid"]
    assert names(minBalance="0") == ["Low", "Mid", "High"]
    assert names(minBalance="600", maxBalance="400") == []
    assert names(category="STANDARD", minBalance="1000") == ["High"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": -1}, {"limit": 201}, {"limit": "x"},
                                    {"minBalance": "-1"}, {"minBalance": "1.001"}, {"maxBalance": "abc"},
                                    {"maxBalance": "NaN"}, {"minBalance": "100000000"}, {"category": "GOLD"},
                                    {"category": "low"}, {"name": "a\x00b"}, {"email": "\x00"}, {"name": "tab\there"}])
def test_search_rejects_bad_parameters(client, params):
    assert client.get("/api/customers/search", params=params).status_code == 422


def test_alert_is_dated_with_its_transaction(client, db, monkeypatch):
    """The transaction's date can be pushed past the clock to keep history in order; its alert must carry the same date."""
    ticks = itertools.count()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.repositories._now", lambda: start + timedelta(seconds=next(ticks)))
    account(client, customer(client, "Dated", "dated@example.com"), 1_000_000)  # reaches the premium threshold
    alert = db.alerts.find_one({})
    assert alert is not None
    assert alert["createdAt"] == db.transactions.find_one({"_id": alert["transactionId"]})["createdAt"]


def test_search_limit(client):
    ids = [customer(client, f"Customer {i}", f"c{i}@example.com") for i in range(3)]
    assert [c["customerId"] for c in search(client, limit=2)] == ids[:2]
    assert len(search(client, limit=200)) == 3


def test_search_route_not_captured_by_id_route(client):
    owner = customer(client)
    response = client.get("/api/customers/search")
    assert response.status_code == 200
    assert [c["customerId"] for c in response.json()] == [owner]
    assert client.get(f"/api/customers/{owner}").status_code == 200  # the id route still works


def test_alert_only_on_crossing(client, db, settings):
    owner = customer(client)
    id = account(client, owner)
    premium = settings.premium_cents
    assert post(client, id, "deposit", money(premium // 2)).status_code == 200
    assert post(client, id, "deposit", money(premium - premium // 2 - 1)).status_code == 200
    assert alert_types(db) == []  # both deposits stayed below the threshold
    assert post(client, id, "deposit", money(1)).status_code == 200
    assert post(client, id, "deposit", money(1)).status_code == 200  # already above: no second alert
    [alert] = client.get("/api/alerts").json()
    txn = client.get(f"/api/accounts/{id}/transactions").json()[2]
    assert alert.pop("alertId") and alert.pop("createdAt")
    assert alert == {"customerId": owner, "accountId": id, "transactionId": txn["txnId"], "type": "HIGH_BALANCE",
                     "totalBalance": money(premium), "threshold": money(premium)}


def test_low_alert_on_crossing_and_rearms(client, db, settings):
    low = settings.low_cents
    id = account(client, customer(client), low + 100)
    assert alert_types(db) == []  # rising past the low threshold is not an alert
    assert post(client, id, "withdraw", money(101)).status_code == 200  # low - 1
    assert alert_types(db) == ["LOW_BALANCE"]
    assert post(client, id, "withdraw", money(1)).status_code == 200  # still below
    assert alert_types(db) == ["LOW_BALANCE"]
    assert post(client, id, "deposit", money(2)).status_code == 200  # back to exactly low
    assert post(client, id, "withdraw", money(1)).status_code == 200  # below again
    assert alert_types(db) == ["LOW_BALANCE", "LOW_BALANCE"]


def test_replay_creates_no_second_alert(client, db, settings):
    id = account(client, customer(client))
    first = post(client, id, "deposit", money(settings.premium_cents), "key-1")
    replay = post(client, id, "deposit", money(settings.premium_cents), "key-1")
    assert (first.status_code, replay.status_code) == (200, 200)
    assert replay.json() == first.json()
    assert alert_types(db) == ["HIGH_BALANCE"]
    assert db.transactions.count_documents({}) == 1


def test_failed_alert_insert_rolls_back_all(client, db, settings, monkeypatch):
    id = account(client, customer(client), settings.premium_cents - 1)

    def broken(self, *args, **kwargs):
        raise RuntimeError("alert insert failed")
    monkeypatch.setattr(AlertRepository, "insert", broken)
    with pytest.raises(RuntimeError, match="alert insert failed"):
        post(client, id, "deposit", money(1))
    assert db.accounts.find_one({"_id": ObjectId(id)})["balanceCents"] == settings.premium_cents - 1
    assert db.transactions.count_documents({}) == 1  # only the setup deposit
    assert db.alerts.count_documents({}) == 0


def test_two_accounts_crossing_concurrently_one_alert(client, db, settings, monkeypatch):
    """Two deposits on two accounts of one customer, each enough to cross the premium threshold on its own. The first is
    held after its writes until the second has started its transaction (taken its snapshot). Without the customer
    write both would see the old total, both would cross, and there would be two alerts."""
    owner = customer(client)
    first = account(client, owner, settings.premium_cents - 1)
    second = account(client, owner)
    insert, get = TransactionRepository.insert, AccountRepository.get
    entered, release = threading.Event(), threading.Event()
    holder = []

    def held_insert(self, *args, **kwargs):
        if not holder:
            holder.append(threading.get_ident())
            entered.set()
            assert release.wait(timeout=8), "the second deposit never started its transaction"
        return insert(self, *args, **kwargs)

    def signalling_get(self, oid, session=None):
        doc = get(self, oid, session)
        if session is not None and entered.is_set() and threading.get_ident() != holder[0]:
            release.set()  # the competitor's transaction has read, so its snapshot predates the holder's commit
        return doc

    monkeypatch.setattr(TransactionRepository, "insert", held_insert)
    monkeypatch.setattr(AccountRepository, "get", signalling_get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(post, client, first, "deposit", money(1))
        assert entered.wait(timeout=8)
        other = pool.submit(post, client, second, "deposit", money(1))
        assert (held.result().status_code, other.result().status_code) == (200, 200)
    assert [(a["type"], str(a["accountId"])) for a in db.alerts.find()] == [("HIGH_BALANCE", first)]
    [found] = search(client)
    assert found["totalBalance"] == money(settings.premium_cents + 1)


def test_alerts_filter_by_customer_newest_first_and_limit(client, db, settings):
    low = settings.low_cents
    alice = account(client, customer(client, "Alice", "alice@example.com"), low)
    bob_id = customer(client, "Bob", "bob@example.com")
    bob = account(client, bob_id, low)
    assert post(client, alice, "withdraw", money(1)).status_code == 200
    assert post(client, bob, "withdraw", money(1)).status_code == 200
    assert post(client, bob, "deposit", money(1)).status_code == 200
    assert post(client, bob, "withdraw", money(1)).status_code == 200
    everything = client.get("/api/alerts").json()
    assert [a["accountId"] for a in everything] == [bob, bob, alice]  # newest first
    only_bob = client.get("/api/alerts", params={"customerId": bob_id}).json()
    assert [a["customerId"] for a in only_bob] == [bob_id, bob_id]
    assert only_bob[0]["createdAt"] >= only_bob[1]["createdAt"]
    assert client.get("/api/alerts", params={"limit": 1}).json() == everything[:1]
    assert client.get("/api/alerts", params={"customerId": str(ObjectId())}).json() == []


@pytest.mark.parametrize("params", [{"customerId": "abc"}, {"limit": 0}, {"limit": 201}])
def test_alerts_reject_bad_parameters(client, params):
    assert client.get("/api/alerts", params=params).status_code == 422
