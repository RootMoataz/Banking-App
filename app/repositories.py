"""MongoDB collections shared by the customer and account services."""
import re
from datetime import datetime, timedelta, timezone

from bson import Int64, ObjectId
from pymongo import ReturnDocument
from pymongo.client_session import ClientSession
from pymongo.database import Database


def _now() -> datetime:
    # MongoDB keeps milliseconds; trimming here makes a create response match every later read.
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class CustomerRepository:
    def __init__(self, db: Database):
        self.collection = db.customers

    def insert(self, name: str, email: str) -> dict:
        # The unique emailKey index rejects a second customer with the same email in any letter case.
        customer = {"name": name, "email": email, "emailKey": email.lower(), "createdAt": _now(),
                    "marketingEnabled": False}
        self.collection.insert_one(customer)
        return customer

    def get(self, oid: ObjectId) -> dict | None:
        return self.collection.find_one({"_id": oid})

    def search(self, name: str | None, email: str | None, total_cond: dict, limit: int) -> list[dict]:
        """Customers matching the text filters and the total-balance condition, each with totalCents, oldest first."""
        # User text is escaped, so "." or "(" match themselves instead of acting as regex syntax.
        text = {field: {"$regex": re.escape(value), "$options": "i"}
                for field, value in (("name", name), ("email", email)) if value is not None}
        # Without a balance condition the first `limit` customers are known up front, so only they need the lookup.
        cap = [{"$limit": limit}]
        return list(self.collection.aggregate([
            {"$match": text},
            {"$sort": {"_id": 1}},
            *([] if total_cond else cap),
            {"$lookup": {"from": "accounts", "localField": "_id", "foreignField": "customerId", "as": "accounts"}},
            {"$addFields": {"totalCents": {"$sum": "$accounts.balanceCents"}}},  # no accounts: 0
            *([{"$match": {"totalCents": total_cond}}, *cap] if total_cond else []),
            {"$project": {"name": 1, "email": 1, "totalCents": 1}},
        ]))

    def list(self, limit: int | None = None) -> list[dict]:
        return list(self.collection.find().sort("_id").limit(limit or 0))

    def update(self, oid: ObjectId, name: str, email: str, session: ClientSession) -> dict | None:
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$set": {"name": name, "email": email, "emailKey": email.lower()}},
            return_document=ReturnDocument.AFTER, session=session)

    def delete(self, oid: ObjectId, session: ClientSession) -> None:
        self.collection.delete_one({"_id": oid}, session=session)

    def touch(self, oid: ObjectId, session: ClientSession) -> dict | None:
        """Write the customer document so concurrent transactions for one customer conflict and retry."""
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$inc": {"version": 1}}, return_document=ReturnDocument.AFTER, session=session)

    def set_marketing(self, oid: ObjectId, enabled: bool) -> dict | None:
        # A write to the customer document, so it conflicts with a money operation in flight. Whichever commits first
        # wins: a change that arrives mid-operation applies to later operations.
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$set": {"marketingEnabled": enabled}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER)

    def next_category_version(self, oid: ObjectId, session: ClientSession) -> int:
        """Count one more category change for the customer and return the new count (the first change is 1)."""
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$inc": {"categoryVersion": 1}}, return_document=ReturnDocument.AFTER,
            session=session)["categoryVersion"]


class AccountRepository:
    def __init__(self, db: Database):
        self.collection = db.accounts

    def insert(self, customer: dict, account_type: str, session: ClientSession) -> dict:
        account = {"customerId": customer["_id"], "customerName": customer["name"],
                   "accountType": account_type, "balanceCents": Int64(0), "createdAt": _now()}
        self.collection.insert_one(account, session=session)
        return account

    def get(self, oid: ObjectId, session: ClientSession | None = None) -> dict | None:
        return self.collection.find_one({"_id": oid}, session=session)

    # Defined before list(), whose name would otherwise shadow the builtin in this annotation.
    def at_least(self, cents: int, limit: int) -> list[dict]:
        """Accounts with a balance of cents or more, highest first; equal balances oldest first (balance_desc)."""
        return list(self.collection.find({"balanceCents": {"$gte": cents}})
                    .sort([("balanceCents", -1), ("_id", 1)]).limit(limit))

    def list(self, customer_oid: ObjectId | None = None, limit: int | None = None) -> list[dict]:
        query = {} if customer_oid is None else {"customerId": customer_oid}
        return list(self.collection.find(query).sort("_id").limit(limit or 0))

    def delete_for(self, customer_oid: ObjectId, session: ClientSession) -> None:
        self.collection.delete_many({"customerId": customer_oid}, session=session)

    def update_type(self, oid: ObjectId, account_type: str) -> dict | None:
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$set": {"accountType": account_type}}, return_document=ReturnDocument.AFTER)

    def delete(self, oid: ObjectId, session: ClientSession) -> None:
        self.collection.delete_one({"_id": oid}, session=session)

    def rename_owner(self, customer_oid: ObjectId, name: str, session: ClientSession) -> None:
        self.collection.update_many({"customerId": customer_oid}, {"$set": {"customerName": name}}, session=session)

    def inc(self, oid: ObjectId, delta_cents: int, cond: dict, session: ClientSession) -> dict | None:
        """Change the balance only when cond still holds, and return the account after the change."""
        return self.collection.find_one_and_update(
            {"_id": oid, **cond}, {"$inc": {"balanceCents": Int64(delta_cents)}},
            return_document=ReturnDocument.AFTER, session=session)

    def customer_total(self, customer_oid: ObjectId, session: ClientSession | None = None) -> int:
        """The sum of all the customer's balances; 0 when they have no accounts."""
        result = list(self.collection.aggregate([
            {"$match": {"customerId": customer_oid}},
            {"$group": {"_id": None, "total": {"$sum": "$balanceCents"}}},
        ], session=session))
        return result[0]["total"] if result else 0


