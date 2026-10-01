"""Transfers between any two accounts: one transaction debits, credits, records both legs and stores notifications."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from bson import ObjectId

from app.repositories import TransactionRepository
from test_search_alerts import account, customer, money, post

URL = "/api/transfers"
MISSING = str(ObjectId())  # well-formed, but never stored
REUSED = "Idempotency-Key was already used for a different request"


def transfer(client, source, target, amount, key=None):
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(URL, json={"fromAccountId": source, "toAccountId": target, "amount": amount}, headers=headers)


def balance(client, id):
    return client.get(f"/api/accounts/{id}").json()["balance"]


def history(client, id):
    response = client.get(f"/api/accounts/{id}/transactions")
    assert response.status_code == 200, response.text
    return response.json()


def stored(db, id):
    return list(db.transactions.find({"accountId": ObjectId(id)}).sort([("createdAt", 1), ("_id", 1)]))


def notifications(client, owner):
    response = client.get(f"/api/customers/{owner}/notifications")
    assert response.status_code == 200, response.text
    return response.json()


def two_customers(client, first_cents=0, second_cents=0):
    a, b = customer(client), customer(client, "Second Owner", "second@example.com")
    return a, account(client, a, first_cents), b, account(client, b, second_cents)


def test_transfer_moves_money_and_records_both_legs(client):
    owner_a, a, owner_b, b = two_customers(client, 10_000)
    response = transfer(client, a, b, "30.00")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"transferId", "fromAccountId", "toAccountId", "amount", "fromBalanceAfter",
                         "toBalanceAfter", "date"}
    assert (body["fromAccountId"], body["toAccountId"], body["amount"]) == (a, b, "30.00")
    assert (body["fromBalanceAfter"], body["toBalanceAfter"]) == ("70.00", "30.00")
    assert (balance(client, a), balance(client, b)) == ("70.00", "30.00")

    deposit, out = history(client, a)
    [into] = history(client, b)
    assert deposit["type"] == "DEPOSIT" and deposit["transferId"] is None
    assert deposit["fromAccountId"] is None and deposit["toAccountId"] is None
    shared = {"transferId": body["transferId"], "fromAccountId": a, "toAccountId": b, "amount": "30.00"}
    assert {k: out[k] for k in shared} == shared and {k: into[k] for k in shared} == shared
    assert (out["type"], out["accountId"], out["customerId"], out["balanceAfter"]) == ("TRANSFER_OUT", a, owner_a, "70.00")
    assert (into["type"], into["accountId"], into["customerId"], into["balanceAfter"]) == ("TRANSFER_IN", b, owner_b, "30.00")
    assert datetime.fromisoformat(body["date"]) == datetime.fromisoformat(out["date"])
    assert out["txnId"] != into["txnId"]

    # Each customer's audit and each account's audit shows its own leg of the transfer.
    audit = lambda **params: client.get("/api/audit/transactions", params=params).json()["items"]  # noqa: E731
    assert [t["type"] for t in audit(customerId=owner_a)] == ["DEPOSIT", "TRANSFER_OUT"]
    assert audit(customerId=owner_b) == [into]
    assert audit(accountId=b) == [into]
    assert audit(accountId=a)[1] == out


def test_transfer_between_one_customers_accounts_stores_no_notification(client, db):
    owner = customer(client)
    client.patch(f"/api/customers/{owner}/preferences", json={"marketingEnabled": True})
    a, b = account(client, owner, 1_000_000), account(client, owner)  # PREMIUM, entered with marketing on
    before = notifications(client, owner)
    version = db.customers.find_one({"_id": ObjectId(owner)})["categoryVersion"]
    # The customer's total is unchanged, even though one account alone drops far below the low threshold.
    assert transfer(client, a, b, "9999.99").status_code == 200
    assert (balance(client, a), balance(client, b)) == ("0.01", "9999.99")
    assert notifications(client, owner) == before
    assert db.customers.find_one({"_id": ObjectId(owner)})["categoryVersion"] == version
    assert [t["customerId"] for t in client.get("/api/audit/transactions",
                                                params={"customerId": owner}).json()["items"]] == [owner] * 3


def test_transfer_category_changes_are_per_customer(client, settings):
    # A enters PREMIUM without marketing, so no message yet; B opts in.
    owner_a, a, owner_b, b = two_customers(client, settings.premium_cents + 5_000)
    client.patch(f"/api/customers/{owner_b}/preferences", json={"marketingEnabled": True})
    assert notifications(client, owner_a) == []
    assert transfer(client, a, b, money(settings.premium_cents)).status_code == 200
    out, into = history(client, a)[-1], history(client, b)[-1]
    # A falls to 50.00 and enters LOW; B rises to 10000.00 and enters PREMIUM. Each message cites its own leg.
    [alert] = notifications(client, owner_a)
    assert (alert["kind"], alert["category"], alert["transactionId"]) == ("LOW_BALANCE_ALERT", "LOW", out["txnId"])
    [premium] = notifications(client, owner_b)
    assert (premium["kind"], premium["category"], premium["transactionId"]) == (
        "PREMIUM_MARKETING", "PREMIUM", into["txnId"])


def test_transfer_staying_in_category_stores_nothing(client):
    owner_a, a, owner_b, b = two_customers(client, 50_000, 50_000)  # both STANDARD
    before_a, before_b = notifications(client, owner_a), notifications(client, owner_b)
    assert transfer(client, a, b, "100.00").status_code == 200
    assert (notifications(client, owner_a), notifications(client, owner_b)) == (before_a, before_b)


def test_same_account_is_rejected(client, db):
    _, a, _, _ = two_customers(client, 10_000)
    for target in (a, a.upper()):
        response = transfer(client, a, target, "1.00")
        assert (response.status_code, response.json()) == (
            422, {"detail": "fromAccountId and toAccountId must be different accounts"})
    assert balance(client, a) == "100.00" and len(stored(db, a)) == 1


@pytest.mark.parametrize("body", [
    {}, {"fromAccountId": MISSING, "toAccountId": MISSING},
    {"fromAccountId": "abc", "toAccountId": MISSING, "amount": "1.00"},
    {"fromAccountId": MISSING, "toAccountId": "g" * 24, "amount": "1.00"},
    {"fromAccountId": MISSING, "toAccountId": str(ObjectId()), "amount": "1.00", "note": "extra"},
    *({"fromAccountId": MISSING, "toAccountId": str(ObjectId()), "amount": amount}
      for amount in (0, -1, "0.001", "NaN", "Infinity", "abc", True, None, "100000000.00"))])
def test_invalid_body_is_422(client, body):
    assert client.post(URL, json=body).status_code == 422


def test_missing_accounts_are_404_and_change_nothing(client, db):
    _, a, _, _ = two_customers(client, 10_000)
    for source, target, detail in [(MISSING, a, "Source account not found"),
                                   (a, MISSING, "Destination account not found")]:
        response = transfer(client, source, target, "1.00")
        assert (response.status_code, response.json()) == (404, {"detail": detail})
    assert balance(client, a) == "100.00" and len(stored(db, a)) == 1


def test_insufficient_funds_is_400_like_withdraw(client, db):
    _, a, _, b = two_customers(client, 10_000)
    response = transfer(client, a, b, "100.01")
    assert (response.status_code, response.json()) == (400, {"detail": "Insufficient funds"})
    assert (balance(client, a), balance(client, b)) == ("100.00", "0.00")
    assert (len(stored(db, a)), len(stored(db, b))) == (1, 0)
    assert transfer(client, a, b, "100.00").json()["fromBalanceAfter"] == "0.00"  # the whole balance may move


def test_destination_limit_rolls_back_the_debit(client, db):
    _, a, _, b = two_customers(client, 10_000, 9_999_999_999 - 500)
    response = transfer(client, a, b, "10.00")
    assert (response.status_code, response.json()) == (400, {"detail": "Balance would exceed 99999999.99"})
    assert (balance(client, a), balance(client, b)) == ("100.00", "99999994.99")
    assert (len(stored(db, a)), len(stored(db, b))) == (1, 1)


def test_failed_credit_record_rolls_back_everything(client, db, monkeypatch):
    _, a, _, b = two_customers(client, 10_000)
    insert, calls = TransactionRepository.insert, []

    def fail_second(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("history write failed")
        return insert(self, *args, **kwargs)
    monkeypatch.setattr(TransactionRepository, "insert", fail_second)
    with pytest.raises(RuntimeError):
        transfer(client, a, b, "10.00")
    assert (balance(client, a), balance(client, b)) == ("100.00", "0.00")
    assert (len(stored(db, a)), len(stored(db, b))) == (1, 0)


def test_same_key_replays_without_moving_money(client, db):
    _, a, _, b = two_customers(client, 10_000)
    first = transfer(client, a, b, "25.00", "t-1")
    assert first.status_code == 200
    assert transfer(client, a, b, "5.00").status_code == 200  # a later keyless transfer
    replay = transfer(client, a, b, "25.00", "t-1")
    assert (replay.status_code, replay.json()) == (200, first.json())  # the balances this transfer produced
    assert (balance(client, a), balance(client, b)) == ("70.00", "30.00")
    assert [r["type"] for r in stored(db, a)] == ["DEPOSIT", "TRANSFER_OUT", "TRANSFER_OUT"]
    assert [r.get("idempotencyKey") for r in stored(db, b)] == [None, None]  # the key lives on the debit only


def test_key_reused_for_a_different_request_is_409(client, db):
    _, a, owner_b, b = two_customers(client, 10_000)
    other = account(client, owner_b)
    assert transfer(client, a, b, "25.00", "t-1").status_code == 200
    for target, amount in [(b, "26.00"), (other, "25.00")]:
        response = transfer(client, a, target, amount, "t-1")
        assert (response.status_code, response.json()) == (409, {"detail": REUSED})
    assert post(client, a, "withdraw", "25.00", "t-1").status_code == 409  # one key namespace per source account
    assert post(client, a, "withdraw", "1.00", "w-1").status_code == 200
    assert transfer(client, a, b, "1.00", "w-1").status_code == 409
    assert transfer(client, b, a, "1.00", "t-1").status_code == 200  # another source account: independent
    assert (balance(client, a), balance(client, b), balance(client, other)) == ("75.00", "24.00", "0.00")


def test_replay_after_both_accounts_deleted(client):
    _, a, _, b = two_customers(client, 10_000)
    first = transfer(client, a, b, "100.00", "t-1").json()
    assert post(client, b, "withdraw", "100.00").status_code == 200
    for id in (a, b):
        assert client.delete(f"/api/accounts/{id}").status_code == 204
    replay = transfer(client, a, b, "100.00", "t-1")
    assert (replay.status_code, replay.json()) == (200, first)
    assert transfer(client, a, b, "100.00", "t-2").status_code == 404  # a new key still needs the accounts


def test_invalid_key_is_422(client):
    _, a, _, b = two_customers(client, 10_000)
    for key in ("", " leading", "x" * 201):
        assert transfer(client, a, b, "1.00", key).status_code == 422
    assert balance(client, a) == "100.00"


def _consistent(db, id):
    """Each stored record's balanceAfter follows from the one before it: the history order matches the money."""
    running = 0
    for r in stored(db, id):
        running += -r["amountCents"] if r["type"] in ("WITHDRAW", "TRANSFER_OUT") else r["amountCents"]
        assert r["balanceAfterCents"] == running
    return running


