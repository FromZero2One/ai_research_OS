"""Company Center service layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company.models import Company, CompanyTag
from core.event_service import EventLogger
from core.exceptions import DuplicateError, NotFoundError


class CompanyService:
    """Business logic for company management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    async def create(self, ticker: str, name: str, **kwargs) -> Company:
        """Create a company with optional tags."""
        # Check uniqueness
        existing = await self.session.execute(
            select(Company).where(Company.ticker == ticker.upper())
        )
        if existing.scalar_one_or_none():
            raise DuplicateError("Company", ticker)

        company = Company(ticker=ticker.upper(), name=name)
        for field in (
            "description",
            "sector",
            "industry",
            "headquarters",
            "founded_year",
            "employees",
            "website",
            "priority",
            "target_price",
            "reason",
        ):
            if field in kwargs and kwargs[field] is not None:
                setattr(company, field, kwargs[field])

        # Handle tags
        tags_in = kwargs.pop("tags", [])
        for tag_name in tags_in:
            company.tags.append(CompanyTag(tag=tag_name))

        self.session.add(company)
        await self.session.flush()
        await self.session.refresh(company, attribute_names=["tags"])

        await self.events.record(
            source="company",
            event_type="company.created",
            entity_type="company",
            entity_id=str(company.id),
            payload={"ticker": company.ticker, "name": company.name},
        )
        return company

    async def get(self, company_id: UUID) -> Company:
        result = await self.session.execute(
            select(Company).where(Company.id == company_id).options(selectinload(Company.tags))
        )
        company = result.scalar_one_or_none()
        if not company:
            raise NotFoundError("Company", str(company_id))
        return company

    async def get_by_ticker(self, ticker: str) -> Company | None:
        result = await self.session.execute(
            select(Company)
            .where(Company.ticker == ticker.upper())
            .options(selectinload(Company.tags))
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        tag: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Company], int]:
        """Search companies with optional filters."""
        stmt = select(Company).options(selectinload(Company.tags))

        if query:
            stmt = stmt.where(Company.name.ilike(f"%{query}%") | Company.ticker.ilike(f"%{query}%"))
        if sector:
            stmt = stmt.where(Company.sector.ilike(f"%{sector}%"))
        if industry:
            stmt = stmt.where(Company.industry.ilike(f"%{industry}%"))
        if tag:
            from company.models import CompanyTag

            stmt = stmt.join(CompanyTag, CompanyTag.company_id == Company.id).where(
                CompanyTag.tag == tag
            )
        if is_active is not None:
            stmt = stmt.where(Company.is_active.is_(is_active))

        # Count total
        count_stmt = stmt.with_only_columns(func.count(Company.id)).order_by(None)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset(skip).limit(limit).order_by(Company.ticker)
        result = await self.session.execute(stmt)
        companies = list(result.scalars().all())

        return companies, total

    async def update(self, company_id: UUID, data: dict) -> Company:
        company = await self.get(company_id)

        updatable = {
            "name",
            "description",
            "sector",
            "industry",
            "headquarters",
            "founded_year",
            "employees",
            "website",
            "is_active",
            "priority",
            "target_price",
            "reason",
        }

        for key, value in data.items():
            if key in updatable and value is not None:
                setattr(company, key, value)

        # Update tags if provided
        if "tags" in data and data["tags"] is not None:
            company.tags.clear()
            for tag_name in data["tags"]:
                company.tags.append(CompanyTag(tag=tag_name))

        await self.session.flush()
        await self.session.refresh(company)
        await self.events.record(
            source="company",
            event_type="company.updated",
            entity_type="company",
            entity_id=str(company.id),
            payload={"changes": list(data.keys())},
        )
        return company

    async def delete(self, company_id: UUID) -> None:
        company = await self.get(company_id)
        await self.session.delete(company)
        await self.events.record(
            source="company",
            event_type="company.deleted",
            entity_type="company",
            entity_id=str(company.id),
        )

    # ── Thesis ─────────────────────────────────────────────────────────

    async def get_thesis(self, ticker: str) -> dict | None:
        """Get current manual thesis for a company (from EventLog override)."""
        from sqlalchemy import desc

        from core.event_log import EventLog

        company = await self.get_by_ticker(ticker)
        if not company:
            return None

        # Manual thesis override in EventLog
        result = await self.session.execute(
            select(EventLog)
            .where(
                EventLog.source == "company",
                EventLog.event_type == "thesis.updated",
                EventLog.entity_id == ticker.upper(),
            )
            .order_by(desc(EventLog.occurred_at))
            .limit(1)
        )
        thesis_log = result.scalar_one_or_none()

        if thesis_log and thesis_log.payload:
            return {
                "ticker": ticker.upper(),
                "company_name": company.name,
                "thesis": thesis_log.payload.get("thesis"),
                "decision": thesis_log.payload.get("decision"),
                "confidence": thesis_log.payload.get("confidence"),
                "updated_at": (
                    thesis_log.occurred_at.isoformat() if thesis_log.occurred_at else None
                ),
            }

        return {
            "ticker": ticker.upper(),
            "company_name": company.name,
        }

    async def get_workspace(self, ticker: str) -> dict | None:
        """Aggregated company workspace — manual thesis only (research removed)."""
        company = await self.get_by_ticker(ticker)
        if not company:
            return None

        # Latest thesis
        thesis = await self.get_thesis(ticker)

        return {
            "ticker": ticker.upper(),
            "company_name": company.name,
            "company_id": str(company.id),
            "thesis": thesis,
            "recent_research": [],
            "evidence_summary": {"supporting": 0, "opposing": 0, "neutral": 0},
        }