class TransactionRepository:
    def __init__(self, db: Database):
        self.collection = db.transactions

    def insert(self, account: dict, kind: str, amount_cents: int, key: str | None, session: ClientSession,
               transfer: dict | None = None) -> dict:
        """Record a balance change made in session; account is the account after that change. A transfer leg also
        passes transfer = {transferId, fromAccountId, toAccountId}."""
        # The caller must already have written this account in the same session (the balance update does), so changes
        # to one account commit one at a time and the newest record is visible here. Dating this one strictly after it
        # keeps (createdAt, _id) order equal to the balance order, even if the clock steps back or ObjectIds from
        # another process sort differently.
        latest = self.collection.find_one({"accountId": account["_id"]}, sort=[("createdAt", -1), ("_id", -1)],
                                          session=session)
        created_at = _now() if latest is None else max(_now(), latest["createdAt"] + timedelta(milliseconds=1))
        # Customer and account IDs are both kept, so the record outlives either one.
        record = {"accountId": account["_id"], "customerId": account["customerId"], "type": kind,
                  "amountCents": Int64(amount_cents), "balanceAfterCents": Int64(account["balanceCents"]),
                  "createdAt": created_at, **(transfer or {})}
        if key is not None:  # keyless records stay out of the idem_unique index, so they never collide
            record["idempotencyKey"] = key
        self.collection.insert_one(record, session=session)
        return record

    def by_key(self, account_oid: ObjectId, key: str, session: ClientSession | None = None) -> dict | None:
        # The $type condition matches the idem_unique partial filter, so MongoDB can use that index.
        return self.collection.find_one({"accountId": account_oid, "idempotencyKey": {"$eq": key, "$type": "string"}},
                                        session=session)

    def credit_of(self, transfer_oid: ObjectId) -> dict | None:
        """The TRANSFER_IN record of a transfer."""
        # The $type condition matches the transfer_legs partial filter, so MongoDB can use that index.
        return self.collection.find_one({"transferId": {"$eq": transfer_oid, "$type": "objectId"},
                                         "type": "TRANSFER_IN"})

    def for_account(self, account_oid: ObjectId, limit: int | None = None) -> list[dict]:
        cursor = self.collection.find({"accountId": account_oid}).sort([("createdAt", 1), ("_id", 1)])
        return list(cursor.limit(limit or 0))

    def page(self, filters: dict, after: tuple[datetime, ObjectId] | None, limit: int) -> list[dict]:
        """Up to limit records matching filters, oldest first, starting strictly after the (createdAt, _id) pair."""
        query = dict(filters)
        if after is not None:
            t, oid = after
            # _id breaks ties, so records sharing one millisecond are neither repeated nor skipped across pages.
            # A plain lower bound lets MongoDB seek into the (customerId, createdAt, _id) index; the $or alone cannot.
            lower = query.get("createdAt", {})
            query["createdAt"] = {**lower, "$gte": max(lower["$gte"], t) if "$gte" in lower else t}
            query["$or"] = [{"createdAt": {"$gt": t}}, {"createdAt": t, "_id": {"$gt": oid}}]
        return list(self.collection.find(query).sort([("createdAt", 1), ("_id", 1)]).limit(limit))


class NotificationRepository:
    def __init__(self, db: Database):
        self.collection = db.notifications

    def insert(self, record: dict, category: str, version: int, message: dict, session: ClientSession) -> dict:
        """Store one message (kind, templateId, message) for the category change that the transaction `record` caused.
        (customerId, categoryVersion, kind) is unique, so one change can never store the same kind twice. The message
        carries the transaction's own date: that date may sit slightly ahead of the clock to keep the history in
        order."""
        notification = {"customerId": record["customerId"], "categoryVersion": version, "category": category,
                        **message, "transactionId": record["_id"], "createdAt": record["createdAt"]}
        self.collection.insert_one(notification, session=session)
        return notification

    def list(self, customer_oid: ObjectId, kind: str | None, limit: int) -> list[dict]:
        query = {"customerId": customer_oid} if kind is None else {"customerId": customer_oid, "kind": kind}
        return list(self.collection.find(query).sort([("createdAt", -1), ("_id", -1)]).limit(limit))
