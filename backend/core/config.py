"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Research OS"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENV: Literal["development", "staging", "production"] = "development"

    # --- Paths ---
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = PROJECT_ROOT.parent / "data"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch"
    DATABASE_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Vector Store ---
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_PREFER_GRPC: bool = True
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_DEVICE: str = "cpu"

    # --- LLM ---
    LLM_PROVIDER: Literal["ollama", "openai"] = "ollama"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.1:70b"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # --- Document ---
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # --- Market ---
    AKSHARE_ENABLED: bool = True
    YFINANCE_ENABLED: bool = True

    # --- Scheduling ---
    SCHEDULER_ENABLED: bool = True
    MARKET_DATA_SCHEDULE: str = "0 2 * * 1-5"  # Weekdays 2am
    REPORT_SCHEDULE: str = "0 6 * * 1-5"  # Weekdays 6am
    OBSERVATION_SCHEDULE: str = "30 5 * * 1-5"  # Weekdays 5:30am (before brief)

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
