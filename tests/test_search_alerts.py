"""Customer search by name, email and total balance, and the balance categories. Category-change notifications are
checked in test_notifications.py."""

from decimal import Decimal

import pytest

from app.config import Settings
from app.money import from_cents, to_cents
from app.services import category


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


DEFAULTS = Settings("unused", "unused")  # the approved example thresholds: 100.00 and 10000.00


@pytest.mark.parametrize("total, expected", [("0.00", "LOW"), ("99.99", "LOW"), ("100.00", "STANDARD"),
                                             ("9999.99", "STANDARD"), ("10000.00", "PREMIUM")])
def test_category_boundaries(total, expected):
    assert category(to_cents(Decimal(total)), DEFAULTS) == expected


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
