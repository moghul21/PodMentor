from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "podmentor"
    environment: str = "local"  # local | ci | production | test

    # Gemini & LLM Configuration
    gemini_api_key: str = ""
    primary_model: str = "gemini-1.5-flash"
    fallback_model: str = "gemini-1.5-flash-8b"
    llm_timeout_seconds: float = 15.0
    llm_max_retries: int = 2

    # Database
    database_path: str = "podmentor.db"
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
