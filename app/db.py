from pymongo import MongoClient
from pymongo.database import Database


def get_database(settings) -> Database:
    return MongoClient(settings.mongodb_uri, tz_aware=True)[settings.mongodb_db]


def ensure_indexes(db: Database) -> None:
    db.customers.create_index("emailKey", unique=True, name="emailKey_unique")
    db.accounts.create_index("customerId")
    # Premium accounts: the balance bound and the highest-first order both come from this index.
    db.accounts.create_index([("balanceCents", -1), ("_id", 1)], name="balance_desc")
    db.transactions.create_index([("accountId", 1), ("createdAt", 1), ("_id", 1)])
    # Finds the other leg of a transfer; deposits and withdrawals have no transferId and stay out of it.
    db.transactions.create_index("transferId", partialFilterExpression={"transferId": {"$type": "objectId"}},
                                 name="transfer_legs")
    db.transactions.create_index([("customerId", 1), ("createdAt", 1), ("_id", 1)])
    db.transactions.create_index(
        [("accountId", 1), ("idempotencyKey", 1)],
        unique=True,
        partialFilterExpression={"idempotencyKey": {"$type": "string"}},
        name="idem_unique",
    )
    # One stored message per kind for each category change, even if a transaction is retried.
    db.notifications.create_index([("customerId", 1), ("categoryVersion", 1), ("kind", 1)], unique=True,
                                  name="notification_unique")
    db.notifications.create_index([("customerId", 1), ("createdAt", -1), ("_id", -1)])
