"""Timeline Service — aggregates research history into a chronological timeline.

Handles cross-session queries, event log mapping, and report diffing.
All raw SQLAlchemy is encapsulated here; routes call service methods only.
"""

from __future__ import annotations

import difflib
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import NotFoundError
from core.logging import logger
from research.models import ResearchReport, ResearchSession


class TimelineService:
    """Aggregate research timeline data across sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_company_timeline(self, ticker: str) -> dict[str, Any]:
        """Full research timeline for a company — all sessions + events sorted chronologically."""
        from company.service import CompanyService
        from core.event_log import EventLog

        company_svc = CompanyService(self.session)
        company = await company_svc.get_by_ticker(ticker)
        if not company:
            return {"ticker": ticker.upper(), "company_name": None, "events": []}

        company_id = company.id
        company_name = company.name

        # 1. All sessions for this company
        result = await self.session.execute(
            select(ResearchSession)
            .where(ResearchSession.company_id == company_id)
            .options(
                selectinload(ResearchSession.reports),
                selectinload(ResearchSession.evidences),
            )
            .order_by(ResearchSession.created_at.asc())
        )
        sessions = list(result.scalars().all())

        # 2. Build flat event list
        events: list[dict[str, Any]] = []

        # Batch-load EventLog entries for all sessions (avoid N+1).
        session_ids = [str(s.id) for s in sessions]
        log_map: dict[str, list[Any]] = {}
        if session_ids:
            logs_result = await self.session.execute(
                select(EventLog)
                .where(
                    EventLog.entity_id.in_(session_ids),
                    EventLog.source == "research",
                )
                .order_by(EventLog.occurred_at.asc())
            )
            for log in logs_result.scalars().all():
                log_map.setdefault(log.entity_id or "", []).append(log)

        for s in sessions:
            # Session created
            events.append(
                {
                    "type": "session_created",
                    "date": s.created_at.isoformat() if s.created_at else "",
                    "session_id": str(s.id),
                    "session_title": s.title,
                    "detail": "创建研究",
                    "status": s.status,
                }
            )

            # Status changes from EventLog
            log_entries = log_map.get(str(s.id), [])

            for log in log_entries:
                event_type = log.event_type
                if event_type == "research.plan_generated":
                    events.append(
                        {
                            "type": "plan_generated",
                            "date": log.occurred_at.isoformat() if log.occurred_at else "",
                            "session_id": str(s.id),
                            "session_title": s.title,
                            "detail": "AI 研究计划生成",
                        }
                    )
                elif event_type in ("report.created", "report.generated"):
                    events.append(
                        {
                            "type": "report_generated",
                            "date": log.occurred_at.isoformat() if log.occurred_at else "",
                            "session_id": str(s.id),
                            "session_title": s.title,
                            "detail": "研究报告生成",
                        }
                    )
                elif event_type == "research.completed":
                    events.append(
                        {
                            "type": "research_completed",
                            "date": log.occurred_at.isoformat() if log.occurred_at else "",
                            "session_id": str(s.id),
                            "session_title": s.title,
                            "thesis": s.thesis,
                            "decision": s.decision,
                            "confidence": s.confidence,
                            "detail": f"研究完结 - {s.decision}" if s.decision else "研究完结",
                        }
                    )
                elif event_type.startswith("research."):
                    status_name = event_type.replace("research.", "")
                    events.append(
                        {
                            "type": "status_change",
                            "date": log.occurred_at.isoformat() if log.occurred_at else "",
                            "session_id": str(s.id),
                            "session_title": s.title,
                            "detail": f"状态变更: {status_name}",
                        }
                    )

            # Report versions
            for report in s.reports or []:
                events.append(
                    {
                        "type": "report_version",
                        "date": report.created_at.isoformat() if report.created_at else "",
                        "session_id": str(s.id),
                        "session_title": s.title,
                        "report_id": str(report.id),
                        "version": report.version,
                        "is_final": report.is_final,
                        "detail": f"报告 v{report.version}{' (终稿)' if report.is_final else ''}",
                    }
                )

        # 3. Observation events (price alerts, research reminders)
        obs_result = await self.session.execute(
            select(EventLog)
            .where(
                EventLog.source == "observation",
                EventLog.event_type == "observation.generated",
            )
            .order_by(desc(EventLog.occurred_at))
            .limit(50)
        )
        for log in obs_result.scalars().all():
            payload = log.payload or {}
            if payload.get("ticker") != ticker.upper():
                continue
            reasons = payload.get("reasons", [])
            events.append(
                {
                    "type": "observation",
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "detail": "; ".join(reasons) if reasons else "系统观察触发",
                    "observation_status": payload.get("status", "attention"),
                }
            )

        # Sort by date ascending
        events.sort(key=lambda e: e.get("date", ""))

        return {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "events": events,
        }

    async def get_report_diff(
        self,
        report_id: uuid.UUID,
        other_version: int,
    ) -> dict[str, Any]:
        """Compare two versions of a report and return structured diff."""
        # Get the current report
        result = await self.session.execute(
            select(ResearchReport).where(ResearchReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise NotFoundError("ResearchReport", str(report_id))

        # Get the other version
        result = await self.session.execute(
            select(ResearchReport).where(
                ResearchReport.session_id == report.session_id,
                ResearchReport.version == other_version,
            )
        )
        other = result.scalar_one_or_none()
        if not other:
            raise NotFoundError("ResearchReport", f"version {other_version}")

        # Generate diff
        old_lines = other.content.splitlines(keepends=True)
        new_lines = report.content.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"v{other_version}",
                tofile=f"v{report.version}",
                n=3,
            )
        )

        additions = 0
        deletions = 0
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        return {
            "report_id": str(report.id),
            "session_id": str(report.session_id),
            "from_version": other_version,
            "to_version": report.version,
            "diff": "".join(diff),
            "stats": {
                "additions": additions,
                "deletions": deletions,
                "context_lines": len(diff) - additions - deletions - 2,
            },
        }

    async def get_session_timeline(self, session_id: uuid.UUID) -> dict[str, Any]:
        """Timeline for a single research session."""
        from core.event_log import EventLog

        result = await self.session.execute(
            select(ResearchSession)
            .where(ResearchSession.id == session_id)
            .options(
                selectinload(ResearchSession.reports),
                selectinload(ResearchSession.evidences),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))

        events: list[dict[str, Any]] = []

        # Session created
        events.append(
            {
                "type": "created",
                "date": session.created_at.isoformat() if session.created_at else "",
                "detail": "研究会话创建",
            }
        )

        # Event log entries
        log_result = await self.session.execute(
            select(EventLog)
            .where(
                EventLog.entity_id == str(session_id),
                EventLog.source == "research",
            )
            .order_by(EventLog.occurred_at.asc())
        )
        for log in log_result.scalars().all():
            event_type = log.event_type.replace("research.", "")
            if event_type == "evidence.added":
                continue
            events.append(
                {
                    "type": event_type,
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "detail": log.summary or event_type,
                }
            )

        # Report versions
        for report in session.reports or []:
            events.append(
                {
                    "type": "report_version",
                    "date": report.created_at.isoformat() if report.created_at else "",
                    "version": report.version,
                    "is_final": report.is_final,
                    "report_id": str(report.id),
                    "detail": f"报告 v{report.version}{' (终稿)' if report.is_final else ''}",
                }
            )

        # Sort by date
        events.sort(key=lambda e: e.get("date", ""))

        return {
            "session_id": str(session_id),
            "session_title": session.title,
            "status": session.status,
            "thesis": session.thesis,
            "decision": session.decision,
            "events": events,
        }

    async def get_evolution_summary(self, session_id: uuid.UUID) -> dict[str, Any]:
        """LLM 总结同公司历次研究的论点演变（复盘能力）。

        输入：该公司全部完结/进行中 session 的 thesis + decision + confidence，
        按时间排序。LLM 输出四段式：论点演变 / 已被证伪的判断 / 新增信息 /
        结论是否漂移。LLM 失败时返回机械摘要，不阻塞调用方。
        """
        from core.adapters.llm import create_llm
        from core.interfaces import LLMMessage

        result = await self.session.execute(
            select(ResearchSession)
            .where(ResearchSession.id == session_id)
            .options(selectinload(ResearchSession.reports))
        )
        current = result.scalar_one_or_none()
        if not current:
            raise NotFoundError("ResearchSession", str(session_id))
        if current.company_id is None:
            return {
                "session_id": str(session_id),
                "evolution": None,
                "reason": "未关联公司，无法跨 session 对比",
            }

        history_result = await self.session.execute(
            select(ResearchSession)
            .where(
                ResearchSession.company_id == current.company_id,
                ResearchSession.thesis.isnot(None),
            )
            .order_by(ResearchSession.created_at.asc())
        )
        history = list(history_result.scalars().all())
        if len(history) < 2:
            return {
                "session_id": str(session_id),
                "evolution": None,
                "reason": "历史论点不足 2 条，无法对比演变",
            }

        # 机械摘要（LLM 失败时的降级输出，也是 LLM 的输入素材）
        lines = []
        for s in history:
            marker = "（本次）" if s.id == current.id else ""
            lines.append(
                f"- {s.created_at:%Y-%m-%d} {marker}[{s.decision or '?'} "
                f"置信度 {s.confidence if s.confidence is not None else '?'}] "
                f"{(s.thesis or '')[:200]}"
            )
        mechanical = "\n".join(lines)

        prompt = (
            "你是投资研究复盘分析师。以下是同一家公司历次研究的投资论点与结论，"
            "按时间排序。请输出 Markdown 四段：\n"
            "1. **论点演变** — 核心判断如何随新证据演进\n"
            "2. **已被证伪/需修正的判断** — 哪些早期论点被后续数据推翻\n"
            "3. **新增关键信息** — 促成演变的新证据\n"
            "4. **结论漂移提示** — 决策方向变化是否与新证据匹配；"
            "若无新证据支撑的转向须明示\n\n"
            "要求：全程中文，引用具体日期与决策，不编造未提及的信息。\n\n"
            f"公司研究历史：\n{mechanical}"
        )
        try:
            llm = create_llm(tier="heavy")
            resp = await llm.generate(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=1024,
            )
            evolution = resp.content
            engine = resp.model
        except Exception as e:
            logger.warning("Evolution summary LLM failed, using mechanical fallback: %s", e)
            evolution = None
            engine = None

        return {
            "session_id": str(session_id),
            "company_id": str(current.company_id),
            "history_count": len(history),
            "mechanical_history": mechanical,
            "evolution": evolution,
            "engine": engine,
        }
