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
    # Creating a new household is always possible for the very first user. Afterwards it needs
    # this flag; joining an existing household with its invite code stays possible.
    allow_new_households: bool = True
    login_max_failures: int = 5  # per e-mail address within the window
    ip_max_failures: int = 20  # per client address (login and invite codes)
    throttle_window_seconds: int = 900
    cors_origins: list[str] = ["http://localhost:5173"]
    # Used to decide which month is "now" (everything before it is locked history).
    timezone: str = "Europe/Berlin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
