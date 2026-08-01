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
    "strength\n"
    "6. **Preliminary Conclusion** — What the evidence suggests\n\n"
    "Use markdown formatting. Be objective — clearly distinguish supported "
    "conclusions from speculation."
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
            item = f"- [{ev.source_type}] {ev.content[:500]}"
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
                context_parts.append(
                    "Sub-questions:\n" + "\n".join(f"- {q}" for q in plan["sub_questions"])
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
