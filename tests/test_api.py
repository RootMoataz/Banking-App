"""Check the banking flows through HTTP, including requests that should fail."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from bson import ObjectId

from app import repositories
from app.repositories import AccountRepository, TransactionRepository

MISSING = str(ObjectId())  # well-formed, but never stored


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
    ("GET", f"/api/accounts/{MISSING}", None),
    ("GET", f"/api/accounts/{MISSING}/transactions", None),
    ("POST", f"/api/accounts/{MISSING}/deposit", {"amount": 1}),
    ("POST", f"/api/accounts/{MISSING}/withdraw", {"amount": 1}),
    ("POST", "/api/accounts", {"userId": MISSING, "accountType": "SAVINGS"}),
])
def test_missing_resources(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"userId": 0, "accountType": "SAVINGS"},
    {"userId": True, "accountType": "SAVINGS"}, {"userId": MISSING, "accountType": " "},
    {"userId": MISSING, "accountType": "x" * 51}, {"userId": MISSING, "accountType": "SAVINGS", "balance": 500}])
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


def test_account_isolation(client):
    id = account(client)
    owner = client.get(f"/api/accounts/{id}").json()["userId"]
    second = client.post("/api/accounts", json={"userId": owner, "accountType": "CURRENT"}).json()["accountId"]
    client.post(f"/api/accounts/{id}/deposit", json={"amount": 10})
    assert client.get(f"/api/accounts/{second}").json()["balance"] == "0.00"
    assert client.get(f"/api/accounts/{second}/transactions").json() == []


def stored_history(db, id):
    """The account's records in the order the history API uses."""
    return list(db.transactions.find({"accountId": ObjectId(id)}).sort([("createdAt", 1), ("_id", 1)]))


def test_concurrent_withdrawals_never_overdraw(client, db):
    # Twenty requests compete for ten withdrawals' worth of money; only ten can succeed.
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": "100.00"})
    with ThreadPoolExecutor(max_workers=20) as pool:
        codes = list(pool.map(lambda _: client.post(url + "/withdraw", json={"amount": "10.00"}).status_code, range(20)))
    assert codes.count(200) == 10
    assert codes.count(400) == 10
    assert client.get(url).json()["balance"] == "0.00"
    txns = client.get(url + "/transactions").json()
    assert len(txns) == len({t["txnId"] for t in txns}) == 11
    # History order agrees with the balance each change produced.
    assert [t["balanceAfterCents"] for t in stored_history(db, id)] == list(range(10000, -1, -1000))


def test_concurrent_deposits_respect_max(client, db):
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": "99999949.99"})  # room for exactly five deposits of 10.00
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: client.post(url + "/deposit", json={"amount": "10.00"}), range(20)))
    assert [r.status_code for r in responses].count(200) == 5
    assert {r.json()["detail"] for r in responses if r.status_code != 200} == {"Balance would exceed 99999999.99"}
    assert client.get(url).json()["balance"] == "99999999.99"
    assert [t["balanceAfterCents"] for t in stored_history(db, id)] == list(range(9999994999, 10000000000, 1000))


def test_history_has_customer_and_account_ids(client, db):
    id = account(client)
    owner = client.get(f"/api/accounts/{id}").json()["userId"]
    client.post(f"/api/accounts/{id}/deposit", json={"amount": "5.00"})
    client.post(f"/api/accounts/{id}/withdraw", json={"amount": "2.00"})
    records = stored_history(db, id)
    assert [(r["type"], r["amountCents"], r["balanceAfterCents"]) for r in records] == [
        ("DEPOSIT", 500, 500), ("WITHDRAW", 200, 300)]
    assert all(r["accountId"] == ObjectId(id) and r["customerId"] == ObjectId(owner) for r in records)
    assert [t["txnId"] for t in client.get(f"/api/accounts/{id}/transactions").json()] == [str(r["_id"]) for r in records]


def test_history_order_survives_clock_step_back(client, db, monkeypatch):
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": "5.00"})
    earlier = repositories._now() - timedelta(hours=1)
    monkeypatch.setattr(repositories, "_now", lambda: earlier)
    client.post(url + "/withdraw", json={"amount": "2.00"})
    assert [t["type"] for t in client.get(url + "/transactions").json()] == ["DEPOSIT", "WITHDRAW"]
    assert [r["balanceAfterCents"] for r in stored_history(db, id)] == [500, 300]


