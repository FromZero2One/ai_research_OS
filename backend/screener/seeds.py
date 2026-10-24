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
    # 估值（派生：总市值 + 最新报告期财务；PE/PS 为年化近似）
    {
        "key": "pe", "name_cn": "市盈率(年化,倍)", "category": "valuation",
        "data_source": "derived", "description": "总市值 / 年化净利润（净利润≤0 时为无数据）",
    },
    {
        "key": "pb", "name_cn": "市净率(倍)", "category": "valuation",
        "data_source": "derived", "description": "总市值 / (总资产-总负债)",
    },
    {
        "key": "ps", "name_cn": "市销率(年化,倍)", "category": "valuation",
        "data_source": "derived", "description": "总市值 / 年化营业收入",
    },
    # 盈利质量（TTM 派生）
    {
        "key": "cfo_to_ni", "name_cn": "现金流/净利润(倍)", "category": "quality",
        "data_source": "derived",
        "description": "TTM 经营现金流 / TTM 净利润（>1 表示利润含金量高）",
    },
    {
        "key": "cfo_to_revenue", "name_cn": "现金流/营收(%)", "category": "quality",
        "data_source": "derived", "description": "TTM 经营现金流 / TTM 营业收入 × 100",
    },
    {
        "key": "accrual_ratio", "name_cn": "应计比率(%)", "category": "quality",
        "data_source": "derived",
        "description": "(TTM 净利润 - TTM 经营现金流) / 最新总资产 × 100（越低越好）",
    },
    # 因子深度（F10 主要指标直接提供）
    {
        "key": "roic", "name_cn": "投入资本回报率(%)", "category": "quality",
        "data_source": "main_finance", "description": "ROIC，衡量资本使用效率",
    },
    {
        "key": "interest_coverage", "name_cn": "利息保障倍数", "category": "solvency",
        "data_source": "main_finance", "description": "息税前利润 / 利息费用",
    },
    {
        "key": "cash_ratio", "name_cn": "现金比率", "category": "solvency",
        "data_source": "main_finance", "description": "货币资金 / 流动负债",
    },
    {
        "key": "fcff", "name_cn": "自由现金流(元)", "category": "cashflow",
        "data_source": "main_finance", "description": "F10 FCFF（企业自由现金流，历史口径）",
    },
    {
        "key": "cfo_to_operating_profit", "name_cn": "现金流/营业利润(倍)", "category": "quality",
        "data_source": "main_finance", "description": "经营现金流 / 营业利润",
    },
    {
        "key": "tax_rate", "name_cn": "实际税率(%)", "category": "quality",
        "data_source": "main_finance", "description": "所得税 / 税前利润",
    },
    {
        "key": "interest_debt_ratio", "name_cn": "有息负债率(%)", "category": "solvency",
        "data_source": "main_finance", "description": "有息负债 / 总资产",
    },
    {
        "key": "peg", "name_cn": "PEG(倍)", "category": "valuation",
        "data_source": "derived", "description": "PE / 净利润同比增速（增速≤0 时无数据）",
    },
    {
        "key": "fcf_yield", "name_cn": "FCF收益率(%)", "category": "valuation",
        "data_source": "derived", "description": "FCFF / 总市值 × 100",
    },
    # 银行专属（F10）
    {
        "key": "net_interest_margin", "name_cn": "净息差(%)", "category": "bank",
        "data_source": "main_finance", "description": "净利息收入 / 生息资产",
    },
    {
        "key": "non_performing_loan", "name_cn": "不良贷款(元)", "category": "bank",
        "data_source": "main_finance", "description": "不良贷款余额",
    },
    {
        "key": "gross_loans", "name_cn": "贷款总额(元)", "category": "bank",
        "data_source": "main_finance", "description": "发放贷款及垫款总额",
    },
    {
        "key": "loan_provision_ratio", "name_cn": "贷款拨备率(%)", "category": "bank",
        "data_source": "main_finance", "description": "贷款损失准备 / 贷款总额",
    },
    {
        "key": "first_adequacy_ratio", "name_cn": "一级资本充足率(%)", "category": "bank",
        "data_source": "main_finance", "description": "一级资本 / 风险加权资产",
    },
    {
        "key": "npl_ratio", "name_cn": "不良贷款率(%)", "category": "bank",
        "data_source": "derived", "description": "不良贷款 / 贷款总额 × 100",
    },
    # 保险专属（F10）
    {
        "key": "net_roi", "name_cn": "净投资收益率(%)", "category": "insurance",
        "data_source": "main_finance", "description": "保险资金净投资收益率",
    },
    {
        "key": "earned_premium", "name_cn": "已赚保费(元)", "category": "insurance",
        "data_source": "main_finance", "description": "已赚保费",
    },
    {
        "key": "solvency_ar", "name_cn": "偿付能力充足率(%)", "category": "insurance",
        "data_source": "main_finance", "description": "综合偿付能力充足率",
    },
]

# ── 内置预设（五套通用 + 金融行业专属）────────────────────────────────
_EX = "exclude"  # 缺数据 → 排除（保守默认）

