"""Request validation and camelCase response models."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, computed_field
from pydantic.alias_generators import to_camel


OBJECT_ID_PATTERN = r"^[0-9a-fA-F]{24}$"
ObjectIdStr = Annotated[str, Field(pattern=OBJECT_ID_PATTERN)]


class Model(BaseModel):
    # Python uses snake_case; API clients see fields such as accountId.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True,
                              extra="forbid", str_strip_whitespace=True, frozen=True)


class UserCreate(Model):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)


class User(UserCreate):
    user_id: str
    created_at: datetime


class Customer(UserCreate):
    customer_id: str
    created_at: datetime


class AccountEdit(Model):
    account_type: str = Field(min_length=1, max_length=50)


class AccountCreate(Model):
    user_id: ObjectIdStr = Field(validation_alias=AliasChoices("customerId", "userId", "user_id"))
    # Accept types such as SAVINGS and CURRENT without restricting clients to a fixed list.
    account_type: str = Field(min_length=1, max_length=50)


Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2,
                                 allow_inf_nan=False)]


class AmountRequest(Model):
    amount: Money


class Account(Model):
    account_id: str
    user_id: str
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
    txn_id: str
    account_id: str
    type: Literal["DEPOSIT", "WITHDRAW"]
    amount: Decimal
    date: datetime
