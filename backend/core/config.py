"""Application configuration via pydantic-settings."""

from __future__ import annotations

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

    # LLM 分级路由：light=分类/抽取等高频轻任务（默认本地小模型，零 API 成本）；
    # heavy=报告/晨报等重任务（None=跟随主 LLM_PROVIDER 配置）。
    LLM_TIER_LIGHT_PROVIDER: Literal["ollama", "openai"] | None = "ollama"
    LLM_TIER_LIGHT_MODEL: str = "qwen2.5:7b"
    LLM_TIER_HEAVY_PROVIDER: Literal["ollama", "openai"] | None = None
    LLM_TIER_HEAVY_MODEL: str | None = None

    # 证据分类器：llm=批量 LLM 分类（失败自动降级），keyword=纯关键词启发式
    EVIDENCE_CLASSIFIER: Literal["llm", "keyword"] = "llm"

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
    # Optional cloud MCP endpoint (fallback layer). Empty disables the layer.
    AKSHARE_CLOUD_MCP_URL: str = ""
    # NewsNow MCP server script (tsx) + upstream base URL.
    NEWSNOW_MCP_SERVER_PATH: str = "/home/wsm/codes/newsnow/tools/mcp-server.ts"
    NEWSNOW_BASE_URL: str = "https://newsnow.busiyi.world"
    # Backtest: external read-only MySQL for historical qfq daily bars
    # (mysql+pymysql://user:pass@host:3306/db). Empty disables the source.
    BACKTEST_MYSQL_URL: str = ""
    BACKTEST_COMMISSION_RATE: float = 0.0003  # 单边佣金 万三
    BACKTEST_STAMP_DUTY_RATE: float = 0.0005  # 卖出印花税 0.05%
    BACKTEST_SLIPPAGE_RATE: float = 0.001  # 单边滑点 0.1%

    # --- Scheduling ---
    # Screener 股票池卫生（ST/停牌之外的最低交易门槛）
    SCREENER_MIN_TURNOVER: float = 0.05  # 换手率下限（%）
    SCREENER_MIN_MARKET_CAP: float = 1e9  # 总市值下限（元，10亿）
    SCREENER_MAX_PER_INDUSTRY: int = 8  # 单次候选每个行业上限

    SCHEDULER_ENABLED: bool = True
    MARKET_DATA_SCHEDULE: str = "0 2 * * 1-5"  # Weekdays 2am
    FINANCIAL_DATA_SCHEDULE: str = "15 3 * * 1-5"  # Weekdays 3:15am (market-wide financials)
    SCREENER_SCHEDULE: str = "30 16 * * 1-5"  # Weekdays 4:30pm after close
    SCREENER_SCHEDULE_PRESETS: str = "core"  # comma-separated style tags
    REPORT_SCHEDULE: str = "0 6 * * 1-5"  # Weekdays 6am
    OBSERVATION_SCHEDULE: str = "30 5 * * 1-5"  # Weekdays 5:30am (before brief)
    EVENT_LOG_CLEANUP_SCHEDULE: str = "0 3 * * 1"  # Weekly Monday 3am
    EVENT_LOG_RETENTION_DAYS: int = 90

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
