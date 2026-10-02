"""Check customer and account edits, ownership, deletion order, and concurrent changes."""

import os
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.config import ROOT
from app.main import create_app
from app.repositories import AccountRepository, CustomerRepository
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from test_api import _hold

MISSING = str(ObjectId())  # well-formed, but never stored


def customer(client, email="moataz@example.com", name="Moataz Hikal"):
    response = client.post("/api/customers", json={"name": name, "email": email})
    assert response.status_code == 201
    return response.json()


def account(client, customer_id):
    response = client.post("/api/accounts", json={"customerId": customer_id, "accountType": "SAVINGS"})
    assert response.status_code == 201
    return response.json()


def test_customer_crud(client):
    assert client.get("/api/customers").json() == []
    original = customer(client, name="Moataz Hikal".upper())
    assert re.fullmatch(r"[0-9a-f]{24}", original["customerId"])
    url = f"/api/customers/{original['customerId']}"
    assert client.get(url).json() == original
    assert client.get("/api/customers").json() == [original]
    edited = client.put(url, json={"name": "Moataz Hikal", "email": "moataz.updated@example.com"})
    assert edited.status_code == 200
    assert edited.json()["name"] == "Moataz Hikal"
    assert edited.json()["createdAt"] == original["createdAt"]
    assert edited.json()["customerId"] == original["customerId"]
    assert client.get(url).json() == edited.json()
    deleted = client.delete(url)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(url).status_code == 404
    assert client.get("/api/customers").json() == []
    assert customer(client, "moataz.updated@example.com")["customerId"] != original["customerId"]


def test_one_customer_many_accounts_and_name_edit(client):
    first = customer(client, name="Moataz Hikal".upper())["customerId"]
    second = customer(client, "second@example.com")["customerId"]
    accounts = [account(client, first), account(client, first)]
    assert all(re.fullmatch(r"[0-9a-f]{24}", a["accountId"]) for a in accounts)
    assert all(a["customerId"] == first and a["userId"] == first for a in accounts)
    assert client.get(f"/api/customers/{first}/accounts").json() == accounts
    assert client.get(f"/api/customers/{second}/accounts").json() == []
    assert client.get("/api/accounts").json() == accounts
    client.put(f"/api/customers/{first}", json={"name": "Moataz Hikal", "email": "moataz@example.com"})
    assert all(a["userName"] == "Moataz Hikal" for a in client.get(f"/api/customers/{first}/accounts").json())


def test_delete_customer_cascades_to_accounts_and_keeps_history(client, db):
    owner = customer(client)["customerId"]
    kept_owner = customer(client, "second@example.com")["customerId"]
    funded, empty, kept = account(client, owner)["accountId"], account(client, owner)["accountId"], account(
        client, kept_owner)["accountId"]
    client.post(f"/api/accounts/{funded}/deposit", json={"amount": "150.00"})
    client.post(f"/api/accounts/{funded}/withdraw", json={"amount": "60.00"})  # enters LOW: one stored alert
    client.post(f"/api/accounts/{kept}/deposit", json={"amount": "5.00"})
    assert client.get(f"/api/customers/{owner}/notifications").json() != []

    deleted = client.delete(f"/api/customers/{owner}")  # a non-zero balance does not block the delete
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"/api/customers/{owner}").status_code == 404
    for id in (funded, empty):
        assert client.get(f"/api/accounts/{id}").status_code == 404
    assert [a["accountId"] for a in client.get("/api/accounts").json()] == [kept]
    assert client.get(f"/api/accounts/{kept}").json()["balance"] == "5.00"
    # Transactions and notifications stay for audit.
    audit = client.get("/api/audit/transactions", params={"customerId": owner}).json()["items"]
    assert [(t["accountId"], t["type"]) for t in audit] == [(funded, "DEPOSIT"), (funded, "WITHDRAW"),
                                                           (funded, "ACCOUNT_CLOSED")]
    assert db.notifications.count_documents({"customerId": ObjectId(owner)}) == 1
    assert client.delete(f"/api/customers/{owner}").status_code == 404


