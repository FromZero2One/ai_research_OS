"""Screener ORM models — 选股运行、深判结果、标准翻译缓存。"""

from __future__ import annotations

import uuid

from datetime import date as _date

from sqlalchemy import Date, Float, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class ScreenerRun(Base, UUIDMixin, TimestampMixin):
    """一次选股运行的完整记录（状态机 pending → screening → judging → completed/failed）。"""

    __tablename__ = "screener_runs"
    __table_args__ = (
        # 并发触发防线：同一时刻至多一个进行中的 run（路由 409 判断 + 数据库兜底）
        Index(
            "uq_screener_runs_active",
            "status",
            unique=True,
            postgresql_where=text(
                "status IN ('pending', 'screening', 'judging', 'cancelling')"
            ),
        ),
        {"schema": "screener"},
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    criteria_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    criteria_text: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column(nullable=True)
    result_count: Mapped[int | None] = mapped_column(nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # v1.5 预设模式列（NULL = v1 自由文本运行，向后兼容）
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    preset_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    combine_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pool_override: Mapped[str | None] = mapped_column(String(16), nullable=True)


class MetricDef(Base, UUIDMixin, TimestampMixin):
    """指标定义库 — 预设量化规则的 metric 键唯一事实源（种子由迁移写入）。"""

    __tablename__ = "metric_defs"
    __table_args__ = {"schema": "screener"}

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name_cn: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CriteriaPreset(Base, UUIDMixin, TimestampMixin):
    """标准预设模板 — 内置五套不可删改，用户自建可编辑删除。"""

    __tablename__ = "criteria_presets"
    __table_args__ = {"schema": "screener"}

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quant_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    qualitative: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    suggested_pool: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    is_builtin: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class ScreenerJudgement(Base, UUIDMixin, TimestampMixin):
    """单只候选的 LLM 深判结果（recommend 可空 — 深判失败时无结论）。"""

    __tablename__ = "screener_judgements"
    __table_args__ = {"schema": "screener"}

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    recommend: Mapped[bool | None] = mapped_column(nullable=True)
    # recommend | reject | insufficient | failed — 区分“不符合”和“数据不足”
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    criteria_hits: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # ok | failed — 单只深判失败不拖垮整次运行
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScreenerRule(Base, UUIDMixin, TimestampMixin):
    """标准文档翻译缓存 — doc_hash 未变则跳过 LLM 翻译。"""

    __tablename__ = "screener_rules"
    __table_args__ = {"schema": "screener"}

    doc_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    criteria_text: Mapped[str] = mapped_column(Text, nullable=False)


class ScreenerBacktestRun(Base, UUIDMixin, TimestampMixin):
    """一次预设历史回测（状态机 pending → running → completed/failed）。

    result 存 {"summary": {...}, "yearly": [...]}；报告落 screener/reports/。
    """

    __tablename__ = "backtest_runs"
    __table_args__ = {"schema": "screener"}

    preset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    years: Mapped[int] = mapped_column(nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScreenerPortfolio(Base, UUIDMixin, TimestampMixin):
    """保存下来的组合方案（参数 + 构建结果），供历史查看与再平衡对照。"""

    __tablename__ = "portfolios"
    __table_args__ = {"schema": "screener"}

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ScreenerPerformanceSnapshot(Base, UUIDMixin, TimestampMixin):
    """推荐后表现的定期快照（同一 run 每日一条，幂等 upsert）。"""

    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "as_of", name="uq_perf_snapshot_run_date"),
        {"schema": "screener"},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    as_of: Mapped[_date] = mapped_column(Date, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    stocks: Mapped[list] = mapped_column(JSONB, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)
