"""Request validation and camelCase response models."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, StrictBool, computed_field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    # Python uses snake_case; API clients see fields such as accountId.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True,
                              extra="forbid", str_strip_whitespace=True, frozen=True)


ObjectIdString = Annotated[str, Field(pattern=r'^[0-9a-fA-F]{24}$')]
Category = Literal['LOW', 'STANDARD', 'PREMIUM']
NotificationKind = Literal['LOW_BALANCE_ALERT', 'LOW_BALANCE_MARKETING', 'PREMIUM_MARKETING']


def to_cents(amount: Decimal) -> int:
    return int(amount * 100)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(Decimal('0.01'))


class UserCreate(Model):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)


class User(UserCreate):
    user_id: ObjectIdString
    created_at: datetime


class Customer(UserCreate):
    customer_id: ObjectIdString
    created_at: datetime
    total_balance: Decimal = Decimal('0.00')
    category: Category = 'LOW'
    marketing_enabled: bool = False


class Preferences(Model):
    marketing_enabled: StrictBool


class AccountEdit(Model):
    account_type: str = Field(min_length=1, max_length=50)


class AccountCreate(Model):
    user_id: ObjectIdString = Field(
                         validation_alias=AliasChoices("customerId", "userId", "user_id"))
    # Accept types such as SAVINGS and CURRENT without restricting clients to a fixed list.
    account_type: str = Field(min_length=1, max_length=50)


Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2,
                                 allow_inf_nan=False)]


class AmountRequest(Model):
    amount: Money


class Account(Model):
    account_id: ObjectIdString
    user_id: ObjectIdString
    user_name: str
    account_type: str
    balance: Decimal = Decimal("0.00")
    created_at: datetime

    @computed_field
    @property
    def customer_id(self) -> str:
        """Both owner fields refer to the same customer record."""
        return self.user_id


class Transaction(Model):
    txn_id: ObjectIdString
    account_id: ObjectIdString
    customer_id: ObjectIdString
    type: Literal["DEPOSIT", "WITHDRAW"]
    amount: Decimal
    date: datetime
    balance_after: Decimal


class Notification(Model):
    notification_id: ObjectIdString
    customer_id: ObjectIdString
    category_version: int
    category: Category
    kind: NotificationKind
    template_id: str
    message: str
    transaction_id: ObjectIdString | None
    created_at: datetime
