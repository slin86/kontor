"""Application settings, loaded from environment variables (prefix ``KONTOR_``)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KONTOR_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./kontor.db"
    session_cookie_name: str = "kontor_session"
    csrf_cookie_name: str = "kontor_csrf"
    session_ttl_days: int = 30
    # Set to True when served over HTTPS (e.g. behind a reverse proxy in the homelab).
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
