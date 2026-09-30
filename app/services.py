"""Customer CRUD, account ownership, and balance changes stored in MongoDB."""

from collections.abc import Callable

from bson import ObjectId
from pymongo.client_session import ClientSession
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .models import (Account, AccountCreate, AccountEdit, AmountRequest,
                     Customer, Transaction, User, UserCreate)
from .money import MAX_CENTS, from_cents, to_cents
from .repositories import AccountRepository, CustomerRepository, TransactionRepository


class BankError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _in_transaction(db: Database, work: Callable[[ClientSession], object]):
    # The driver reruns work after a transient error such as a write conflict with another request.
    with db.client.start_session() as session:
        return session.with_transaction(work)


def _customer(doc: dict) -> Customer:
    return Customer(customer_id=str(doc["_id"]), name=doc["name"], email=doc["email"], created_at=doc["createdAt"])


def _account(doc: dict) -> Account:
    return Account(account_id=str(doc["_id"]), user_id=str(doc["customerId"]), user_name=doc["customerName"],
                   account_type=doc["accountType"], balance=from_cents(doc["balanceCents"]),
                   created_at=doc["createdAt"])


def _transaction(doc: dict) -> Transaction:
    return Transaction(txn_id=str(doc["_id"]), account_id=str(doc["accountId"]), type=doc["type"],
                       amount=from_cents(doc["amountCents"]), date=doc["createdAt"])


class CustomerService:
    def __init__(self, db: Database):
        self.db = db
        self.customers = CustomerRepository(db)
        self.accounts = AccountRepository(db)

    def _insert(self, data: UserCreate) -> dict:
        try:
            return self.customers.insert(data.name, str(data.email))
        except DuplicateKeyError:
            raise BankError(409, "A user with this email already exists") from None

    def create_user(self, data: UserCreate) -> User:
        doc = self._insert(data)
        return User(user_id=str(doc["_id"]), name=doc["name"], email=doc["email"], created_at=doc["createdAt"])

    def create_customer(self, data: UserCreate) -> Customer:
        return _customer(self._insert(data))

    def get_customer(self, customer_oid: ObjectId) -> Customer:
        doc = self.customers.get(customer_oid)
        if doc is None:
            raise BankError(404, "Customer not found")
        return _customer(doc)

    def get_all_customers(self) -> list[Customer]:
        return [_customer(doc) for doc in self.customers.list()]

    def edit_customer(self, customer_oid: ObjectId, data: UserCreate) -> Customer:
        def work(session: ClientSession) -> dict:
            if self.customers.touch(customer_oid, session) is None:
                raise BankError(404, "Customer not found")
            updated = self.customers.update(customer_oid, data.name, str(data.email), session)
            # Keep the accounts' cached display name in sync with the customer.
            self.accounts.rename_owner(customer_oid, data.name, session)
            return updated

        try:
            return _customer(_in_transaction(self.db, work))
        except DuplicateKeyError:
            raise BankError(409, "A customer with this email already exists") from None

    def delete_customer(self, customer_oid: ObjectId) -> None:
        def work(session: ClientSession) -> None:
            if self.customers.touch(customer_oid, session) is None:
                raise BankError(404, "Customer not found")
            if self.accounts.any_for(customer_oid, session):
                raise BankError(409, "Delete the customer's accounts first")
            self.customers.delete(customer_oid, session)

        _in_transaction(self.db, work)


class AccountService:
    def __init__(self, db: Database):
        self.db = db
        self.customers = CustomerRepository(db)
        self.accounts = AccountRepository(db)
        self.transactions = TransactionRepository(db)

    def create_account(self, data: AccountCreate) -> Account:
        customer_oid = ObjectId(data.user_id)

        def work(session: ClientSession) -> dict:
            customer = self.customers.touch(customer_oid, session)
            if customer is None:
                raise BankError(404, "Customer not found")
            return self.accounts.insert(customer, data.account_type, session)

        return _account(_in_transaction(self.db, work))

    def get_all_accounts(self) -> list[Account]:
        return [_account(doc) for doc in self.accounts.list()]

    def get_customer_accounts(self, customer_oid: ObjectId) -> list[Account]:
        if self.customers.get(customer_oid) is None:
            raise BankError(404, "Customer not found")
        return [_account(doc) for doc in self.accounts.list(customer_oid)]

    def edit_account(self, account_oid: ObjectId, data: AccountEdit) -> Account:
        doc = self.accounts.update_type(account_oid, data.account_type)
        if doc is None:
            raise BankError(404, "Account not found")
        return _account(doc)

    def delete_account(self, account_oid: ObjectId) -> None:
        # The account's transactions stay: they keep the account and customer IDs for later audits.
        def work(session: ClientSession) -> None:
            account = self.accounts.get(account_oid, session)
            if account is None:
                raise BankError(404, "Account not found")
            self.customers.touch(account["customerId"], session)
            if account["balanceCents"] != 0:
                raise BankError(409, "Withdraw the remaining balance before deleting the account")
            self.accounts.delete(account_oid, session)

        _in_transaction(self.db, work)

    def get_account(self, account_oid: ObjectId) -> Account:
        doc = self.accounts.get(account_oid)
        if doc is None:
            raise BankError(404, "Account not found")
        return _account(doc)

    def deposit(self, account_oid: ObjectId, data: AmountRequest) -> Account:
        return self._transact(account_oid, data, "DEPOSIT")

    def withdraw(self, account_oid: ObjectId, data: AmountRequest) -> Account:
        return self._transact(account_oid, data, "WITHDRAW")

    def _transact(self, account_oid: ObjectId, data: AmountRequest, kind: str) -> Account:
        # The database checks the bound and changes the balance in one update, so two
        # withdrawals can't spend the same money.
        cents = to_cents(data.amount)
        if kind == "WITHDRAW":
            delta, cond = -cents, {"balanceCents": {"$gte": cents}}
        else:
            delta, cond = cents, {"balanceCents": {"$lte": MAX_CENTS - cents}}
        account = self.accounts.inc(account_oid, delta, cond)
        if account is None:
            self.get_account(account_oid)  # 404 when the account is missing
            raise BankError(400, "Insufficient funds" if kind == "WITHDRAW" else "Balance would exceed 99999999.99")
        self.transactions.insert(account, kind, cents)
        return _account(account)

    def get_transactions(self, account_oid: ObjectId) -> list[Transaction]:
        self.get_account(account_oid)
        return [_transaction(doc) for doc in self.transactions.for_account(account_oid)]
