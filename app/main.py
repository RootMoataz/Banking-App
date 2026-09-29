"""FastAPI routes for customers, accounts, and transactions."""

from typing import Annotated

from fastapi import FastAPI, Path, Response
from fastapi.responses import JSONResponse

from .models import Account, AccountCreate, AccountEdit, AmountRequest, Customer, Transaction, User, UserCreate
from .repositories import MemoryStore
from .services import AccountService, BankError, CustomerService

AccountId = Annotated[int, Path(gt=0)]


def create_app() -> FastAPI:
    app = FastAPI(title="Paper Maker Banking App", version="1.1.0",
                  description="Customer and account CRUD with deposit/withdraw service operations. "
                  "One customer can own many accounts. In-memory only: data resets on restart.",
                  openapi_tags=[
                      {"name": "Customers", "description": "Create, list, retrieve, replace and delete customers."},
                      {"name": "Accounts", "description": "Each account belongs to one customer. Edit accountType only; use deposit/withdraw for balance changes."},
                      {"name": "Transactions", "description": "Successful deposits and withdrawals, oldest first."},
                      {"name": "Users", "description": "Compatibility endpoint from the original project; users and customers share the same records."},
                  ])
    # A fresh app gets fresh records, which also keeps the tests independent.
    store = MemoryStore()
    service = AccountService(store)
    customers = CustomerService(store)

    @app.exception_handler(BankError)
    async def bank_error_handler(request, exc: BankError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    @app.post("/api/users", response_model=User, status_code=201, tags=["Users"],
              responses={409: {"description": "Duplicate email"}})
    def create_user(data: UserCreate):
        return customers.create_user(data)

    @app.get("/api/customers", response_model=list[Customer], tags=["Customers"],
             summary="GetAllCustomers")
    def get_all_customers():
        """Return customers in the order they were created. No customers means an empty list."""
        return customers.get_all_customers()

    @app.post("/api/customers", response_model=Customer, status_code=201,
              tags=["Customers"], summary="PostCustomer",
              responses={409: {"description": "Email already exists"}})
    def post_customer(data: UserCreate):
        """Send a name and an unused email address to create a customer."""
        return customers.create_customer(data)

    @app.get("/api/customers/{id}", response_model=Customer, tags=["Customers"],
             summary="GetCustomerById", responses={404: {"description": "Customer not found"}})
    def get_customer(id: AccountId):
        return customers.get_customer(id)

    @app.put("/api/customers/{id}", response_model=Customer, tags=["Customers"],
             summary="EditCustomer", responses={404: {"description": "Customer not found"},
                                               409: {"description": "Email already exists"}})
    def edit_customer(id: AccountId, data: UserCreate):
        """Send both name and email. The customer's ID, creation date and accounts stay the same."""
        return customers.edit_customer(id, data)

    @app.delete("/api/customers/{id}", status_code=204, tags=["Customers"],
                summary="DeleteCustomer", responses={404: {"description": "Customer not found"},
                                                     409: {"description": "Customer still has accounts"}})
    def delete_customer(id: AccountId):
        """Delete the customer's accounts first; otherwise this returns 409."""
        customers.delete_customer(id)
        return Response(status_code=204)

    @app.get("/api/customers/{id}/accounts", response_model=list[Account], tags=["Customers"],
             summary="GetCustomerAccounts", responses={404: {"description": "Customer not found"}})
    def customer_accounts(id: AccountId):
        """Show this customer's accounts. A customer can have more than one, or none yet."""
        return service.get_customer_accounts(id)

    @app.get("/api/accounts", response_model=list[Account], tags=["Accounts"], summary="GetAllAccounts")
    def get_all_accounts():
        return service.get_all_accounts()

    @app.post("/api/accounts", response_model=Account, status_code=201,
              tags=["Accounts"], responses={404: {"description": "Customer not found"}})
    def create_account(data: AccountCreate):
        """Use an existing customerId to open an account at zero. The original userId input still works."""
        return service.create_account(data)

    @app.put("/api/accounts/{id}", response_model=Account, tags=["Accounts"], summary="EditAccount",
             responses={404: {"description": "Account not found"}})
    def edit_account(id: AccountId, data: AccountEdit):
        """Send the new accountType. To change the balance, use deposit or withdraw instead."""
        return service.edit_account(id, data)

    @app.delete("/api/accounts/{id}", status_code=204, tags=["Accounts"], summary="DeleteAccount",
                responses={404: {"description": "Account not found"},
                           409: {"description": "Account balance must be zero"}})
    def delete_account(id: AccountId):
        """Withdraw any remaining money first. Deleting the account also clears its history."""
        service.delete_account(id)
        return Response(status_code=204)

    @app.get("/api/accounts/{id}", response_model=Account, tags=["Accounts"],
             responses={404: {"description": "Account not found"}})
    def get_account(id: AccountId):
        return service.get_account(id)

    @app.post("/api/accounts/{id}/deposit", response_model=Account, tags=["Accounts"],
              responses={400: {"description": "Balance limit exceeded"},
                         404: {"description": "Account not found"}})
    def deposit(id: AccountId, data: AmountRequest):
        """Add a positive amount and record the deposit. Fractions of a cent aren't accepted."""
        return service.deposit(id, data)

    @app.post("/api/accounts/{id}/withdraw", response_model=Account, tags=["Accounts"],
              responses={400: {"description": "Insufficient funds"},
                         404: {"description": "Account not found"}})
    def withdraw(id: AccountId, data: AmountRequest):
        """Take out a positive amount, up to the current balance, and record the withdrawal."""
        return service.withdraw(id, data)

    @app.get("/api/accounts/{id}/transactions", response_model=list[Transaction],
             tags=["Transactions"], responses={404: {"description": "Account not found"}})
    def transactions(id: AccountId):
        return service.get_transactions(id)

    return app


app = create_app()
