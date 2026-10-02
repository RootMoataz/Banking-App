"""Login brute-force protection: five failures in a row lock an email for 15 minutes, counted in MongoDB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD

from app import auth
from app.config import load_settings

LOGIN = "/api/auth/login"


def attempt(client, email, password):
    return client.post(LOGIN, json={"email": email, "password": password})


def test_settings_defaults_and_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    for name in ("LOGIN_MAX_FAILURES", "LOGIN_LOCK_MINUTES"):
        monkeypatch.delenv(name, raising=False)
    defaults = load_settings(env_file=tmp_path / "absent.env")
    assert (defaults.login_max_failures, defaults.login_lock_minutes) == (5, 15)
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    monkeypatch.setenv("LOGIN_LOCK_MINUTES", "1")
    configured = load_settings(env_file=tmp_path / "absent.env")
    assert (configured.login_max_failures, configured.login_lock_minutes) == (3, 1)


@pytest.mark.parametrize("name", ["LOGIN_MAX_FAILURES", "LOGIN_LOCK_MINUTES"])
@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_bad_login_limits_name_the_variable(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_settings(env_file=tmp_path / "absent.env")


def test_lock_minutes_are_capped_at_one_day(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("LOGIN_LOCK_MINUTES", "1440")
    assert load_settings(env_file=tmp_path / "absent.env").login_lock_minutes == 1440
    monkeypatch.setenv("LOGIN_LOCK_MINUTES", "1441")
    with pytest.raises(ValueError, match="LOGIN_LOCK_MINUTES"):
        load_settings(env_file=tmp_path / "absent.env")


def test_five_failures_then_429_with_retry_after(anonymous_client, customer_client):
    for _ in range(5):
        assert attempt(anonymous_client, customer_client.email, "wrong").status_code == 401
    locked = attempt(anonymous_client, customer_client.email, "wrong")
    assert locked.status_code == 429
    assert 0 < int(locked.headers["Retry-After"]) <= 15 * 60
    assert locked.json()["retryAfter"] == int(locked.headers["Retry-After"])
    assert "token" not in locked.json()


def test_parallel_wrong_logins_get_at_most_five_password_checks(anonymous_client, customer_client, monkeypatch):
    checks = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda password, stored: checks.append(1) or real(password, stored))
    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = [r.status_code for r in pool.map(lambda _: attempt(anonymous_client, customer_client.email, "wrong"),
                                                    range(20))]
    assert statuses.count(401) == 5 and statuses.count(429) == 15 and len(checks) == 5


def test_correct_password_during_the_lock_is_still_429(anonymous_client, customer_client):
    for _ in range(5):
        attempt(anonymous_client, customer_client.email, "wrong")
    response = attempt(anonymous_client, customer_client.email, customer_client.password)
    assert response.status_code == 429 and "Retry-After" in response.headers and "token" not in response.json()


def test_lock_ignores_email_letter_case(anonymous_client, customer_client):
    for _ in range(5):
        attempt(anonymous_client, customer_client.email.upper(), "wrong")
    assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 429


def test_success_resets_the_counter(anonymous_client, customer_client, db):
    for _ in range(4):
        attempt(anonymous_client, customer_client.email, "wrong")
    assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 200
    assert db.login_attempts.find_one({"emailKey": customer_client.email.lower()}) is None
    for _ in range(4):  # four more failures are still below the limit because the count started again
        assert attempt(anonymous_client, customer_client.email, "wrong").status_code == 401
    assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 200


def test_unknown_email_is_counted_and_looks_like_a_wrong_password(anonymous_client, customer_client):
    for _ in range(5):
        known = attempt(anonymous_client, customer_client.email, "wrong")
        unknown = attempt(anonymous_client, "ghost@example.com", "wrong")
        assert known.status_code == unknown.status_code == 401 and known.json() == unknown.json()
    known, unknown = (attempt(anonymous_client, e, "wrong") for e in (customer_client.email, "ghost@example.com"))
    assert known.status_code == unknown.status_code == 429
    assert known.json()["detail"] == unknown.json()["detail"]
    # The two locks started a moment apart, so the seconds left may differ by a second or two.
    assert abs(int(known.headers["Retry-After"]) - int(unknown.headers["Retry-After"])) <= 2


def test_the_lock_expires(anonymous_client, customer_client, db):
    for _ in range(5):
        attempt(anonymous_client, customer_client.email, "wrong")
    db.login_attempts.update_one({"emailKey": customer_client.email.lower()},
                                 {"$set": {"lockedUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 200
    assert db.login_attempts.find_one({"emailKey": customer_client.email.lower()}) is None


def test_disabled_user_attempts_are_counted(anonymous_client, customer_client, db):
    db.users.update_one({"emailKey": customer_client.email.lower()}, {"$set": {"disabled": True}})
    for _ in range(5):
        assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 401
    assert attempt(anonymous_client, customer_client.email, customer_client.password).status_code == 429


def test_failure_after_the_lock_expires_starts_a_new_count(anonymous_client, customer_client, db):
    for _ in range(5):
        attempt(anonymous_client, customer_client.email, "wrong")
    db.login_attempts.update_one({"emailKey": customer_client.email.lower()},
                                 {"$set": {"lockedUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert attempt(anonymous_client, customer_client.email, "wrong").status_code == 401
    assert db.login_attempts.find_one({"emailKey": customer_client.email.lower()})["failures"] == 1


def test_other_emails_are_not_locked(anonymous_client, customer_client, make_customer_client):
    other = make_customer_client("other@example.com")
    for _ in range(5):
        attempt(anonymous_client, customer_client.email, "wrong")
    assert attempt(anonymous_client, other.email, other.password).status_code == 200


def test_the_admin_is_throttled_too(anonymous_client, client):
    for _ in range(5):
        assert attempt(anonymous_client, ADMIN_EMAIL, "wrong").status_code == 401
    assert attempt(anonymous_client, ADMIN_EMAIL, ADMIN_PASSWORD).status_code == 429


def test_stored_attempt_holds_no_password_and_has_a_ttl_index(anonymous_client, customer_client, db):
    attempt(anonymous_client, customer_client.email, "secret-wrong-pw")
    doc = db.login_attempts.find_one({"emailKey": customer_client.email.lower()})
    assert doc["failures"] == 1 and "secret-wrong-pw" not in str(doc)
    ttl = [i for i in db.login_attempts.list_indexes() if "expireAfterSeconds" in i]
    assert [list(i["key"]) for i in ttl] == [["updatedAt"]]
