"""Screener 预设库内置种子 — 指标定义 + 内置五套预设（唯一事实源）。

迁移 upgrade() 与测试 conftest（create_all 后）都从这里取数，
保证开发库（alembic）与测试库（create_all）种子一致。
"""

from __future__ import annotations

import sqlalchemy as sa

# ── 指标定义（key 对齐 rules_schema.KNOWN_METRICS）──────────────────────
BUILTIN_METRICS: list[dict] = [
    # 行情快照
    {"key": "price", "name_cn": "现价(元)", "category": "snapshot", "data_source": "snapshot", "description": "最新收盘价"},
    {"key": "turnover", "name_cn": "换手率(%)", "category": "snapshot", "data_source": "snapshot", "description": "当日换手率"},
    {"key": "market_cap", "name_cn": "总市值(元)", "category": "size", "data_source": "snapshot", "description": "总市值"},
    # 业绩报表（yjbb）
    {"key": "roe", "name_cn": "净资产收益率(%)", "category": "profitability", "data_source": "yjbb", "description": "净利润 / 平均净资产"},
    {"key": "gross_margin", "name_cn": "销售毛利率(%)", "category": "profitability", "data_source": "yjbb", "description": "毛利 / 营业收入"},
    {"key": "net_margin", "name_cn": "销售净利率(%)", "category": "profitability", "data_source": "yjbb", "description": "净利润 / 营业收入"},
    {"key": "revenue", "name_cn": "营业收入(元)", "category": "growth", "data_source": "yjbb", "description": "报告期营业收入"},
    {"key": "net_income", "name_cn": "净利润(元)", "category": "growth", "data_source": "yjbb", "description": "报告期归母净利润"},
    {"key": "revenue_growth", "name_cn": "营业收入同比(%)", "category": "growth", "data_source": "yjbb", "description": "营业总收入同比增长率"},
    {"key": "net_income_growth", "name_cn": "净利润同比(%)", "category": "growth", "data_source": "yjbb", "description": "归母净利润同比增长率"},
    {"key": "eps", "name_cn": "每股收益(元)", "category": "profitability", "data_source": "yjbb", "description": "基本每股收益"},
    # 资产负债表 / F10 主要指标
    {"key": "debt_to_equity", "name_cn": "负债权益比(%)", "category": "solvency", "data_source": "balance_sheet", "description": "总负债 / 股东权益 × 100（D/E）"},
    {"key": "current_ratio", "name_cn": "流动比率", "category": "solvency", "data_source": "main_finance", "description": "流动资产 / 流动负债"},
    {"key": "quick_ratio", "name_cn": "速动比率", "category": "solvency", "data_source": "main_finance", "description": "(流动资产-存货) / 流动负债"},
    # 现金流量表
    {"key": "operating_cash_flow", "name_cn": "经营现金流净额(元)", "category": "cashflow", "data_source": "cash_flow", "description": "经营活动产生的现金流量净额"},
    # 营运效率（F10 主要指标）
    {"key": "asset_turnover", "name_cn": "总资产周转率", "category": "profitability", "data_source": "main_finance", "description": "营业收入 / 平均总资产"},
    {"key": "inventory_turnover", "name_cn": "存货周转率", "category": "profitability", "data_source": "main_finance", "description": "营业成本 / 平均存货"},
    {"key": "receivables_turnover", "name_cn": "应收账款周转率", "category": "profitability", "data_source": "main_finance", "description": "营业收入 / 平均应收账款"},
]

# ── 内置五套预设（spec「内置五套预设」一节逐字落地）──────────────────────
_EX = "exclude"  # 缺数据 → 排除（保守默认）

