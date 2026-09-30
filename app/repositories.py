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
        customer = {"name": name, "email": email, "emailKey": email.casefold(), "createdAt": _now()}
        self.collection.insert_one(customer)
        return customer

    def get(self, oid: ObjectId) -> dict | None:
        return self.collection.find_one({"_id": oid})

    def search(self, name: str | None, email: str | None, total_cond: dict, limit: int) -> list[dict]:
        """Customers matching the text filters and the total-balance condition, each with totalCents, oldest first."""
        # User text is escaped, so "." or "(" match themselves instead of acting as regex syntax.
        text = {field: {"$regex": re.escape(value), "$options": "i"}
                for field, value in (("name", name), ("email", email)) if value is not None}
        return list(self.collection.aggregate([
            {"$match": text},
            {"$sort": {"_id": 1}},
            {"$lookup": {"from": "accounts", "localField": "_id", "foreignField": "customerId", "as": "accounts"}},
            {"$addFields": {"totalCents": {"$sum": "$accounts.balanceCents"}}},  # no accounts: 0
            {"$match": {"totalCents": total_cond} if total_cond else {}},
            {"$limit": limit},
            {"$project": {"name": 1, "email": 1, "totalCents": 1}},
        ]))

    def list(self) -> list[dict]:
        return list(self.collection.find().sort("_id"))

    def update(self, oid: ObjectId, name: str, email: str, session: ClientSession) -> dict | None:
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$set": {"name": name, "email": email, "emailKey": email.casefold()}},
            return_document=ReturnDocument.AFTER, session=session)

    def delete(self, oid: ObjectId, session: ClientSession) -> None:
        self.collection.delete_one({"_id": oid}, session=session)

    def touch(self, oid: ObjectId, session: ClientSession) -> dict | None:
        """Write the customer document so concurrent transactions for one customer conflict and retry."""
        return self.collection.find_one_and_update(
            {"_id": oid}, {"$inc": {"version": 1}}, return_document=ReturnDocument.AFTER, session=session)


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

    def list(self, customer_oid: ObjectId | None = None) -> list[dict]:
        query = {} if customer_oid is None else {"customerId": customer_oid}
        return list(self.collection.find(query).sort("_id"))

    def any_for(self, customer_oid: ObjectId, session: ClientSession) -> bool:
        return self.collection.count_documents({"customerId": customer_oid}, limit=1, session=session) > 0

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

    def insert(self, account: dict, kind: str, amount_cents: int, key: str | None, session: ClientSession) -> dict:
        """Record a balance change made in session; account is the account after that change."""
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
                  "createdAt": created_at}
        if key is not None:  # keyless records stay out of the idem_unique index, so they never collide
            record["idempotencyKey"] = key
        self.collection.insert_one(record, session=session)
        return record

    def by_key(self, account_oid: ObjectId, key: str, session: ClientSession | None = None) -> dict | None:
        # The $type condition matches the idem_unique partial filter, so MongoDB can use that index.
        return self.collection.find_one({"accountId": account_oid, "idempotencyKey": {"$eq": key, "$type": "string"}},
                                        session=session)

    def for_account(self, account_oid: ObjectId) -> list[dict]:
        return list(self.collection.find({"accountId": account_oid}).sort([("createdAt", 1), ("_id", 1)]))


class AlertRepository:
    def __init__(self, db: Database):
        self.collection = db.alerts

    def insert(self, record: dict, kind: str, total_cents: int, threshold_cents: int, session: ClientSession) -> dict:
        """Record that the transaction `record` moved its customer's total across threshold_cents. The alert carries the
        transaction's own date: that date may sit slightly ahead of the clock to keep the history in order."""
        alert = {"customerId": record["customerId"], "accountId": record["accountId"], "transactionId": record["_id"],
                 "type": kind, "totalCents": Int64(total_cents), "thresholdCents": Int64(threshold_cents),
                 "createdAt": record["createdAt"]}
        self.collection.insert_one(alert, session=session)
        return alert

    def list(self, customer_oid: ObjectId | None, limit: int) -> list[dict]:
        query = {} if customer_oid is None else {"customerId": customer_oid}
        return list(self.collection.find(query).sort([("createdAt", -1), ("_id", -1)]).limit(limit))
