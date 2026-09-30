"""Customer CRUD and search, account ownership, balance changes, threshold alerts and the transaction audit, stored in
MongoDB."""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from bson import ObjectId
from pymongo.client_session import ClientSession
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .audit import decode_cursor, encode_cursor, fingerprint, utc
from .config import Settings
from .models import (Account, AccountCreate, AccountEdit, Alert, AmountRequest, AuditPage, Category, Customer,
                     CustomerSummary, MoneyResult, Transaction, User, UserCreate)
from .money import MAX_CENTS, from_cents, to_cents
from .repositories import AccountRepository, AlertRepository, CustomerRepository, TransactionRepository


class BankError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def category(total_cents: int, settings: Settings) -> Category:
    if total_cents < settings.low_cents:
        return "LOW"
    return "PREMIUM" if total_cents >= settings.premium_cents else "STANDARD"


def crossing(before: int, after: int, settings: Settings) -> str | None:
    """The alert for a change of a customer's total from before to after, if it crossed a threshold."""
    if before >= settings.low_cents > after:
        return "LOW_BALANCE"
    if before < settings.premium_cents <= after:
        return "HIGH_BALANCE"
    return None


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
    return Transaction(txn_id=str(doc["_id"]), account_id=str(doc["accountId"]), customer_id=str(doc["customerId"]),
                       type=doc["type"], amount=from_cents(doc["amountCents"]),
                       balance_after=from_cents(doc["balanceAfterCents"]), date=doc["createdAt"])


def _alert(doc: dict) -> Alert:
    return Alert(alert_id=str(doc["_id"]), customer_id=str(doc["customerId"]), account_id=str(doc["accountId"]),
                 transaction_id=str(doc["transactionId"]), type=doc["type"], total_balance=from_cents(doc["totalCents"]),
                 threshold=from_cents(doc["thresholdCents"]), created_at=doc["createdAt"])


