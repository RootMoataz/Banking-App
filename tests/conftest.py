import os
import uuid
from dataclasses import replace

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.config import ROOT, load_settings
from app.db import ensure_indexes, get_database
from app.main import create_app

COLLECTIONS = ("customers", "accounts", "transactions", "notifications")


def _assert_test_db(name: str) -> None:
    """Checked wherever data is destroyed, so no test can ever wipe the real database."""
    assert name.startswith("paper_maker_test_"), f"refusing to touch database {name!r}"


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
    with TestClient(create_app(settings)) as test_client:
        yield test_client
