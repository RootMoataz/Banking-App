"""Only explicitly selected, disposable databases are used for integration tests."""
import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings():
    load_dotenv('.env')
    uri = os.getenv('MONGODB_TEST_URI')
    prefix = os.getenv('MONGODB_TEST_DATABASE', '')
    if not uri or not prefix:
        pytest.skip('Set MONGODB_TEST_URI and MONGODB_TEST_DATABASE for real MongoDB integration tests')
    if not prefix.startswith('paper_maker_test_') or prefix == os.getenv('MONGODB_DATABASE'):
        pytest.fail('Tests require a separate paper_maker_test_ database prefix')
    name = prefix + '_' + uuid4().hex[:12]
    config = Settings(uri=uri, database=name)
    yield config
    # The generated name belongs only to this fixture; never drop a supplied database.
    with MongoClient(uri, serverSelectionTimeoutMS=3000) as mongo:
        mongo.drop_database(name)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def db(settings):
    with MongoClient(settings.uri.get_secret_value(), tz_aware=True) as mongo:
        yield mongo[settings.database]
