import pytest
from aiplatform.settings import Settings, get_settings


def test_default_settings_load():
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="sk-test",
        anthropic_api_key="sk-ant-test",
    )
    assert s.app_env == "development"
    assert s.llm_provider == "openai"
    assert s.chunk_size == 800
    assert s.chunk_overlap == 100


def test_chunk_overlap_must_be_less_than_chunk_size():
    with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            chunk_size=100,
            chunk_overlap=100,
        )


def test_database_url_must_use_asyncpg():
    with pytest.raises(ValueError, match="asyncpg"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url="postgresql://aiplatform:aiplatform@localhost:5432/aiplatform",
        )


def test_secrets_are_masked():
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="sk-real-key",
    )
    assert "sk-real-key" not in repr(s)
    assert s.openai_api_key.get_secret_value() == "sk-real-key"


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_database_url_rejected_in_production():
    with pytest.raises(ValueError, match="local-dev default"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            app_env="production",
            openai_api_key="sk-test",
        )


def test_default_database_url_allowed_outside_production():
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="development",
    )
    assert s.database_url.startswith("postgresql+asyncpg://aiplatform:aiplatform@")


def test_real_database_url_allowed_in_production():
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="production",
        openai_api_key="sk-test",
        database_url="postgresql+asyncpg://real_user:real_pass@prod-host:5432/aiplatform",
    )
    assert s.is_production is True
