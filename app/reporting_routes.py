"""Audit lookups, stored notifications, and customer marketing preferences."""
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from .models import Customer, Notification, NotificationKind, ObjectIdString, Preferences, Transaction
from .routes import Limit, Offset

router = APIRouter(prefix='/api', responses={404:{'description':'Record not found'},503:{'description':'Database unavailable'}})


@router.get('/audit/transactions', response_model=list[Transaction], tags=['Audit'])
def audit_transactions(request: Request, customerId: ObjectIdString | None = None,
                       accountId: ObjectIdString | None = None,
                       date_from: Annotated[AwareDatetime | None, Query(alias='from')] = None,
                       date_to: Annotated[AwareDatetime | None, Query(alias='to')] = None,
                       offset: Offset = 0, limit: Limit = 50):
    """Combine filters with AND. Use timezone-aware dates; from is inclusive, to exclusive."""
    return request.app.state.audit.list_transactions(customerId, accountId, date_from, date_to, offset, limit)


@router.get('/audit/transactions/{id}', response_model=Transaction, tags=['Audit'])
def audit_transaction(id: ObjectIdString, request: Request):
    return request.app.state.audit.get_transaction(id)


@router.patch('/customers/{id}/preferences', response_model=Customer, tags=['Customers'])
def preferences(id: ObjectIdString, data: Preferences, request: Request):
    """Opt in or out of future marketing. Operational balance alerts remain enabled."""
    return request.app.state.customers.set_preferences(id, data.marketing_enabled)


@router.get('/customers/{id}/notifications', response_model=list[Notification], tags=['Notifications'])
def notifications(id: ObjectIdString, request: Request, kind: NotificationKind | None = None,
                  offset: Offset = 0, limit: Limit = 50):
    """Newest-first stored messages. These have not been emailed or pushed."""
    return request.app.state.customers.get_notifications(id, kind, offset, limit)
