from decimal import Decimal, localcontext

MAX_CENTS = 9_999_999_999


def to_cents(amount: Decimal) -> int:
    """Whole cents for a non-negative amount with at most two decimals and no more than the maximum balance."""
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be a finite, non-negative number")
    # exact arithmetic: the default 28-digit precision could round a sub-cent amount up to a whole cent
    with localcontext() as ctx:
        ctx.prec = len(amount.as_tuple().digits) + 10
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError("amount must have at most two decimals")
        if cents > MAX_CENTS:
            raise ValueError("amount is above the maximum balance of 99,999,999.99")
    return int(cents)


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))
