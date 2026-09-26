"""
aiplatform.storage.corp_db's default-credential guard runs at *module
import time* (it bypasses aiplatform.settings entirely — including for its
own APP_ENV check, so that importing this module never forces construction
of the shared Settings object just to read one flag), so these tests reload
the module under different env vars rather than calling a function — the
only way to exercise import-time code.
"""

import importlib

import pytest


def _reload_corp_db():
    import aiplatform.storage.corp_db as corp_db_module

    return importlib.reload(corp_db_module)


@pytest.fixture(autouse=True)
def _restore_clean_module_state(monkeypatch):
    monkeypatch.delenv("CORP_DATABASE_URL", raising=False)
    yield
    monkeypatch.delenv("CORP_DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    _reload_corp_db()


def test_default_corp_database_url_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="local-dev default"):
        _reload_corp_db()


def test_default_corp_database_url_allowed_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")

    mod = _reload_corp_db()

    assert mod._CORP_DATABASE_URL.endswith("aiplatform_corp")


def test_real_corp_database_url_allowed_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "CORP_DATABASE_URL", "postgresql+asyncpg://real_user:real_pass@prod-host:5432/corp"
    )

    mod = _reload_corp_db()

    assert mod._CORP_DATABASE_URL == "postgresql+asyncpg://real_user:real_pass@prod-host:5432/corp"
