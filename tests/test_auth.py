"""JWT login, registration and the ADMIN / CUSTOMER role rules (the shared contract for r30)."""

import hashlib
import json
import logging
import time
from dataclasses import replace

import jwt
import pytest
from bson import ObjectId
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.auth import SCRYPT_N, decode_token, hash_password, issue_token, verify_password
from app.config import Settings, load_settings
from app.main import create_app
from app.services import BankError

SECRET = "x" * 40
OFFLINE = Settings("mongodb://unused", "paper_maker_test_offline", jwt_secret=SECRET)
MISSING = str(ObjectId())


# ---- offline: settings, hashing, tokens -------------------------------------------------------------------------

def test_jwt_secret_is_required(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_settings(env_file=tmp_path / "absent.env")


def test_jwt_secret_must_have_32_characters(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("JWT_SECRET", "x" * 31)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load_settings(env_file=tmp_path / "absent.env")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    assert load_settings(env_file=tmp_path / "absent.env").jwt_secret == "x" * 32


def test_auth_settings_defaults_and_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    for name in ("JWT_EXPIRATION_MINUTES", "ADMIN_EMAIL", "ADMIN_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    defaults = load_settings(env_file=tmp_path / "absent.env")
    assert (defaults.jwt_expiration_minutes, defaults.admin_email, defaults.admin_password) == (60, None, None)
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "5")
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "boss-password")
    configured = load_settings(env_file=tmp_path / "absent.env")
    assert (configured.jwt_expiration_minutes, configured.admin_email, configured.admin_password) == (
        5, "boss@example.com", "boss-password")


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_bad_jwt_expiration_names_the_variable(monkeypatch, tmp_path, value):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", value)
    with pytest.raises(ValueError, match="JWT_EXPIRATION_MINUTES"):
        load_settings(env_file=tmp_path / "absent.env")


def test_secrets_are_not_in_the_settings_repr():
    text = repr(replace(OFFLINE, admin_password="very-secret-admin-pw"))
    assert SECRET not in text and "very-secret-admin-pw" not in text


@pytest.mark.parametrize("secret", ["", "short"])
def test_app_refuses_to_start_with_a_missing_or_short_secret(secret):
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(create_app(Settings("mongodb://unused", "paper_maker_test_offline", jwt_secret=secret))):
            pass


def test_password_hash_is_salted_and_verifies():
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second and "correct horse" not in first
    assert verify_password("correct horse", first) and verify_password("correct horse", second)
    assert not verify_password("correct horsf", first)
    assert not verify_password("correct horse", "not a hash")


def test_new_hashes_use_the_stronger_cost_and_old_hashes_still_verify():
    assert SCRYPT_N == 2 ** 15
    assert hash_password("whatever-pw").split("$")[1] == str(2 ** 15)
    salt = b"s" * 16
    digest = hashlib.scrypt(b"old-parameter-pw", salt=salt, n=2 ** 14, r=8, p=1)
    old = f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"
    assert verify_password("old-parameter-pw", old)
    assert not verify_password("old-parameter-px", old)
    assert not verify_password("old-parameter-pw", hash_password("another-password"))


def _token(claims, secret=SECRET, algorithm="HS256"):
    return jwt.encode(claims, secret, algorithm=algorithm)


def test_token_round_trip_and_claims():
    sub = str(ObjectId())
    claims = jwt.decode(issue_token(sub, OFFLINE), SECRET, algorithms=["HS256"])
    assert claims["sub"] == sub and claims["exp"] - claims["iat"] == 60 * 60
    assert decode_token(issue_token(sub, OFFLINE), OFFLINE) == sub


def test_token_lifetime_follows_the_setting():
    claims = jwt.decode(issue_token(MISSING, replace(OFFLINE, jwt_expiration_minutes=5)), SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 300


@pytest.mark.parametrize("token", [
    _token({"sub": MISSING, "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600}),  # expired
    _token({"sub": MISSING, "exp": int(time.time()) + 3600}, secret="y" * 40),  # another secret
    _token({"iat": int(time.time()), "exp": int(time.time()) + 3600}),  # no sub
    _token({"sub": MISSING}),  # no exp
    _token({"sub": MISSING, "exp": int(time.time()) + 3600}, secret=SECRET * 2, algorithm="HS512"),  # another algorithm
    jwt.encode({"sub": MISSING, "exp": int(time.time()) + 3600}, None, algorithm="none"),  # unsigned
    "not-a-token",
    "",
])
def test_bad_tokens_are_rejected(token):
    with pytest.raises(BankError) as raised:
        decode_token(token, OFFLINE)
    assert raised.value.status == 401


def test_tampered_token_is_rejected():
    token = issue_token(MISSING, OFFLINE)
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(BankError):
        decode_token(forged, OFFLINE)


# ---- register / login / me --------------------------------------------------------------------------------------

def register(client, email="new@example.com", name="New Person", password="correct horse battery", **extra):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password, **extra})


def test_register_creates_customer_and_user(anonymous_client, client, db):
    response = register(anonymous_client)
    assert response.status_code == 201
    body = response.json()
    assert body["tokenType"] == "Bearer" and body["token"]
    user = body["user"]
    assert set(user) == {"email", "role", "customerId", "name"}
    assert (user["email"], user["role"], user["name"]) == ("new@example.com", "CUSTOMER", "New Person")
    customer = client.get(f"/api/customers/{user['customerId']}").json()  # staff sees the customer record
    assert (customer["name"], customer["email"]) == ("New Person", "new@example.com")
    stored = db.users.find_one({"emailKey": "new@example.com"})
    assert str(stored["customerId"]) == user["customerId"] and stored["role"] == "CUSTOMER"


def test_register_token_works_for_me(anonymous_client):
    body = register(anonymous_client).json()
    me = anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json() == body["user"]


def test_register_duplicate_email_is_409_in_any_letter_case(anonymous_client, db):
    assert register(anonymous_client, email="dup@example.com").status_code == 201
    again = register(anonymous_client, email="DUP@Example.com", name="Someone Else")
    assert again.status_code == 409 and "detail" in again.json()
    assert db.customers.count_documents({}) == 1 and db.users.count_documents({"role": "CUSTOMER"}) == 1


def test_register_with_the_email_of_an_existing_customer_is_409_and_makes_no_user(anonymous_client, client, db):
    client.post("/api/customers", json={"name": "Walk In", "email": "walkin@example.com"})
    assert register(anonymous_client, email="walkin@example.com").status_code == 409
    assert db.users.count_documents({"emailKey": "walkin@example.com"}) == 0


def test_register_failure_leaves_neither_half(client, db, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("app.repositories.UserRepository.insert", fail)
    app_client = TestClient(client.app, raise_server_exceptions=False)
    assert register(app_client, email="half@example.com").status_code == 500
    assert db.customers.count_documents({}) == 0
    assert db.users.count_documents({"role": "CUSTOMER"}) == 0


def test_register_user_failure_after_customer_insert_rolls_the_customer_back(client, db, monkeypatch):
    def duplicate(*args, **kwargs):
        raise DuplicateKeyError("users emailKey")

    monkeypatch.setattr("app.repositories.UserRepository.insert", duplicate)
    assert register(TestClient(client.app), email="half@example.com").status_code == 409
    assert db.customers.count_documents({}) == 0


@pytest.mark.parametrize("extra", [{"role": "ADMIN"}, {"isAdmin": True}, {"customerId": MISSING}])
def test_registration_cannot_make_an_admin(anonymous_client, db, extra):
    assert register(anonymous_client, **extra).status_code == 422
    assert db.users.count_documents({"emailKey": "new@example.com"}) == 0
    assert register(anonymous_client).json()["user"]["role"] == "CUSTOMER"
    assert db.users.count_documents({"role": "ADMIN"}) == 1  # only the fixture's admin


@pytest.mark.parametrize("password", ["short", "1234567", "x" * 73, "é" * 37, "new@example.com", "NEW@example.com"])
def test_register_rejects_bad_passwords(anonymous_client, password):
    assert register(anonymous_client, password=password).status_code == 422


@pytest.mark.parametrize("password", ["12345678", "x" * 72, "é" * 36, "  spaces kept  "])
def test_register_accepts_8_to_72_bytes_and_keeps_spaces(anonymous_client, password):
    assert register(anonymous_client, password=password).status_code == 201
    assert anonymous_client.post("/api/auth/login",
                                 json={"email": "new@example.com", "password": password}).status_code == 200


@pytest.mark.parametrize("body", [{"email": "nope", "name": "N", "password": "12345678"},
                                  {"email": "a@example.com", "name": "", "password": "12345678"},
                                  {"email": "a@example.com", "password": "12345678"}])
def test_register_validates_the_body(anonymous_client, body):
    assert anonymous_client.post("/api/auth/register", json=body).status_code == 422


def test_login_returns_token_and_user(anonymous_client):
    register(anonymous_client, email="Mixed@Example.com")
    response = anonymous_client.post("/api/auth/login", json={"email": "mixed@example.COM",
                                                              "password": "correct horse battery"})
    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "Bearer" and body["user"]["role"] == "CUSTOMER"
    assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200


def test_login_failures_are_identical(anonymous_client):
    register(anonymous_client)
    wrong_password = anonymous_client.post("/api/auth/login", json={"email": "new@example.com", "password": "nope"})
    unknown_email = anonymous_client.post("/api/auth/login", json={"email": "who@example.com", "password": "nope"})
    malformed = anonymous_client.post("/api/auth/login", json={"email": "not-an-email", "password": "nope"})
    assert wrong_password.status_code == unknown_email.status_code == malformed.status_code == 401
    assert wrong_password.json() == unknown_email.json() == malformed.json()
    assert "token" not in wrong_password.json()


def test_disabled_user_cannot_log_in(anonymous_client, db):
    register(anonymous_client)
    db.users.update_one({"emailKey": "new@example.com"}, {"$set": {"disabled": True}})
    response = anonymous_client.post("/api/auth/login", json={"email": "new@example.com",
                                                              "password": "correct horse battery"})
    assert response.status_code == 401


def test_me_for_admin_and_customer(client, customer_client):
    assert client.get("/api/auth/me").json() == {"email": ADMIN_EMAIL, "role": "ADMIN", "customerId": None,
                                                 "name": "Administrator"}
    assert customer_client.get("/api/auth/me").json() == {
        "email": "customer@example.com", "role": "CUSTOMER", "customerId": customer_client.customer_id,
        "name": "Casey Customer"}


def test_me_follows_a_customer_rename(client, customer_client):
    client.put(f"/api/customers/{customer_client.customer_id}",
               json={"name": "Renamed Person", "email": "customer@example.com"})
    assert customer_client.get("/api/auth/me").json()["name"] == "Renamed Person"


def test_health_is_public(anonymous_client):
    response = anonymous_client.get("/api/public/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_passwords_never_appear_in_responses(anonymous_client, client, db):
    password = "unmistakable-password-42"
    bodies = [register(anonymous_client, password=password).text,
              anonymous_client.post("/api/auth/login", json={"email": "new@example.com", "password": password}).text,
              client.get("/api/customers").text, client.get("/api/auth/me").text]
    stored_hash = db.users.find_one({"emailKey": "new@example.com"})["passwordHash"]
    token = anonymous_client.post("/api/auth/login", json={"email": "new@example.com", "password": password}).json()["token"]
    bodies.append(anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).text)
    for text in bodies:
        assert password not in text and stored_hash not in text and "passwordHash" not in text
    assert password not in stored_hash


# ---- validation errors do not echo input ------------------------------------------------------------------------

@pytest.mark.parametrize("path, body", [
    ("/api/auth/register", {"name": "N N", "email": "lone@example.com", "password": "\ud800abcdefgh"}),
    ("/api/auth/login", {"email": "lone@example.com", "password": "\ud800abcdefgh"}),
])
def test_lone_surrogate_password_is_a_422_and_never_echoed(anonymous_client, path, body):
    response = anonymous_client.post(path, content=json.dumps(body), headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text
    assert "abcdefgh" not in response.text


def test_validation_errors_have_no_input_or_ctx(anonymous_client):
    response = register(anonymous_client, password="short")
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors and all({"type", "loc", "msg"} <= set(e) for e in errors)
    assert all("input" not in e and "ctx" not in e for e in errors)
    other = anonymous_client.post("/api/auth/register", json={"name": "N", "email": "nope", "password": "pw-secret-123"})
    assert other.status_code == 422 and "pw-secret-123" not in other.text and "nope" not in other.text


# ---- every other route needs a valid token ----------------------------------------------------------------------

def test_missing_and_invalid_tokens_are_401(anonymous_client):
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}):
        response = anonymous_client.get("/api/customers", headers=headers)
        assert response.status_code == 401 and "detail" in response.json()


def test_expired_token_is_401(anonymous_client, settings, db):
    user = db.users.find_one({"role": "ADMIN"})
    expired = jwt.encode({"sub": str(user["_id"]), "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600},
                         settings.jwt_secret, algorithm="HS256")
    assert anonymous_client.get("/api/customers", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_tampered_and_foreign_tokens_are_401(anonymous_client, settings, db):
    sub = str(db.users.find_one({"role": "ADMIN"})["_id"])
    good = issue_token(sub, settings)
    for token in (good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB"),
                  issue_token(sub, replace(settings, jwt_secret="z" * 40))):
        assert anonymous_client.get("/api/customers", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_for_unknown_user_or_odd_subject_is_401(anonymous_client, settings):
    for sub in (MISSING, "not-an-object-id"):
        token = issue_token(sub, settings)
        assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_for_a_deleted_user_is_401(customer_client, db):
    assert customer_client.get("/api/auth/me").status_code == 200
    db.users.delete_many({"emailKey": "customer@example.com"})
    assert customer_client.get("/api/auth/me").status_code == 401
    assert customer_client.get(f"/api/customers/{customer_client.customer_id}").status_code == 401


def test_token_for_a_disabled_user_is_401(customer_client, db):
    db.users.update_one({"emailKey": "customer@example.com"}, {"$set": {"disabled": True}})
    assert customer_client.get("/api/auth/me").status_code == 401


def test_role_in_the_database_wins_over_the_token(customer_client, db):
    assert customer_client.get("/api/customers").status_code == 403
    db.users.update_one({"emailKey": "customer@example.com"}, {"$set": {"role": "ADMIN"}})
    assert customer_client.get("/api/customers").status_code == 200
    db.users.update_one({"emailKey": "customer@example.com"}, {"$set": {"role": "CUSTOMER"}})
    assert customer_client.get("/api/customers").status_code == 403


def test_deleting_a_customer_ends_their_login(client, customer_client, db):
    assert client.delete(f"/api/customers/{customer_client.customer_id}").status_code == 204
    assert db.users.count_documents({"emailKey": "customer@example.com"}) == 0
    assert customer_client.get("/api/auth/me").status_code == 401


# ---- role matrix ------------------------------------------------------------------------------------------------

@pytest.fixture
def world(client, make_customer_client):
    """Staff `client`, customers `alice` and `bob`, each with one funded account."""
    alice, bob = make_customer_client("alice@example.com", "Alice A"), make_customer_client("bob@example.com", "Bob B")
    for who in (alice, bob):
        account = client.post("/api/accounts", json={"customerId": who.customer_id, "accountType": "SAVINGS"}).json()
        client.post(f"/api/accounts/{account['accountId']}/deposit", json={"amount": "100.00"})
        who.account_id = account["accountId"]
    return alice, bob


def fill(template, who, other):
    if not isinstance(template, str):
        return template
    return template.format(own=who.customer_id, other=other.customer_id, own_acct=who.account_id,
                           other_acct=other.account_id)


FORBIDDEN_FOR_CUSTOMERS = [  # 403 whatever the target: the action itself is staff-only
    ("GET", "/api/customers", None),
    ("POST", "/api/customers", {"name": "X Y", "email": "x@example.com"}),
    ("GET", "/api/customers/search", None),
    ("PUT", "/api/customers/{own}", {"name": "X Y", "email": "x@example.com"}),
    ("DELETE", "/api/customers/{own}", None),
    ("DELETE", "/api/customers/{other}", None),
    ("GET", "/api/accounts", None),
    ("GET", "/api/accounts/premium", None),
    ("PUT", "/api/accounts/{own_acct}", {"accountType": "CURRENT"}),
    ("DELETE", "/api/accounts/{own_acct}", None),
    ("POST", "/api/accounts/{own_acct}/deposit", {"amount": "1.00"}),
    ("POST", "/api/accounts/{own_acct}/withdraw", {"amount": "1.00"}),
    ("POST", "/api/accounts/{other_acct}/deposit", {"amount": "1.00"}),
    ("GET", "/api/audit/transactions?customerId={own}", None),
    ("POST", "/api/users", {"name": "X Y", "email": "x@example.com"}),
    ("POST", "/api/accounts", {"customerId": "{other}", "accountType": "SAVINGS"}),
    ("POST", "/api/transfers", {"fromAccountId": "{other_acct}", "toAccountId": "{own_acct}", "amount": "1.00"}),
]
HIDDEN_FROM_CUSTOMERS = [  # another customer's object: 404, exactly like a missing one
    ("GET", "/api/customers/{other}", None),
    ("GET", "/api/customers/{other}/accounts", None),
    ("PATCH", "/api/customers/{other}/preferences", {"marketingEnabled": True}),
    ("GET", "/api/customers/{other}/notifications", None),
    ("GET", "/api/accounts/{other_acct}", None),
    ("GET", "/api/accounts/{other_acct}/transactions", None),
]
ALLOWED_FOR_CUSTOMERS = [
    ("GET", "/api/customers/{own}", None),
    ("GET", "/api/customers/{own}/accounts", None),
    ("PATCH", "/api/customers/{own}/preferences", {"marketingEnabled": True}),
    ("GET", "/api/customers/{own}/notifications", None),
    ("POST", "/api/accounts", {"customerId": "{own}", "accountType": "CURRENT"}),
    ("GET", "/api/accounts/{own_acct}", None),
    ("GET", "/api/accounts/{own_acct}/transactions", None),
    ("POST", "/api/transfers", {"fromAccountId": "{own_acct}", "toAccountId": "{other_acct}", "amount": "1.00"}),
    ("GET", "/api/auth/me", None),
]


def call(who, other, method, template, body, client):
    body = None if body is None else {k: fill(v, who, other) for k, v in body.items()}
    return client.request(method, fill(template, who, other), json=body)


@pytest.mark.parametrize("method, path, body", FORBIDDEN_FOR_CUSTOMERS)
def test_customer_gets_403_on_staff_only_actions(world, method, path, body):
    alice, bob = world
    response = call(alice, bob, method, path, body, alice)
    assert response.status_code == 403 and "detail" in response.json()


@pytest.mark.parametrize("method, path, body", HIDDEN_FROM_CUSTOMERS)
def test_customer_gets_404_for_other_peoples_objects(world, method, path, body):
    alice, bob = world
    response = call(alice, bob, method, path, body, alice)
    assert response.status_code == 404
    missing = alice.request(method, path.format(own=alice.customer_id, other=MISSING, own_acct=alice.account_id,
                                                other_acct=MISSING), json=body)
    assert response.json()["detail"].split()[0] == missing.json()["detail"].split()[0]  # same wording: "Customer"/"Account"


@pytest.mark.parametrize("method, path, body", ALLOWED_FOR_CUSTOMERS)
def test_customer_may_use_their_own_things(world, method, path, body):
    alice, bob = world
    response = call(alice, bob, method, path, body, alice)
    assert response.status_code in (200, 201), response.text


@pytest.mark.parametrize("method, path, body", FORBIDDEN_FOR_CUSTOMERS + HIDDEN_FROM_CUSTOMERS + ALLOWED_FOR_CUSTOMERS)
def test_staff_may_do_everything(world, client, method, path, body):
    alice, bob = world
    response = call(alice, bob, method, path, body, client)
    assert response.status_code not in (401, 403), response.text
    if method != "DELETE":  # deleting a funded account answers 409, which is still not 401/403
        assert response.status_code in (200, 201), response.text


@pytest.mark.parametrize("method, path, body", FORBIDDEN_FOR_CUSTOMERS + HIDDEN_FROM_CUSTOMERS + ALLOWED_FOR_CUSTOMERS)
def test_every_route_needs_a_token(world, anonymous_client, method, path, body):
    alice, bob = world
    assert call(alice, bob, method, path, body, anonymous_client).status_code == 401


def test_customer_sees_only_their_own_accounts_and_money(world, client):
    alice, bob = world
    accounts = alice.get(f"/api/customers/{alice.customer_id}/accounts").json()
    assert [a["accountId"] for a in accounts] == [alice.account_id]
    assert alice.get(f"/api/accounts/{alice.account_id}").json()["balance"] == "100.00"
    transactions = alice.get(f"/api/accounts/{alice.account_id}/transactions").json()
    assert [t["type"] for t in transactions] == ["DEPOSIT"]


def test_customer_opens_an_account_for_themself_only(world, client, db):
    alice, bob = world
    mine = alice.post("/api/accounts", json={"customerId": alice.customer_id, "accountType": "CURRENT"})
    assert mine.status_code == 201 and mine.json()["customerId"] == alice.customer_id
    legacy = alice.post("/api/accounts", json={"userId": alice.customer_id, "accountType": "CURRENT"})
    assert legacy.status_code == 201
    assert alice.post("/api/accounts", json={"customerId": bob.customer_id, "accountType": "X"}).status_code == 403
    assert db.accounts.count_documents({"customerId": ObjectId(bob.customer_id)}) == 1


def test_customer_transfers_only_from_their_own_account(world, db):
    alice, bob = world
    ok = alice.post("/api/transfers", json={"fromAccountId": alice.account_id, "toAccountId": bob.account_id,
                                            "amount": "40.00"})
    assert ok.status_code == 200
    assert (ok.json()["fromBalanceAfter"], ok.json()["toBalanceAfter"]) == ("60.00", None)  # a stranger's balance stays hidden
    for source in (bob.account_id, MISSING):
        stolen = alice.post("/api/transfers", json={"fromAccountId": source, "toAccountId": alice.account_id,
                                                    "amount": "40.00"})
        assert stolen.status_code == 403
    assert db.accounts.find_one({"_id": ObjectId(bob.account_id)})["balanceCents"] == 14000


def test_customer_sees_both_balances_when_moving_money_between_their_own_accounts(world, client):
    alice, _ = world
    second = client.post("/api/accounts", json={"customerId": alice.customer_id, "accountType": "CURRENT"}).json()
    ok = alice.post("/api/transfers", json={"fromAccountId": alice.account_id, "toAccountId": second["accountId"],
                                            "amount": "10.00"})
    assert ok.status_code == 200
    assert (ok.json()["fromBalanceAfter"], ok.json()["toBalanceAfter"]) == ("90.00", "10.00")


def test_customer_never_learns_a_strangers_balance_from_a_transfer(world):
    alice, bob = world
    ok = alice.post("/api/transfers", json={"fromAccountId": alice.account_id, "toAccountId": bob.account_id,
                                            "amount": "1.00"})
    assert ok.status_code == 200
    assert ok.json()["fromBalanceAfter"] == "99.00" and ok.json()["toBalanceAfter"] is None
    assert "101.00" not in ok.text


def test_staff_transfer_still_returns_both_balances(world, client):
    alice, bob = world
    ok = client.post("/api/transfers", json={"fromAccountId": alice.account_id, "toAccountId": bob.account_id,
                                             "amount": "1.00"})
    assert (ok.json()["fromBalanceAfter"], ok.json()["toBalanceAfter"]) == ("99.00", "101.00")


def test_customer_marketing_preference_is_their_own(world):
    alice, bob = world
    changed = alice.patch(f"/api/customers/{alice.customer_id}/preferences", json={"marketingEnabled": True})
    assert changed.json()["marketingEnabled"] is True
    assert bob.get(f"/api/customers/{bob.customer_id}").json()["marketingEnabled"] is False


def test_an_authenticated_bad_request_is_still_validated(world):
    alice, _ = world
    assert alice.get("/api/accounts/abc").status_code == 422


def test_forbidden_beats_validation_and_missing(world):
    alice, _ = world
    assert alice.post("/api/accounts/abc/deposit", json={"amount": "-1"}).status_code == 403
    assert alice.get(f"/api/customers/{MISSING}").status_code == 404


# ---- admin bootstrap --------------------------------------------------------------------------------------------

def test_admin_bootstrap_creates_one_admin_and_is_idempotent(settings, db):
    configured = replace(settings, admin_email="Boss@Example.com", admin_password="first-boss-password")
    with TestClient(create_app(configured)) as first:
        login = first.post("/api/auth/login", json={"email": "boss@example.com", "password": "first-boss-password"})
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "ADMIN" and login.json()["user"]["customerId"] is None
        stored = db.users.find_one({"emailKey": "boss@example.com"})
    # Restart with another password: the existing account is left alone, nothing is duplicated or overwritten.
    with TestClient(create_app(replace(configured, admin_password="second-boss-password"))) as second:
        assert second.post("/api/auth/login", json={"email": "boss@example.com",
                                                    "password": "first-boss-password"}).status_code == 200
        assert second.post("/api/auth/login", json={"email": "boss@example.com",
                                                    "password": "second-boss-password"}).status_code == 401
    assert db.users.count_documents({"emailKey": "boss@example.com"}) == 1
    assert db.users.find_one({"emailKey": "boss@example.com"})["passwordHash"] == stored["passwordHash"]


def test_no_admin_is_bootstrapped_without_both_settings(settings, db):
    for partial in (replace(settings, admin_email="solo@example.com"),
                    replace(settings, admin_password="solo-password-long")):
        with TestClient(create_app(partial)):
            pass
    assert db.users.count_documents({"emailKey": "solo@example.com"}) == 0


def test_admin_password_must_have_12_characters_and_the_error_hides_the_value(settings):
    weak = replace(settings, admin_email="weak@example.com", admin_password="short-pw-11")
    assert len("short-pw-11") == 11
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD") as raised:
        with TestClient(create_app(weak)):
            pass
    assert "short-pw-11" not in str(raised.value)


def test_admin_bootstrap_skips_an_email_that_belongs_to_a_customer_and_warns(settings, db, caplog):
    with TestClient(create_app(settings)) as c:
        register(c, email="taken@example.com", password="customer-password-1")
    configured = replace(settings, admin_email="taken@example.com", admin_password="admin-password-long")
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        with TestClient(create_app(configured)):
            pass
    assert db.users.find_one({"emailKey": "taken@example.com"})["role"] == "CUSTOMER"
    assert any(r.levelno == logging.WARNING and "taken@example.com" in r.getMessage() for r in caplog.records)
    assert "admin-password-long" not in caplog.text
