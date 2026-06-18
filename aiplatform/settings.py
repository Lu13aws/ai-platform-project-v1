"""
Platform settings — single source of truth for all configuration.

All values are loaded from environment variables and/or .env file.
Never hardcode secrets. Never import os.environ directly elsewhere — use settings.

Usage:
    from aiplatform.settings import settings
    print(settings.database_url)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────

    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    # ── Database ──────────────────────────────────────────────────────────────

    database_url: str = Field(
        default="postgresql+asyncpg://aiplatform:aiplatform@localhost:5432/aiplatform",
    )
    alembic_database_url: str = Field(
        default="postgresql://aiplatform:aiplatform@localhost:5432/aiplatform",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def validate_async_driver(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver: postgresql+asyncpg://..."
            )
        return v

    # ── LLM — Provider Selection ──────────────────────────────────────────────

    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2048, ge=1, le=16384)
    llm_cache_enabled: bool = True

    # ── OpenAI ────────────────────────────────────────────────────────────────

    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # ── Anthropic ─────────────────────────────────────────────────────────────

    anthropic_api_key: SecretStr = Field(default=SecretStr(""))
    anthropic_chat_model: str = "claude-haiku-4-5-20251001"

    # ── AWS ───────────────────────────────────────────────────────────────────

    aws_region: str = "eu-central-1"
    aws_access_key_id: SecretStr = Field(default=SecretStr(""))
    aws_secret_access_key: SecretStr = Field(default=SecretStr(""))
    aws_session_token: SecretStr = Field(default=SecretStr(""))
    s3_bucket_name: str = "ai-platform-documents-dev"
    s3_prefix: str = "raw/"

    # ── Ingestion ─────────────────────────────────────────────────────────────

    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=100, ge=0, le=500)
    max_chunks_per_doc: int = Field(default=500, ge=10)
    hash_algorithm: Literal["sha256", "sha512", "md5"] = "sha256"

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self

    # ── Retrieval ─────────────────────────────────────────────────────────────

    retrieval_top_k: int = Field(default=5, ge=1, le=50)
    retrieval_similarity_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # ── Cost Controls ─────────────────────────────────────────────────────────

    max_llm_calls_per_run: int = Field(default=100, ge=1)
    max_embedding_calls_per_run: int = Field(default=1000, ge=1)

    # ── Notifications ─────────────────────────────────────────────────────────

    sns_topic_arn: str = ""  # ARN of the radar-notifications SNS topic

    # ── Feature Flags ─────────────────────────────────────────────────────────

    # Set to False for Lambda functions that don't use the LLM (e.g. cleanup)
    # to skip the production API key validation.
    require_llm: bool = True

    # ── RAG Demo App ──────────────────────────────────────────────────────────

    rag_demo_port: int = Field(default=8000, ge=1024, le=65535)
    rag_demo_title: str = "AI Knowledge Platform — Public RAG Demo"

    # ── Derived ───────────────────────────────────────────────────────────────

    @property
    def active_llm_api_key(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_api_key.get_secret_value()
        return self.anthropic_api_key.get_secret_value()

    @model_validator(mode="after")
    def validate_provider_key_in_production(self) -> "Settings":
        if self.is_production and self.require_llm and not self.active_llm_api_key:
            raise ValueError(
                f"API key for provider '{self.llm_provider}' is required in production."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached Settings singleton.

    In tests, call get_settings.cache_clear() after patching env vars.
    """
    return Settings()


settings: Settings = get_settings()
