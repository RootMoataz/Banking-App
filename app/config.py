import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

from .money import to_cents

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = field(repr=False)  # never print the connection string: it carries the password
    mongodb_db: str
    low_cents: int = 10_000
    premium_cents: int = 1_000_000

    def __post_init__(self):
        if not self.mongodb_db:
            raise ValueError("MONGODB_DB must not be empty")
        if not 0 <= self.low_cents < self.premium_cents:
            raise ValueError("need 0 <= low < premium threshold")


def _threshold(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return to_cents(Decimal(raw))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be an amount from 0.00 to 99999999.99 with at most two decimals, got {raw!r}") from None


def load_settings(env_file: Path = ROOT / ".env") -> Settings:
    """Read settings from the environment; the .env is found relative to the code, not the current directory."""
    load_dotenv(env_file)
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    return Settings(
        uri,
        os.environ.get("MONGODB_DB", "paper_maker"),
        _threshold("LOW_BALANCE_THRESHOLD", "100.00"),
        _threshold("PREMIUM_BALANCE_THRESHOLD", "10000.00"),
    )
