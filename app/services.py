"""Banking operations commit together with their audit records and messages."""
from datetime import datetime, timezone

from bson import ObjectId

from .audit import TransactionRepository
from .errors import BankError
from .models import Account, Customer, User, from_cents, to_cents
from .notifications import NotificationRepository, category_for, message_templates
from .repositories import AccountRepository, CustomerRepository


def customer_model(row):
    return Customer(customer_id=str(row['_id']), name=row['name'], email=row['email'],
                    created_at=row['createdAt'], total_balance=from_cents(row['totalCents']),
                    category=row['category'], marketing_enabled=row['marketingEnabled'])


def account_model(row, customer):
    return Account(account_id=str(row['_id']), user_id=str(row['customerId']),
                   user_name=customer['name'], account_type=row['accountType'],
                   balance=from_cents(row['balanceCents']), created_at=row['createdAt'])


class CustomerService:
    def __init__(self, store):
        self.store = store
        self.customers = CustomerRepository(store.database)
        self.accounts = AccountRepository(store.database)
        self.notifications = NotificationRepository(store.database)

    def create_customer(self, data):
        return self.store.run_transaction(lambda session: customer_model(self.customers.add(data, session)))

    def create_user(self, data):
        customer = self.create_customer(data)
        return User(user_id=customer.customer_id, name=customer.name, email=customer.email,
                    created_at=customer.created_at)

    def get_customer(self, customer_id):
        return customer_model(self.customers.get(customer_id))

    def get_all_customers(self, search=None, category=None, offset=0, limit=50):
        return [customer_model(row) for row in self.customers.list(search, category, offset, limit)]

    def edit_customer(self, customer_id, data):
        def edit(session):
            self.customers.touch(customer_id, session)
            return customer_model(self.customers.update(customer_id, dict(name=data.name, email=str(data.email),
                                               normalizedEmail=str(data.email).casefold()), session))
        return self.store.run_transaction(edit)

    def delete_customer(self, customer_id):
        def archive(session):
            self.customers.touch(customer_id, session)
            if self.accounts.has_active(customer_id, session):
                raise BankError(409, "Close the customer's accounts first")
            self.customers.update(customer_id, dict(active=False, archivedAt=datetime.now(timezone.utc)), session)
        self.store.run_transaction(archive)

    def set_preferences(self, customer_id, marketing_enabled):
        def update(session):
            self.customers.touch(customer_id, session)
            return customer_model(self.customers.update(customer_id, {'marketingEnabled':marketing_enabled}, session))
        return self.store.run_transaction(update)

    def get_notifications(self, customer_id, kind=None, offset=0, limit=50):
        self.customers.get(customer_id)
        return self.notifications.list_for_customer(ObjectId(customer_id), kind, offset, limit)


class AccountService:
    def __init__(self, store):
        self.store = store
        self.accounts = AccountRepository(store.database)
        self.customers = CustomerRepository(store.database)
        self.transactions = TransactionRepository(store.database)
        self.notifications = NotificationRepository(store.database)

    def create_account(self, data):
        def create(session):
            owner = self.customers.touch(data.user_id, session)
            row = self.accounts.add(data.user_id, data.account_type, session)
            if not owner['initialized']:
                version = owner['categoryVersion'] + 1
                self.customers.update(owner['_id'], {'initialized':True,'categoryVersion':version}, session)
                self.notifications.add_messages(owner['_id'], version,
                    message_templates('LOW', owner['marketingEnabled']), None, session)
            return account_model(row, owner)
        return self.store.run_transaction(create)

    def get_account(self, account_id):
        row = self.accounts.get(account_id)
        return account_model(row, self.customers.get(row['customerId']))

    def get_all_accounts(self, offset=0, limit=50):
        return [account_model(row, self.customers.get(row['customerId']))
                for row in self.accounts.list(offset=offset, limit=limit)]

    def get_customer_accounts(self, customer_id, offset=0, limit=50):
        owner = self.customers.get(customer_id)
        return [account_model(row, owner) for row in self.accounts.list(customer_id, offset, limit)]

    def edit_account(self, account_id, data):
        def edit(session):
            row = self.accounts.get(account_id, session)
            owner = self.customers.touch(row['customerId'], session)
            row = self.accounts.update(account_id, {'accountType':data.account_type}, session)
            return account_model(row, owner)
        return self.store.run_transaction(edit)

    def delete_account(self, account_id):
        def close(session):
            row = self.accounts.get(account_id, session)
            self.customers.touch(row['customerId'], session)
            if row['balanceCents']:
                raise BankError(409, 'Withdraw the remaining balance before closing the account')
            self.accounts.update(account_id, dict(active=False, closedAt=datetime.now(timezone.utc)), session)
        self.store.run_transaction(close)

    def deposit(self, account_id, data):
        return self._transact(account_id, data, 'DEPOSIT')

    def withdraw(self, account_id, data):
        return self._transact(account_id, data, 'WITHDRAW')

    def _transact(self, account_id, data, kind):
        amount = to_cents(data.amount)
        delta = amount if kind == 'DEPOSIT' else -amount

        def change(session):
            row = self.accounts.get(account_id, session)
            owner = self.customers.touch(row['customerId'], session)
            total = owner['totalCents'] + delta
            if total > 9223372036854775807:
                raise BankError(400, 'Combined customer balance exceeds the storage limit')
            row = self.accounts.change_balance(account_id, delta, session)
            category = category_for(total)
            changed = category != owner['category']
            version = owner['categoryVersion'] + int(changed)
            self.customers.update(owner['_id'], dict(totalCents=total, category=category, categoryVersion=version), session)
            transaction_id = self.transactions.add(dict(accountId=row['_id'], customerId=owner['_id'],
                type=kind, amountCents=amount, balanceAfterCents=row['balanceCents'], date=datetime.now(timezone.utc)), session)
            if changed:
                self.notifications.add_messages(owner['_id'], version,
                    message_templates(category, owner['marketingEnabled']), transaction_id, session, category)
            return account_model(row, owner)
        return self.store.run_transaction(change)

    def get_transactions(self, account_id, offset=0, limit=50):
        self.accounts.get(account_id, include_closed=True)
        return self.transactions.list({'accountId':ObjectId(account_id)}, offset, limit)
