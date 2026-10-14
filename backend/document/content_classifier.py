"""Chunk content-type classifier — 纯函数关键词规则，可单测。

分工原则（2026-10-14）：接口管"数"，PDF 管"事"。文档切片按内容类型打标，
让定性研究（MD&A/风险/附注/公告）可被定向检索；财报表格本身不作为指标来源。

类型枚举：
- mda:           经营讨论 / 管理层分析 / 业务与展望
- risk:          风险因素 / 风险管理
- notes:         财务报表附注 / 会计政策 / 或有事项 / 关联交易
- announcement:  公司公告 / 决议 / 停复牌
- other:         无法归类（默认）
"""

from __future__ import annotations

CONTENT_TYPES: tuple[str, ...] = ("mda", "risk", "notes", "announcement", "other")

# 各类型特征关键词；announcement 最易误伤（年报正文常出现"公告"字样），
# 故其关键词要求更强的公告语境。
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mda": (
        "经营情况讨论",
        "管理层讨论与分析",
        "经营讨论与分析",
        "董事会报告",
        "主营业务分析",
        "业务概述",
        "经营回顾",
        "未来发展的讨论",
        "发展战略与经营计划",
        "核心竞争力分析",
        "行业格局和趋势",
    ),
    "risk": (
        "风险因素",
        "可能面对的风险",
        "可能面临的风险",
        "重大风险提示",
        "风险管理",
        "风险警示",
    ),
    "notes": (
        "财务报表附注",
        "会计政策",
        "会计估计",
        "或有事项",
        "承诺事项",
        "关联方及关联交易",
        "合并财务报表项目注释",
        "审计报告",
    ),
    "announcement": (
        "提示性公告",
        "股东大会决议公告",
        "董事会决议公告",
        "停牌公告",
        "复牌公告",
        "澄清公告",
        "业绩预告",
        "业绩快报",
    ),
}


def classify_chunk(text: str) -> str:
    """按关键词命中数判定切片内容类型；无命中返回 other。

    平局时按 mda > risk > notes > announcement 的优先顺序取先者
    （定性研究最常用 mda，故优先）。
    """
    if not text or not text.strip():
        return "other"

    best_type, best_score = "other", 0
    for ctype in ("mda", "risk", "notes", "announcement"):
        score = sum(1 for kw in _KEYWORDS[ctype] if kw in text)
        if score > best_score:
            best_type, best_score = ctype, score
    return best_type
