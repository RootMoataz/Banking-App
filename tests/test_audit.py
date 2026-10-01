"""Transaction audit: customer/account filters, [from, to) windows, (createdAt, _id) order, fingerprinted cursors."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from bson import Int64, ObjectId

from app.audit import decode_cursor, encode_cursor, fingerprint

T = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
MS = timedelta(milliseconds=1)
URL = "/api/audit/transactions"


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def raw_cursor(payload):
    """A cursor built by hand, the way a client could tamper with one."""
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def record(db, account_oid, customer_oid, at, oid=None):
    """Insert a transaction directly, so tests control createdAt exactly (the API dates each record at least 1 ms after
    the account's previous one, so it can never produce equal timestamps on one account)."""
    doc = {"accountId": account_oid, "customerId": customer_oid, "type": "DEPOSIT", "amountCents": Int64(100),
           "balanceAfterCents": Int64(100), "createdAt": at}
    if oid is not None:
        doc["_id"] = oid
    return str(db.transactions.insert_one(doc).inserted_id)


def audit(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(page):
    return [t["txnId"] for t in page["items"]]


def walk(client, limit, **params):
    """Follow nextCursor to the end; return every page's txnIds."""
    pages, cursor = [], None
    for _ in range(20):  # a cursor that stops advancing must fail the test, not hang it
        page = audit(client, **params, limit=limit, **({} if cursor is None else {"cursor": cursor}))
        pages.append(ids(page))
        cursor = page["nextCursor"]
        if cursor is None:
            return pages
    pytest.fail(f"paging did not end: {pages}")


def customer(client, name="Moataz Hikal", email="moataz@example.com"):
    response = client.post("/api/customers", json={"name": name, "email": email})
    assert response.status_code == 201
    return response.json()["customerId"]


def account(client, owner):
    response = client.post("/api/accounts", json={"customerId": owner, "accountType": "SAVINGS"})
    assert response.status_code == 201
    return response.json()["accountId"]


def post(client, id, operation, amount):
    response = client.post(f"/api/accounts/{id}/{operation}", json={"amount": amount})
    assert response.status_code == 200, response.text
    return response.json()


# --- app/audit.py, no database ---

def test_cursor_round_trip():
    oid = ObjectId()
    cursor = encode_cursor(T + 5 * MS, oid, "0123456789abcdef")
    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")  # URL-safe as is
    assert decode_cursor(cursor) == (T + 5 * MS, oid, "0123456789abcdef")


def test_cursor_round_trip_converts_to_utc():
    plus_two = datetime(2026, 3, 1, 14, tzinfo=timezone(timedelta(hours=2)))
    t, _, _ = decode_cursor(encode_cursor(plus_two, ObjectId(), "f"))
    assert t == T and t.utcoffset() == timedelta(0)


GOOD = {"t": "2026-03-01T12:00:00.000+00:00", "id": "a" * 24, "fp": "0123456789abcdef"}


@pytest.mark.parametrize("cursor", [
    "", "not base64!", "%%%%", "abc", "ñandú",
    base64.urlsafe_b64encode(b"\xff\xfe\x00").decode(),  # not UTF-8
    raw_cursor("just a string"), raw_cursor([1, 2, 3]), raw_cursor(None), raw_cursor({}),
    raw_cursor({k: v for k, v in GOOD.items() if k != "fp"}),
    raw_cursor({**GOOD, "t": 1767225600000}), raw_cursor({**GOOD, "t": "yesterday"}),
    raw_cursor({**GOOD, "t": "2026-03-01T12:00:00"}),  # no offset: not one of ours
    raw_cursor({**GOOD, "t": None}), raw_cursor({**GOOD, "t": "0001-01-01T00:00:00+01:00"}),  # before year 1 in UTC
    raw_cursor({**GOOD, "id": "xyz"}), raw_cursor({**GOOD, "id": "a" * 23}),
    raw_cursor({**GOOD, "id": 12345}), raw_cursor({**GOOD, "id": "g" * 24}), raw_cursor({**GOOD, "id": " " + "a" * 23}),
    raw_cursor({**GOOD, "fp": 5}), raw_cursor({**GOOD, "fp": None}), raw_cursor({**GOOD, "fp": ["x"]}),
])
def test_decode_rejects_malformed_cursor(cursor):
    with pytest.raises(ValueError):
        decode_cursor(cursor)


def test_decode_accepts_hand_built_cursor():
    assert decode_cursor(raw_cursor(GOOD)) == (T, ObjectId("a" * 24), "0123456789abcdef")


def test_fingerprint_is_canonical():
    cid, aid = "65f1a2b3c4d5e6f7a8b9c0d1", "65F1A2B3C4D5E6F7A8B9C0D2"
    fp = fingerprint(cid, aid, T, T + timedelta(days=1))
    assert len(fp) == 16 and int(fp, 16) >= 0
    assert fingerprint(cid.upper(), aid.lower(), T, T + timedelta(days=1)) == fp
    plus_two = timezone(timedelta(hours=2))
    assert fingerprint(cid, aid, T.astimezone(plus_two), (T + timedelta(days=1)).astimezone(plus_two)) == fp
    naive = T.replace(tzinfo=None)
    assert fingerprint(cid, aid, naive, naive + timedelta(days=1)) == fp  # a naive time is UTC


def test_fingerprint_distinguishes_filters():
    cid, aid = "65f1a2b3c4d5e6f7a8b9c0d1", "65f1a2b3c4d5e6f7a8b9c0d2"
    variants = [fingerprint(cid, None, None, None), fingerprint(None, cid, None, None),
                fingerprint(cid, aid, None, None), fingerprint(cid, None, T, None), fingerprint(cid, None, None, T),
                fingerprint(cid, None, T, T + MS), fingerprint(aid, None, None, None)]
    assert len(set(variants)) == len(variants)


# --- GET /api/audit/transactions ---

def test_requires_customer_or_account(client):
    for params in ({}, {"from": iso(T)}, {"limit": 5}):
        response = client.get(URL, params=params)
        assert response.status_code == 422
        assert response.json() == {"detail": "Give customerId, accountId or both"}


@pytest.mark.parametrize("params", [
    {"customerId": "abc"}, {"accountId": "z" * 24}, {"customerId": "a" * 25}, {"accountId": ""},
    {"customerId": "a" * 24, "limit": 0}, {"customerId": "a" * 24, "limit": -1}, {"customerId": "a" * 24, "limit": 201},
    {"customerId": "a" * 24, "limit": "x"}, {"customerId": "a" * 24, "from": "yesterday"},
    {"customerId": "a" * 24, "to": "2026-13-01T00:00:00Z"}])
def test_rejects_bad_parameters(client, params):
    assert client.get(URL, params=params).status_code == 422


@pytest.mark.parametrize("params", [{"from": "0001-01-01T00:00:00+01:00"}, {"to": "9999-12-31T23:59:59.999999Z"},
                                    {"to": "9999-12-31T23:59:59-01:00"}])
def test_times_outside_utc_range_are_422(client, params):
    response = client.get(URL, params={"customerId": "a" * 24, **params})
    assert (response.status_code, response.json()) == (422, {"detail": "from or to is out of range"})


def test_limit_bounds_accepted(client):
    assert audit(client, customerId="a" * 24, limit=1) == {"items": [], "nextCursor": None}
    assert audit(client, customerId="a" * 24, limit=200) == {"items": [], "nextCursor": None}


def test_by_customer_includes_every_account_even_deleted(client, db):
    owner = customer(client)
    kept, closed = account(client, owner), account(client, owner)
    post(client, kept, "deposit", "10.00")
    post(client, closed, "deposit", "5.00")
    post(client, closed, "withdraw", "5.00")
    assert client.delete(f"/api/accounts/{closed}").status_code == 204
    other = account(client, customer(client, "Other", "other@example.com"))
    post(client, other, "deposit", "1.00")  # another customer's record stays out

    page = audit(client, customerId=owner)
    assert page["nextCursor"] is None
    assert [(t["accountId"], t["type"], t["amount"], t["balanceAfter"]) for t in page["items"]] == [
        (kept, "DEPOSIT", "10.00", "10.00"), (closed, "DEPOSIT", "5.00", "5.00"), (closed, "WITHDRAW", "5.00", "0.00")]
    assert {t["customerId"] for t in page["items"]} == {owner}
    assert set(page["items"][0]) == {"txnId", "accountId", "customerId", "type", "amount", "balanceAfter", "date",
                                     "transferId", "fromAccountId", "toAccountId"}
    assert [page["items"][0][k] for k in ("transferId", "fromAccountId", "toAccountId")] == [None] * 3
    assert [t["accountId"] for t in audit(client, accountId=closed)["items"]] == [closed, closed]


def test_history_survives_deleting_customer_and_accounts(client):
    owner = customer(client)
    first, second = account(client, owner), account(client, owner)
    post(client, first, "deposit", "20.00")
    post(client, second, "deposit", "3.00")
    before = audit(client, customerId=owner)
    post(client, first, "withdraw", "20.00")  # balances must be zero before deleting
    post(client, second, "withdraw", "3.00")
    for id in (first, second):
        assert client.delete(f"/api/accounts/{id}").status_code == 204
    assert client.delete(f"/api/customers/{owner}").status_code == 204
    assert client.get(f"/api/customers/{owner}").status_code == 404

    after = audit(client, customerId=owner)
    assert len(after["items"]) == 4
    assert after["items"][:2] == before["items"]
    assert [t["type"] for t in after["items"]] == ["DEPOSIT", "DEPOSIT", "WITHDRAW", "WITHDRAW"]
    assert [t["type"] for t in audit(client, accountId=second)["items"]] == ["DEPOSIT", "WITHDRAW"]


def test_from_inclusive_to_exclusive(client, db):
    acct, cust = ObjectId(), ObjectId()
    at = {name: record(db, acct, cust, t) for name, t in
          [("before", T - MS), ("start", T), ("inside", T + MS), ("last", T + 9 * MS), ("end", T + 10 * MS)]}
    window = ids(audit(client, accountId=str(acct), **{"from": iso(T), "to": iso(T + 10 * MS)}))
    assert window == [at["start"], at["inside"], at["last"]]
    assert ids(audit(client, accountId=str(acct), **{"from": iso(T + 10 * MS)})) == [at["end"]]
    assert ids(audit(client, accountId=str(acct), to=iso(T))) == [at["before"]]


def test_sub_millisecond_bounds(client, db):
    """MongoDB keeps milliseconds. A bound between two stored milliseconds must still keep from inclusive and to
    exclusive, instead of being cut down to the millisecond below it."""
    acct = ObjectId()
    start, inside, end = (record(db, acct, ObjectId(), t) for t in (T, T + MS, T + 2 * MS))
    half = timedelta(microseconds=500)
    assert ids(audit(client, accountId=str(acct), **{"from": iso(T + half)})) == [inside, end]
    assert ids(audit(client, accountId=str(acct), to=iso(T + MS + half))) == [start, inside]


@pytest.mark.parametrize("start, end", [(T, T), (T + MS, T)])
def test_from_not_before_to_is_empty(client, db, start, end):
    acct = ObjectId()
    for t in (T - MS, T, T + MS):
        record(db, acct, ObjectId(), t)
    page = audit(client, accountId=str(acct), **{"from": iso(start), "to": iso(end)})
    assert page == {"items": [], "nextCursor": None}  # an empty window, as with search's inverted balance bounds


def test_naive_times_are_utc(client, db):
    acct = ObjectId()
    rows = [record(db, acct, ObjectId(), T + i * MS) for i in range(4)]
    naive = {"from": T.replace(tzinfo=None).isoformat(), "to": (T + 3 * MS).replace(tzinfo=None).isoformat()}
    aware = {"from": iso(T), "to": iso(T + 3 * MS)}
    first = audit(client, accountId=str(acct), limit=2, **naive)
    assert first["items"] == audit(client, accountId=str(acct), limit=2, **aware)["items"]
    assert ids(first) == rows[:2]
    assert ids(audit(client, accountId=str(acct), cursor=first["nextCursor"], **aware)) == rows[2:3]


def test_ordered_by_created_at_then_id(client, db):
    acct, cust = ObjectId(), ObjectId()
    low, mid, high = sorted(ObjectId() for _ in range(3))
    # Inserted out of order, and with _id order disagreeing with createdAt order.
    later = record(db, acct, cust, T + MS, low)
    tie_high = record(db, acct, cust, T, high)
    tie_mid = record(db, acct, cust, T, mid)
    assert ids(audit(client, accountId=str(acct))) == [tie_mid, tie_high, later]
    assert ids(audit(client, customerId=str(cust))) == [tie_mid, tie_high, later]


def test_paging_has_no_duplicates_or_gaps_with_equal_timestamps(client, db):
    cust = ObjectId()
    a, b = ObjectId(), ObjectId()
    # Two accounts of one customer; four records share one millisecond, so a page boundary falls inside the tie.
    for acct, t in [(a, T), (b, T), (a, T), (b, T), (a, T + MS), (b, T + 2 * MS)]:
        record(db, acct, cust, t)
    everything = ids(audit(client, customerId=str(cust)))
    assert len(everything) == 6
    pages = walk(client, 2, customerId=str(cust))
    assert [len(p) for p in pages] == [2, 2, 2]  # a full last page still ends the walk: no empty extra page
    assert sum(pages, []) == everything
    by_account = walk(client, 2, accountId=str(a))
    assert sum(by_account, []) == ids(audit(client, accountId=str(a)))
    assert [len(p) for p in by_account] == [2, 1]
    assert sum(walk(client, 1, customerId=str(cust)), []) == everything


def test_page_size_may_change_between_pages(client, db):
    acct = ObjectId()
    rows = [record(db, acct, ObjectId(), T) for _ in range(5)]
    first = audit(client, accountId=str(acct), limit=2)
    second = audit(client, accountId=str(acct), limit=3, cursor=first["nextCursor"])
    assert (ids(first), ids(second), second["nextCursor"]) == (rows[:2], rows[2:], None)


def test_account_and_customer_filters_combine(client, db):
    cust, acct = ObjectId(), ObjectId()
    both = record(db, acct, cust, T)
    record(db, acct, ObjectId(), T)  # same account ID, other customer
    record(db, ObjectId(), cust, T)
    assert ids(audit(client, customerId=str(cust), accountId=str(acct))) == [both]


def test_cursor_rejected_for_other_filters(client, db):
    cust, acct = ObjectId(), ObjectId()
    for i in range(3):
        record(db, acct, cust, T + i * MS)
    base = {"customerId": str(cust), "from": iso(T), "to": iso(T + timedelta(days=1))}
    cursor = audit(client, limit=1, **base)["nextCursor"]
    assert cursor is not None
    others = [{**base, "customerId": str(ObjectId())}, {**base, "accountId": str(acct)},
              {k: v for k, v in base.items() if k != "to"}, {k: v for k, v in base.items() if k != "from"},
              {**base, "from": iso(T - MS)}, {**base, "to": iso(T + timedelta(days=2))},
              {"accountId": str(acct), "from": base["from"], "to": base["to"]}]
    for params in others:
        response = client.get(URL, params={**params, "cursor": cursor})
        assert response.status_code == 422, params
        assert response.json() == {"detail": "The cursor was issued for different filters"}
    assert client.get(URL, params={**base, "cursor": cursor}).status_code == 200


def test_same_filter_written_differently_continues(client, db):
    cust, acct = ObjectId(), ObjectId()
    rows = [record(db, acct, cust, T + i * MS) for i in range(4)]
    end = T + timedelta(hours=1)
    first = audit(client, customerId=str(cust), limit=1, **{"from": iso(T), "to": iso(end)})
    assert ids(first) == rows[:1]
    plus_two = timezone(timedelta(hours=2))
    rewrites = [{"customerId": str(cust).upper(), "from": T.isoformat(), "to": end.isoformat()},  # +00:00
                {"customerId": str(cust).upper(), "from": T.astimezone(plus_two).isoformat(),
                 "to": end.astimezone(plus_two).isoformat()}]
    for params in rewrites:
        assert ids(audit(client, limit=2, cursor=first["nextCursor"], **params)) == rows[1:3]


@pytest.mark.parametrize("cursor", [
    "garbage", "not base64!", raw_cursor([1]), raw_cursor({**GOOD, "t": 5}), raw_cursor({**GOOD, "id": "xyz"}),
    raw_cursor({**GOOD, "fp": 5}), raw_cursor({"t": GOOD["t"], "id": GOOD["id"]})])
def test_malformed_cursor_is_422(client, cursor):
    response = client.get(URL, params={"customerId": "a" * 24, "cursor": cursor})
    assert response.status_code == 422
    assert response.json() == {"detail": "Malformed cursor"}


def test_forged_cursor_with_wrong_fingerprint_is_422(client):
    response = client.get(URL, params={"customerId": "a" * 24, "cursor": raw_cursor(GOOD)})
    assert (response.status_code, response.json()) == (422, {"detail": "The cursor was issued for different filters"})
