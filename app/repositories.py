"""Store records here; the services decide when they can be changed."""
from threading import RLock

from .models import Account, Transaction, User


class UserRepository:
    def __init__(self):
        self.users: dict[int, User] = {}
        self.emails: dict[str, int] = {}
        # Counting existing records would reuse IDs after a customer is deleted.
        self.next_id = 1

    def get(self, user_id: int):
        return self.users.get(user_id)

    def add(self, user: User):
        self.users[user.user_id] = user
        self.emails[str(user.email).casefold()] = user.user_id


class AccountRepository:
    def __init__(self):
        self.accounts: dict[int, Account] = {}
        self.next_id = 1

    def get(self, account_id: int):
        return self.accounts.get(account_id)

    def save(self, account: Account):
        self.accounts[account.account_id] = account


class TransactionRepository:
    def __init__(self):
        self.transactions: dict[int, list[Transaction]] = {}
        self.next_id = 1

    def add(self, transaction: Transaction):
        self.transactions.setdefault(transaction.account_id, []).append(transaction)
        self.next_id += 1

    def for_account(self, account_id: int):
        return list(self.transactions.get(account_id, []))


class MemoryStore:
    def __init__(self):
        # A service can call another locked method while finishing the same request.
        self.lock = RLock()
        self.users = UserRepository()
        self.accounts = AccountRepository()
        self.transactions = TransactionRepository()
