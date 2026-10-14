"""AI Center service — prompt management + template execution."""

from __future__ import annotations

import time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.models import PromptTemplate
from core.adapters.llm import create_llm
from core.event_service import EventLogger
from core.exceptions import NotFoundError
from core.interfaces import LLMMessage


def apply_variables(text: str, variables: dict) -> str:
    """Replace ``{name}`` placeholders without breaking literal braces.

    Unlike ``str.format(**variables)`` this never raises on missing keys or
    literal ``{``/``}`` characters in the template (e.g. JSON examples), and
    leaves unknown placeholders intact instead of crashing the request.
    """
    if not variables or not text:
        return text
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text


class AIService:
    """AI capability management — prompt templates + template execution."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.llm = create_llm()

    # ── Prompt Templates ──────────────────────────────────────────

    async def create_template(self, **kwargs) -> PromptTemplate:
        template = PromptTemplate(**kwargs)
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def get_template(self, template_id: str) -> PromptTemplate:
        # Try UUID first, then name
        import uuid

        try:
            uuid.UUID(template_id)
            conditions = or_(
                PromptTemplate.id == template_id,
                PromptTemplate.name == template_id,
            )
        except ValueError:
            conditions = PromptTemplate.name == template_id
        result = await self.session.execute(select(PromptTemplate).where(conditions))
        template = result.scalar_one_or_none()
        if not template:
            raise NotFoundError("PromptTemplate", template_id)
        return template

    async def update_template(self, template_id: str, **kwargs) -> PromptTemplate:
        template = await self.get_template(template_id)
        for key, val in kwargs.items():
            if val is not None:
                setattr(template, key, val)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def delete_template(self, template_id: str) -> None:
        template = await self.get_template(template_id)
        await self.session.delete(template)
        await self.session.flush()

    async def list_templates(self) -> list[PromptTemplate]:
        result = await self.session.execute(
            select(PromptTemplate).where(PromptTemplate.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def generate(
        self,
        prompt_name: str,
        variables: dict | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Execute a prompt template with variables."""
        template = await self.get_template(prompt_name)

        # Build messages
        system = template.system_prompt or ""
        user_prompt = template.user_prompt_template or ""

        # Apply variables
        system = apply_variables(system, variables or {})
        user_prompt = apply_variables(user_prompt, variables or {})

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user_prompt),
        ]

        start = time.time()
        result = await self.llm.generate(
            messages=messages,
            temperature=temperature or template.temperature or 0.7,
            max_tokens=template.max_tokens or 4096,
        )
        elapsed = (time.time() - start) * 1000

        await self.events.record(
            source="ai",
            event_type="llm.generate",
            entity_type="prompt",
            entity_id=str(template.id),
            payload={
                "prompt_name": prompt_name,
                "model": result.model,
                "elapsed_ms": round(elapsed),
            },
        )

        return {
            "content": result.content,
            "model": result.model,
            "usage": result.usage,
            "processing_time_ms": round(elapsed, 2),
        }
