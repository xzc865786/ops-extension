from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ops:ops@localhost:5432/qiyuan_ops"
    sub2api_base_url: str = "http://sub2api:8080"
    session_secret: str = "dev-secret-change-me"
    # Short TTL: Sub2API bearer is never stored; Custom Menu must re-hit Bootstrap.
    session_ttl_hours: int = 2
    # If last Bootstrap (last_checked_at) is older than this many seconds, clear
    # session and 401 with SESSION_REBOOTSTRAP_REQUIRED — never call Sub2API with a
    # stored bearer. Default matches TTL (2h).
    session_max_age_without_bootstrap: int = 7200
    cookie_name: str = "ops_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    public_base_url: str = "http://localhost:8090"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "qiyuan-ops"
    minio_use_ssl: bool = False
    # Optional browser-reachable host for presigned download redirects.
    # If unset, downloads always stream through the authenticated API proxy.
    minio_public_endpoint: str | None = None  # host:port
    minio_public_url: str | None = None  # e.g. https://files.example.com
    attachment_max_bytes: int = 20 * 1024 * 1024
    cors_origins: str = ""
    log_level: str = "INFO"
    # Dev-only: skip Sub2API and accept X-Dev-User JSON header
    dev_auth_bypass: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
