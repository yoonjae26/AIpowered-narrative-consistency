from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

	app_name: str = "NarrativeOS API"
	app_version: str = "0.1.0"
	environment: str = Field(default="development")
	debug: bool = False
	api_prefix: str = "/api"
	secret_key: str = Field(default="change-me-in-production")
	access_token_expire_minutes: int = 60 * 24
	refresh_token_expire_days: int = 7
	cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
	cors_allow_credentials: bool = True
	cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
	cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
	rate_limit_requests: int = 120
	rate_limit_window_seconds: int = 60
	redis_url: str = "redis://localhost:6379/0"
	database_url: str = "sqlite:///./narrativeos.db"
	llm_provider: str = "qwen"
	llm_model: str = "qwen2.5:7b-instruct"
	llm_base_url: str | None = None
	openai_api_key: str | None = None
	anthropic_api_key: str | None = None
	langfuse_public_key: str | None = None
	langfuse_secret_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
	return Settings()
