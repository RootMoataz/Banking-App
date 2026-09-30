"""Stateless audit cursors and the filter fingerprint that ties a cursor to the filters it was issued for."""

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId

_HEX_ID = re.compile(r"[0-9a-fA-F]{24}")


def utc(value: datetime) -> datetime:
    """The same instant in UTC, rounded up to a whole millisecond. A naive time is taken as UTC.

    MongoDB stores milliseconds and PyMongo cuts finer times down, so rounding up here keeps `from` inclusive and
    `to` exclusive for every stored date. Raises ValueError when the result falls outside years 1 to 9999."""
    try:
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        extra = value.microsecond % 1000
        return value + timedelta(microseconds=1000 - extra) if extra else value
    except OverflowError:
        raise ValueError(f"{value.isoformat()} is out of range in UTC") from None


def fingerprint(customer_id: str | None, account_id: str | None, start: datetime | None, end: datetime | None) -> str:
    """First 16 hex characters of SHA-256 over the canonical filters, so one filter written two ways matches."""
    filters = {"customerId": customer_id and customer_id.lower(), "accountId": account_id and account_id.lower(),
               "from": start and utc(start).isoformat(timespec="milliseconds"),
               "to": end and utc(end).isoformat(timespec="milliseconds")}
    # Keys stay in the order above; absent or empty filters are left out.
    canonical = json.dumps({k: v for k, v in filters.items() if v}, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def encode_cursor(t: datetime, oid: ObjectId, fp: str) -> str:
    payload = json.dumps({"t": utc(t).isoformat(timespec="milliseconds"), "id": str(oid), "fp": fp},
                         separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(s: str) -> tuple[datetime, ObjectId, str]:
    """Raises ValueError for anything encode_cursor could not have produced."""
    raw = base64.b64decode(s + "=" * (-len(s) % 4), altchars=b"-_", validate=True)
    data = json.loads(raw.decode())  # UnicodeDecodeError and JSONDecodeError are ValueErrors
    if not isinstance(data, dict) or set(data) != {"t", "id", "fp"}:
        raise ValueError("cursor must hold exactly t, id and fp")
    t, oid, fp = data["t"], data["id"], data["fp"]
    if not isinstance(t, str) or not isinstance(oid, str) or not isinstance(fp, str):
        raise ValueError("cursor fields must be strings")
    created = datetime.fromisoformat(t)
    if created.tzinfo is None:
        raise ValueError("cursor time has no UTC offset")
    if not _HEX_ID.fullmatch(oid):
        raise ValueError("cursor id is not a 24-character hex ObjectId")
    return utc(created), ObjectId(oid), fp