def test_delete_customer_records_closing_transaction_for_funded_account_only(client, db):
    owner = customer(client)["customerId"]
    funded, empty = account(client, owner)["accountId"], account(client, owner)["accountId"]
    client.post(f"/api/accounts/{funded}/deposit", json={"amount": "100.00"})
    assert client.delete(f"/api/customers/{owner}").status_code == 204
    assert client.get(f"/api/accounts/{funded}").status_code == 404
    items = client.get("/api/audit/transactions", params={"customerId": owner}).json()["items"]
    assert [(t["accountId"], t["type"]) for t in items] == [(funded, "DEPOSIT"), (funded, "ACCOUNT_CLOSED")]
    closed = items[1]
    assert (closed["amount"], closed["balanceAfter"], closed["customerId"]) == ("100.00", "0.00", owner)
    assert closed["transferId"] is None and closed["fromAccountId"] is None and closed["toAccountId"] is None
    assert closed["date"] > items[0]["date"]
    assert db.transactions.count_documents({"accountId": ObjectId(empty)}) == 0


def test_delete_customer_with_only_empty_accounts_records_nothing(client, db):
    owner = customer(client)["customerId"]
    account(client, owner)
    assert client.delete(f"/api/customers/{owner}").status_code == 204
    assert db.transactions.count_documents({"customerId": ObjectId(owner)}) == 0


def test_failed_cascade_deletes_nothing(client, db, monkeypatch):
    owner = customer(client)["customerId"]
    id = account(client, owner)["accountId"]
    client.post(f"/api/accounts/{id}/deposit", json={"amount": "10.00"})

    def fail(*args, **kwargs):
        raise RuntimeError("customer delete failed")
    monkeypatch.setattr(CustomerRepository, "delete", fail)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/customers/{owner}")
    assert client.get(f"/api/accounts/{id}").status_code == 200  # the account delete rolled back too
    assert db.transactions.count_documents({"accountId": ObjectId(id), "type": "ACCOUNT_CLOSED"}) == 0


def test_account_crud_and_deletion_rules(client):
    id = customer(client)["customerId"]
    original = account(client, id)
    url = f"/api/accounts/{original['accountId']}"
    edited = client.put(url, json={"accountType": "CURRENT"})
    assert edited.status_code == 200
    assert edited.json()["accountType"] == "CURRENT"
    for key in ["customerId", "userId", "accountId", "createdAt", "balance"]:
        assert edited.json()[key] == original[key]
    client.post(url + "/deposit", json={"amount": "1.23"})
    assert client.delete(url).status_code == 409
    assert client.get(url).json()["balance"] == "1.23"
    client.post(url + "/withdraw", json={"amount": "1.23"})
    deleted = client.delete(url)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(url).status_code == 404
    assert client.get(url + "/transactions").status_code == 404
    assert client.get(f"/api/customers/{id}/accounts").json() == []
    assert client.delete(f"/api/customers/{id}").status_code == 204


def test_deleted_ids_never_overwrite_survivors(client):
    # Deleting an early record must not make the next ID collide with a later one.
    customers = [customer(client, f"person{i}@example.com") for i in range(3)]
    client.delete(f"/api/customers/{customers[0]['customerId']}")
    assert customer(client, "new@example.com")["customerId"] not in {c["customerId"] for c in customers}
    owner = customers[2]["customerId"]
    assert client.get(f"/api/customers/{owner}").json() == customers[2]
    accounts = [account(client, owner) for _ in range(3)]
    client.delete(f"/api/accounts/{accounts[0]['accountId']}")
    assert account(client, owner)["accountId"] not in {a["accountId"] for a in accounts}
    assert client.get(f"/api/accounts/{accounts[2]['accountId']}").json() == accounts[2]


def test_edit_email_uniqueness_and_index_cleanup(client):
    first = customer(client)["customerId"]
    second = customer(client, "second@example.com")["customerId"]
    response = client.put(f"/api/customers/{second}", json={"name": "Moataz Hikal", "email": "MOATAZ@example.com"})
    assert response.status_code == 409
    assert client.get(f"/api/customers/{second}").json()["email"] == "second@example.com"
    assert client.put(f"/api/customers/{first}", json={"name": "Moataz Hikal", "email": "MOATAZ@example.com"}).status_code == 200
    assert client.put(f"/api/customers/{first}", json={"name": "Moataz Hikal", "email": "new@example.com"}).status_code == 200
    assert customer(client)["customerId"] not in {first, second}


