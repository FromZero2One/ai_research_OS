"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from secrets import token_hex
from typing import Literal

from pydantic import Field
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
    DATABASE_URL: str = "postgresql+asyncpg://airesearch:airesearch_dev@127.0.0.1:5432/airesearch"
    DATABASE_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Vector Store ---
    QDRANT_HOST: str = "127.0.0.1"
    QDRANT_PORT: int = 6333
    QDRANT_PREFER_GRPC: bool = True
    QDRANT_COLLECTION: str = "documents"
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024  # BGE-M3 (default Ollama embedding model)
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_PREWARM: bool = True  # pre-warm the embedding model at startup (set False in tests)

    # --- LLM ---
    LLM_PROVIDER: Literal["ollama", "openai"] = "ollama"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.1:70b"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # --- Redis ---
    REDIS_URL: str = "redis://127.0.0.1:6380/0"  # docker-compose exposes 6380→6379
    REDIS_TTL: int = 3600

    # --- Security ---
    # Single-user local tool by default: no auth is enforced on routes.
    # Default secret is random per boot so a forgotten deployment never
    # ships with a known key. Set SECRET_KEY explicitly if you persist
    # tokens across restarts or expose the service.
    SECRET_KEY: str = Field(default_factory=lambda: token_hex(32))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # --- Document ---
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    # Hard safety valve for the in-memory BM25 corpus (0 = unlimited).
    # Unlike the old hard-coded 10000 cap, hitting this logs a warning
    # instead of silently truncating the search index.
    BM25_MAX_CHUNKS: int = 0

    # --- Market ---
    AKSHARE_ENABLED: bool = True
    YFINANCE_ENABLED: bool = True

    # --- External data sources (machine-specific, override in .env) ---
    # Directory of the akshare_mcp venv used for the subprocess data layer.
    AKSHARE_MCP_DIR: str = "/home/wsm/codes/akshare_mcp"
    # Optional cloud MCP endpoint (Layer 3 fallback). Empty disables the layer.
    AKSHARE_CLOUD_MCP_URL: str = ""
    # Read-only MySQL mirror maintained by akshare_mcp (A-stock data).
    AKSHARE_MYSQL_HOST: str = "127.0.0.1"
    AKSHARE_MYSQL_PORT: int = 3306
    AKSHARE_MYSQL_USER: str = "root"
    AKSHARE_MYSQL_PASSWORD: str = "root"
    AKSHARE_MYSQL_DATABASE: str = "akshare"
    # NewsNow MCP server script (tsx) + upstream base URL.
    NEWSNOW_MCP_SERVER_PATH: str = "/home/wsm/codes/newsnow/tools/mcp-server.ts"
    NEWSNOW_BASE_URL: str = "https://newsnow.busiyi.world"

    # --- Scheduling ---
    SCHEDULER_ENABLED: bool = True
    MARKET_DATA_SCHEDULE: str = "0 2 * * 1-5"  # Weekdays 2am
    REPORT_SCHEDULE: str = "0 6 * * 1-5"  # Weekdays 6am
    OBSERVATION_SCHEDULE: str = "30 5 * * 1-5"  # Weekdays 5:30am (before brief)
    EVENT_LOG_CLEANUP_SCHEDULE: str = "0 3 * * 1"  # Weekly Monday 3am
    EVENT_LOG_RETENTION_DAYS: int = 90

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
