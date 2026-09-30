"""Immutable money records and bounded queries, including closed accounts."""
from datetime import timedelta, timezone

from bson import ObjectId

from .errors import BankError
from .models import Transaction, from_cents


def transaction_model(row):
    return Transaction(txn_id=str(row['_id']), account_id=str(row['accountId']),
                       customer_id=str(row['customerId']), type=row['type'],
                       amount=from_cents(row['amountCents']), balance_after=from_cents(row['balanceAfterCents']),
                       date=row['date'])


class TransactionRepository:
    def __init__(self, database):
        self.collection = database.transactions

    def add(self, record, session):
        return self.collection.insert_one(record, session=session).inserted_id

    def list(self, query, offset=0, limit=50):
        return [transaction_model(row) for row in self.collection.find(query)
                .sort([('date',1),('_id',1)]).skip(offset).limit(limit)]

    def get(self, transaction_id):
        row = self.collection.find_one({'_id':ObjectId(transaction_id)})
        if row is None:
            raise BankError(404, 'Transaction not found')
        return transaction_model(row)


class AuditService:
    def __init__(self, store):
        self.transactions = TransactionRepository(store.database)

    def list_transactions(self, customer_id=None, account_id=None, date_from=None, date_to=None, offset=0, limit=50):
        if date_from and date_to and date_from >= date_to:
            raise BankError(422, 'from must be earlier than to')
        query = {}
        if customer_id:
            query['customerId'] = ObjectId(customer_id)
        if account_id:
            query['accountId'] = ObjectId(account_id)
        if date_from or date_to:
            query['date'] = {}
            if date_from:
                query['date']['$gte'] = self._millisecond_boundary(date_from)
            if date_to:
                query['date']['$lt'] = self._millisecond_boundary(date_to)
        return self.transactions.list(query, offset, limit)

    @staticmethod
    def _millisecond_boundary(value):
        # BSON dates have millisecond precision. Round up so neither boundary
        # includes/excludes a stored record solely because the driver truncates.
        try:
            value = value.astimezone(timezone.utc)
            remainder = value.microsecond % 1000
            return value + timedelta(microseconds=1000-remainder) if remainder else value
        except (OverflowError, ValueError):
            raise BankError(422, 'Date boundary is outside the supported UTC range') from None

    def get_transaction(self, transaction_id):
        return self.transactions.get(transaction_id)
