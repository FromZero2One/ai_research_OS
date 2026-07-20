"""Research Center service — the core workflow engine.

This is the most important module in the system. The flow:

  Question → Research Plan → Evidence Gathering → Analysis → Report → Thesis → Decision
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.adapters.llm import create_llm
from core.event_service import EventLogger
from core.exceptions import NotFoundError, ValidationError
from core.interfaces import LLMMessage
from research.models import ResearchEvidence, ResearchReport, ResearchSession

RESEARCH_PLAN_SYSTEM_PROMPT = """You are a professional investment research analyst. Given a research question, create a structured research plan.

Your plan must include:
1. **research_goal**: A clear restatement of what needs to be researched
2. **sub_questions**: 3-6 specific questions that must be answered to reach a conclusion
3. **analysis_dimensions**: Key dimensions to analyze (e.g., financial health, competitive position, industry trends, management quality, valuation, risks)
4. **data_requirements**: What specific data points are needed
5. **suggested_sources**: Types of documents or data sources to consult

Respond with valid JSON only, no markdown formatting."""


class ResearchPlanner:
    """Generates structured research plans from questions using LLM."""

    PLAN_KEY = "research_plan"

    def __init__(self) -> None:
        self.llm = create_llm()

    async def generate_plan(
        self,
        question: str,
        context: str | None = None,
        company_name: str | None = None,
    ) -> dict:
        """Generate a structured research plan using LLM."""
        user_prompt = f"Research Question: {question}\n"
        if context:
            user_prompt += f"Context: {context}\n"
        if company_name:
            user_prompt += f"Company: {company_name}\n"

        user_prompt += (
            "\nCreate a detailed research plan as JSON with keys: "
            "research_goal, sub_questions (list), analysis_dimensions (list), "
            "data_requirements (list), suggested_sources (list)."
        )

        messages = [
            LLMMessage(role="system", content=RESEARCH_PLAN_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.llm.generate(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        try:
            # Strip markdown code fences if present
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
            if content.startswith("json"):
                content = content[4:].strip()
            plan = json.loads(content)
            # Validate required keys
            required = {"research_goal", "sub_questions", "analysis_dimensions"}
            if not required.issubset(plan.keys()):
                plan["research_goal"] = plan.get("research_goal", question)
                plan["sub_questions"] = plan.get("sub_questions", [question])
                plan["analysis_dimensions"] = plan.get("analysis_dimensions", ["Financial", "Industry", "Competitive"])
            plan["data_requirements"] = plan.get("data_requirements", [])
            plan["suggested_sources"] = plan.get("suggested_sources", [])
            return plan
        except (json.JSONDecodeError, AttributeError):
            # Fallback: return a basic plan
            return {
                "research_goal": question,
                "sub_questions": [question],
                "analysis_dimensions": ["Financial Analysis", "Industry Analysis", "Competitive Position", "Risk Factors"],
                "data_requirements": ["Revenue and earnings trends", "Market share data"],
                "suggested_sources": ["Annual reports", "Industry reports", "News"],
            }


class ResearchService:
    """Research workflow orchestration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.planner = ResearchPlanner()

    # ── Sessions ──────────────────────────────────────────────────

    async def create_session(
        self,
        title: str,
        question: str,
        context: str | None = None,
        company_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        auto_plan: bool = True,
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

        # Auto-generate research plan
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

                plan = await self.planner.generate_plan(question, context, company_name)
                session.extra_metadata = session.extra_metadata or {}
                session.extra_metadata[ResearchPlanner.PLAN_KEY] = plan
                await self.session.flush()
            except Exception:
                # Plan generation failure shouldn't block session creation
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

    async def generate_plan(
        self, session_id: uuid.UUID
    ) -> dict:
        """Generate (or regenerate) a research plan for an existing session."""
        session = await self.get_session(session_id)

        company_name = None
        if session.company_id:
            from company.service import CompanyService
            try:
                company_svc = CompanyService(self.session)
                company = await company_svc.get(session.company_id)
                company_name = company.name
            except NotFoundError:
                pass

        plan = await self.planner.generate_plan(
            session.question, session.context, company_name
        )
        session.extra_metadata = session.extra_metadata or {}
        session.extra_metadata[ResearchPlanner.PLAN_KEY] = plan
        await self.session.flush()

        await self.events.record(
            source="research",
            event_type="research.plan_generated",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={"sub_questions": len(plan.get("sub_questions", []))},
        )
        return plan

    async def get_session(
        self, session_id: uuid.UUID, eager: bool = False
    ) -> ResearchSession:
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

    async def list_sessions(
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

        # Count
        count_result = await self.session.execute(
            stmt.with_only_columns(ResearchSession.id).order_by(None)
        )
        total = len(count_result.all())

        stmt = stmt.order_by(desc(ResearchSession.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_session(
        self, session_id: uuid.UUID, **kwargs
    ) -> ResearchSession:
        session = await self.get_session(session_id)

        for key, val in kwargs.items():
            if val is not None and hasattr(session, key):
                setattr(session, key, val)

        await self.session.flush()

        # Log significant transitions
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

    async def delete_session(self, session_id: uuid.UUID) -> None:
        session = await self.get_session(session_id)
        await self.session.delete(session)

    # ── Evidence ──────────────────────────────────────────────────

    async def add_evidence(
        self, session_id: uuid.UUID, **kwargs
    ) -> ResearchEvidence:
        # Verify session exists
        session = await self.get_session(session_id)
        if session.status == "completed":
            # Allow adding evidence but don't change status
            pass

        evidence = ResearchEvidence(session_id=session_id, **kwargs)
        self.session.add(evidence)

        # Auto-transition to researching if still in draft
        if session.status == "draft":
            session.status = "researching"

        await self.session.flush()
        await self.session.refresh(evidence)

        await self.events.record(
            source="research",
            event_type="evidence.added",
            entity_type="research_evidence",
            entity_id=str(evidence.id),
            payload={
                "session_id": str(session_id),
                "source_type": kwargs.get("source_type"),
                "evidence_type": kwargs.get("evidence_type"),
            },
        )
        return evidence

    async def get_evidences(
        self, session_id: uuid.UUID
    ) -> list[ResearchEvidence]:
        result = await self.session.execute(
            select(ResearchEvidence)
            .where(ResearchEvidence.session_id == session_id)
            .order_by(ResearchEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def remove_evidence(self, evidence_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(ResearchEvidence).where(ResearchEvidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        if not evidence:
            raise NotFoundError("ResearchEvidence", str(evidence_id))
        await self.session.delete(evidence)

    # ── Reports ───────────────────────────────────────────────────

    async def create_report(
        self,
        session_id: uuid.UUID,
        title: str,
        content: str,
        format_: str = "markdown",
        is_final: bool = False,
    ) -> ResearchReport:
        session = await self.get_session(session_id)

        # Determine version
        result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
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

    async def get_reports(
        self, session_id: uuid.UUID
    ) -> list[ResearchReport]:
        result = await self.session.execute(
            select(ResearchReport)
            .where(ResearchReport.session_id == session_id)
            .order_by(ResearchReport.version.desc())
        )
        return list(result.scalars().all())

    # ── AI Report Generation ─────────────────────────────────────────

    REPORT_SYSTEM_PROMPT = """You are a professional investment research analyst. Generate a structured research report based on the provided evidence and research plan.

The report must include these sections:
1. **Executive Summary** — 2-3 sentence overview of findings
2. **Key Findings** — Bullet points of the most important evidence (supporting and opposing)
3. **Analysis by Dimension** — For each analysis dimension, summarize what the evidence shows
4. **Risk Factors** — Key risks identified
5. **Evidence Balance** — Summary of supporting vs opposing evidence strength
6. **Preliminary Conclusion** — What the evidence suggests

Use markdown formatting. Be objective — clearly distinguish supported conclusions from speculation."""

    async def auto_generate_report(
        self,
        session_id: uuid.UUID,
        is_final: bool = False,
    ) -> ResearchReport:
        """Auto-generate a research report using LLM from collected evidence.

        Gathers all evidence for a session, reads the research plan,
        and calls LLM to synthesize a structured report.
        """
        session = await self.get_session(session_id, eager=True)
        plan = (session.extra_metadata or {}).get(ResearchPlanner.PLAN_KEY)

        # Build evidence context
        supporting = []
        opposing = []
        neutral = []
        for ev in (session.evidences or []):
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
                context_parts.append("Sub-questions:\n" + "\n".join(f"- {q}" for q in plan["sub_questions"]))
            if plan.get("analysis_dimensions"):
                context_parts.append("Analysis Dimensions:\n" + "\n".join(f"- {d}" for d in plan["analysis_dimensions"]))

        context_parts.append(f"\n## Supporting Evidence ({len(supporting)})")
        context_parts.extend(supporting if supporting else ["(None collected yet)"])

        context_parts.append(f"\n## Opposing Evidence ({len(opposing)})")
        context_parts.extend(opposing if opposing else ["(None collected yet)"])

        context_parts.append(f"\n## Neutral Evidence ({len(neutral)})")
        context_parts.extend(neutral if neutral else ["(None collected yet)"])

        user_prompt = "\n".join(context_parts)

        messages = [
            LLMMessage(role="system", content=self.REPORT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.planner.llm.generate(
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )

        report_title = f"Research Report: {session.title}"
        report = await self.create_report(
            session_id=session_id,
            title=report_title,
            content=response.content,
            format_="markdown",
            is_final=is_final,
        )

        # Auto-transition to reviewing if still researching
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
                "title": report_title,
                "version": report.version,
                "is_final": is_final,
                "supporting_count": len(supporting),
                "opposing_count": len(opposing),
            },
        )
        return report

    async def finalize_thesis(
        self,
        session_id: uuid.UUID,
        thesis: str,
        decision: str,
        confidence: float,
    ) -> ResearchSession:
        """Finalize the research with a thesis and decision."""
        session = await self.get_session(session_id)
        session.thesis = thesis
        session.decision = decision
        session.confidence = confidence
        session.status = "completed"

        await self.session.flush()

        await self.events.record(
            source="research",
            event_type="research.completed",
            entity_type="research_session",
            entity_id=str(session.id),
            payload={
                "title": session.title,
                "decision": decision,
                "confidence": confidence,
            },
        )
        await self.session.refresh(session)
        return session

    # ── AI-Assisted Research (V1) ─────────────────────────────────

    async def auto_gather_evidence(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
        use_plan: bool = True,
    ) -> dict:
        """Auto-gather evidence from Knowledge Center and Market Center.

        Uses the research plan sub-questions for targeted searches, then
        classifies each piece of evidence as supporting/opposing/neutral.

        Returns summary of what was collected.
        """
        from knowledge.service import KnowledgeService
        from market.service import MarketService

        session = await self.get_session(session_id)
        question = session.question
        plan = (session.extra_metadata or {}).get(ResearchPlanner.PLAN_KEY)

        # Build search queries from plan or fall back to main question
        search_queries = [question]
        if use_plan and plan:
            search_queries.extend(plan.get("sub_questions", [])[:5])

        knowledge = KnowledgeService(db)
        seen_sources: set[str] = set()
        count = 0

        # 1. Knowledge base search — one query per sub-question for breadth
        for query in search_queries:
            results = await knowledge.search(query, top_k=3)
            for result in results:
                dedup_key = f"{result.document_id}:{result.chunk_index}"
                if dedup_key in seen_sources:
                    continue
                seen_sources.add(dedup_key)

                # Determine evidence type using simple heuristics
                # (full LLM classification would be V2)
                evidence_type = self._classify_evidence(result.content, query)

                await self.add_evidence(
                    session_id=session_id,
                    content=result.content[:2000],
                    source_type="document",
                    source_id=result.document_id,
                    source_title=result.title,
                    relevance_score=result.score,
                    evidence_type=evidence_type,
                )
                count += 1

        # 2. Market data if company is set
        if session.company_id:
            try:
                from company.service import CompanyService

                company_svc = CompanyService(db)
                company = await company_svc.get(session.company_id)

                market = MarketService(db)

                # 2a. Recent prices
                prices = await market.get_prices(company.ticker, limit=30)
                if prices:
                    latest = prices[-1]
                price_summary = (
                    f"Recent price data for {company.ticker}:\n"
                    f"Latest: {latest.date} Close={latest.close:.2f} "
                    f"Vol={latest.volume:.0f}\n"
                    f"30d Range: High={max(p.close for p in prices):.2f} "
                    f"Low={min(p.close for p in prices):.2f}"
                )
                await self.add_evidence(
                    session_id=session_id,
                    content=price_summary,
                    source_type="market_data",
                    source_id=company.ticker,
                    source_title=f"{company.ticker} Price (30d)",
                    relevance_score=0.7,
                    evidence_type="neutral",
                )
                count += 1

                # 2b. Financial metrics if available
                try:
                    financials = await market.get_financials(
                        company.ticker, limit=2
                    )
                    if financials:
                        fin_lines = [
                            f"{f['fiscal_year']}-{f.get('fiscal_period', 'FY')}: "
                            f"{f.get('metric_name', '?')} = {f.get('metric_value', 'N/A')}"
                            for f in financials[:10]
                        ]
                        if fin_lines:
                            await self.add_evidence(
                                session_id=session_id,
                                content=f"Financial metrics for {company.ticker}:\n" + "\n".join(fin_lines),
                                source_type="market_data",
                                source_id=company.ticker,
                                source_title=f"{company.ticker} Financials",
                                relevance_score=0.8,
                                evidence_type="neutral",
                            )
                            count += 1
                except Exception:
                    pass  # Financial data may not be available
            except Exception:
                pass  # Company or market data may not be available

        return {
            "session_id": str(session_id),
            "evidences_added": count,
            "searched_queries": len(search_queries),
        }

    def _classify_evidence(self, content: str, query: str) -> str:
        """Simple heuristic to classify evidence type.

        V1: keyword-based. V2+ will use LLM for nuanced classification.
        """
        content_lower = content.lower()
        query_lower = query.lower()

        # Extract positive/negative signal words
        positive_words = {"growth", "increase", "profit", "record", "strong", "positive",
                         "growth", "expanded", "leadership", "advantage", "opportunity"}
        negative_words = {"decline", "decrease", "loss", "risk", "threat", "weak",
                         "decline", "challenge", "uncertainty", "regulation", "competition"}

        pos_count = sum(1 for w in positive_words if w in content_lower)
        neg_count = sum(1 for w in negative_words if w in content_lower)

        if pos_count > neg_count + 1:
            return "supporting"
        elif neg_count > pos_count + 1:
            return "opposing"
        return "neutral"
