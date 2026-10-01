"""Idempotency-Key on deposits and withdrawals: a retried request replays its first result and moves no money."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from bson import ObjectId

from app.repositories import TransactionRepository

REUSED = "Idempotency-Key was already used for a different request"


def account(client, deposit=None):
    customer = client.post("/api/customers", json={"name": "Moataz Hikal", "email": "moataz@example.com"})
    assert customer.status_code == 201
    response = client.post("/api/accounts", json={"customerId": customer.json()["customerId"], "accountType": "SAVINGS"})
    assert response.status_code == 201
    id = response.json()["accountId"]
    if deposit is not None:
        assert post(client, id, "deposit", deposit).status_code == 200
    return id


def post(client, id, operation, amount, key=None):
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(f"/api/accounts/{id}/{operation}", json={"amount": amount}, headers=headers)


def history(db, id):
    return list(db.transactions.find({"accountId": ObjectId(id)}).sort([("createdAt", 1), ("_id", 1)]))


def balance(client, id):
    return client.get(f"/api/accounts/{id}").json()["balance"]


def test_same_key_replays_same_result(client, db):
    id = account(client)
    first = post(client, id, "deposit", "25.00", "key-1")
    second = post(client, id, "deposit", "25.00", "key-1")
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["balance"] == "25.00"
    assert balance(client, id) == "25.00"
    assert [r["idempotencyKey"] for r in history(db, id)] == ["key-1"]


def test_same_key_different_amount_is_409(client, db):
    id = account(client)
    assert post(client, id, "deposit", "25.00", "key-1").status_code == 200
    reused = post(client, id, "deposit", "26.00", "key-1")
    assert (reused.status_code, reused.json()) == (409, {"detail": REUSED})
    assert balance(client, id) == "25.00"
    assert len(history(db, id)) == 1


def test_same_key_other_operation_type_is_409(client, db):
    id = account(client)
    assert post(client, id, "deposit", "25.00", "key-1").status_code == 200
    reused = post(client, id, "withdraw", "25.00", "key-1")
    assert (reused.status_code, reused.json()) == (409, {"detail": REUSED})
    assert balance(client, id) == "25.00"
    assert len(history(db, id)) == 1


def test_same_key_on_another_account_is_independent(client, db):
    id = account(client)
    owner = client.get(f"/api/accounts/{id}").json()["customerId"]
    other = client.post("/api/accounts", json={"customerId": owner, "accountType": "CURRENT"}).json()["accountId"]
    assert post(client, id, "deposit", "25.00", "key-1").json()["balance"] == "25.00"
    assert post(client, other, "deposit", "5.00", "key-1").json()["balance"] == "5.00"
    assert len(history(db, id)) == len(history(db, other)) == 1


def test_replay_after_later_balance_change_returns_stored_balance(client, db):
    id = account(client)
    first = post(client, id, "deposit", "25.00", "key-1")
    assert post(client, id, "deposit", "10.00").json()["balance"] == "35.00"
    replay = post(client, id, "deposit", "25.00", "key-1")
    assert replay.status_code == 200
    assert replay.json() == first.json()  # the balance this deposit produced, not the live one
    assert balance(client, id) == "35.00"
    assert len(history(db, id)) == 2


def test_replay_after_account_deleted_returns_transaction_record(client, db):
    id = account(client)
    owner = client.get(f"/api/accounts/{id}").json()["customerId"]
    assert post(client, id, "deposit", "25.00", "key-1").status_code == 200
    assert post(client, id, "withdraw", "25.00", "key-2").status_code == 200
    assert client.delete(f"/api/accounts/{id}").status_code == 204
    deposit, withdrawal = history(db, id)
    replay = post(client, id, "deposit", "25.00", "key-1")
    assert replay.status_code == 200
    body = replay.json()
    assert datetime.fromisoformat(body.pop("date")) == deposit["createdAt"]
    assert body == {"txnId": str(deposit["_id"]), "accountId": id, "customerId": owner, "type": "DEPOSIT",
                    "amount": "25.00", "balanceAfter": "25.00", "transferId": None, "fromAccountId": None,
                    "toAccountId": None}
    assert post(client, id, "withdraw", "25.00", "key-2").json()["txnId"] == str(withdrawal["_id"])
    assert post(client, id, "withdraw", "25.00", "key-1").status_code == 409
    assert post(client, id, "deposit", "25.00", "key-3").status_code == 404  # a new key still needs the account
    assert len(history(db, id)) == 2


def test_deleted_account_replay_http_shape(client, db):
    id = account(client)
    assert post(client, id, "deposit", "1.00", "key-1").status_code == 200
    assert post(client, id, "withdraw", "1.00").status_code == 200
    assert client.delete(f"/api/accounts/{id}").status_code == 204
    replay = post(client, id, "deposit", "1.00", "key-1")
    assert replay.status_code == 200
    assert set(replay.json()) == {"txnId", "accountId", "customerId", "type", "amount", "balanceAfter", "date",
                                  "transferId", "fromAccountId", "toAccountId"}
    spec = client.get("/openapi.json").json()
    for operation in ["deposit", "withdraw"]:
        route = spec["paths"]["/api/accounts/{id}/" + operation]["post"]
        schema = route["responses"]["200"]["content"]["application/json"]["schema"]
        assert {s["$ref"] for s in schema["anyOf"]} == {"#/components/schemas/Account", "#/components/schemas/Transaction"}
        assert "Idempotency-Key" in {p["name"] for p in route["parameters"] if p["in"] == "header"}


def test_two_keyless_deposits_both_succeed(client, db):
    id = account(client)
    assert post(client, id, "deposit", "10.00").json()["balance"] == "10.00"
    assert post(client, id, "deposit", "10.00").json()["balance"] == "20.00"
    records = history(db, id)
    assert len(records) == 2
    assert not any("idempotencyKey" in r for r in records)  # keyless records stay out of the unique index


def test_history_lists_customer_and_balance_after(client):
    id = account(client, deposit="5.00")
    owner = client.get(f"/api/accounts/{id}").json()["customerId"]
    [txn] = client.get(f"/api/accounts/{id}/transactions").json()
    assert (txn["customerId"], txn["balanceAfter"]) == (owner, "5.00")


@pytest.mark.parametrize("key", ["", " ", "   ", "x" * 201, "tab\there", "café".encode("latin-1")])
@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_invalid_key_is_422(client, db, key, operation):
    id = account(client, deposit="5.00")
    assert post(client, id, operation, "1.00", key).status_code == 422
    assert balance(client, id) == "5.00"
    assert len(history(db, id)) == 1


def test_header_name_is_case_insensitive(client, db):
    id = account(client)
    send = lambda: client.post(f"/api/accounts/{id}/deposit", json={"amount": "1.00"}, headers={"idempotency-key": "lower"})  # noqa: E731
    assert (send().status_code, send().status_code) == (200, 200)
    assert len(history(db, id)) == 1


def test_by_key_uses_the_partial_unique_index(db):
    """The `$type: string` part of the filter is what lets MongoDB pick idem_unique; without it the lookup scans another index."""
    plan = db.transactions.find({"accountId": ObjectId(), "idempotencyKey": {"$eq": "k", "$type": "string"}}).explain()
    assert "idem_unique" in str(plan["queryPlanner"]["winningPlan"])


def test_longest_key_is_accepted(client, db):
    id = account(client)
    key = "k" * 200
    assert post(client, id, "deposit", "1.00", key).status_code == 200
    assert post(client, id, "deposit", "1.00", key).json()["balance"] == "1.00"
    assert [r["idempotencyKey"] for r in history(db, id)] == [key]


def test_duplicate_key_after_missed_lookup_replays(client, db, monkeypatch):
    # Two requests with one key can both miss the lookup; the unique index then rejects the second insert. Hiding
    # every in-transaction lookup forces that path: the loser's transaction aborts, then it replays or gets 409.
    id = account(client)
    assert post(client, id, "deposit", "25.00", "key-1").status_code == 200
    by_key = TransactionRepository.by_key
    monkeypatch.setattr(TransactionRepository, "by_key",
                        lambda self, oid, key, session=None: None if session else by_key(self, oid, key))
    replay = post(client, id, "deposit", "25.00", "key-1")
    assert (replay.status_code, replay.json()["balance"]) == (200, "25.00")
    assert post(client, id, "deposit", "26.00", "key-1").status_code == 409
    assert balance(client, id) == "25.00"
    assert len(history(db, id)) == 1


def test_account_without_customer_record_is_500(client, db):
    # The customer write serializes money operations; an account whose customer record is gone is an internal
    # inconsistency, reported instead of skipped.
    id = account(client, deposit="5.00")
    db.customers.delete_many({})
    for operation in ["deposit", "withdraw"]:
        response = post(client, id, operation, "1.00", "key-" + operation)
        assert (response.status_code, response.json()) == (500, {"detail": "Account owner record is missing"})
    assert db.accounts.find_one({"_id": ObjectId(id)})["balanceCents"] == 500
    assert len(history(db, id)) == 1


def _gate(monkeypatch, lookups):
    """Hold the first history insert (after its balance change, before its commit) until `lookups` in-transaction key
    lookups have run from `lookups` DISTINCT request threads: the holder's own and one per competitor, each made while the
    holder was uncommitted (a competitor's retries after a write conflict do not count again). Returns
    an Event set when the holder is held, so competitors start strictly after its writes (no sleep-based guessing)."""
    insert, by_key = TransactionRepository.insert, TransactionRepository.by_key
    entered, release, lock, seen = threading.Event(), threading.Event(), threading.Lock(), set()

    def held_insert(self, *args, **kwargs):
        with lock:
            first = not entered.is_set()
            entered.set()
        if first:
            assert release.wait(timeout=8), "not every competitor reached its in-transaction key lookup"
        return insert(self, *args, **kwargs)

    def counted_by_key(self, account_oid, key, session=None):
        if session is not None:
            with lock:
                seen.add(threading.get_ident())  # one entry per request thread: a competitor's retries must not count twice
                if len(seen) == lookups:
                    release.set()
        return by_key(self, account_oid, key, session)

    monkeypatch.setattr(TransactionRepository, "insert", held_insert)
    monkeypatch.setattr(TransactionRepository, "by_key", counted_by_key)
    return entered


def _race(client, monkeypatch, id, operation, amounts):
    """Send amounts[0] first and hold it before its commit; then send the rest with the same key."""
    entered = _gate(monkeypatch, lookups=len(amounts))
    with ThreadPoolExecutor(max_workers=len(amounts)) as pool:
        held = pool.submit(post, client, id, operation, amounts[0], "same-key")
        assert entered.wait(timeout=8)
        rest = [pool.submit(post, client, id, operation, amount, "same-key") for amount in amounts[1:]]
        return [held.result()] + [future.result() for future in rest]


def test_concurrent_same_key_never_500(client, db, monkeypatch):
    id = account(client)
    responses = _race(client, monkeypatch, id, "deposit", ["1.00"] + ["2.00", "1.00"] * 4 + ["2.00"])
    by_status = {}
    for response in responses:
        by_status.setdefault(response.status_code, []).append(response.json())
    assert set(by_status) == {200, 409}
    assert [body["balance"] for body in by_status[200]] == ["1.00"] * 5  # the held request won; the rest replayed it
    assert by_status[409] == [{"detail": REUSED}] * 5  # same key, different amount
    assert balance(client, id) == "1.00"
    assert len(history(db, id)) == 1


def test_concurrent_same_key_draining_withdrawal(client, db, monkeypatch):
    id = account(client, deposit="100.00")
    responses = _race(client, monkeypatch, id, "withdraw", ["100.00"] * 10)
    assert [(r.status_code, r.json()["balance"]) for r in responses] == [(200, "0.00")] * 10  # never Insufficient funds
    assert balance(client, id) == "0.00"
    assert [r["type"] for r in history(db, id)] == ["DEPOSIT", "WITHDRAW"]


def test_concurrent_same_key_max_balance_deposit(client, db, monkeypatch):
    id = account(client)
    responses = _race(client, monkeypatch, id, "deposit", ["99999999.99"] * 10)
    assert [(r.status_code, r.json()["balance"]) for r in responses] == [(200, "99999999.99")] * 10  # never over the limit
    assert balance(client, id) == "99999999.99"
    assert len(history(db, id)) == 1
