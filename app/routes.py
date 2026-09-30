"""Customer and account controllers; money rules live in the services."""
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from .models import (Account, AccountCreate, AccountEdit, AmountRequest, Category,
                     Customer, ObjectIdString, Transaction, User, UserCreate)

router = APIRouter(prefix='/api', responses={404:{'description':'Record not found'},
                    409:{'description':'Conflicting record or account state'},
                    503:{'description':'Database unavailable'}})
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post('/users', response_model=User, status_code=201, tags=['Users'])
def create_user(data: UserCreate, request: Request):
    """Compatibility alias: users and customers are the same records."""
    return request.app.state.customers.create_user(data)


@router.get('/customers', response_model=list[Customer], tags=['Customers'], summary='GetAllCustomers')
def get_all_customers(request: Request, search: Annotated[str | None, Query(max_length=100)] = None,
                      category: Category | None = None, offset: Offset = 0, limit: Limit = 50):
    """Search literal name/email text, filter by combined balance category, and page results."""
    return request.app.state.customers.get_all_customers(search, category, offset, limit)


@router.post('/customers', response_model=Customer, status_code=201, tags=['Customers'], summary='PostCustomer')
def post_customer(data: UserCreate, request: Request):
    return request.app.state.customers.create_customer(data)


@router.get('/customers/{id}', response_model=Customer, tags=['Customers'], summary='GetCustomerById')
def get_customer(id: ObjectIdString, request: Request):
    return request.app.state.customers.get_customer(id)


@router.put('/customers/{id}', response_model=Customer, tags=['Customers'], summary='EditCustomer')
def edit_customer(id: ObjectIdString, data: UserCreate, request: Request):
    """Replace name and email; preferences and account ownership stay unchanged."""
    return request.app.state.customers.edit_customer(id, data)


@router.delete('/customers/{id}', status_code=204, tags=['Customers'], summary='DeleteCustomer')
def delete_customer(id: ObjectIdString, request: Request):
    """Archive a customer after all accounts are closed. Audit records are retained."""
    request.app.state.customers.delete_customer(id)
    return Response(status_code=204)


@router.get('/customers/{id}/accounts', response_model=list[Account], tags=['Customers'])
def customer_accounts(id: ObjectIdString, request: Request, offset: Offset = 0, limit: Limit = 50):
    return request.app.state.accounts.get_customer_accounts(id, offset, limit)


@router.get('/accounts', response_model=list[Account], tags=['Accounts'], summary='GetAllAccounts')
def get_all_accounts(request: Request, offset: Offset = 0, limit: Limit = 50):
    return request.app.state.accounts.get_all_accounts(offset, limit)


@router.post('/accounts', response_model=Account, status_code=201, tags=['Accounts'])
def create_account(data: AccountCreate, request: Request):
    """Open a zero-balance account for an existing customerId (or legacy userId)."""
    return request.app.state.accounts.create_account(data)


@router.get('/accounts/{id}', response_model=Account, tags=['Accounts'])
def get_account(id: ObjectIdString, request: Request):
    return request.app.state.accounts.get_account(id)


@router.put('/accounts/{id}', response_model=Account, tags=['Accounts'], summary='EditAccount')
def edit_account(id: ObjectIdString, data: AccountEdit, request: Request):
    return request.app.state.accounts.edit_account(id, data)


@router.delete('/accounts/{id}', status_code=204, tags=['Accounts'], summary='DeleteAccount')
def delete_account(id: ObjectIdString, request: Request):
    """Close a zero-balance account and preserve its transaction history."""
    request.app.state.accounts.delete_account(id)
    return Response(status_code=204)


@router.post('/accounts/{id}/deposit', response_model=Account, tags=['Accounts'], responses={400:{'description':'Balance limit exceeded'}})
def deposit(id: ObjectIdString, data: AmountRequest, request: Request):
    return request.app.state.accounts.deposit(id, data)


@router.post('/accounts/{id}/withdraw', response_model=Account, tags=['Accounts'], responses={400:{'description':'Insufficient funds'}})
def withdraw(id: ObjectIdString, data: AmountRequest, request: Request):
    return request.app.state.accounts.withdraw(id, data)


@router.get('/accounts/{id}/transactions', response_model=list[Transaction], tags=['Transactions'])
def transactions(id: ObjectIdString, request: Request, offset: Offset = 0, limit: Limit = 50):
    """Oldest-first history, including transactions belonging to a closed account."""
    return request.app.state.accounts.get_transactions(id, offset, limit)