def test_insufficient_funds_and_limit_messages_differ(client):
    id = account(client)
    url = f"/api/accounts/{id}"
    withdrawn = client.post(url + "/withdraw", json={"amount": "0.01"})
    assert (withdrawn.status_code, withdrawn.json()) == (400, {"detail": "Insufficient funds"})
    client.post(url + "/deposit", json={"amount": "99999999.99"})
    deposited = client.post(url + "/deposit", json={"amount": "0.01"})
    assert (deposited.status_code, deposited.json()) == (400, {"detail": "Balance would exceed 99999999.99"})


def test_failed_insert_rolls_back_balance(client, db, monkeypatch):
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": "5.00"})

    def fail(*args, **kwargs):
        raise RuntimeError("history write failed")
    monkeypatch.setattr(TransactionRepository, "insert", fail)
    for operation in ["deposit", "withdraw"]:
        with pytest.raises(RuntimeError):
            client.post(f"{url}/{operation}", json={"amount": "1.00"})
        assert client.get(url).json()["balance"] == "5.00"  # checked after each, so the two can't cancel out
        assert len(stored_history(db, id)) == 1


def test_delete_account_keeps_transactions(client, db):
    id = account(client)
    url = f"/api/accounts/{id}"
    client.post(url + "/deposit", json={"amount": "3.00"})
    client.post(url + "/withdraw", json={"amount": "3.00"})
    assert client.delete(url).status_code == 204
    assert [(r["type"], r["balanceAfterCents"]) for r in stored_history(db, id)] == [("DEPOSIT", 300), ("WITHDRAW", 0)]
    assert client.get(url + "/transactions").status_code == 404


def _hold(monkeypatch, cls, name):
    """Hold cls.name open inside its transaction. Returns an Event set at that moment, so a competing request starts
    strictly after the held transaction's uncommitted writes (no sleep-based guessing)."""
    original, entered = getattr(cls, name), threading.Event()

    def slow(self, *args, **kwargs):
        entered.set()
        time.sleep(0.5)  # the competitor now conflicts with our uncommitted writes and must retry after we commit
        return original(self, *args, **kwargs)
    monkeypatch.setattr(cls, name, slow)
    return entered


@pytest.mark.parametrize("first", ["deposit", "delete"])
def test_delete_races_deposit(client, db, monkeypatch, first):
    id = account(client)
    url = f"/api/accounts/{id}"
    send = {"deposit": lambda: client.post(url + "/deposit", json={"amount": "1.00"}), "delete": lambda: client.delete(url)}
    second = "delete" if first == "deposit" else "deposit"
    if first == "deposit":
        entered = _hold(monkeypatch, TransactionRepository, "insert")  # after the balance change, before the commit
    else:
        entered = _hold(monkeypatch, AccountRepository, "delete")
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(send[first])
        assert entered.wait(timeout=10)
        other = pool.submit(send[second])
        codes = {first: held.result().status_code, second: other.result().status_code}
    if first == "deposit":
        # The deposit commits first; the delete retries, then sees money in the account.
        assert codes == {"deposit": 200, "delete": 409}
        assert client.get(url).json()["balance"] == "1.00"
        assert len(stored_history(db, id)) == 1
    else:
        # The delete commits first; the deposit retries, then finds no account.
        assert codes == {"delete": 204, "deposit": 404}
        assert db.accounts.count_documents({"_id": ObjectId(id)}) == 0
        assert stored_history(db, id) == []  # never a balance change on a deleted account


def test_docs_and_malformed_requests(client):
    assert client.get("/docs").status_code == 200
    assert "/api/customers/{id}" in client.get("/openapi.json").json()["paths"]
    assert client.get("/api/accounts/0").status_code == 422
    assert client.get("/api/accounts/abc").status_code == 422
    assert client.post("/api/accounts", content="{", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post(f"/api/accounts/{MISSING}/deposit", json={}).status_code == 422