@pytest.mark.parametrize("method,path,body", [
    ("GET", f"/api/customers/{MISSING}", None),
    ("GET", f"/api/customers/{MISSING}/accounts", None),
    ("PUT", f"/api/customers/{MISSING}", {"name": "Moataz Hikal", "email": "none@example.com"}),
    ("DELETE", f"/api/customers/{MISSING}", None),
    ("PUT", f"/api/accounts/{MISSING}", {"accountType": "CURRENT"}),
    ("DELETE", f"/api/accounts/{MISSING}", None),
])
def test_crud_missing_resources(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 404


@pytest.mark.parametrize("body", [{}, {"name": "Moataz Hikal"}, {"name": " ", "email": "moataz@example.com"},
                                      {"name": "Moataz Hikal", "email": "invalid"},
                                      {"name": "Moataz Hikal", "email": "moataz@example.com", "customerId": MISSING}])
def test_customer_edit_validation(client, body):
    original = customer(client)
    url = f"/api/customers/{original['customerId']}"
    assert client.put(url, json=body).status_code == 422
    assert client.get(url).json() == original


@pytest.mark.parametrize("body", [{}, {"accountType": " "}, {"accountType": "x" * 51},
    {"accountType": "CURRENT", "balance": 999}, {"accountType": "CURRENT", "customerId": MISSING}])
def test_account_edit_rejects_invalid_fields(client, body):
    original = account(client, customer(client)["customerId"])
    url = f"/api/accounts/{original['accountId']}"
    assert client.put(url, json=body).status_code == 422
    assert client.get(url).json() == original


def test_legacy_users_share_customer_records(client):
    user = client.post("/api/users", json={"name": "Moataz Hikal", "email": "legacy@example.com"}).json()
    assert client.get(f"/api/customers/{user['userId']}").json()["name"] == "Moataz Hikal"
    assert client.post("/api/customers", json={"name": "Moataz Hikal", "email": "legacy@example.com"}).status_code == 409


def test_swagger_documents_crud_and_customer_ownership(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/api/customers"]) == {"get", "post"}
    assert set(paths["/api/customers/{id}"]) == {"get", "put", "delete"}
    assert set(paths["/api/accounts"]) == {"get", "post"}
    assert set(paths["/api/accounts/{id}"]) == {"get", "put", "delete"}
    assert "204" in paths["/api/customers/{id}"]["delete"]["responses"]
    assert "409" not in paths["/api/customers/{id}"]["delete"]["responses"]  # accounts are deleted with the customer
    assert "409" in paths["/api/accounts/{id}"]["delete"]["responses"]
    assert "customerId" in schema["components"]["schemas"]["AccountCreate"]["properties"]
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize("bad", ["1", "abc", "g" * 24, "a" * 23, "a" * 25])
def test_malformed_id_is_422(client, bad):
    assert client.get(f"/api/customers/{bad}").status_code == 422
    assert client.get(f"/api/customers/{bad}/accounts").status_code == 422
    assert client.put(f"/api/customers/{bad}", json={"name": "Moataz Hikal", "email": "x@example.com"}).status_code == 422
    assert client.delete(f"/api/customers/{bad}").status_code == 422
    assert client.get(f"/api/accounts/{bad}").status_code == 422
    assert client.put(f"/api/accounts/{bad}", json={"accountType": "CURRENT"}).status_code == 422
    assert client.delete(f"/api/accounts/{bad}").status_code == 422
    assert client.post("/api/accounts", json={"customerId": bad, "accountType": "SAVINGS"}).status_code == 422
    assert client.post(f"/api/accounts/{bad}/deposit", json={"amount": "1.00"}).status_code == 422
    assert client.post(f"/api/accounts/{bad}/withdraw", json={"amount": "1.00"}).status_code == 422
    assert client.get(f"/api/accounts/{bad}/transactions").status_code == 422


def test_valid_missing_id_is_404(client):
    owner = customer(client)["customerId"]
    assert client.get(f"/api/customers/{owner.upper()}").status_code == 200  # hex case doesn't matter
    assert client.get(f"/api/customers/{MISSING}").status_code == 404
    assert client.get(f"/api/accounts/{MISSING}").status_code == 404
    assert client.post("/api/accounts", json={"customerId": MISSING, "accountType": "SAVINGS"}).status_code == 404


def test_duplicate_email_race_returns_409(client):
    emails = ["race@example.com", "RACE@example.com", "race@example.com", "Race@Example.com"]
    with ThreadPoolExecutor(max_workers=len(emails)) as pool:
        codes = list(pool.map(lambda email: client.post(
            "/api/customers", json={"name": "Moataz Hikal", "email": email}).status_code, emails))
    assert sorted(codes) == [201, 409, 409, 409]
    assert len(client.get("/api/customers").json()) == 1


def _log_in_as_bootstrapped_admin(test_client):
    response = test_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    test_client.headers["Authorization"] = f"Bearer {response.json()['token']}"


def test_data_persists_across_app_instances(settings):
    with_admin = replace(settings, admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD)
    with TestClient(create_app(with_admin)) as first:
        _log_in_as_bootstrapped_admin(first)
        created = customer(first)
    with TestClient(create_app(with_admin)) as second:
        _log_in_as_bootstrapped_admin(second)
        assert second.get(f"/api/customers/{created['customerId']}").json() == created


def _slow_account_insert(monkeypatch):
    """Hold account creation open once it has touched the customer. Returns an Event that is set at that moment, so a
    competing request starts strictly after creation's uncommitted customer write (no sleep-based guessing)."""
    insert, entered = AccountRepository.insert, threading.Event()

    def slow(self, *args, **kwargs):
        entered.set()
        time.sleep(0.5)  # the competitor now conflicts with our uncommitted customer write and must retry after we commit
        return insert(self, *args, **kwargs)
    monkeypatch.setattr(AccountRepository, "insert", slow)
    return entered


def test_delete_races_account_creation(client, db, monkeypatch):
    owner = customer(client)["customerId"]
    entered = _slow_account_insert(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = pool.submit(client.post, "/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
        assert entered.wait(timeout=10)
        deleted = pool.submit(client.delete, f"/api/customers/{owner}")
        codes = (created.result().status_code, deleted.result().status_code)
    assert codes == (201, 204)  # the delete conflicts, retries after the commit, then deletes the new account too
    assert db.customers.count_documents({"_id": ObjectId(owner)}) == 0
    assert db.accounts.count_documents({"customerId": ObjectId(owner)}) == 0  # never an orphan account


def test_account_creation_after_customer_delete_is_404(client, db, monkeypatch):
    owner = customer(client)["customerId"]
    account(client, owner)
    entered = _hold(monkeypatch, CustomerRepository, "delete")
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(client.delete, f"/api/customers/{owner}")
        assert entered.wait(timeout=10)
        created = pool.submit(client.post, "/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
        codes = (deleted.result().status_code, created.result().status_code)
    assert codes == (204, 404)  # creation conflicts, retries after the delete commits, then finds no customer
    assert db.accounts.count_documents({"customerId": ObjectId(owner)}) == 0


def test_rename_races_account_creation(client, monkeypatch):
    owner = customer(client)["customerId"]
    entered = _slow_account_insert(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = pool.submit(client.post, "/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
        assert entered.wait(timeout=10)
        renamed = pool.submit(client.put, f"/api/customers/{owner}",
                              json={"name": "Renamed Owner", "email": "moataz@example.com"})
        assert (created.result().status_code, renamed.result().status_code) == (201, 200)
    assert [a["userName"] for a in client.get(f"/api/customers/{owner}/accounts").json()] == ["Renamed Owner"]


def test_app_creates_indexes_on_a_fresh_database(settings, db):
    """Email uniqueness must not depend on someone having run scripts/setup_indexes.py first."""
    fresh = replace(settings, mongodb_db=f"paper_maker_test_{uuid.uuid4().hex[:8]}",
                    admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD)
    try:
        with TestClient(create_app(fresh)) as fresh_client:
            _log_in_as_bootstrapped_admin(fresh_client)
            body = {"name": "Moataz Hikal", "email": "fresh@example.com"}
            assert fresh_client.post("/api/customers", json=body).status_code == 201
            assert fresh_client.post("/api/customers", json=body).status_code == 409
    finally:
        assert fresh.mongodb_db.startswith("paper_maker_test_")
        db.client.drop_database(fresh.mongodb_db)


def test_importing_main_opens_no_database_connection():
    # uvicorn imports app.main before serving, so the import itself must not read settings or connect.
    code = ("import pymongo, app.config\n"
            "def fail(*args, **kwargs):\n"
            "    raise AssertionError('app.main touched the database at import')\n"
            "pymongo.MongoClient = fail\n"
            "app.config.load_settings = fail\n"
            "import app.main\n"
            "assert app.main.app.title\n")
    env = {key: value for key, value in os.environ.items() if key != "MONGODB_URI"}
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
