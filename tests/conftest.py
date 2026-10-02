import os
import uuid
from dataclasses import replace

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

# Set before any settings are loaded: the app refuses to start without a JWT secret of at least 32 characters.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-not-used-anywhere-else-0123456789"

from bson import ObjectId

from app.auth import Principal, hash_password, issue_token
from app.config import ROOT, load_settings
from app.db import ensure_indexes, get_database
from app.main import create_app
from app.repositories import UserRepository

COLLECTIONS = ("customers", "accounts", "transactions", "notifications", "users")
ADMIN_EMAIL = "admin@paper-maker.test"
ADMIN_PASSWORD = "admin-test-password"
_ADMIN_HASH = hash_password(ADMIN_PASSWORD)  # hashed once: scrypt is slow on purpose


def _assert_test_db(name: str) -> None:
    """Checked wherever data is destroyed, so no test can ever wipe the real database."""
    assert name.startswith("paper_maker_test_"), f"refusing to touch database {name!r}"


class _AdminForAnyToken:
    def authenticate(self, token):
        return Principal(ObjectId(), "offline@example.com", "ADMIN", None)


def offline_client(app_settings) -> TestClient:
    """A client with no database and no lifespan, signed in as staff, for requests that fail validation before any
    handler runs (authentication comes first, so they need some identity)."""
    offline_app = create_app(app_settings)
    offline_app.state.auth = _AdminForAnyToken()
    offline_client_ = TestClient(offline_app)
    offline_client_.headers["Authorization"] = "Bearer offline"
    return offline_client_


@pytest.fixture(scope="session")
def settings():
    if not os.environ.get("MONGODB_URI") and not dotenv_values(ROOT / ".env").get("MONGODB_URI"):
        raise RuntimeError("MONGODB_URI is not set")
    # Thresholds are pinned (the documented defaults) so tests do not depend on a local .env.
    test_settings = replace(load_settings(), mongodb_db=f"paper_maker_test_{uuid.uuid4().hex[:8]}",
                            low_cents=10_000, premium_cents=1_000_000)
    _assert_test_db(test_settings.mongodb_db)
    return test_settings


@pytest.fixture(scope="session")
def db(settings):
    database = get_database(settings)
    try:
        ensure_indexes(database)
        yield database
    finally:  # runs even when index creation fails, so a broken run leaves nothing on Atlas
        _assert_test_db(database.name)
        database.client.drop_database(database.name)
        database.client.close()


@pytest.fixture(autouse=True)
def clean_collections(request):
    # Pure unit tests never ask for db/client, so they must not trigger a connection to Atlas.
    if "db" not in request.fixturenames and "client" not in request.fixturenames:
        return
    db = request.getfixturevalue("db")
    _assert_test_db(db.name)
    for name in COLLECTIONS:
        db[name].delete_many({})


def pytest_configure(config):
    config.addinivalue_line("markers", "atlas: needs the MongoDB Atlas test database (deselect with -m 'not atlas')")


def pytest_collection_modifyitems(items):
    for item in items:
        if "db" in item.fixturenames or "client" in item.fixturenames:
            item.add_marker(pytest.mark.atlas)


@pytest.fixture
def client(settings, db, monkeypatch):
    # A fresh app per test, but on the session's connection and indexes: startup would otherwise open a new
    # MongoClient and recreate nine indexes on Atlas for every test. Tests that need the real startup path
    # (index creation, two app instances) build create_app(settings) themselves and do not use this fixture.
    monkeypatch.setattr("app.main.get_database", lambda _settings: db)
    monkeypatch.setattr("app.main.ensure_indexes", lambda _db: None)
    monkeypatch.setattr(db.client, "close", lambda: None)  # app shutdown must not close the shared client
    admin = UserRepository(db).insert(ADMIN_EMAIL, _ADMIN_HASH, "ADMIN", None, "Administrator")
    with TestClient(create_app(settings)) as test_client:
        # Every existing test calls the API as staff; tests of other roles use anonymous_client or customer_client.
        test_client.headers["Authorization"] = f"Bearer {issue_token(str(admin['_id']), settings)}"
        yield test_client


@pytest.fixture
def anonymous_client(client):
    """The same app as `client`, with no token."""
    return TestClient(client.app)


@pytest.fixture
def make_customer_client(client):
    """Returns make(email, name): registers a customer through the API and returns a client holding their token."""
    def make(email="customer@example.com", name="Casey Customer", password="correct horse battery"):
        customer = TestClient(client.app)
        response = customer.post("/api/auth/register", json={"name": name, "email": email, "password": password})
        assert response.status_code == 201, response.text
        body = response.json()
        customer.headers["Authorization"] = f"Bearer {body['token']}"
        customer.customer_id, customer.email, customer.password = body["user"]["customerId"], email, password
        return customer
    return make


@pytest.fixture
def customer_client(make_customer_client):
    return make_customer_client()
