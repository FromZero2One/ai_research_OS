"""Research report management — CRUD + LLM auto-generation."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_service import EventLogger
from core.interfaces import LLMMessage
from research.models import ResearchReport, ResearchSession
from research.planner import PLAN_KEY, ResearchPlanner

REPORT_SYSTEM_PROMPT = (
    "You are a professional investment research analyst. Generate a "
    "structured research report based on the provided evidence and plan.\n\n"
    "The report must include these sections:\n"
    "1. **Executive Summary** — 2-3 sentence overview of findings\n"
    "2. **Key Findings** — Bullet points of the most important evidence "
    "(supporting and opposing)\n"
    "3. **Analysis by Dimension** — For each analysis dimension, summarize "
    "what the evidence shows\n"
    "4. **Risk Factors** — Key risks identified\n"
    "5. **Evidence Balance** — Summary of supporting vs opposing evidence "
    "strength, with reliability-weighted assessment\n"
    "6. **Preliminary Conclusion** — What the evidence suggests\n"
    "7. **Risk Disclosure** — 标准风险揭示：注明本报告基于的证据范围、"
    "数据新鲜度限制（如最后更新时间距今天数）、低可靠性证据占比较高时须明示，"
    "并声明不构成投资建议\n\n"
    "Use markdown formatting. Be objective — clearly distinguish supported "
    "conclusions from speculation. 证据条目附有可靠性(reliability)与新鲜度"
    "(数据距今年数)标注时，低可靠性(<0.5)或陈旧(>90天)的证据必须在正文中"
    "明确说明其局限。\n\n"
    "## 论断双轨规则（必须遵守）\n"
    "每条证据开头有唯一编号 [ev:<id>]。写作时：\n"
    "1. **定性论断**（管理层表述、行业趋势、竞争优势、风险叙述等）必须在句末"
    "内联标注来源证据编号，格式如：……（见 [ev:abc123]）。每条定性论断都要有引用，"
    "同一句引用多个证据时写 [ev:id1][ev:id2]。\n"
    "2. **数字论断**（营收、利润、比率、价格等）只能使用证据条目中"
    "「已核实事实」区块或 Market 数据区块给出的数字，禁止自行推算、换算或"
    "从定性文本中提取数字；数字后标注口径（如 归母/合并、同比）。\n"
    "3. 证据文本中的数字若与「已核实事实」冲突，以「已核实事实」为准，"
    "并在正文中说明差异。"
)


class ReportService:
    """Research report CRUD and AI-powered generation."""

    def __init__(self, session: AsyncSession, planner: ResearchPlanner | None = None) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.planner = planner or ResearchPlanner()

    async def create(
        self,
        session_id: uuid.UUID,
        title: str,
        content: str,
        format_: str = "markdown",
        is_final: bool = False,
    ) -> ResearchReport:
        result = await self.session.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            from core.exceptions import NotFoundError as NE

            raise NE("ResearchSession", str(session_id))

        # Determine version
        ver_result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
            .limit(1)
        )
        latest = ver_result.scalar_one_or_none()
        version = (latest.version + 1) if latest else 1

        report = ResearchReport(
            session_id=session_id,
            title=title,
            content=content,
            format=format_,
            version=version,
            is_final=is_final,
        )
        self.session.add(report)

        if is_final:
            session.status = "completed"

        await self.session.flush()
        await self.session.refresh(report)

        await self.events.record(
            source="research",
            event_type="report.created",
            entity_type="research_report",
            entity_id=str(report.id),
            payload={
                "session_id": str(session_id),
                "title": title,
                "version": version,
                "is_final": is_final,
            },
        )
        return report

    async def list(self, session_id: uuid.UUID) -> list[ResearchReport]:
        result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
        )
        return list(result.scalars().all())

    async def auto_generate(
        self,
        session_id: uuid.UUID,
        is_final: bool = False,
    ) -> ResearchReport:
        """Generate a research report via LLM from collected evidence."""
        # Load session with evidence
        result = await self.session.execute(
            select(ResearchSession)
            .where(ResearchSession.id == session_id)
            .options(selectinload(ResearchSession.evidences))
        )
        session = result.scalar_one_or_none()
        if not session:
            from core.exceptions import NotFoundError as NE

            raise NE("ResearchSession", str(session_id))

        plan = (session.extra_metadata or {}).get(PLAN_KEY)

        # Build evidence context
        supporting, opposing, neutral = [], [], []
        for ev in session.evidences or []:
            # 质量标注：可靠性 + 新鲜度，供 LLM 在报告中说明证据局限
            quality_tags = []
            if ev.reliability is not None:
                quality_tags.append(f"reliability={ev.reliability:.2f}")
            if ev.data_freshness is not None:
                quality_tags.append(f"data_age={ev.data_freshness}h")
            quality_str = f" ({', '.join(quality_tags)})" if quality_tags else ""

            # 结构化事实区块：数字来自抽取结果（已核实的原文数字），
            # 报告 LLM 只负责叙述，不自行推算
            facts_str = ""
            sf = ev.structured_facts or {}
            fact_list = sf.get("facts") or []
            if fact_list and not sf.get("not_mentioned"):
                parts = [
                    f"{f.get('metric_name')}={f.get('value')}{f.get('unit', '')}"
                    f"({f.get('period', '')})"
                    for f in fact_list[:8]
                    if isinstance(f, dict) and f.get("metric_name") is not None
                ]
                if parts:
                    facts_str = f" [已核实事实: {'; '.join(parts)}]"

            # 双轨标注：[ev:id] 供报告内联回溯；nature 提示 LLM 论断性质
            nature_str = f" nature={ev.content_nature}" if ev.content_nature else ""
            item = (
                f"- [ev:{ev.id}][{ev.source_type}]{nature_str}"
                f"{quality_str}{facts_str} {ev.content[:500]}"
            )
            if ev.evidence_type == "supporting":
                supporting.append(item)
            elif ev.evidence_type == "opposing":
                opposing.append(item)
            else:
                neutral.append(item)

        context_parts = [f"# Research: {session.title}", f"Question: {session.question}"]
        if session.context:
            context_parts.append(f"Context: {session.context}")

        if plan:
            context_parts.append("\n## Research Plan")
            context_parts.append(f"Goal: {plan.get('research_goal', '')}")
            if plan.get("sub_questions"):
                from research.gather_service import _sub_question_texts

                sq_texts = _sub_question_texts(plan["sub_questions"])
                if sq_texts:
                    context_parts.append(
                        "Sub-questions:\n" + "\n".join(f"- {q}" for q in sq_texts)
                    )
            if plan.get("analysis_dimensions"):
                context_parts.append(
                    "Analysis Dimensions:\n"
                    + "\n".join(f"- {d}" for d in plan["analysis_dimensions"])
                )

        context_parts.append(f"\n## Supporting Evidence ({len(supporting)})")
        context_parts.extend(supporting if supporting else ["(None collected yet)"])
        context_parts.append(f"\n## Opposing Evidence ({len(opposing)})")
        context_parts.extend(opposing if opposing else ["(None collected yet)"])
        context_parts.append(f"\n## Neutral Evidence ({len(neutral)})")
        context_parts.extend(neutral if neutral else ["(None collected yet)"])

        # 阶段5：多周期比对（YoY/QoQ，由已核实事实计算）+ 同业对比（指标库直查）
        from research.period_compare import (
            build_peer_comparison_block,
            build_period_comparison_block,
        )

        if period_block := build_period_comparison_block(session.evidences):
            context_parts.append(f"\n{period_block}")
        if peer_block := await build_peer_comparison_block(self.session, session.company_id):
            context_parts.append(f"\n{peer_block}")

        messages = [
            LLMMessage(role="system", content=REPORT_SYSTEM_PROMPT),
            LLMMessage(role="user", content="\n".join(context_parts)),
        ]

        response = await self.planner.llm.generate(
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )

        report = await self.create(
            session_id=session_id,
            title=f"Research Report: {session.title}",
            content=response.content,
            format_="markdown",
            is_final=is_final,
        )

        if session.status == "researching":
            session.status = "reviewing"
            await self.session.flush()

        await self.events.record(
            source="research",
            event_type="report.generated",
            entity_type="research_report",
            entity_id=str(report.id),
            payload={
                "session_id": str(session_id),
                "title": report.title,
                "version": report.version,
                "is_final": is_final,
                "supporting_count": len(supporting),
                "opposing_count": len(opposing),
            },
        )
        return report
