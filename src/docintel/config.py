"""Typed application config, loaded from environment variables / .env.

Why pydantic-settings instead of os.getenv: a missing or malformed setting fails
loudly at startup with a clear error, instead of surfacing as `None` deep inside
an API call. On Cloud Run the same class reads real env vars injected from
Secret Manager — no code change between local and prod.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # SecretStr hides the value in logs/reprs: print(settings) shows '**********'.
    # Optional at this stage so tests and data exploration run without a key.
    openai_api_key: SecretStr | None = None

    data_dir: Path = PROJECT_ROOT / "data"
    duckdb_path: Path = PROJECT_ROOT / "data" / "docintel.duckdb"


@lru_cache  # one Settings instance per process (like a module-level singleton)
def get_settings() -> Settings:
    return Settings()
