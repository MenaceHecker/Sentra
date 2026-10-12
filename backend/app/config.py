from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://sentra:sentra@localhost:5432/sentra"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    llm_provider: str = "openai"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    sim_system_base_url: str = "http://localhost:9000"

    # Background jobs (ingestion from the simulated system, runbook seeding).
    # Tests set this to false so they never touch the real dev database or
    # depend on the simulated system being up.
    enable_background_jobs: bool = True
    ingestion_interval_seconds: float = 10.0

    backend_cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
