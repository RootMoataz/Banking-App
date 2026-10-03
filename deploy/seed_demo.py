"""Create (or restore) the public demo accounts in the database the app settings point at.

Usage, from the repository root, with MONGODB_URI, MONGODB_DB and JWT_SECRET in the environment:
    python deploy/seed_demo.py --yes            create the demo users that do not exist yet
    python deploy/seed_demo.py --yes --reset    first remove the demo users, customers, accounts, history and
                                                messages (found by the demo emails below), then create them again
Nothing is written without --yes. Only the demo emails are touched; no other user or customer is read or changed.
Every demo account shares one public password, listed in DEMO.md. The data is synthetic.
"""
import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import AuthService, hash_password  # noqa: E402
from app.config import Settings, load_settings  # noqa: E402
from app.db import ensure_indexes, get_database  # noqa: E402
from app.models import AccountCreate, AmountRequest, RegisterRequest, TransferRequest  # noqa: E402
from app.repositories import UserRepository  # noqa: E402
from app.services import AccountService, CustomerService  # noqa: E402

DEMO_PASSWORD = "paper-demo-ledger-2026"
ADMIN = ("demo-admin@example.com", "Demo Admin")

# name, email, opted into marketing, then the steps per account. A step is ("deposit" | "withdraw", amount) or
# ("transfer", amount, "Checking" | "Savings" as the destination); a transfer leaves the account it is listed under.
# With the default thresholds (100.00 and 10000.00) the totals are 60.00 LOW, 1849.75 STANDARD, 28000.00 PREMIUM.
CUSTOMERS = [
    ("Demo Low", "demo-low@example.com", False,
     {"Checking": [("deposit", "250.00"), ("withdraw", "200.00"), ("transfer", "5.00", "Savings")],
      "Savings": [("deposit", "10.00")]}),
    ("Demo Standard", "demo-standard@example.com", False,
     {"Checking": [("deposit", "1200.00"), ("withdraw", "150.25"), ("transfer", "300.00", "Savings")],
      "Savings": [("deposit", "800.00")]}),
    ("Demo Premium", "demo-premium@example.com", True,
     {"Checking": [("deposit", "3500.00"), ("withdraw", "500.00")],
      "Savings": [("deposit", "25000.00"), ("transfer", "1000.00", "Checking")]}),
]
DEMO_EMAILS = [ADMIN[0], *(c[1] for c in CUSTOMERS)]


def reset(db) -> int:
    """Remove everything the demo owns, found through the demo emails only. Returns the number of users removed."""
    keys = [email.lower() for email in DEMO_EMAILS]
    customer_ids = [c["_id"] for c in db.customers.find({"emailKey": {"$in": keys}}, {"_id": 1})]
    db.accounts.delete_many({"customerId": {"$in": customer_ids}})
    db.transactions.delete_many({"customerId": {"$in": customer_ids}})
    db.notifications.delete_many({"customerId": {"$in": customer_ids}})
    db.customers.delete_many({"_id": {"$in": customer_ids}})
    db.login_attempts.delete_many({"emailKey": {"$in": keys}})  # a lockout from visitors is cleared too
    return db.users.delete_many({"emailKey": {"$in": keys}}).deleted_count


def _seed_customer(db, settings: Settings, name: str, email: str, marketing: bool, plan: dict) -> None:
    auth, customers, accounts = AuthService(db, settings), CustomerService(db, settings), AccountService(db, settings)
    user = auth.register(RegisterRequest(name=name, email=email, password=DEMO_PASSWORD)).user
    owner = ObjectId(user.customer_id)
    if marketing:  # before any money moves, so the category messages include the marketing ones
        customers.set_marketing(owner, True)
    ids = {kind: ObjectId(accounts.create_account(AccountCreate(user_id=str(owner), account_type=kind.upper())).account_id)
           for kind in plan}
    for kind, steps in plan.items():
        for step in steps:
            action, amount = step[0], Decimal(step[1])
            if action == "transfer":
                accounts.transfer(TransferRequest(from_account_id=str(ids[kind]), to_account_id=str(ids[step[2]]),
                                                  amount=amount))
            else:
                getattr(accounts, action)(ids[kind], AmountRequest(amount=amount))


def seed(db, settings: Settings, reset_first: bool = False) -> dict:
    """Create the demo users that are missing. With reset_first, remove the demo data first so all of it is new."""
    removed = reset(db) if reset_first else 0
    users, created = UserRepository(db), 0
    if users.by_email(ADMIN[0]) is None:
        users.insert(ADMIN[0], hash_password(DEMO_PASSWORD), "ADMIN", None, ADMIN[1])
        created += 1
    for name, email, marketing, plan in CUSTOMERS:
        if users.by_email(email) is None:
            _seed_customer(db, settings, name, email, marketing, plan)
            created += 1
    return {"removed": removed, "created": created}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="really write to the database")
    parser.add_argument("--reset", action="store_true", help="remove the demo data first, then create it again")
    args = parser.parse_args()
    if not os.environ.get("MONGODB_DB"):
        print("Refusing to run: set MONGODB_DB in the environment, so the target database is never a default.")
        return 2
    settings = load_settings()
    print(f"Database: {settings.mongodb_db}")
    print(f"Demo emails: {', '.join(DEMO_EMAILS)}")
    print("Mode: " + ("remove the demo data, then create it" if args.reset else "create the missing demo users"))
    if not args.yes:
        print("Nothing written. Add --yes to write to this database.")
        return 1
    db = get_database(settings)
    try:
        ensure_indexes(db)
        result = seed(db, settings, args.reset)
    finally:
        db.client.close()
    print(f"Done: {result['removed']} demo users removed, {result['created']} created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
