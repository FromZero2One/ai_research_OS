"""共享 psycopg2 连接 — 供 tools/ 下一次性脚本使用。

连接参数优先级：PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD 环境变量 >
DATABASE_URL（环境变量或 backend/.env）> 开发默认值。
避免每个脚本各复制一份硬编码 DB 配置。

用法（tools 脚本内）：
    from _db import connect

    conn = connect()
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2

_DEFAULT_URL = "postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch"


def _read_env_file() -> dict[str, str]:
    """解析 backend/.env（简单 KEY=VALUE，不支持引号嵌套）。"""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    out: dict[str, str] = {}
    if not env_file.exists():
        return out
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _database_url() -> str:
    file_env = _read_env_file()
    return os.getenv("DATABASE_URL") or file_env.get("DATABASE_URL") or _DEFAULT_URL


def connect(**kwargs):
    """psycopg2 连接；kwargs 透传 psycopg2.connect。"""
    url = _database_url().replace("postgresql+asyncpg://", "postgresql://")
    p = urlparse(url)
    file_env = _read_env_file()

    def _get(name: str, default: str) -> str:
        return os.getenv(name) or file_env.get(name) or default

    return psycopg2.connect(
        host=_get("PG_HOST", p.hostname or "localhost"),
        port=int(_get("PG_PORT", str(p.port or 5432))),
        dbname=_get("PG_DB", p.path.lstrip("/") or "airesearch"),
        user=_get("PG_USER", unquote(p.username or "")),
        password=_get("PG_PASSWORD", unquote(p.password or "")),
        **kwargs,
    )
