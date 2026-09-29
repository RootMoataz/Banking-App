"""Check the banking flows through HTTP, including requests that should fail."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def account(client):
    user = client.post("/api/users", json={"name": "Moataz Hikal", "email": "moataz@example.com"})
    assert user.status_code == 201
    response = client.post("/api/accounts", json={"userId": user.json()["userId"], "accountType": "SAVINGS"})
    assert response.status_code == 201
    return response.json()["accountId"]


def test_full_flow(client):
    id = account(client)
    url = f"/api/accounts/{id}"
    assert client.get(url).json()["balance"] == "0.00"
    assert client.get(url).json()["userName"] == "Moataz Hikal"
    assert client.get(url + "/transactions").json() == []
    assert client.post(url + "/deposit", json={"amount": 500}).json()["balance"] == "500.00"
    assert client.post(url + "/withdraw", json={"amount": 200}).json()["balance"] == "300.00"
    txns = client.get(url + "/transactions").json()
    assert [(t["type"], t["amount"]) for t in txns] == [("DEPOSIT", "500.00"), ("WITHDRAW", "200.00")]
    assert len({t["txnId"] for t in txns}) == 2
    assert all(t["accountId"] == id and t["date"].endswith("Z") for t in txns)
    assert client.post(url + "/withdraw", json={"amount": 300}).json()["balance"] == "0.00"


@pytest.mark.parametrize("amount", [0, -1, "0.001", "NaN", "Infinity", "-Infinity", "abc", True, None, 100000000])
@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_invalid_amounts_do_not_change_state(client, amount, operation):
    id = account(client)
    response = client.post(f"/api/accounts/{id}/{operation}", json={"amount": amount})
    assert response.status_code == 422
    assert client.get(f"/api/accounts/{id}").json()["balance"] == "0.00"
    assert client.get(f"/api/accounts/{id}/transactions").json() == []


def test_overdraft_and_precision(client):
    id = account(client)
    url = f"/api/accounts/{id}"
    for amount in ["0.10", "0.20"]:
        assert client.post(url + "/deposit", json={"amount": amount}).status_code == 200
    assert client.get(url).json()["balance"] == "0.30"
    assert client.post(url + "/withdraw", json={"amount": "0.31"}).status_code == 400
    assert client.get(url).json()["balance"] == "0.30"
    assert len(client.get(url + "/transactions").json()) == 2


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/accounts/99", None),
    ("GET", "/api/accounts/99/transactions", None),
    ("POST", "/api/accounts/99/deposit", {"amount": 1}),
    ("POST", "/api/accounts/99/withdraw", {"amount": 1}),
    ("POST", "/api/accounts", {"userId": 99, "accountType": "SAVINGS"}),
])
def test_missing_resources(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"userId": 0, "accountType": "SAVINGS"},
    {"userId": True, "accountType": "SAVINGS"}, {"userId": 1, "accountType": " "},
    {"userId": 1, "accountType": "x" * 51}, {"userId": 1, "accountType": "SAVINGS", "balance": 500}])
def test_account_validation(client, payload):
    assert client.post("/api/accounts", json=payload).status_code == 422


def test_user_validation_and_duplicate_email(client):
    for body in [{"name": " ", "email": "moataz@example.com"}, {"name": "Moataz Hikal", "email": "bad"}]:
        assert client.post("/api/users", json=body).status_code == 422
    account(client)
    assert client.post("/api/users", json={"name": "Moataz Hikal", "email": "MOATAZ@example.com"}).status_code == 409


def test_balance_limit(client):
    id = account(client)
    url = f"/api/accounts/{id}"
    assert client.post(url + "/deposit", json={"amount": "99999999.99"}).status_code == 200
    assert client.post(url + "/deposit", json={"amount": "0.01"}).status_code == 400
    assert client.get(url).json()["balance"] == "99999999.99"
    assert len(client.get(url + "/transactions").json()) == 1


def test_account_isolation_and_restart(client):
    id = account(client)
    second = client.post("/api/accounts", json={"userId": 1, "accountType": "CURRENT"}).json()["accountId"]
    client.post(f"/api/accounts/{id}/deposit", json={"amount": 10})
    assert client.get(f"/api/accounts/{second}").json()["balance"] == "0.00"
    assert client.get(f"/api/accounts/{second}/transactions").json() == []
    with TestClient(create_app()) as fresh:
        assert fresh.get(f"/api/accounts/{id}").status_code == 404


def test_concurrent_withdrawals_cannot_overdraw(client):
    # Twenty requests compete for ten units; only ten should be able to withdraw.
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": 10})
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: client.post(url + "/withdraw", json={"amount": 1}).status_code, range(20)))
    assert codes.count(200) == 10
    assert codes.count(400) == 10
    assert client.get(url).json()["balance"] == "0.00"
    txns = client.get(url + "/transactions").json()
    assert len(txns) == len({t["txnId"] for t in txns}) == 11


def test_docs_and_malformed_requests(client):
    assert client.get("/docs").status_code == 200
    assert "/api/customers/{id}" in client.get("/openapi.json").json()["paths"]
    assert client.get("/api/accounts/0").status_code == 422
    assert client.get("/api/accounts/abc").status_code == 422
    assert client.post("/api/accounts", content="{", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/accounts/1/deposit", json={}).status_code == 422
