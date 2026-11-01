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
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    cookie_secure: bool = False  # True behind HTTPS (forced in production)
    demo_mode: bool = True  # seeds clearly-labeled demo data; must be False in production
    allow_mock_connectors: bool = True  # mock connectors are never registered in production
    base_currency_default: str = "EUR"

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def validate_for_runtime(self) -> None:
        if self.is_production:
            problems = []
            if not self.credential_key:
                problems.append("ONEFINANCE_CREDENTIAL_KEY is required")
            if self.demo_mode or self.allow_mock_connectors:
                problems.append("demo_mode and allow_mock_connectors must be false in production")
            if problems:
                raise RuntimeError("; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_runtime()
    return s
