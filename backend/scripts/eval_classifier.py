# ruff: noqa: E501
"""证据分类评测 — LLM 分类 vs 关键词基线。

用内置的中文金融标注样本（黄金标签）评测 EvidenceService 的两级分类：
1. LLM 批量分类（EVIDENCE_CLASSIFIER=llm，light tier）
2. 关键词基线 classify()

输出总体准确率、逐类 precision/recall/F1、混淆矩阵与 LLM 自评置信度，
用于验证分类质量（配合 /events 中 evidence.classified 的 llm_updated 比例）。
不依赖数据库，直接调 LLM，可随时运行。

Usage:
    PYTHONPATH=. python scripts/eval_classifier.py [--batch-size 8]

注意：Ollama 未运行或本地模型缺失时 LLM 路径会失败并打印跳过提示。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict

from core.proxy_cleanup import clean_proxy_env

clean_proxy_env()

from core.adapters.llm import create_llm  # noqa: E402
from core.interfaces import LLMMessage  # noqa: E402
from core.logging import logger  # noqa: E402
from research.evidence_service import EvidenceService  # noqa: E402

# 黄金标注样本：(question, content, expected_type)
# 覆盖金融语境的典型正向/反向/中性信号，含关键词基线易误判的反例。
GOLDEN_SET: list[tuple[str, str, str]] = [
    # ── supporting ──
    ("A公司的长期增长逻辑是什么？", "公司2024年营收同比增长18%，其中海外业务占比提升至35%，毛利率同比提升2.1个百分点。", "supporting"),
    ("A公司的长期增长逻辑是什么？", "公司与头部新能源车企签订五年战略供货协议，锁定未来三年产能。", "supporting"),
    ("B银行的资产质量是否恶化？", "最新披露的不良贷款率较上季度下降3个基点，拨备覆盖率维持在200%以上。", "supporting"),
    ("C公司的核心竞争力如何？", "研发投入占营收比例连续三年超过10%，核心专利数量行业第一。", "supporting"),
    ("A公司的长期增长逻辑是什么？", "受益于行业景气度上行，公司在手订单能见度已排至明年三季度。", "supporting"),
    # ── opposing ──
    ("A公司的长期增长逻辑是什么？", "公司商誉账面值达48亿元，占净资产比例超过40%，存在较大减值风险。", "opposing"),
    ("A公司的长期增长逻辑是什么？", "大股东累计质押其所持股份的72%，且近期解除质押后再质押频率明显上升。", "opposing"),
    ("A公司的长期增长逻辑是什么？", "2024年经营性现金流净额为-3.2亿元，与净利润严重背离，应收账款同比暴增65%。", "opposing"),
    ("D公司的经营是否健康？", "公司因涉嫌信息披露违规被证监会立案调查，股价次日跌停。", "opposing"),
    ("B银行的资产质量是否恶化？", "核心一级资本充足率逼近监管红线，内源性资本补充能力持续弱化。", "opposing"),
    ("E制造企业的盈利趋势如何？", "主要原材料价格同比上涨30%，而产品提价幅度不足10%，毛利率承压明显。", "opposing"),
    # ── neutral ──
    ("A公司的长期增长逻辑是什么？", "截至今日收盘，公司股价报15.68元，全天成交额8.2亿元，换手率1.4%。", "neutral"),
    ("A公司的长期增长逻辑是什么？", "公司拟于下月召开年度股东大会，审议常规议案。", "neutral"),
    ("A公司的长期增长逻辑是什么？", "公司公告显示，独立董事任期届满后将进行常规改选。", "neutral"),
    ("B银行的资产质量是否恶化？", "银行今日发布关于召开投资者说明会的公告，说明会以网络文字互动形式进行。", "neutral"),
]

VALID_TYPES = ("supporting", "opposing", "neutral")
TYPE_CN = {"supporting": "支持", "opposing": "反对", "neutral": "中性"}

# 与 evidence_service.classify_batch 同源的 schema/prompt（复制以保证评测独立可跑）
_CLASSIFY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "evidence_type": {"type": "string", "enum": list(VALID_TYPES)},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["idx", "evidence_type", "confidence"],
            },
        }
    },
    "required": ["classifications"],
}

_CLASSIFY_SYSTEM_PROMPT = (
    "你是一名严谨的投资研究助理。根据研究问题，判断每条证据对结论的方向：\n"
    "- supporting：支持看多/看好的结论（增长、盈利改善、竞争优势、政策利好等）\n"
    "- opposing：反对或预警信号（业绩暴雷、商誉减值、大股东质押、诉讼、"
    "行业下行、应收暴增、现金流恶化等金融语境的反向信号）\n"
    "- neutral：中性事实（单纯行情数据、与方向无关的陈述）\n"
    "要求：逐条判断，不遗漏；confidence 为 0-1 的自评置信度；"
    "输出 JSON，格式为 {\"classifications\": [{\"idx\": 0, "
    "\"evidence_type\": \"...\", \"reason\": \"...\", \"confidence\": 0.9}]}，"
    "idx 对应输入的证据编号。"
)


async def llm_classify(question: str, contents: list[str]) -> list[str] | None:
    """调用 LLM 批量分类，失败返回 None（与 classify_batch 的降级语义一致）。"""
    items = "\n".join(f"[{i}] {c[:400]}" for i, c in enumerate(contents))
    try:
        llm = create_llm(tier="light")
        result = await llm.generate_structured(
            messages=[
                LLMMessage(role="system", content=_CLASSIFY_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f"研究问题：{question}\n\n证据列表：\n{items}"),
            ],
            schema=_CLASSIFY_SCHEMA,
            temperature=0.2,
        )
    except Exception as e:
        logger.warning("LLM 分类调用失败：%s", e)
        return None

    preds = [None] * len(contents)
    for c in result.get("classifications", []):
        idx, etype = c.get("idx"), c.get("evidence_type")
        if isinstance(idx, int) and 0 <= idx < len(contents) and etype in VALID_TYPES:
            preds[idx] = etype
    return preds


def per_class_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, dict]:
    """逐类 precision/recall/F1（不支持某类时记 0）。"""
    metrics: dict[str, dict] = {}
    for t in VALID_TYPES:
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == t and b == t)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != t and b == t)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == t and b != t)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics[t] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return metrics


def confusion(y_true: list[str], y_pred: list[str]) -> dict[tuple[str, str], int]:
    cm: dict[tuple[str, str], int] = defaultdict(int)
    for a, b in zip(y_true, y_pred):
        cm[(a, b)] += 1
    return cm


def print_report(name: str, y_true: list[str], y_pred: list[str], extra: str = "") -> float:
    """打印单个分类器的评测报告，返回总体准确率。"""
    n = len(y_true)
    acc = sum(1 for a, b in zip(y_true, y_pred) if a == b) / n if n else 0.0
    print(f"\n{'=' * 60}\n[{name}]{extra} 样本 {n} · 准确率 {acc:.1%}\n{'=' * 60}")
    for t, m in per_class_metrics(y_true, y_pred).items():
        print(
            f"  {TYPE_CN[t]:<4} P={m['precision']:.2f} R={m['recall']:.2f} "
            f"F1={m['f1']:.2f} (support={m['support']})"
        )
    print("  混淆矩阵（行=真实，列=预测；顺序 支持/反对/中性）:")
    header = "          " + "".join(f"{TYPE_CN[p]:>8}" for p in VALID_TYPES)
    print(header)
    for t in VALID_TYPES:
        row = f"{TYPE_CN[t]:<10}" + "".join(f"{confusion(y_true, y_pred).get((t, p), 0):>8}" for p in VALID_TYPES)
        print(row)
    return acc


async def main(batch_size: int) -> int:
    questions = [q for q, _, _ in GOLDEN_SET]
    contents = [c for _, c, _ in GOLDEN_SET]
    y_true = [t for _, _, t in GOLDEN_SET]

    # ── 关键词基线（零依赖，恒可跑） ──
    y_kw = [EvidenceService.classify(c, q) for c, q in zip(contents, questions)]
    kw_acc = print_report("关键词基线", y_true, y_kw)

    # ── LLM 分类（按问题分批，贴近真实 gather 场景） ──
    y_llm: list[str | None] = [None] * len(GOLDEN_SET)
    groups: dict[str, list[int]] = defaultdict(list)
    for i, q in enumerate(questions):
        groups[q].append(i)

    llm_ok = True
    for q, idxs in groups.items():
        for start in range(0, len(idxs), batch_size):
            batch = idxs[start : start + batch_size]
            preds = await llm_classify(q, [contents[i] for i in batch])
            if preds is None:
                llm_ok = False
                continue
            for j, p in zip(batch, preds):
                y_llm[j] = p

    if not llm_ok:
        print("\n⚠️ LLM 不可用（Ollama 未运行或模型缺失），仅输出关键词基线结果。")
        return 1

    missing = [i for i, p in enumerate(y_llm) if p is None]
    if missing:
        print(f"\n⚠️ LLM 漏判 {len(missing)} 条（idx={missing}），按 neutral 兜底计入。")
    y_llm_final = [p or "neutral" for p in y_llm]
    llm_acc = print_report("LLM 分类", y_true, y_llm_final, f"（batch_size={batch_size}）")

    print(f"\n{'=' * 60}\n总结：关键词基线 {kw_acc:.1%} → LLM {llm_acc:.1%}（提升 {(llm_acc - kw_acc) * 100:+.1f}pp）")
    print("建议：LLM 明显低于基线时，检查 light tier 模型配置与 EVIDENCE_CLASSIFIER 开关。")
    return 0 if llm_acc >= kw_acc else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="证据分类评测")
    parser.add_argument("--batch-size", type=int, default=8, help="每批送入 LLM 的证据条数")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.batch_size)))
