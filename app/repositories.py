"""Customer and account queries. Mutations use the caller's transaction session."""
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from .errors import BankError


class CustomerRepository:
    def __init__(self, database):
        self.collection = database.customers

    def get(self, customer_id, session=None):
        row = self.collection.find_one({'_id':ObjectId(customer_id), 'active':True}, session=session)
        if row is None:
            raise BankError(404, 'Customer not found')
        return row

    def touch(self, customer_id, session):
        # Every operation for one customer writes this document, including preferences.
        row = self.collection.find_one_and_update({'_id':ObjectId(customer_id),'active':True},
                    {'$inc':{'revision':1}}, return_document=ReturnDocument.AFTER, session=session)
        if row is None:
            raise BankError(404, 'Customer not found')
        return row

    def add(self, data, session):
        row = dict(name=data.name, email=str(data.email), normalizedEmail=str(data.email).casefold(),
                   createdAt=datetime.now(timezone.utc), active=True, totalCents=0, category='LOW',
                   categoryVersion=0, marketingEnabled=False, initialized=False, revision=0)
        self.collection.insert_one(row, session=session)
        # Read back BSON's millisecond timestamp so POST and later GET agree.
        return self.collection.find_one({'_id':row['_id']}, session=session)

    def update(self, customer_id, values, session):
        return self.collection.find_one_and_update({'_id':ObjectId(customer_id)}, {'$set':values},
                                                   return_document=ReturnDocument.AFTER, session=session)

    def list(self, search=None, category=None, offset=0, limit=50):
        query = {'active':True}
        if search:
            literal = {'$regex':re.escape(search), '$options':'i'}
            query['$or'] = [{'name':literal}, {'email':literal}]
        if category:
            query['category'] = category
        return list(self.collection.find(query).sort([('createdAt',1),('_id',1)]).skip(offset).limit(limit))


class AccountRepository:
    def __init__(self, database):
        self.collection = database.accounts

    def get(self, account_id, session=None, include_closed=False):
        query = {'_id':ObjectId(account_id)}
        if not include_closed:
            query['active'] = True
        row = self.collection.find_one(query, session=session)
        if row is None:
            raise BankError(404, 'Account not found')
        return row

    def add(self, customer_id, account_type, session):
        row = dict(customerId=ObjectId(customer_id), accountType=account_type, balanceCents=0,
                   createdAt=datetime.now(timezone.utc), active=True)
        self.collection.insert_one(row, session=session)
        return self.collection.find_one({'_id':row['_id']}, session=session)

    def update(self, account_id, values, session):
        return self.collection.find_one_and_update({'_id':ObjectId(account_id)}, {'$set':values},
                                                   return_document=ReturnDocument.AFTER, session=session)

    def change_balance(self, account_id, delta, session):
        bounds = {'$gte':-delta} if delta < 0 else {'$lte':9999999999-delta}
        row = self.collection.find_one_and_update({'_id':ObjectId(account_id), 'active':True, 'balanceCents':bounds},
                    {'$inc':{'balanceCents':delta}}, return_document=ReturnDocument.AFTER, session=session)
        if row is None:
            raise BankError(400, 'Insufficient funds' if delta < 0 else 'Balance would exceed 99999999.99')
        return row

    def has_active(self, customer_id, session):
        return self.collection.find_one({'customerId':ObjectId(customer_id), 'active':True}, session=session) is not None

    def list(self, customer_id=None, offset=0, limit=50):
        query = {'active':True}
        if customer_id:
            query['customerId'] = ObjectId(customer_id)
        return list(self.collection.find(query).sort([('createdAt',1),('_id',1)]).skip(offset).limit(limit))
