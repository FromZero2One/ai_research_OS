"""标准文档读写 — 用户维护的选股标准（markdown），固定在 screener/criteria.md。"""

from __future__ import annotations

from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent


def criteria_path() -> Path:
    """标准文档路径（screener/criteria.md，与模块同目录）。"""
    return _MODULE_DIR / "criteria.md"


def read_criteria() -> str:
    """读取标准文档全文。"""
    return criteria_path().read_text(encoding="utf-8")


def write_criteria(text: str) -> None:
    """覆盖保存标准文档（前端编辑器保存入口）。"""
    criteria_path().write_text(text, encoding="utf-8")
