"""Request validation and camelCase response models."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (AliasChoices, BaseModel, ConfigDict, EmailStr, Field, StrictBool, StringConstraints,
                      computed_field, model_validator)
from pydantic.alias_generators import to_camel


NO_CONTROL_CHARS = r"^[^\x00-\x1f\x7f]*$"  # a NUL in a search regex would reach MongoDB and come back as a 500
OBJECT_ID_PATTERN = r"^[0-9a-fA-F]{24}$"
ObjectIdStr = Annotated[str, Field(pattern=OBJECT_ID_PATTERN)]


class Model(BaseModel):
    # Python uses snake_case; API clients see fields such as accountId.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True,
                              extra="forbid", str_strip_whitespace=True, frozen=True)


class UserBase(Model):
    # Unconstrained: responses must serialize stored names, including legacy ones with control characters.
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)


class UserCreate(UserBase):
    name: str = Field(min_length=1, max_length=100, pattern=NO_CONTROL_CHARS)


class User(UserBase):
    user_id: str
    created_at: datetime


class Customer(UserBase):
    customer_id: str
    created_at: datetime
    marketing_enabled: bool = False


class Preferences(Model):
    marketing_enabled: StrictBool


class AccountEdit(Model):
    account_type: str = Field(min_length=1, max_length=50, pattern=NO_CONTROL_CHARS)


class AccountCreate(Model):
    user_id: ObjectIdStr = Field(validation_alias=AliasChoices("customerId", "userId", "user_id"))
    # Accept types such as SAVINGS and CURRENT without restricting clients to a fixed list.
    account_type: str = Field(min_length=1, max_length=50, pattern=NO_CONTROL_CHARS)


Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2,
                                 allow_inf_nan=False)]


class AmountRequest(Model):
    amount: Money


class TransferRequest(Model):
    from_account_id: ObjectIdStr
    to_account_id: ObjectIdStr
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
    customer_id: str
    # A transfer stores one record per account: TRANSFER_OUT on the source and TRANSFER_IN on the destination.
    # ACCOUNT_CLOSED records the balance removed when a customer delete removes the account.
    type: Literal["DEPOSIT", "WITHDRAW", "TRANSFER_OUT", "TRANSFER_IN", "ACCOUNT_CLOSED"]
    amount: Decimal
    balance_after: Decimal  # of this record's account
    date: datetime
    # Set on both transfer records, null for deposits and withdrawals.
    transfer_id: str | None = None
    from_account_id: str | None = None
    to_account_id: str | None = None


# A replayed deposit or withdrawal returns its stored transaction when the account has since been deleted.
MoneyResult = Account | Transaction


class TransferResult(Model):
    transfer_id: str
    from_account_id: str
    to_account_id: str
    amount: Decimal
    from_balance_after: Decimal
    to_balance_after: Decimal | None = None  # hidden from a customer unless the destination is theirs
    date: datetime  # the TRANSFER_OUT record's date


class AuditPage(Model):
    items: list[Transaction]
    next_cursor: str | None


Category =Literal["LOW", "STANDARD", "PREMIUM"]


class CustomerSummary(Model):
    customer_id: str
    name: str
    email: str
    total_balance: Decimal
    category: Category


# A low-balance alert is operational and always stored; the marketing kinds need the customer's opt-in.
NotificationKind = Literal["LOW_BALANCE_ALERT", "LOW_BALANCE_MARKETING", "PREMIUM_MARKETING"]


class Notification(Model):
    notification_id: str
    customer_id: str
    category_version: int
    category: Category
    kind: NotificationKind
    template_id: str
    message: str
    transaction_id: str
    created_at: datetime


Role = Literal["ADMIN", "CUSTOMER"]


class RegisterRequest(Model):
    # Passwords are kept exactly as typed (spaces included), so stripping is off here and applied to the name only.
    model_config = ConfigDict(str_strip_whitespace=False)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100,
                                           pattern=NO_CONTROL_CHARS)]
    email: EmailStr = Field(max_length=100)
    password: str = Field(max_length=200, description="8 to 72 UTF-8 bytes (bcrypt-style limit), not the email")

    @model_validator(mode="after")
    def _password_rules(self):
        if not 8 <= len(self.password.encode()) <= 72:
            raise ValueError("password must be 8 to 72 bytes long")
        if self.password.lower() == str(self.email).lower():
            raise ValueError("password must not be the email")
        return self


class LoginRequest(Model):
    model_config = ConfigDict(str_strip_whitespace=False)
    # Plain strings: a malformed email or odd password is a wrong login (401), not a validation hint.
    email: str = Field(max_length=100)
    password: str = Field(max_length=200)


class AuthUser(Model):
    email: str
    role: Role
    customer_id: str | None
    name: str


class TokenResponse(Model):
    token: str
    token_type: Literal["Bearer"] = "Bearer"
    user: AuthUser
