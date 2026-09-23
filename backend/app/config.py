from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from the environment or the repo-root .env file."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = (
        "postgresql+psycopg://lender_matching:lender_matching@localhost:5433/lender_matching"
    )

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Hosted providers (Neon, Supabase, ...) hand out plain postgresql:// URLs.
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    cors_origins: list[str] = ["http://localhost:5173"]

    # Hatchet is optional at runtime: without a token the API falls back to the
    # in-process runner so the product still works end to end.
    hatchet_client_token: str | None = None
    underwriting_mode: str = "auto"  # auto | hatchet | sync

    # PDF extraction. `auto` uses whichever provider has a key (Anthropic first).
    extraction_provider: str = "auto"  # auto | anthropic | openai
    anthropic_api_key: str | None = None
    extraction_model: str = "claude-opus-5"
    openai_api_key: str | None = None
    # Any OpenAI-compatible endpoint, e.g. Azure: https://<resource>.openai.azure.com/openai/v1
    # (there the model is the deployment name). Empty = api.openai.com.
    openai_base_url: str | None = None
    openai_extraction_model: str = "gpt-4.1"
    uploads_dir: str = "uploads"

    @property
    def use_hatchet(self) -> bool:
        if self.underwriting_mode == "sync":
            return False
        return bool(self.hatchet_client_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