BUILTIN_PRESETS: list[dict] = [
    {
        "name": "核心资产",
        "description": "巴菲特式：高 ROE、高净利率、真金白银盈利、低杠杆、大市值",
        "style_tag": "core",
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": 15, "missing_data_policy": _EX},
            {"metric": "roic", "op": ">", "value": 10, "missing_data_policy": _EX},
            {"metric": "net_margin", "op": ">", "value": 10, "missing_data_policy": _EX},
            {"metric": "cfo_to_ni", "op": ">", "value": 0.8, "missing_data_policy": _EX},
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
            {"metric": "cfo_to_ni", "op": ">", "value": 0.5, "missing_data_policy": _EX},
            {"metric": "peg", "op": "<", "value": 2, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["所处行业渗透率持续提升", "增长由主营业务驱动", "细分行业排名前二"],
        "suggested_pool": "all",
    },
    {
        "name": "深度价值",
        "description": "格雷厄姆式：低负债、流动比率充裕、现金流为正、估值便宜的大市值股",
        "style_tag": "value",
        "quant_rules": [
            {"metric": "debt_to_equity", "op": "<", "value": 40, "missing_data_policy": _EX},
            {"metric": "current_ratio", "op": ">", "value": 2, "missing_data_policy": _EX},
            {"metric": "cfo_to_ni", "op": ">", "value": 0.7, "missing_data_policy": _EX},
            {"metric": "fcf_yield", "op": ">", "value": 0, "missing_data_policy": _EX},
            {"metric": "pe", "op": "<", "value": 25, "missing_data_policy": _EX},
            {"metric": "pb", "op": "<", "value": 3, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 5e9, "missing_data_policy": _EX},
        ],
        "qualitative": ["现金充裕", "非壳公司", "无暴雷风险"],
        "suggested_pool": "all",
    },
    {
        "name": "质量价值 GARP",
        "description": "芒格式：质量与估值兼顾，要求盈利持续性、护城河、股东回报与合理估值",
        "style_tag": "garp",
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": 15, "missing_data_policy": _EX},
            {"metric": "roic", "op": ">", "value": 10, "missing_data_policy": _EX},
            {"metric": "net_margin", "op": ">", "value": 12, "missing_data_policy": _EX},
            {"metric": "debt_to_equity", "op": "<", "value": 55, "missing_data_policy": _EX},
            {"metric": "cfo_to_ni", "op": ">", "value": 0.8, "missing_data_policy": _EX},
            {"metric": "pe", "op": "<", "value": 40, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 2e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["盈利具有持续性", "存在护城河", "无重大违规", "重视股东回报"],
        "suggested_pool": "all",
    },
    {
        "name": "周期反转",
        "description": "逆向：周期底部的大市值低负债龙头，市净率处于低位，赌困境反转",
        "style_tag": "cycle",
        "quant_rules": [
            {"metric": "market_cap", "op": ">", "value": 1.5e10, "missing_data_policy": _EX},
            {"metric": "debt_to_equity", "op": "<", "value": 65, "missing_data_policy": _EX},
            {"metric": "pb", "op": "<", "value": 2.5, "missing_data_policy": _EX},
        ],
        "qualitative": ["处于周期底部", "行业龙头且成本低", "无产能过剩包袱"],
        "suggested_pool": "all",
    },
    {
        "name": "金融价值",
        "description": (
            "银行/保险/券商专属：低 PB、低 PE、盈利稳定的金融龙头"
            "（不使用流动比率/毛利率等工业口径）"
        ),
        "style_tag": "financial",
        "quant_rules": [
            {"metric": "pb", "op": "<", "value": 1.5, "missing_data_policy": _EX},
            {"metric": "pe", "op": "<", "value": 10, "missing_data_policy": _EX},
            {"metric": "roe", "op": ">", "value": 8, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["资产质量稳健", "拨备/资本充足", "无重大监管处罚"],
        "suggested_pool": "all",
    },
    {
        "name": "银行价值",
        "description": "银行专属：低 PB/PE、不良率可控、资本充足的大型银行",
        "style_tag": "bank",
        "quant_rules": [
            {"metric": "pb", "op": "<", "value": 1.5, "missing_data_policy": _EX},
            {"metric": "pe", "op": "<", "value": 10, "missing_data_policy": _EX},
            {"metric": "roe", "op": ">", "value": 8, "missing_data_policy": _EX},
            {"metric": "npl_ratio", "op": "<", "value": 2, "missing_data_policy": _EX},
            {"metric": "first_adequacy_ratio", "op": ">", "value": 10, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 1e11, "missing_data_policy": _EX},
        ],
        "qualitative": ["资产质量稳健", "拨备充足"],
        "suggested_pool": "all",
    },
    {
        "name": "保险价值",
        "description": "保险专属：低估值、盈利稳定、偿付能力充足的大型险企",
        "style_tag": "insurance",
        "quant_rules": [
            {"metric": "pb", "op": "<", "value": 2, "missing_data_policy": _EX},
            {"metric": "pe", "op": "<", "value": 15, "missing_data_policy": _EX},
            {"metric": "roe", "op": ">", "value": 8, "missing_data_policy": _EX},
            {"metric": "solvency_ar", "op": ">", "value": 150, "missing_data_policy": _EX},
            {"metric": "market_cap", "op": ">", "value": 5e10, "missing_data_policy": _EX},
        ],
        "qualitative": ["新业务价值增长", "投资收益率稳健"],
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
