"""Research session CRUD — create, read, list, update, delete."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from core.logging import logger
from research.models import ResearchSession
from research.planner import PLAN_KEY, ResearchPlanner


class SessionService:
    """Research session lifecycle management."""

    def __init__(self, session: AsyncSession, planner: ResearchPlanner | None = None) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.planner = planner or ResearchPlanner()

    async def create(
        self,
        title: str,
        question: str,
        context: str | None = None,
        company_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        auto_plan: bool = True,
        plan_type: str | None = None,
    ) -> ResearchSession:
        session = ResearchSession(
            title=title,
            question=question,
            context=context,
            company_id=company_id,
            status="draft",
            tags=tags,
        )
        self.session.add(session)
        await self.session.flush()
        await self.session.refresh(session)

        # 持久化 plan_type：后台 quick_research 链的 generate_plan 需要读它
        if plan_type:
            session.extra_metadata = session.extra_metadata or {}
            session.extra_metadata["plan_type"] = plan_type

        if auto_plan:
            try:
                company_name = None
                if company_id:
                    from company.service import CompanyService

                    try:
                        company_svc = CompanyService(self.session)
                        company = await company_svc.get(company_id)
                        company_name = company.name
                    except NotFoundError:
                        pass

                plan = await self.planner.generate_plan(
                    question, context, company_name, plan_type=plan_type
                )
                session.extra_metadata = session.extra_metadata or {}
                session.extra_metadata[PLAN_KEY] = plan
                await self.session.flush()
            except Exception:
                logger.warning("Auto-plan generation failed during session creation")
                pass

        await self.events.record(
            source="research",
            event_type="research.started",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={
                "title": title,
                "question": question[:200],
                "company_id": str(company_id) if company_id else None,
            },
        )
        return session

    async def generate_plan(self, session_id: uuid.UUID) -> dict:
        session = await self.get(session_id)

        company_name = None
        if session.company_id:
            from company.service import CompanyService

            try:
                company_svc = CompanyService(self.session)
                company = await company_svc.get(session.company_id)
                company_name = company.name
            except NotFoundError:
                pass

        # 优先用创建时选定的 plan_type（模板命中则零 LLM 调用）
        plan_type = (session.extra_metadata or {}).get("plan_type")
        plan = await self.planner.generate_plan(
            session.question, session.context, company_name, plan_type=plan_type
        )
        session.extra_metadata = session.extra_metadata or {}
        session.extra_metadata[PLAN_KEY] = plan
        await self.session.flush()

        await self.events.record(
            source="research",
            event_type="research.plan_generated",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={"sub_questions": len(plan.get("sub_questions", []))},
        )
        return plan

    async def get(self, session_id: uuid.UUID, eager: bool = False) -> ResearchSession:
        stmt = select(ResearchSession).where(ResearchSession.id == session_id)
        if eager:
            stmt = stmt.options(
                selectinload(ResearchSession.evidences),
                selectinload(ResearchSession.reports),
            )
        result = await self.session.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))
        return session

    async def list(
        self,
        status: str | None = None,
        company_id: uuid.UUID | None = None,
        query: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ResearchSession], int]:
        stmt = select(ResearchSession)
        if status:
            stmt = stmt.where(ResearchSession.status == status)
        if company_id:
            stmt = stmt.where(ResearchSession.company_id == company_id)
        if query:
            stmt = stmt.where(
                ResearchSession.title.ilike(f"%{query}%")
                | ResearchSession.question.ilike(f"%{query}%")
            )
        count_stmt = stmt.with_only_columns(func.count(ResearchSession.id)).order_by(None)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(desc(ResearchSession.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update(self, session_id: uuid.UUID, **kwargs) -> ResearchSession:
        session = await self.get(session_id)
        for key, val in kwargs.items():
            if val is not None and hasattr(session, key):
                setattr(session, key, val)
        await self.session.flush()

        if "status" in kwargs and kwargs["status"]:
            await self.events.record(
                source="research",
                event_type=f"research.{kwargs['status']}",
                entity_type="research_session",
                entity_id=str(session.id),
                payload={"title": session.title},
            )
        await self.session.refresh(session)
        return session

    async def get_plan(self, session_id: uuid.UUID) -> dict | None:
        """Get research plan from session metadata."""
        session = await self.get(session_id)
        plan = (session.extra_metadata or {}).get(PLAN_KEY)
        return plan

    # ── Progress tracking (used by quick research SSE/worker) ──────────

    PROGRESS_KEY = "quick_research_progress"

    async def get_progress(self, session_id: uuid.UUID) -> dict:
        """Get quick-research progress from session metadata."""
        try:
            session = await self.get(session_id)
        except NotFoundError:
            return {"step": "error", "error": "Session not found"}
        progress = (session.extra_metadata or {}).get(self.PROGRESS_KEY, {})
        return {
            "step": progress.get("step", "starting"),
            "message": progress.get("message", ""),
            "status": session.status,
            "session_id": str(session.id),
            "report_id": progress.get("report_id"),
            "error": progress.get("error"),
        }

    async def update_progress(
        self,
        session_id: uuid.UUID,
        step: str,
        message: str,
        **extra,
    ) -> None:
        """Update quick-research progress in session metadata."""
        session = await self.get(session_id)
        session.extra_metadata = session.extra_metadata or {}
        session.extra_metadata[self.PROGRESS_KEY] = {
            "step": step,
            "message": message,
            **extra,
        }

    async def delete(self, session_id: uuid.UUID) -> None:
        session = await self.get(session_id)
        await self.session.delete(session)
