"""Evidence gathering — auto-collect from Knowledge Center and Market Center."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from research.evidence_service import EvidenceService
from research.planner import PLAN_KEY
from research.session_service import SessionService


class GatherService:
    """Orchestrates automatic evidence gathering from various sources."""

    def __init__(
        self,
        session: AsyncSession,
        evidence_service: EvidenceService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self.session = session
        self.evidence = evidence_service or EvidenceService(session)
        self.sessions = session_service or SessionService(session)

    async def auto_gather(
        self,
        session_id: uuid.UUID,
        use_plan: bool = True,
    ) -> dict:
        """Auto-gather evidence from Knowledge Center and Market Center."""
        from knowledge.service import KnowledgeService
        from market.service.financial_service import FinancialService
        from market.service.price_service import PriceService

        session = await self.sessions.get(session_id)
        question = session.question
        plan = (session.extra_metadata or {}).get(PLAN_KEY)

        search_queries = [question]
        if use_plan and plan:
            # sub_questions 为 ResearchPlanItem 对象（含 text/priority），提取文本
            search_queries.extend(
                _sub_question_texts(plan.get("sub_questions", []))[:5]
            )

        knowledge = KnowledgeService(self.session)
        seen_sources: set[str] = set()
        count = 0
        collected: list = []  # 收集 (evidence, doc_type)，收尾统一 LLM 批量分类+抽取

        # 1. Knowledge base search
        for query in search_queries:
            results = await knowledge.search(query, top_k=3)
            for result in results:
                dedup_key = f"{result.document_id}:{result.chunk_index}"
                if dedup_key in seen_sources:
                    continue
                seen_sources.add(dedup_key)

                evidence_type = EvidenceService.classify(result.content, query)
                ev = await self.evidence.add(
                    session_id=session_id,
                    content=result.content[:2000],
                    source_type="document",
                    source_id=result.document_id,
                    source_title=result.title,
                    relevance_score=result.score,
                    evidence_type=evidence_type,
                    # 论断性质初值（LLM 批量分类时覆盖）：报告双轨用
                    content_nature=EvidenceService.classify_nature(result.content),
                    # 证据质量评分：按文档类型映射引用等级
                    citation_quality=_citation_quality_for_doc(result.doc_type),
                    reliability=_reliability_for_document(result.score, result.doc_type),
                )
                collected.append((ev, result.doc_type))
                count += 1

        # 2. Market data if company is set
        if session.company_id:
            try:
                from company.service import CompanyService

                company_svc = CompanyService(self.session)
                company = await company_svc.get(session.company_id)

                market_prices = PriceService(self.session)
                market_financials = FinancialService(self.session)

                # 2a. Recent prices
                prices = await market_prices.get_prices(company.ticker, limit=30)
                latest = prices[-1] if prices else None
                if prices and latest:
                    closes = [p.close for p in prices if p.close is not None]
                    range_str = f"High={max(closes):.2f} Low={min(closes):.2f}" if closes else "n/a"
                    price_summary = (
                        f"Recent price data for {company.ticker}:\n"
                        f"Latest: {latest.date} Close={latest.close:.2f} "
                        f"Vol={latest.volume:.0f}\n"
                        f"30d Range: {range_str}"
                    )
                    ev = await self.evidence.add(
                        session_id=session_id,
                        content=price_summary,
                        source_type="market_data",
                        source_id=company.ticker,
                        source_title=f"{company.ticker} Price (30d)",
                        relevance_score=0.7,
                        evidence_type="neutral",
                        # 行情数据 = 数字论断（接口管"数"）
                        content_nature="quantitative",
                        # 行情数据可靠性高、新鲜度按最新数据日期计算
                        reliability=0.9,
                        citation_quality="institutional",
                        data_freshness=_hours_since(latest.date),
                    )
                    collected.append((ev, None))
                    count += 1

                # 2b. Financial metrics
                try:
                    financials = await market_financials.get_financials(company.ticker)
                    if financials:
                        fin_lines = []
                        for f in financials[:10]:
                            fin_lines.append(
                                f"{f.fiscal_year}-{f.fiscal_period}: "
                                f"{f.metric_name} = {f.metric_value}"
                            )
                        if fin_lines:
                            ev = await self.evidence.add(
                                session_id=session_id,
                                content=(
                                    "Financial metrics for "
                                    + company.ticker
                                    + ":\n"
                                    + "\n".join(fin_lines)
                                ),
                                source_type="market_data",
                                source_id=company.ticker,
                                source_title=f"{company.ticker} Financials",
                                relevance_score=0.8,
                                evidence_type="neutral",
                                # 指标数据 = 数字论断（接口管"数"）
                                content_nature="quantitative",
                            )
                            collected.append((ev, None))
                            count += 1
                except Exception:
                    logger.warning("Failed to fetch financials during auto-gather")
                    pass
            except Exception:
                logger.warning("Failed to fetch company/market data during auto-gather")
                pass

        # 3. 批量 LLM 分类（keyword 初值已在入库时写入，LLM 失败自动保留）
        evidence_objs = [ev for ev, _dt in collected]
        if evidence_objs:
            await self.evidence.classify_batch(evidence_objs, question)

        # 4. 财报类文档证据抽取结构化事实（P1，失败静默跳过）
        report_type_evs = [
            ev for ev, dt in collected if dt in _FACT_EXTRACT_DOC_TYPES
        ]
        await _extract_facts_for_reports(self.evidence, report_type_evs)

        # 5. 交叉验证：structured_facts vs Market 接口值（④ 质检器，
        #    差异生成观察事件；不进报告数字链路）
        discrepancies = 0
        if session.company_id and report_type_evs:
            try:
                from company.service import CompanyService

                company = await CompanyService(self.session).get(session.company_id)
                discrepancies = await _cross_validate_facts(
                    self.session,
                    report_type_evs,
                    company.ticker,
                    company.name,
                )
            except Exception as e:
                logger.warning("Fact cross-validation skipped: %s", e)

        # 6. 证据继承：同公司已完成会话的历史证据原样带入（标 inherited_from_session_id）
        inherited_added = 0
        if session.company_id:
            try:
                from company.service import CompanyService

                company = await CompanyService(self.session).get(session.company_id)
                inherited_added = await _select_and_inherit(
                    self.session, session_id, session.company_id, company.ticker
                )
            except Exception as e:
                logger.warning("Evidence inheritance skipped: %s", e)

        return {
            "session_id": str(session_id),
            "evidences_added": count,
            "searched_queries": len(search_queries),
            "llm_classified": settings_enabled_classifier(),
            "fact_discrepancies": discrepancies,
            "inherited_added": inherited_added,
        }


# 证据继承上限：单次 auto-gather 最多带入的历史证据条数
_INHERIT_MAX = 10


async def _select_and_inherit(
    session_db: AsyncSession,
    session_id: uuid.UUID,
    company_id: uuid.UUID,
    ticker: str | None,
) -> int:
    """证据继承：同公司已完成会话的证据原样带入当前会话，标 inherited_from_session_id。

    规则（见 specs/2026-10-16-evidence-inheritance-design.md）：
    - 仅源会话 status='completed'；按会话 updated_at 倒序（最新会话优先）
    - 幂等：已是继承证据（标记非空）不重复带入
    - 去重：与当前会话已有 (source_type, source_id, content[:256]) 相同的跳过
    - 上限 _INHERIT_MAX 条；不重新走 LLM 分类/事实抽取（原会话已完成）
    """
    from research.models import ResearchEvidence, ResearchSession

    existing = (
        (await session_db.execute(
            select(ResearchEvidence).where(ResearchEvidence.session_id == session_id)
        )).scalars().all()
    )
    seen = {
        (ev.source_type, ev.source_id, (ev.content or "")[:256])
        for ev in existing
    }

    stmt = (
        select(ResearchEvidence, ResearchSession)
        .join(ResearchSession, ResearchEvidence.session_id == ResearchSession.id)
        .where(
            ResearchSession.company_id == company_id,
            ResearchSession.id != session_id,
            ResearchSession.status == "completed",
            ResearchEvidence.inherited_from_session_id.is_(None),
        )
        .order_by(ResearchSession.updated_at.desc(), ResearchEvidence.created_at.desc())
        .limit(_INHERIT_MAX * 6)  # 预留去重过滤后的余量
    )
    rows = (await session_db.execute(stmt)).all()  # list of (evidence, source_session)

    added = 0
    for evidence, _src_session in rows:
        if added >= _INHERIT_MAX:
            break
        key = (evidence.source_type, evidence.source_id, (evidence.content or "")[:256])
        if key in seen:
            continue
        session_db.add(
            ResearchEvidence(
                session_id=session_id,
                content=evidence.content,
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                source_title=evidence.source_title,
                relevance_score=evidence.relevance_score,
                evidence_type=evidence.evidence_type,
                content_nature=evidence.content_nature,
                summary=evidence.summary,
                reliability=evidence.reliability,
                data_freshness=evidence.data_freshness,
                citation_quality=evidence.citation_quality,
                classification_source=evidence.classification_source,
                classification_confidence=evidence.classification_confidence,
                structured_facts=evidence.structured_facts,
                inherited_from_session_id=evidence.session_id,
            )
        )
        seen.add(key)
        added += 1

    if added:
        await session_db.flush()
        from core.event_service import EventLogger

        await EventLogger(session_db).record(
            source="research",
            event_type="evidence.inherited",
            entity_type="research_evidence_batch",
            entity_id=str(session_id),
            payload={"count": added, "ticker": ticker},
        )
        logger.info("Evidence inherited: %d rows into session %s", added, session_id)
    return added


def settings_enabled_classifier() -> str:
    """供调用方了解本次分类实际使用的引擎。"""
    from core.config import settings

    return settings.EVIDENCE_CLASSIFIER


# 财报类文档类型 → 允许抽取（新闻数字噪声大，不抽）
_FACT_EXTRACT_DOC_TYPES = {"report", "sec_10k", "sec_10q"}

_FINANCIAL_FACTS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string"},
                    "value": {"type": "number"},
                    "unit": {"type": "string"},
                    "period": {"type": "string"},
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "flat", "n/a"],
                    },
                },
                "required": ["metric_name", "value", "unit", "period"],
            },
        },
        "not_mentioned": {"type": "boolean"},
    },
    "required": ["facts", "not_mentioned"],
}

_FACT_SYSTEM_PROMPT = (
    "你是财务数据抽取器。从给定的公司文档片段中抽取明确出现的财务数字。\n"
    "铁律：\n"
    "1. 只抽取原文明确写出的数字，禁止推算、换算、估算。\n"
    "2. 原文中没有任何财务数字时，输出 {\"facts\": [], \"not_mentioned\": true}。\n"
    "3. metric_name 用原文的指标名；unit 保留原文单位；period 标注报告期（如 2025年报）。\n"
    "4. direction 标注同比/环比方向（up/down/flat），原文未说明则为 n/a。\n"
    "5. 输出 JSON，格式为 {\"facts\": [{\"metric_name\": \"...\", \"value\": 0, "
    "\"unit\": \"...\", \"period\": \"...\", \"direction\": \"...\"}], "
    "\"not_mentioned\": false}。"
)


async def _extract_facts_for_reports(evidence_svc, evidences) -> int:
    """对财报类文档证据抽取结构化财务事实，写入 structured_facts。

    调用方已按 doc_type ∈ {report, sec_10k, sec_10q} 过滤；此处跳过
    已抽取的证据，LLM 失败静默继续。返回成功抽取的条数。
    """
    targets = [ev for ev in evidences if ev.structured_facts is None]
    if not targets:
        return 0

    from core.adapters.llm import create_llm
    from core.interfaces import LLMMessage
    from market.models import normalize_metric_name

    llm = create_llm(tier="light")
    extracted = 0
    for ev in targets:
        try:
            result = await llm.generate_structured(
                messages=[
                    LLMMessage(role="system", content=_FACT_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=ev.content[:2000]),
                ],
                schema=_FINANCIAL_FACTS_SCHEMA,
                temperature=0.1,
            )
        except Exception as e:
            logger.warning("Fact extraction failed for evidence %s: %s", ev.id, e)
            continue

        facts = result.get("facts") or []
        if result.get("not_mentioned") or not facts:
            ev.structured_facts = {"facts": [], "not_mentioned": True}
            continue

        # 指标名归一化（接 FinancialMetricName 标准枚举）
        for f in facts:
            if isinstance(f, dict) and f.get("metric_name"):
                f["metric_name"] = normalize_metric_name(f["metric_name"])
        ev.structured_facts = {"facts": facts, "not_mentioned": False}
        extracted += 1

    if extracted:
        logger.info(
            "Structured facts extracted for %d/%d report evidences", extracted, len(targets)
        )
    return extracted


async def _cross_validate_facts(
    session_db,
    evidences: list,
    ticker: str,
    company_name: str | None = None,
) -> int:
    """structured_facts 与 Market 接口值交叉验证（④ 质检器）。

    偏差 ≥10% 视为疑似口径差异（合并 vs 归母/追溯调整），
    写入 Observation（attention）+ 事件日志。返回差异条数。
    """
    all_facts = [
        f
        for ev in evidences
        if ev.structured_facts and not ev.structured_facts.get("not_mentioned")
        for f in (ev.structured_facts.get("facts") or [])
    ]
    if not all_facts:
        return 0

    try:
        from market.service.financial_service import FinancialService

        metrics = await FinancialService(session_db).get_financials(ticker)
    except Exception as e:
        logger.warning("Fact cross-validation skipped (market fetch failed): %s", e)
        return 0

    from research.fact_validator import compare_facts_with_market

    discrepancies = compare_facts_with_market(all_facts, metrics)
    if not discrepancies:
        return 0

    from core.event_service import EventLogger
    from core.observation import Observation

    session_db.add(
        Observation(
            ticker=ticker,
            company_name=company_name or ticker,
            reasons="\n".join(f"[口径差异] {d}" for d in discrepancies[:10]),
            status="attention",
        )
    )
    await EventLogger(session_db).record(
        source="research",
        event_type="facts.cross_validated",
        entity_type="research_evidence_batch",
        payload={"ticker": ticker, "discrepancies": len(discrepancies)},
    )
    logger.info(
        "Fact cross-validation: %d discrepancies for %s", len(discrepancies), ticker
    )
    return len(discrepancies)


def _sub_question_texts(items) -> list[str]:
    """从计划子问题（字符串或 ResearchPlanItem 字典）提取纯文本。"""
    texts = []
    for item in items or []:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict) and item.get("text"):
            texts.append(item["text"])
    return texts


def _citation_quality_for_doc(doc_type: str | None) -> str:
    """按文档类型映射引用质量等级。"""
    mapping = {
        "sec_10k": "institutional",
        "sec_10q": "institutional",
        "report": "analyst",
        "transcript": "analyst",
        "news_article": "internal",
    }
    return mapping.get(doc_type or "", "internal")


def _reliability_for_document(score: float, doc_type: str | None) -> float:
    """文档证据可靠性 = 检索得分 × 文档类型权重，上限 0.95。"""
    type_weight = {
        "sec_10k": 1.0,
        "sec_10q": 0.95,
        "report": 0.85,
        "transcript": 0.75,
        "markdown": 0.7,
        "pdf": 0.8,
        "news_article": 0.6,
    }.get(doc_type or "", 0.7)
    return round(min(0.95, score * type_weight), 2)


def _hours_since(d) -> int:
    """计算距某日期的小时数（行情/财报数据新鲜度）。"""
    from datetime import datetime
    from datetime import time as dt_time

    ref = datetime.combine(d, dt_time.min)
    return max(0, int((datetime.now() - ref).total_seconds() // 3600))
