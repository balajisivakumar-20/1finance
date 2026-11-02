from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ONEFINANCE_", env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://onefinance:onefinance@localhost:5432/onefinance"
    redis_url: str = "redis://localhost:6379/0"
    # 32-byte base64 key for AES-256-GCM credential encryption. MUST be set in production (KMS/Vault-backed).
    credential_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    # Stay signed in across visits: signed out after 14 days without use, re-confirm sign-in every 30 days.
    session_idle_minutes: int = 14 * 24 * 60
    session_absolute_hours: int = 30 * 24
    cookie_secure: bool = False  # True behind HTTPS (forced in production)
    demo_mode: bool = True  # seeds clearly-labeled demo data; must be False in production
    allow_mock_connectors: bool = True  # mock connectors are never registered in production
    base_currency_default: str = "EUR"
    # Public origin users reach the web app on (Google redirects back to {public_url}/api/v1/auth/google/callback).
    public_url: str = "http://localhost:3000"
    # Google sign-in (OAuth client of type "Web application"). Leave empty to disable.
    google_client_id: str = ""
    google_client_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def validate_for_runtime(self) -> None:
        if self.is_production:
            problems = []
            if not self.credential_key:
                problems.append("ONEFINANCE_CREDENTIAL_KEY is required")
            if self.demo_mode or self.allow_mock_connectors:
                problems.append("demo_mode and allow_mock_connectors must be false in production")
            if not self.cookie_secure or not self.public_url.startswith("https://"):
                problems.append("ONEFINANCE_COOKIE_SECURE=true and an https:// ONEFINANCE_PUBLIC_URL are required")
            if problems:
                raise RuntimeError("; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_runtime()
    return s
