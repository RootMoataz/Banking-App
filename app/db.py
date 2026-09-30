from pymongo import MongoClient
from pymongo.database import Database


def get_database(settings) -> Database:
    return MongoClient(settings.mongodb_uri, tz_aware=True)[settings.mongodb_db]


def ensure_indexes(db: Database) -> None:
    db.customers.create_index("emailKey", unique=True, name="emailKey_unique")
    db.accounts.create_index("customerId")
    db.transactions.create_index([("accountId", 1), ("createdAt", 1), ("_id", 1)])
    db.transactions.create_index([("customerId", 1), ("createdAt", 1), ("_id", 1)])
    db.transactions.create_index(
        [("accountId", 1), ("idempotencyKey", 1)],
        unique=True,
        partialFilterExpression={"idempotencyKey": {"$type": "string"}},
        name="idem_unique",
    )
    db.alerts.create_index([("customerId", 1), ("createdAt", -1)])
