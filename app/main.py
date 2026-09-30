"""FastAPI routes for customers, accounts, and transactions."""

from contextlib import asynccontextmanager
from typing import Annotated

from bson import ObjectId
from fastapi import FastAPI, Path, Response
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .db import ensure_indexes, get_database
from .models import (OBJECT_ID_PATTERN, Account, AccountCreate, AccountEdit, AmountRequest,
                     Customer, Transaction, User, UserCreate)
from .services import AccountService, BankError, CustomerService

Id = Annotated[str, Path(pattern=OBJECT_ID_PATTERN, description="24-character hex ID")]


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Settings and the connection are created at startup, not at import: uvicorn
        # imports this module first, and tests build apps for their own database.
        db = get_database(settings or load_settings())
        ensure_indexes(db)  # idempotent; email uniqueness must not depend on a manual setup step
        app.state.customers = CustomerService(db)
        app.state.accounts = AccountService(db)
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

    @app.post("/api/accounts/{id}/deposit", response_model=Account, tags=["Accounts"],
              responses={400: {"description": "Balance limit exceeded"},
                         404: {"description": "Account not found"}})
    def deposit(id: Id, data: AmountRequest):
        """Add a positive amount and record the deposit. Fractions of a cent aren't accepted."""
        return app.state.accounts.deposit(ObjectId(id), data)

    @app.post("/api/accounts/{id}/withdraw", response_model=Account, tags=["Accounts"],
              responses={400: {"description": "Insufficient funds"},
                         404: {"description": "Account not found"}})
    def withdraw(id: Id, data: AmountRequest):
        """Take out a positive amount, up to the current balance, and record the withdrawal."""
        return app.state.accounts.withdraw(ObjectId(id), data)

    @app.get("/api/accounts/{id}/transactions", response_model=list[Transaction],
             tags=["Transactions"], responses={404: {"description": "Account not found"}})
    def transactions(id: Id):
        return app.state.accounts.get_transactions(ObjectId(id))

    return app


app = create_app()
