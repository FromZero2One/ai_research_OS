"""Company Center service layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company.models import Company, CompanyTag
from core.exceptions import DuplicateError, NotFoundError
from core.event_service import EventLogger


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
        for field in ("description", "sector", "industry", "headquarters",
                       "founded_year", "employees", "website"):
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
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.tags))
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
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Company], int]:
        """Search companies with optional filters."""
        stmt = select(Company).options(selectinload(Company.tags))

        if query:
            stmt = stmt.where(
                Company.name.ilike(f"%{query}%")
                | Company.ticker.ilike(f"%{query}%")
            )
        if sector:
            stmt = stmt.where(Company.sector.ilike(f"%{sector}%"))
        if industry:
            stmt = stmt.where(Company.industry.ilike(f"%{industry}%"))

        # Count total
        count_stmt = stmt.with_only_columns(Company.id).order_by(None)
        total_result = await self.session.execute(count_stmt)
        total = len(total_result.all())

        stmt = stmt.offset(skip).limit(limit).order_by(Company.ticker)
        result = await self.session.execute(stmt)
        companies = list(result.scalars().all())

        # Filter by tag in Python (simple V1 approach)
        if tag:
            companies = [c for c in companies if any(t.tag == tag for t in c.tags)]
            total = len(companies)

        return companies, total

    async def update(self, company_id: UUID, data: dict) -> Company:
        company = await self.get(company_id)

        updatable = {"name", "description", "sector", "industry",
                      "headquarters", "founded_year", "employees",
                      "website", "is_active"}

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