def test_opposite_transfers_conserve_money(client, db):
    _, a, _, b = two_customers(client, 10_000, 10_000)
    jobs = [(a, b)] * 10 + [(b, a)] * 10
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        codes = list(pool.map(lambda pair: transfer(client, *pair, "10.00").status_code, jobs))
    assert codes == [200] * 20  # each side starts with enough to send all ten before receiving any
    assert (balance(client, a), balance(client, b)) == ("100.00", "100.00")
    assert (_consistent(db, a), _consistent(db, b)) == (10_000, 10_000)
    transfer_ids = [r["transferId"] for r in db.transactions.find({"type": "TRANSFER_OUT"})]
    assert len(set(transfer_ids)) == 20
    assert db.transactions.count_documents({"type": "TRANSFER_IN", "transferId": {"$in": transfer_ids}}) == 20


def test_racing_transfers_and_withdrawals_never_overdraw(client, db):
    _, a, _, b = two_customers(client, 10_000)
    jobs = ["transfer", "withdraw"] * 10  # twenty requests of 10.00 compete for 100.00
    send = {"transfer": lambda: transfer(client, a, b, "10.00"), "withdraw": lambda: post(client, a, "withdraw", "10.00")}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        responses = list(pool.map(lambda job: (job, send[job]()), jobs))
    ok = [job for job, r in responses if r.status_code == 200]
    assert len(ok) == 10
    assert {r.json()["detail"] for _, r in responses if r.status_code != 200} == {"Insufficient funds"}
    assert balance(client, a) == "0.00"
    assert balance(client, b) == money(1_000 * ok.count("transfer"))
    assert _consistent(db, a) == 0 and _consistent(db, b) == 1_000 * ok.count("transfer")


def test_swagger_documents_transfers(client):
    route = client.get("/openapi.json").json()["paths"]["/api/transfers"]["post"]
    assert {"400", "404", "409", "422"} <= set(route["responses"])
    assert "Idempotency-Key" in {p["name"] for p in route["parameters"] if p["in"] == "header"}
