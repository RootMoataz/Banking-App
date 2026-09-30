import pytest


def test_missing_configuration_is_safe(monkeypatch, tmp_path):
    from app.config import Settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('MONGODB_URI', raising=False)
    monkeypatch.delenv('MONGODB_DATABASE', raising=False)
    with pytest.raises(ValueError, match='MONGODB_URI and MONGODB_DATABASE'):
        Settings.from_env()


def test_credentials_are_redacted_and_env_is_loaded(monkeypatch, tmp_path):
    from app.config import Settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('MONGODB_URI', raising=False)
    monkeypatch.delenv('MONGODB_DATABASE', raising=False)
    (tmp_path / '.env').write_text('MONGODB_URI=mongodb://demo:sentinel_secret@localhost\nMONGODB_DATABASE=paper_maker\n')
    settings = Settings.from_env()
    assert settings.database == 'paper_maker'
    assert 'sentinel_secret' not in repr(settings)


@pytest.mark.parametrize('name', ['', 'bad/name', 'admin', 'local', 'config'])
def test_reject_reserved_or_invalid_databases(name):
    from app.config import Settings
    with pytest.raises(ValueError):
        Settings(uri='mongodb://localhost', database=name)


def test_failed_startup_hides_driver_details_and_closes_client(monkeypatch):
    from fastapi.testclient import TestClient
    from pymongo.errors import OperationFailure
    from app.config import Settings
    from app.database import MongoStore
    from app.main import create_app
    closed = []
    original_close = MongoStore.close
    def fail(self):
        raise OperationFailure('mongodb://demo:sentinel_secret@localhost')
    def close(self):
        closed.append(True)
        original_close(self)
    monkeypatch.setattr(MongoStore, 'connect', fail)
    monkeypatch.setattr(MongoStore, 'close', close)
    with pytest.raises(RuntimeError) as error:
        with TestClient(create_app(Settings(uri='mongodb://localhost', database='workshop'))):
            pass
    assert 'sentinel_secret' not in str(error.value)
    assert closed == [True]
