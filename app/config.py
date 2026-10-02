import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import dotenv_values

from .money import to_cents

MIN_JWT_SECRET_LENGTH = 32
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://localhost:5173"
# What a browser sends as Origin: scheme, host and optional port, with no path or trailing slash.
_ORIGIN = re.compile(r"https?://[^\s/?#*]+")


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = field(repr=False)  # never print the connection string: it carries the password
    mongodb_db: str
    low_cents: int = 10_000
    premium_cents: int = 1_000_000
    cors_allowed_origins: tuple[str, ...] = tuple(DEFAULT_CORS_ORIGINS.split(","))
    jwt_secret: str = field(default="", repr=False)  # checked at startup and by load_settings; never printed
    jwt_expiration_minutes: int = 60
    admin_email: str | None = None
    admin_password: str | None = field(default=None, repr=False)
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    def __post_init__(self):
        if not self.mongodb_db:
            raise ValueError("MONGODB_DB must not be empty")
        if not 0 <= self.low_cents < self.premium_cents:
            raise ValueError("need 0 <= low < premium threshold")


def _threshold(name: str, setting, default: str) -> int:
    raw = setting(name, default)
    try:
        return to_cents(Decimal(raw))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be an amount from 0.00 to 99999999.99 with at most two decimals, got {raw!r}") from None


def _expiration(raw: str) -> int:
    if not raw.isascii() or not raw.isdecimal() or int(raw) < 1:
        raise ValueError(f"JWT_EXPIRATION_MINUTES must be a whole number of minutes, 1 or more, got {raw!r}")
    return int(raw)


def _positive_int(name: str, raw: str, maximum: int | None = None) -> int:
    if not raw.isascii() or not raw.isdecimal() or int(raw) < 1 or (maximum is not None and int(raw) > maximum):
        limit = "" if maximum is None else f" and at most {maximum}"
        raise ValueError(f"{name} must be a whole number, 1 or more{limit}, got {raw!r}")
    return int(raw)


def _origins(raw: str) -> tuple[str, ...]:
    origins = tuple(o.strip() for o in raw.split(",") if o.strip())
    if not origins or not all(_ORIGIN.fullmatch(o) for o in origins):
        raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated list of origins such as "
                         f"http://localhost:3000 (no path, no trailing slash, no *), got {raw!r}")
    return origins


def load_settings(env_file: Path = ROOT / ".env") -> Settings:
    """Read settings from the environment; the .env is found relative to the code, not the current directory."""
    # Read the file without copying it into os.environ, so child processes never inherit the URI.
    # A real environment variable wins over the file.
    file_values = dotenv_values(env_file)

    def setting(name: str, default: str | None = None) -> str | None:
        if name in os.environ:
            return os.environ[name]
        value = file_values.get(name)  # a bare `KEY` line gives None: treat it as unset
        return default if value is None else value

    uri = setting("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    secret = setting("JWT_SECRET")
    if not secret or len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be set to at least {MIN_JWT_SECRET_LENGTH} characters")
    return Settings(
        uri,
        setting("MONGODB_DB", "paper_maker"),
        _threshold("LOW_BALANCE_THRESHOLD", setting, "100.00"),
        _threshold("PREMIUM_BALANCE_THRESHOLD", setting, "10000.00"),
        _origins(setting("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ORIGINS)),
        secret,
        _expiration(setting("JWT_EXPIRATION_MINUTES", "60")),
        setting("ADMIN_EMAIL") or None,
        setting("ADMIN_PASSWORD") or None,
        _positive_int("LOGIN_MAX_FAILURES", setting("LOGIN_MAX_FAILURES", "5")),
        # At most one day, the life of a login_attempts document, so the TTL index can never lift a lock early.
        _positive_int("LOGIN_LOCK_MINUTES", setting("LOGIN_LOCK_MINUTES", "15"), 24 * 60),
    )
