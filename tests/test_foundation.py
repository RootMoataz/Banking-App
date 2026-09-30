from decimal import Decimal

import pytest

from app.config import Settings, load_settings
from app.money import MAX_CENTS, from_cents, to_cents


def test_cents_round_trip():
    assert to_cents(Decimal("99999999.99")) == MAX_CENTS
    assert str(from_cents(2500)) == "25.00"


def test_rejects_sub_cent():
    with pytest.raises(ValueError):
        to_cents(Decimal("0.001"))


def test_rejects_negative():
    with pytest.raises(ValueError):
        to_cents(Decimal("-1.00"))


@pytest.mark.parametrize("bad", ["Infinity", "-Infinity", "NaN", "sNaN"])
def test_to_cents_rejects_non_finite_with_value_error(bad):
    with pytest.raises(ValueError):
        to_cents(Decimal(bad))


def test_to_cents_rejects_sub_cent_beyond_default_precision():
    # 28 significant digits: amount * 100 would silently round to a whole cent
    with pytest.raises(ValueError):
        to_cents(Decimal("1.00000000000000000000000000001"))


def test_to_cents_rejects_more_than_max_balance():
    with pytest.raises(ValueError):
        to_cents(Decimal("100000000.00"))
    with pytest.raises(ValueError):
        to_cents(Decimal("1e30"))


def test_to_cents_accepts_scientific_notation_and_trailing_zeros():
    assert to_cents(Decimal("1E+2")) == 10_000
    assert to_cents(Decimal("0.10000")) == 10
    assert to_cents(Decimal("-0")) == 0


def test_settings_repr_hides_the_uri():
    assert "SECRETPLACEHOLDER" not in repr(Settings("mongodb+srv://u:SECRETPLACEHOLDER@h/", "d"))


def test_load_settings_missing_uri_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_URI is not set"):
        load_settings(env_file=tmp_path / "absent.env")


@pytest.mark.parametrize("value", ["abc", "100,00", "NaN", "Infinity", "-5", "1e40"])
def test_load_settings_bad_threshold_names_the_variable(monkeypatch, tmp_path, value):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("LOW_BALANCE_THRESHOLD", value)
    with pytest.raises(ValueError, match="LOW_BALANCE_THRESHOLD"):
        load_settings(env_file=tmp_path / "absent.env")


def test_load_settings_rejects_empty_database_name(monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://x")
    monkeypatch.setenv("MONGODB_DB", "")
    with pytest.raises(ValueError, match="MONGODB_DB"):
        load_settings(env_file=tmp_path / "absent.env")


def test_load_settings_finds_env_from_any_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.chdir(tmp_path)  # the project's .env must be found relative to the code, not the cwd
    assert load_settings().mongodb_uri.startswith("mongodb")


def test_thresholds_must_be_ordered():
    with pytest.raises(ValueError):
        Settings("mongodb://x", "d", low_cents=10000, premium_cents=100)


def test_indexes_exist(db):
    names = {i["name"] for i in db.customers.list_indexes()}
    assert "emailKey_unique" in names


def test_idempotency_index_is_partial_unique(db):
    idx = {i["name"]: i for i in db.transactions.list_indexes()}["idem_unique"]
    assert idx["unique"] is True
    assert idx["partialFilterExpression"] == {"idempotencyKey": {"$type": "string"}}
