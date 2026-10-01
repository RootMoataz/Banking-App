"""Premium accounts: accounts whose own balance is at or above a threshold, highest balance first."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_search_alerts import account, customer, money

URL = "/api/accounts/premium"


def premium(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def balances(found):
    return [a["balance"] for a in found]


def test_default_threshold_is_the_premium_setting(client, settings):
    owner = customer(client)
    cents = settings.premium_cents
    ids = {c: account(client, owner, c) for c in (0, cents - 1, cents, cents * 2)}
    found = premium(client)
    assert balances(found) == [money(cents * 2), money(cents)]  # inclusive, highest first
    assert [a["accountId"] for a in found] == [ids[cents * 2], ids[cents]]
    assert found[0] == client.get(f"/api/accounts/{ids[cents * 2]}").json()  # the usual Account shape


def test_default_follows_configuration_not_a_constant(client, settings):
    owner = customer(client)
    for cents in (5_000, 60_000):
        account(client, owner, cents)
    with TestClient(create_app(replace(settings, premium_cents=50_000))) as configured:
        assert balances(premium(configured)) == ["600.00"]
    assert premium(client) == []  # the pinned 10000.00 default


def test_threshold_and_limit(client):
    owner = customer(client)
    for cents in (100, 2_500, 2_500, 99):
        account(client, owner, cents)
    account(client, customer(client, "Other", "other@example.com"), 5_000)  # every customer's accounts count
    assert balances(premium(client, threshold="1.00")) == ["50.00", "25.00", "25.00", "1.00"]
    assert balances(premium(client, threshold="0")) == ["50.00", "25.00", "25.00", "1.00", "0.99"]
    assert balances(premium(client, threshold="25.00", limit=2)) == ["50.00", "25.00"]
    assert premium(client, threshold="99999999.99") == []
    tied = premium(client, threshold="25.00")[1:]
    assert tied[0]["accountId"] < tied[1]["accountId"]  # equal balances: oldest account first


@pytest.mark.parametrize("params", [{"threshold": "-1"}, {"threshold": "1.001"}, {"threshold": "abc"},
                                    {"threshold": "NaN"}, {"threshold": "Infinity"}, {"threshold": "100000000"},
                                    {"limit": 0}, {"limit": 201}, {"limit": "x"}])
def test_bad_parameters_are_422(client, params):
    assert client.get(URL, params=params).status_code == 422


def test_route_is_not_captured_by_the_id_route(client):
    assert client.get(URL).status_code == 200
    spec = client.get("/openapi.json").json()["paths"]
    assert {p["name"] for p in spec[URL]["get"]["parameters"]} == {"threshold", "limit"}


def test_query_uses_the_balance_index(db):
    plan = db.accounts.find({"balanceCents": {"$gte": 1}}).sort([("balanceCents", -1), ("_id", 1)]).explain()
    assert "balance_desc" in str(plan["queryPlanner"]["winningPlan"])
