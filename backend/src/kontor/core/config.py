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
    # AI helper. A local server (Ollama or LM Studio, OpenAI-compatible API) reads documents and
    # suggests categories. An optional cloud key is only ever used for short item names, never for
    # documents. Everything stays off while the URL / key are empty.
    ai_local_url: str = ""  # Ollama http://pc.home.lan:11434 or LM Studio http://pc.home.lan:1234
    ai_local_model: str = ""  # empty: use the first model the server lists
    ai_local_timeout_seconds: int = 180
    ai_cloud_api_key: str = ""
    ai_cloud_model: str = "claude-haiku-4-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
