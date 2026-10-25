"""审计并改写预设的定性标准（让每条都能在年报/财务数据里找到证据）。

背景：原标准里「细分行业排名前二」「行业渗透率持续提升」「无暴雷风险」这类表述，
年报正文几乎不会写，LLM 只能判「数据不足」——高成长 46 只里 43 只因此无法给出结论。
改写原则：
1. 每条标准必须指向年报里**真实存在**的章节或字段（行业情况/主营业务分析/核心竞争力/
   风险因素/审计意见/分红方案）或本系统已有的财务指标；
2. 保留原标准的投资含义，只把「无法验证的表述」换成「可验证的表述」；
3. 需要披露缺失即视为不满足（缺失不等于通过）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools\\rewrite_presets_qualitative.py            # 只打印
    .venv\\Scripts\\python -X utf8 tools\\rewrite_presets_qualitative.py --apply    # 写库
"""
import json
import sys
from pathlib import Path

import psycopg2

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")
BACKUP = Path("data/presets_qualitative_backup.json")
APPLY = "--apply" in sys.argv

# 预设名 → (原标准, 改写后标准, 证据来源)
REWRITE: dict[str, list[tuple[str, str, str]]] = {
    "高成长": [
        (
            "所处行业渗透率持续提升",
            "年报「行业情况」或「主营业务分析」显示所处行业需求增长或渗透率提升",
            "年报 MD&A 行业趋势段落",
        ),
        (
            "增长由主营业务驱动",
            "营收增长主要来自主营业务（非投资收益、资产处置等非经常性损益）",
            "主营业务分产品/分行业收入构成 + 非经常性损益",
        ),
        (
            "细分行业排名前二",
            "年报自述为行业前列/主要供应商，或披露市占率提升",
            "年报「核心竞争力」/「行业地位」表述",
        ),
    ],
    "深度价值": [
        (
            "现金充裕",
            "货币资金与经营现金流足以覆盖短期负债，现金比率健康",
            "现金比率/流动比率 + 现金流量表",
        ),
        (
            "非壳公司",
            "主营业务有实质收入规模，年报披露分产品收入构成",
            "营业收入构成",
        ),
        (
            "无暴雷风险",
            "审计意见为标准无保留意见，且年报重大事项未披露诉讼、处罚或退市风险警示",
            "审计报告 + 重大事项/风险因素",
        ),
    ],
    "质量价值 GARP": [
        (
            "盈利具有持续性",
            "最新报告期营收与净利同比为正，且毛利率未明显下滑",
            "财务指标 + 主营业务分析",
        ),
        (
            "存在护城河",
            "年报「核心竞争力」披露品牌/技术/专利/渠道/成本等可持续竞争优势",
            "年报核心竞争力章节",
        ),
        (
            "无重大违规",
            "内控审计意见为标准无保留意见，且年报重大事项未披露违法违规或立案调查",
            "重要事项 + 内控审计意见",
        ),
        (
            "重视股东回报",
            "年报披露现金分红方案或股份回购计划",
            "利润分配/分红方案",
        ),
    ],
    "金融价值": [
        (
            "资产质量稳健",
            "不良贷款率处于行业稳健水平且未同比恶化",
            "财务指标 npl_ratio + 年报资产质量章节",
        ),
        (
            "拨备/资本充足",
            "拨备覆盖率与资本充足率满足监管要求，且同比未下降",
            "财务指标 + 年报监管指标表",
        ),
        (
            "无重大监管处罚",
            "年报披露的资本充足率等监管指标达标，且重大事项未披露监管处罚或风险处置",
            "监管指标表 + 重要事项/风险因素",
        ),
    ],
    "周期反转": [
        (
            "处于周期底部",
            "年报描述行业景气处于低位或已出现价格/需求触底回升迹象",
            "年报行业情况/MD&A",
        ),
        (
            "行业龙头且成本低",
            "年报自述行业地位领先，并具备成本优势（一体化/自给率/规模效应）",
            "年报核心竞争力",
        ),
        (
            "无产能过剩包袱",
            "年报披露的产能利用率与在建工程规模可控，扩产与需求匹配",
            "产能情况/在建工程",
        ),
    ],
}


def main() -> None:
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, qualitative FROM screener.criteria_presets")
    rows = cur.fetchall()

    backup: dict[str, dict] = {}
    updates: list[tuple[str, list[str]]] = []
    for pid, name, qual in rows:
        if name not in REWRITE:
            continue
        backup[name] = {"id": str(pid), "qualitative": qual}
        mapping = {old: new for old, new, _ in REWRITE[name]}
        new_qual = [mapping.get(q, q) for q in (qual or [])]
        print("=" * 70)
        print(f"{name}  ({pid})")
        for old, new, src in REWRITE[name]:
            print(f"  旧: {old}")
            print(f"  新: {new}")
            print(f"  证据来源: {src}")
        updates.append((str(pid), new_qual))

    if not APPLY:
        print("\n（未写库；加 --apply 生效）")
        return

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(
        json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n备份已写入 {BACKUP}")

    for pid, new_qual in updates:
        cur.execute(
            "UPDATE screener.criteria_presets SET qualitative = %s, updated_at = now() "
            "WHERE id = %s",
            (json.dumps(new_qual, ensure_ascii=False), pid),
        )
    conn.commit()
    print("已更新预设:", len(updates))
    conn.close()


main()
