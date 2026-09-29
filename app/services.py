"""Customer CRUD, account ownership, and balance changes."""

from datetime import datetime, timezone
from decimal import Decimal

from .models import (Account, AccountCreate, AccountEdit, AmountRequest,
                     Customer, Transaction, User, UserCreate)
from .repositories import MemoryStore


class BankError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class CustomerService:
    def __init__(self, store: MemoryStore):
        self.store = store

    def create_user(self, data: UserCreate) -> User:
        with self.store.lock:
            if str(data.email).casefold() in self.store.users.emails:
                raise BankError(409, "A user with this email already exists")
            user = User(user_id=self.store.users.next_id, name=data.name,
                        email=data.email, created_at=datetime.now(timezone.utc))
            self.store.users.add(user)
            self.store.users.next_id += 1
            return user

    @staticmethod
    def _customer(user: User) -> Customer:
        return Customer(customer_id=user.user_id, name=user.name,
                        email=user.email, created_at=user.created_at)

    def create_customer(self, data: UserCreate) -> Customer:
        return self._customer(self.create_user(data))

    def get_customer(self, customer_id: int) -> Customer:
        with self.store.lock:
            user = self.store.users.get(customer_id)
            if user is None:
                raise BankError(404, "Customer not found")
            return self._customer(user)

    def get_all_customers(self) -> list[Customer]:
        with self.store.lock:
            return [self._customer(user) for user in self.store.users.users.values()]

    def edit_customer(self, customer_id: int, data: UserCreate) -> Customer:
        with self.store.lock:
            self.get_customer(customer_id)
            owner = self.store.users.emails.get(str(data.email).casefold())
            if owner is not None and owner != customer_id:
                raise BankError(409, "A customer with this email already exists")
            current = self.store.users.get(customer_id)
            updated = current.model_copy(update={"name": data.name, "email": data.email})
            del self.store.users.emails[str(current.email).casefold()]
            self.store.users.add(updated)
            # Keep the account's cached display name in sync with the customer.
            for account in list(self.store.accounts.accounts.values()):
                if account.user_id == customer_id:
                    self.store.accounts.save(account.model_copy(update={"user_name": data.name}))
            return self._customer(updated)

    def delete_customer(self, customer_id: int) -> None:
        with self.store.lock:
            self.get_customer(customer_id)
            if any(a.user_id == customer_id for a in self.store.accounts.accounts.values()):
                raise BankError(409, "Delete the customer's accounts first")
            user = self.store.users.users.pop(customer_id)
            del self.store.users.emails[str(user.email).casefold()]


class AccountService:
    MAX_BALANCE = Decimal("99999999.99")  # The largest value that fits DECIMAL(10,2) in the brief.

    def __init__(self, store: MemoryStore):
        self.store = store

    def create_account(self, data: AccountCreate) -> Account:
        with self.store.lock:
            user = self.store.users.get(data.user_id)
            if user is None:
                raise BankError(404, "Customer not found")
            account = Account(account_id=self.store.accounts.next_id,
                              user_id=user.user_id, user_name=user.name,
                              account_type=data.account_type,
                              created_at=datetime.now(timezone.utc))
            self.store.accounts.save(account)
            self.store.accounts.next_id += 1
            return account

    def get_all_accounts(self) -> list[Account]:
        with self.store.lock:
            return list(self.store.accounts.accounts.values())

    def get_customer_accounts(self, customer_id: int) -> list[Account]:
        with self.store.lock:
            if self.store.users.get(customer_id) is None:
                raise BankError(404, "Customer not found")
            return [a for a in self.store.accounts.accounts.values() if a.user_id == customer_id]

    def edit_account(self, account_id: int, data: AccountEdit) -> Account:
        with self.store.lock:
            account = self.get_account(account_id)
            updated = account.model_copy(update={"account_type": data.account_type})
            self.store.accounts.save(updated)
            return updated

    def delete_account(self, account_id: int) -> None:
        with self.store.lock:
            account = self.get_account(account_id)
            if account.balance != 0:
                raise BankError(409, "Withdraw the remaining balance before deleting the account")
            del self.store.accounts.accounts[account_id]
            self.store.transactions.transactions.pop(account_id, None)

    def get_account(self, account_id: int) -> Account:
        with self.store.lock:
            account = self.store.accounts.get(account_id)
            if account is None:
                raise BankError(404, "Account not found")
            return account

    def deposit(self, account_id: int, data: AmountRequest) -> Account:
        return self._transact(account_id, data, "DEPOSIT")

    def withdraw(self, account_id: int, data: AmountRequest) -> Account:
        return self._transact(account_id, data, "WITHDRAW")

    def _transact(self, account_id: int, data: AmountRequest, kind: str) -> Account:
        # Keep the balance check and update together so two withdrawals can't spend the same money.
        with self.store.lock:
            account = self.get_account(account_id)
            amount = data.amount.quantize(Decimal("0.01"))
            if kind == "WITHDRAW" and amount > account.balance:
                raise BankError(400, "Insufficient funds")
            balance = account.balance + (amount if kind == "DEPOSIT" else -amount)
            if balance > self.MAX_BALANCE:
                raise BankError(400, "Balance would exceed 99999999.99")
            updated = account.model_copy(update={"balance": balance})
            transaction = Transaction(txn_id=self.store.transactions.next_id,
                                      account_id=account_id, type=kind, amount=amount,
                                      date=datetime.now(timezone.utc))
            self.store.accounts.save(updated)
            self.store.transactions.add(transaction)
            return updated

    def get_transactions(self, account_id: int) -> list[Transaction]:
        with self.store.lock:
            self.get_account(account_id)
            return self.store.transactions.for_account(account_id)
