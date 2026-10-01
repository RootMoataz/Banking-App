"""Offline checks (no MongoDB needed): the CORS_ALLOWED_ORIGINS setting and the CORS headers it produces."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.main import create_app

SETTINGS = Settings("mongodb://unused", "paper_maker_test_offline")
ALLOWED = "http://localhost:5173"


def preflight(client, origin, path="/api/transfers", headers="content-type,idempotency-key"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": headers})


def test_default_origins():
    assert SETTINGS.cors_allowed_origins == ("http://localhost:3000", "http://localhost:5173")


def test_preflight_from_an_allowed_origin():
    response = preflight(TestClient(create_app(SETTINGS)), ALLOWED)  # no lifespan: CORS answers before any route
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed and "content-type" in allowed
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_another_origin_gets_no_cors_header():
    client = TestClient(create_app(SETTINGS))
    response = preflight(client, "http://evil.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert preflight(client, ALLOWED, headers="authorization").status_code == 400  # only the two named headers


def test_simple_request_headers():
    client = TestClient(create_app(SETTINGS))
    # A malformed ID fails validation before any handler runs, so no database is needed.
    allowed = client.get("/api/accounts/abc", headers={"Origin": ALLOWED})
    assert (allowed.status_code, allowed.headers["access-control-allow-origin"]) == (422, ALLOWED)
    other = client.get("/api/accounts/abc", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_configured_origins_replace_the_defaults():
    client = TestClient(create_app(replace(SETTINGS, cors_allowed_origins=("https://bank.example",))))
    assert preflight(client, "https://bank.example").headers["access-control-allow-origin"] == "https://bank.example"
    assert "access-control-allow-origin" not in preflight(client, ALLOWED).headers


@pytest.mark.parametrize("raw, expected", [
    ("https://a.example", ("https://a.example",)),
    (" http://localhost:3000 , https://b.example:8443 ", ("http://localhost:3000", "https://b.example:8443")),
])
def test_load_settings_reads_cors_origins(monkeypatch, tmp_path, raw, expected):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", raw)
    assert load_settings(env_file=tmp_path / "absent.env").cors_allowed_origins == expected


def test_cors_origins_from_env_file(monkeypatch, tmp_path):
    for name in ("MONGODB_URI", "CORS_ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text("MONGODB_URI=mongodb://from-file\nCORS_ALLOWED_ORIGINS=https://file.example\n")
    assert load_settings(env_file=env_file).cors_allowed_origins == ("https://file.example",)


@pytest.mark.parametrize("raw", ["", " , ", "*", "localhost:3000", "http://localhost:3000/", "ftp://a.example",
                                 "http://a.example/path", "http://a.example,not an origin"])
def test_bad_cors_origins_name_the_variable(monkeypatch, tmp_path, raw):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", raw)
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        load_settings(env_file=tmp_path / "absent.env")


def test_cors_error_does_not_leak_the_uri(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://u:SECRETPLACEHOLDER@h/")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(ValueError) as raised:
        load_settings(env_file=tmp_path / "absent.env")
    assert "SECRETPLACEHOLDER" not in str(raised.value)
