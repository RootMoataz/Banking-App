"""FastAPI routes for customers, accounts, transactions, alerts, and the transaction audit."""

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from bson import ObjectId
from fastapi import FastAPI, Header, Path, Query, Response
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .db import ensure_indexes, get_database
from .models import (OBJECT_ID_PATTERN, Account, AccountCreate, AccountEdit, Alert, AmountRequest, AuditPage,
                     Category, Customer, CustomerSummary, MoneyResult, Transaction, User, UserCreate)
from .services import AccountService, BankError, CustomerService

NO_CONTROL_CHARS = r"^[^\x00-\x1f\x7f]*$"  # a NUL in a search regex would reach MongoDB and come back as a 500

Id = Annotated[str, Path(pattern=OBJECT_ID_PATTERN, description="24-character hex ID")]
IdempotencyKey = Annotated[str | None, Header(
    alias="Idempotency-Key", min_length=1, max_length=200, pattern=r"^ *[\x21-\x7e][\x20-\x7e]*$",
    description="Optional, up to 200 printable ASCII characters. Resending a key with the same request replays the "
                "first result without moving money again; reusing it for a different request returns 409.")]
Limit = Annotated[int, Query(ge=1, le=200, description="At most this many results, 1 to 200")]


def _balance(alias: str):
    return Query(alias=alias, ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False,
                 description="A total balance such as 100.00, inclusive")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Settings and the connection are created at startup, not at import: uvicorn
        # imports this module first, and tests build apps for their own database.
        resolved = settings or load_settings()
        db = get_database(resolved)
        ensure_indexes(db)  # idempotent; email uniqueness must not depend on a manual setup step
        app.state.customers = CustomerService(db, resolved)
        app.state.accounts = AccountService(db, resolved)
        try:
            yield
        finally:
            db.client.close()

    app = FastAPI(title="Paper Maker Banking App", version="1.1.0", lifespan=lifespan,
                  description="Customer and account CRUD with deposit/withdraw service operations. "
                  "One customer can own many accounts. Records are stored in MongoDB.",
                  openapi_tags=[
                      {"name": "Customers", "description": "Create, list, retrieve, replace and delete customers."},
                      {"name": "Accounts", "description": "Each account belongs to one customer. Edit accountType only; use deposit/withdraw for balance changes."},
                      {"name": "Transactions", "description": "Successful deposits and withdrawals, oldest first."},
                      {"name": "Alerts", "description": "In-app records of a customer's total balance crossing a threshold."},
                      {"name": "Audit", "description": "Transaction history by customer or account, filtered by "
                                                       "date and read page by page, including deleted accounts "
                                                       "and customers."},
                      {"name": "Users", "description": "Compatibility endpoint from the original project; users and customers share the same records."},
                  ])

    @app.exception_handler(BankError)
    async def bank_error_handler(request, exc: BankError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    @app.post("/api/users", response_model=User, status_code=201, tags=["Users"],
              responses={409: {"description": "Duplicate email"}})
    def create_user(data: UserCreate):
        return app.state.customers.create_user(data)

    @app.get("/api/customers", response_model=list[Customer], tags=["Customers"],
             summary="GetAllCustomers")
    def get_all_customers():
        """Return customers in the order they were created. No customers means an empty list."""
        return app.state.customers.get_all_customers()

    @app.post("/api/customers", response_model=Customer, status_code=201,
              tags=["Customers"], summary="PostCustomer",
              responses={409: {"description": "Email already exists"}})
    def post_customer(data: UserCreate):
        """Send a name and an unused email address to create a customer."""
        return app.state.customers.create_customer(data)

    # Registered before /api/customers/{id}, which would otherwise take "search" as an ID and answer 422.
    @app.get("/api/customers/search", response_model=list[CustomerSummary], tags=["Customers"],
             summary="SearchCustomers")
    def search_customers(name: Annotated[str | None, Query(max_length=100, pattern=NO_CONTROL_CHARS)] = None,
                         email: Annotated[str | None, Query(max_length=100, pattern=NO_CONTROL_CHARS)] = None,
                         category: Category | None = None,
                         min_balance: Annotated[Decimal | None, _balance("minBalance")] = None,
                         max_balance: Annotated[Decimal | None, _balance("maxBalance")] = None,
                         limit: Limit = 50):
        """Filter customers by name or email (case-insensitive substring), by category, and by total balance
        (inclusive bounds). The total is the sum of all the customer's accounts; a customer with none has 0.00.
        Categories: LOW below the low threshold, PREMIUM at or above the premium threshold, otherwise STANDARD."""
        return app.state.customers.search(name, email, category, min_balance, max_balance, limit)

    @app.get("/api/customers/{id}", response_model=Customer, tags=["Customers"],
             summary="GetCustomerById", responses={404: {"description": "Customer not found"}})
    def get_customer(id: Id):
        return app.state.customers.get_customer(ObjectId(id))

    @app.put("/api/customers/{id}", response_model=Customer, tags=["Customers"],
             summary="EditCustomer", responses={404: {"description": "Customer not found"},
                                               409: {"description": "Email already exists"}})
    def edit_customer(id: Id, data: UserCreate):
        """Send both name and email. The customer's ID, creation date and accounts stay the same."""
        return app.state.customers.edit_customer(ObjectId(id), data)

    @app.delete("/api/customers/{id}", status_code=204, tags=["Customers"],
                summary="DeleteCustomer", responses={404: {"description": "Customer not found"},
                                                     409: {"description": "Customer still has accounts"}})
    def delete_customer(id: Id):
        """Delete the customer's accounts first; otherwise this returns 409."""
        app.state.customers.delete_customer(ObjectId(id))
        return Response(status_code=204)

    @app.get("/api/customers/{id}/accounts", response_model=list[Account], tags=["Customers"],
             summary="GetCustomerAccounts", responses={404: {"description": "Customer not found"}})
    def customer_accounts(id: Id):
        """Show this customer's accounts. A customer can have more than one, or none yet."""
        return app.state.accounts.get_customer_accounts(ObjectId(id))

    @app.get("/api/accounts", response_model=list[Account], tags=["Accounts"], summary="GetAllAccounts")
    def get_all_accounts():
        return app.state.accounts.get_all_accounts()

    @app.post("/api/accounts", response_model=Account, status_code=201,
              tags=["Accounts"], responses={404: {"description": "Customer not found"}})
    def create_account(data: AccountCreate):
        """Use an existing customerId to open an account at zero. The original userId input still works."""
        return app.state.accounts.create_account(data)

    @app.put("/api/accounts/{id}", response_model=Account, tags=["Accounts"], summary="EditAccount",
             responses={404: {"description": "Account not found"}})
    def edit_account(id: Id, data: AccountEdit):
        """Send the new accountType. To change the balance, use deposit or withdraw instead."""
        return app.state.accounts.edit_account(ObjectId(id), data)

    @app.delete("/api/accounts/{id}", status_code=204, tags=["Accounts"], summary="DeleteAccount",
                responses={404: {"description": "Account not found"},
                           409: {"description": "Account balance must be zero"}})
    def delete_account(id: Id):
        """Withdraw any remaining money first. The account's transactions are kept."""
        app.state.accounts.delete_account(ObjectId(id))
        return Response(status_code=204)

    @app.get("/api/accounts/{id}", response_model=Account, tags=["Accounts"],
             responses={404: {"description": "Account not found"}})
    def get_account(id: Id):
        return app.state.accounts.get_account(ObjectId(id))

    @app.post("/api/accounts/{id}/deposit", response_model=MoneyResult, tags=["Accounts"],
              responses={400: {"description": "Balance limit exceeded"},
                         404: {"description": "Account not found"},
                         409: {"description": "Idempotency-Key already used for a different request"}})
    def deposit(id: Id, data: AmountRequest, key: IdempotencyKey = None):
        """Add a positive amount and record the deposit. Fractions of a cent aren't accepted.
        A replay returns the balance right after the original deposit, or its transaction record if the account
        has since been deleted."""
        return app.state.accounts.deposit(ObjectId(id), data, key)

    @app.post("/api/accounts/{id}/withdraw", response_model=MoneyResult, tags=["Accounts"],
              responses={400: {"description": "Insufficient funds"},
                         404: {"description": "Account not found"},
                         409: {"description": "Idempotency-Key already used for a different request"}})
    def withdraw(id: Id, data: AmountRequest, key: IdempotencyKey = None):
        """Take out a positive amount, up to the current balance, and record the withdrawal.
        A replay returns the balance right after the original withdrawal, or its transaction record if the account
        has since been deleted."""
        return app.state.accounts.withdraw(ObjectId(id), data, key)

    @app.get("/api/accounts/{id}/transactions", response_model=list[Transaction],
             tags=["Transactions"], responses={404: {"description": "Account not found"}})
    def transactions(id: Id):
        return app.state.accounts.get_transactions(ObjectId(id))

    @app.get("/api/alerts", response_model=list[Alert], tags=["Alerts"], summary="GetAlerts")
    def alerts(customer_id: Annotated[str | None, Query(alias="customerId", pattern=OBJECT_ID_PATTERN)] = None,
               limit: Limit = 50):
        """Alerts written when a deposit or withdrawal moved a customer's total below the low threshold or up to the
        premium threshold, newest first."""
        return app.state.accounts.get_alerts(None if customer_id is None else ObjectId(customer_id), limit)

    @app.get("/api/audit/transactions", response_model=AuditPage, tags=["Audit"], summary="AuditTransactions",
             responses={422: {"description": "No customerId or accountId, a malformed parameter or cursor, or a cursor "
                                             "issued for different filters"}})
    def audit_transactions(
            customer_id: Annotated[str | None, Query(alias="customerId", pattern=OBJECT_ID_PATTERN)] = None,
            account_id: Annotated[str | None, Query(alias="accountId", pattern=OBJECT_ID_PATTERN)] = None,
            start: Annotated[datetime | None, Query(alias="from", description="Inclusive, ISO 8601")] = None,
            end: Annotated[datetime | None, Query(alias="to", description="Exclusive, ISO 8601")] = None,
            limit: Limit = 50,
            cursor: Annotated[str | None, Query(max_length=500, description="The previous page's nextCursor")] = None):
        """Every deposit and withdrawal of a customer (all their accounts) or of one account, oldest first by date,
        then by txnId. Give customerId, accountId or both. Records are kept after their account and customer are
        deleted, so deleted IDs still return their history.

        Times are ISO 8601 such as 2026-09-30T08:00:00Z; a time without an offset is read as UTC. In a URL write an
        offset as `%2B02:00` (a bare `+` becomes a space and is rejected), or simply use `Z`. `from` is inclusive
        and `to` is exclusive; when `from` is not before `to` the window is empty. To read the next page, send the
        same filters with `cursor` set to the previous page's nextCursor (null on the last page). A filter may be
        written differently (ID letter case, `Z` or `+00:00`, another offset for the same instant) and `limit` may
        change, but a cursor sent with other filters is rejected with 422."""
        return app.state.accounts.audit(customer_id, account_id, start, end, limit, cursor)

    return app


app = create_app()