BUILTIN_PRESETS: list[dict] = [
    {
        "name": "核心资产",
        "description": "巴菲特式：高 ROE、高净利率、真金白银盈利、低杠杆、大市值",
        "style_tag": "core",
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": 15, "missing_data_policy": _EX},
            {"metric": "net_margin", "op": ">", "value": 10, "missing_data_policy": _EX},
            {"metric": "operating_cash_flow", "op": ">", "value": 0, "missing_data_policy": _EX},
            {"metric": "debt_to_equity", "op": "<", "value": 50, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 3e10, "missing_data_policy": _EX},
        ],
        "qualitative": [],
        "suggested_pool": "all",
    },
    {
        "name": "高成长",
        "description": "费雪式：营收与净利润双高增长的中大市值成长股，配合定性赛道判断",
        "style_tag": "growth",
        "quant_rules": [
            {"metric": "revenue_growth", "op": ">", "value": 20, "missing_data_policy": _EX},
            {"metric": "net_income_growth", "op": ">", "value": 20, "missing_data_policy": _EX},
            {"metric": "roe", "op": ">", "value": 12, "missing_data_policy": _EX},
            {"metric": "net_margin", "op": ">", "value": 8, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["所处行业渗透率持续提升", "增长由主营业务驱动", "细分行业排名前二"],
        "suggested_pool": "all",
    },
    {
        "name": "深度价值",
        "description": "格雷厄姆式：低负债、流动比率充裕、现金流为正的便宜大市值股",
        "style_tag": "value",
        "quant_rules": [
            {"metric": "debt_to_equity", "op": "<", "value": 40, "missing_data_policy": _EX},
            {"metric": "current_ratio", "op": ">", "value": 2, "missing_data_policy": _EX},
            {"metric": "operating_cash_flow", "op": ">", "value": 0, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 5e9, "missing_data_policy": _EX},
        ],
        "qualitative": ["现金充裕", "非壳公司", "无暴雷风险"],
        "suggested_pool": "all",
    },
    {
        "name": "质量价值 GARP",
        "description": "芒格式：质量与估值兼顾，要求盈利持续性、护城河与股东回报",
        "style_tag": "garp",
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": 15, "missing_data_policy": _EX},
            {"metric": "net_margin", "op": ">", "value": 12, "missing_data_policy": _EX},
            {"metric": "debt_to_equity", "op": "<", "value": 55, "missing_data_policy": _EX},
            {"metric": "operating_cash_flow", "op": ">", "value": 0, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 2e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["盈利具有持续性", "存在护城河", "无重大违规", "重视股东回报"],
        "suggested_pool": "all",
    },
    {
        "name": "周期反转",
        "description": "逆向：周期底部的大市值低负债龙头，赌困境反转",
        "style_tag": "cycle",
        "quant_rules": [
            {"metric": "market_cap", "op": ">", "value": 1.5e10, "missing_data_policy": _EX},
            {"metric": "debt_to_equity", "op": "<", "value": 65, "missing_data_policy": _EX},
        ],
        "qualitative": ["处于周期底部", "行业龙头且成本低", "无产能过剩包袱"],
        "suggested_pool": "all",
    },
]

_MD = sa.MetaData()
_METRIC_TABLE = sa.Table(
    "metric_defs",
    _MD,
    sa.Column("id", sa.Uuid()),
    sa.Column("key", sa.String(64)),
    sa.Column("name_cn", sa.String(128)),
    sa.Column("category", sa.String(32)),
    sa.Column("data_source", sa.String(32)),
    sa.Column("description", sa.Text()),
    schema="screener",
)
_PRESET_TABLE = sa.Table(
    "criteria_presets",
    _MD,
    sa.Column("id", sa.Uuid()),
    sa.Column("name", sa.String(128)),
    sa.Column("description", sa.Text()),
    sa.Column("style_tag", sa.String(32)),
    sa.Column("quant_rules", sa.JSON),
    sa.Column("qualitative", sa.JSON),
    sa.Column("suggested_pool", sa.String(16)),
    sa.Column("is_builtin", sa.Boolean),
    sa.Column("is_active", sa.Boolean),
    schema="screener",
)


def insert_builtin_seeds(conn: sa.Connection) -> None:
    """幂等写入内置种子（sync connection；先清内置预设再插，metric 按 key 去重）。"""
    import uuid

    conn.execute(sa.delete(_METRIC_TABLE))
    conn.execute(
        _METRIC_TABLE.insert().values([{**m, "id": uuid.uuid4()} for m in BUILTIN_METRICS])
    )
    conn.execute(sa.delete(_PRESET_TABLE).where(_PRESET_TABLE.c.is_builtin.is_(True)))
    conn.execute(
        _PRESET_TABLE.insert().values(
            [{**p, "id": uuid.uuid4(), "is_builtin": True, "is_active": True} for p in BUILTIN_PRESETS]
        )
    )
