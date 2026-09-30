"""Connection lifecycle and transaction boundaries shared by the repositories."""
from pymongo import MongoClient
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .config import Settings


class MongoStore:
    def __init__(self, settings: Settings):
        self.client = MongoClient(settings.uri.get_secret_value(), tz_aware=True,
                                  serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                                  timeoutMS=15000)
        self.database = self.client[settings.database]

    def connect(self):
        self.client.admin.command('ping')
        topology = self.client.admin.command('hello')
        if not topology.get('setName') and topology.get('msg') != 'isdbgrid':
            raise ValueError('A transaction-capable replica set or Atlas cluster is required')
        self.ensure_indexes()

    def ensure_indexes(self):
        db = self.database
        db.customers.create_index('normalizedEmail', unique=True)
        db.customers.create_index([('active',1),('category',1),('createdAt',1),('_id',1)])
        db.accounts.create_index([('customerId',1),('active',1),('createdAt',1),('_id',1)])
        db.accounts.create_index([('active',1),('createdAt',1),('_id',1)])
        db.transactions.create_index([('accountId',1),('date',1),('_id',1)])
        db.transactions.create_index([('customerId',1),('date',1),('_id',1)])
        db.transactions.create_index([('date',1),('_id',1)])
        db.notifications.create_index([('customerId',1),('categoryVersion',1),('kind',1)], unique=True)
        db.notifications.create_index([('customerId',1),('createdAt',-1),('_id',-1)])

    def run_transaction(self, callback):
        with self.client.start_session() as session:
            return session.with_transaction(callback, read_concern=ReadConcern('snapshot'),
                                            write_concern=WriteConcern('majority'), max_commit_time_ms=5000)

    def close(self):
        self.client.close()
