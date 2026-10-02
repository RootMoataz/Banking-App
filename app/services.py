"""Customer CRUD and search, marketing preferences, account ownership, balance changes and transfers,
category-change notifications and the transaction audit, stored in MongoDB."""

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from bson import ObjectId
from pymongo.client_session import ClientSession
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .audit import decode_cursor, encode_cursor, fingerprint, utc
from .config import Settings
from .models import (Account, AccountCreate, AccountEdit, AmountRequest, AuditPage, Category, Customer,
                     CustomerSummary, MoneyResult, Notification, NotificationKind, Transaction, TransferRequest,
                     TransferResult, User, UserCreate)
from .money import MAX_CENTS, from_cents, to_cents
from .notifications import messages
from .repositories import (AccountRepository, CustomerRepository, NotificationRepository, TransactionRepository,
                           UserRepository)

logger = logging.getLogger(__name__)


class BankError(Exception):
    def __init__(self, status: int, detail: str, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.headers = headers


def category(total_cents: int, settings: Settings) -> Category:
    if total_cents < settings.low_cents:
        return "LOW"
    return "PREMIUM" if total_cents >= settings.premium_cents else "STANDARD"


def _in_transaction(db: Database, work: Callable[[ClientSession], object]):
    # The driver reruns work after a transient error such as a write conflict with another request.
    with db.client.start_session() as session:
        return session.with_transaction(work)


def _customer(doc: dict) -> Customer:
    return Customer(customer_id=str(doc["_id"]), name=doc["name"], email=doc["email"], created_at=doc["createdAt"],
                    marketing_enabled=doc.get("marketingEnabled", False))


def _account(doc: dict) -> Account:
    return Account(account_id=str(doc["_id"]), user_id=str(doc["customerId"]), user_name=doc["customerName"],
                   account_type=doc["accountType"], balance=from_cents(doc["balanceCents"]),
                   created_at=doc["createdAt"])


def _optional_id(value: ObjectId | None) -> str | None:
    return None if value is None else str(value)


def _transaction(doc: dict) -> Transaction:
    return Transaction(txn_id=str(doc["_id"]), account_id=str(doc["accountId"]), customer_id=str(doc["customerId"]),
                       type=doc["type"], amount=from_cents(doc["amountCents"]),
                       balance_after=from_cents(doc["balanceAfterCents"]), date=doc["createdAt"],
                       transfer_id=_optional_id(doc.get("transferId")),
                       from_account_id=_optional_id(doc.get("fromAccountId")),
                       to_account_id=_optional_id(doc.get("toAccountId")))


def _transfer(out: dict, into: dict) -> TransferResult:
    """The transfer as its two stored records describe it, so a replay matches the original response."""
    return TransferResult(transfer_id=str(out["transferId"]), from_account_id=str(out["fromAccountId"]),
                          to_account_id=str(out["toAccountId"]), amount=from_cents(out["amountCents"]),
                          from_balance_after=from_cents(out["balanceAfterCents"]),
                          to_balance_after=from_cents(into["balanceAfterCents"]), date=out["createdAt"])


def _notification(doc: dict) -> Notification:
    return Notification(notification_id=str(doc["_id"]), customer_id=str(doc["customerId"]),
                        category_version=doc["categoryVersion"], category=doc["category"], kind=doc["kind"],
                        template_id=doc["templateId"], message=doc["message"],
                        transaction_id=str(doc["transactionId"]), created_at=doc["createdAt"])


class CustomerService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.customers = CustomerRepository(db)
        self.accounts = AccountRepository(db)
        self.transactions = TransactionRepository(db)
        self.notifications = NotificationRepository(db)
        self.users = UserRepository(db)

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

    def get_all_customers(self, limit: int | None = None) -> list[Customer]:
        return [_customer(doc) for doc in self.customers.list(limit)]

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
            # The customer write makes a concurrent account creation or money operation for this customer conflict and
            # retry, so it then finds the customer or account gone and no orphan account is left.
            if self.customers.touch(customer_oid, session) is None:
                raise BankError(404, "Customer not found")
            # Every account goes with its customer, whatever its balance; a closing record keeps the removed balance in
            # the ledger. Transactions and notifications stay for audit.
            self.accounts.delete_for(customer_oid, self.transactions, session)
            self.users.delete_for_customer(customer_oid, session)  # their login ends with them
            self.customers.delete(customer_oid, session)

        _in_transaction(self.db, work)

    def set_marketing(self, customer_oid: ObjectId, enabled: bool) -> Customer:
        """Affects later messages only: nothing already stored is added or removed."""
        doc = self.customers.set_marketing(customer_oid, enabled)
        if doc is None:
            raise BankError(404, "Customer not found")
        return _customer(doc)

    def get_notifications(self, customer_oid: ObjectId, kind: NotificationKind | None,
                          limit: int) -> list[Notification]:
        if self.customers.get(customer_oid) is None:
            raise BankError(404, "Customer not found")
        return [_notification(doc) for doc in self.notifications.list(customer_oid, kind, limit)]


class AccountService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.customers = CustomerRepository(db)
        self.accounts = AccountRepository(db)
        self.transactions = TransactionRepository(db)
        self.notifications = NotificationRepository(db)

    def create_account(self, data: AccountCreate) -> Account:
        customer_oid = ObjectId(data.user_id)

        def work(session: ClientSession) -> dict:
            customer = self.customers.touch(customer_oid, session)
            if customer is None:
                raise BankError(404, "Customer not found")
            return self.accounts.insert(customer, data.account_type, session)

        return _account(_in_transaction(self.db, work))

    def get_all_accounts(self, limit: int | None = None) -> list[Account]:
        return [_account(doc) for doc in self.accounts.list(limit=limit)]

    def premium_accounts(self, threshold: Decimal | None, limit: int) -> list[Account]:
        cents = self.settings.premium_cents if threshold is None else to_cents(threshold)
        return [_account(doc) for doc in self.accounts.at_least(cents, limit)]

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

        # The balance change, its history record and any notification commit together or not at all.
        def work(session: ClientSession) -> tuple[str, dict]:
            # First on every attempt: the driver may rerun this after another request with the key committed, and a
            # replay must not depend on the account still existing or on the balance still passing the bound check.
            if key is not None and (prior := self.transactions.by_key(account_oid, key, session)) is not None:
                return "replay", prior
            account = self.accounts.get(account_oid, session)
            if account is None:
                raise BankError(404, "Account not found")
            # Serializes this change with every other change to the customer's accounts, records and preferences.
            owner = self._touch_owner(account, session)
            after = self.accounts.inc(account_oid, delta, cond, session)
            if after is None:
                raise BankError(400, "Insufficient funds" if kind == "WITHDRAW" else "Balance would exceed 99999999.99")
            record = self.transactions.insert(after, kind, cents, key, session)
            self._notify(owner, record, delta, session)
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

    def _touch_owner(self, account: dict, session: ClientSession) -> dict:
        owner = self.customers.touch(account["customerId"], session)
        if owner is None:
            logger.error("Account %s has no owner record for customer %s", account["_id"], account["customerId"])
            raise BankError(500, "Account owner record is missing")
        return owner

    def _notify(self, owner: dict, record: dict, delta: int, session: ClientSession) -> None:
        """Store the messages for owner's category change, if the balance change delta in record caused one."""
        # The owner's customer write makes a concurrent change to any of this customer's accounts conflict and retry,
        # so this total is current and two operations cannot both report the same category change.
        total_after = self.accounts.customer_total(owner["_id"], session)
        entered = category(total_after, self.settings)
        if entered == category(total_after - delta, self.settings):
            return
        # Every change counts, STANDARD included, so returning to a category later is a new message.
        version = self.customers.next_category_version(owner["_id"], session)
        for message in messages(entered, owner.get("marketingEnabled", False), self.settings):
            try:
                self.notifications.insert(record, entered, version, message, session)
            except DuplicateKeyError:
                # Not an idempotency replay: the customer's category counter and messages disagree.
                logger.error("Duplicate notification for customerId=%s categoryVersion=%s", owner["_id"], version)
                raise BankError(500, "Notification state is inconsistent for this customer") from None

    def transfer(self, data: TransferRequest, key: str | None = None) -> TransferResult:
        source, target = ObjectId(data.from_account_id), ObjectId(data.to_account_id)
        if source == target:
            raise BankError(422, "fromAccountId and toAccountId must be different accounts")
        cents = to_cents(data.amount)

        # Both balance changes, both records and any notifications commit together or not at all.
        def work(session: ClientSession) -> tuple[str, object]:
            # The key belongs to the source account, as for a withdrawal; checked first on every attempt, as there.
            if key is not None and (prior := self.transactions.by_key(source, key, session)) is not None:
                return "replay", prior
            accounts = {}
            for oid, missing in ((source, "Source account not found"), (target, "Destination account not found")):
                accounts[oid] = self.accounts.get(oid, session)
                if accounts[oid] is None:
                    raise BankError(404, missing)
            # Each owner is written once (one customer may own both accounts), in ID order, so this transfer conflicts
            # with every other change to either customer; the loser of a conflict retries.
            owners = {}
            for account in sorted(accounts.values(), key=lambda a: a["customerId"]):
                if account["customerId"] not in owners:
                    owners[account["customerId"]] = self._touch_owner(account, session)
            # Each bound is checked in the same update that changes the balance, as in _transact.
            debited = self.accounts.inc(source, -cents, {"balanceCents": {"$gte": cents}}, session)
            if debited is None:
                raise BankError(400, "Insufficient funds")
            credited = self.accounts.inc(target, cents, {"balanceCents": {"$lte": MAX_CENTS - cents}}, session)
            if credited is None:
                raise BankError(400, "Balance would exceed 99999999.99")  # aborting also undoes the debit
            legs = {"transferId": ObjectId(), "fromAccountId": source, "toAccountId": target}
            out = self.transactions.insert(debited, "TRANSFER_OUT", cents, key, session, legs)
            into = self.transactions.insert(credited, "TRANSFER_IN", cents, None, session, legs)
            # Between one customer's own accounts the total does not change, so there is no category change.
            if debited["customerId"] != credited["customerId"]:
                self._notify(owners[debited["customerId"]], out, -cents, session)
                self._notify(owners[credited["customerId"]], into, cents, session)
            return "done", (out, into)

        try:
            outcome, result = _in_transaction(self.db, work)
        except DuplicateKeyError:
            # As in _transact: a request with the same key committed first and this one moved no money.
            prior = self.transactions.by_key(source, key) if key is not None else None
            if prior is None:
                raise
            outcome, result = "replay", prior
        if outcome == "done":
            return _transfer(*result)
        if result["type"] != "TRANSFER_OUT" or result["amountCents"] != cents or result["toAccountId"] != target:
            raise BankError(409, "Idempotency-Key was already used for a different request")
        return _transfer(result, self.transactions.credit_of(result["transferId"]))

    def get_transactions(self, account_oid: ObjectId, limit: int | None = None) -> list[Transaction]:
        self.get_account(account_oid)
        return [_transaction(doc) for doc in self.transactions.for_account(account_oid, limit)]

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