class CustomerService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
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

    def search(self, name: str | None, email: str | None, category_: Category | None, min_balance: Decimal | None,
               max_balance: Decimal | None, limit: int) -> list[CustomerSummary]:
        low, premium = self.settings.low_cents, self.settings.premium_cents
        # Category and balance bounds combine into one condition on the customer's total.
        cond = {"LOW": {"$lt": low}, "STANDARD": {"$gte": low, "$lt": premium},
                "PREMIUM": {"$gte": premium}, None: {}}[category_]
        if min_balance is not None:
            cond["$gte"] = max(cond.get("$gte", 0), to_cents(min_balance))
        if max_balance is not None:
            cond["$lte"] = to_cents(max_balance)
        return [CustomerSummary(customer_id=str(doc["_id"]), name=doc["name"], email=doc["email"],
                                total_balance=from_cents(doc["totalCents"]),
                                category=category(doc["totalCents"], self.settings))
                for doc in self.customers.search(name, email, cond, limit)]

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
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.customers = CustomerRepository(db)
        self.accounts = AccountRepository(db)
        self.transactions = TransactionRepository(db)
        self.alerts = AlertRepository(db)

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

    def deposit(self, account_oid: ObjectId, data: AmountRequest, key: str | None = None) -> MoneyResult:
        return self._transact(account_oid, data, "DEPOSIT", key)

    def withdraw(self, account_oid: ObjectId, data: AmountRequest, key: str | None = None) -> MoneyResult:
        return self._transact(account_oid, data, "WITHDRAW", key)

    def _transact(self, account_oid: ObjectId, data: AmountRequest, kind: str, key: str | None) -> MoneyResult:
        # The database checks the bound and changes the balance in one update, so two
        # withdrawals can't spend the same money.
        cents = to_cents(data.amount)
        if kind == "WITHDRAW":
            delta, cond = -cents, {"balanceCents": {"$gte": cents}}
        else:
            delta, cond = cents, {"balanceCents": {"$lte": MAX_CENTS - cents}}

        # The balance change, its history record and any alert commit together or not at all.
        def work(session: ClientSession) -> tuple[str, dict]:
            # First on every attempt: the driver may rerun this after another request with the key committed, and a
            # replay must not depend on the account still existing or on the balance still passing the bound check.
            if key is not None and (prior := self.transactions.by_key(account_oid, key, session)) is not None:
                return "replay", prior
            account = self.accounts.get(account_oid, session)
            if account is None:
                raise BankError(404, "Account not found")
            # Serializes this change with every other change to the customer's accounts and records.
            if self.customers.touch(account["customerId"], session) is None:
                raise BankError(500, "Account owner record is missing")
            after = self.accounts.inc(account_oid, delta, cond, session)
            if after is None:
                raise BankError(400, "Insufficient funds" if kind == "WITHDRAW" else "Balance would exceed 99999999.99")
            record = self.transactions.insert(after, kind, cents, key, session)
            # The customer write above makes a concurrent change to any of this customer's accounts conflict and retry,
            # so this total is current and two operations cannot both report the same crossing.
            total_after = self.accounts.customer_total(after["customerId"], session)
            alert = crossing(total_after - delta, total_after, self.settings)
            if alert is not None:
                threshold = self.settings.low_cents if alert == "LOW_BALANCE" else self.settings.premium_cents
                self.alerts.insert(record, alert, total_after, threshold, session)
            return "done", after

        try:
            outcome, doc = _in_transaction(self.db, work)
        except DuplicateKeyError:
            # A request with the same key committed after this one's lookup; the unique index rejected this insert and
            # the whole transaction aborted, so no money moved. Replay the committed one.
            prior = self.transactions.by_key(account_oid, key) if key is not None else None
            if prior is None:
                raise
            return self._replay(prior, kind, cents)
        return self._replay(doc, kind, cents) if outcome == "replay" else _account(doc)

    def _replay(self, prior: dict, kind: str, cents: int) -> MoneyResult:
        if prior["type"] != kind or prior["amountCents"] != cents:
            raise BankError(409, "Idempotency-Key was already used for a different request")
        account = self.accounts.get(prior["accountId"])
        if account is None:
            return _transaction(prior)
        # The balance this operation produced, not the live one.
        return _account({**account, "balanceCents": prior["balanceAfterCents"]})

    def get_transactions(self, account_oid: ObjectId) -> list[Transaction]:
        self.get_account(account_oid)
        return [_transaction(doc) for doc in self.transactions.for_account(account_oid)]

    def get_alerts(self, customer_oid: ObjectId | None, limit: int) -> list[Alert]:
        # Alerts outlive their customer, like transactions, so an unknown customer just has none.
        return [_alert(doc) for doc in self.alerts.list(customer_oid, limit)]

    def audit(self, customer_id: str | None, account_id: str | None, start: datetime | None, end: datetime | None,
              limit: int, cursor: str | None) -> AuditPage:
        # No existence checks: records outlive their account and customer, so a deleted ID still has history.
        if customer_id is None and account_id is None:
            raise BankError(422, "Give customerId, accountId or both")
        try:
            fp = fingerprint(customer_id, account_id, start, end)
        except ValueError:  # e.g. year 1 with a positive offset has no UTC equivalent
            raise BankError(422, "from or to is out of range") from None
        after = None
        if cursor is not None:
            try:
                t, oid, cursor_fp = decode_cursor(cursor)
            except ValueError:
                raise BankError(422, "Malformed cursor") from None
            if cursor_fp != fp:
                raise BankError(422, "The cursor was issued for different filters")
            after = (t, oid)
        filters = {}
        if customer_id is not None:
            filters["customerId"] = ObjectId(customer_id)
        if account_id is not None:
            filters["accountId"] = ObjectId(account_id)
        window = {op: utc(t) for op, t in (("$gte", start), ("$lt", end)) if t is not None}
        if window:
            filters["createdAt"] = window
        docs = self.transactions.page(filters, after, limit + 1)  # the extra record only shows another page exists
        items = docs[:limit]
        more = len(docs) > limit
        return AuditPage(items=[_transaction(doc) for doc in items],
                         next_cursor=encode_cursor(items[-1]["createdAt"], items[-1]["_id"], fp) if more else None)
