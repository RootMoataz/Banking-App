"""Messages for a customer whose category changed. They are stored for the API to show; nothing is emailed or pushed."""

from .config import Settings
from .models import Category
from .money import from_cents

# Workshop wording: no loan product, rate, link or approval decision is offered or implied.
LOAN_OPTIONS = ("Explore available loan options and learn how to apply. "
                "Eligibility and approval depend on assessment.")


def _amount(cents: int) -> str:
    return f"{from_cents(cents):,}"  # 10000.00 -> 10,000.00


def messages(entered: Category, marketing_enabled: bool, settings: Settings) -> list[dict]:
    """The messages for a customer entering the category `entered`. Entering STANDARD has none."""
    found = []
    if entered == "LOW":
        found.append({"kind": "LOW_BALANCE_ALERT", "templateId": "low-balance-v1",
                      "message": f"Your combined account balance is below {_amount(settings.low_cents)}."})
        if marketing_enabled:
            found.append({"kind": "LOW_BALANCE_MARKETING", "templateId": "loan-options-v1", "message": LOAN_OPTIONS})
    elif entered == "PREMIUM" and marketing_enabled:
        found.append({"kind": "PREMIUM_MARKETING", "templateId": "premium-v1",
                      "message": f"Your combined balance has reached {_amount(settings.premium_cents)}. "
                                 "Explore available premium banking benefits."})
    return found
