"""AI Center service — LLM orchestration, prompt management, summarization."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.models import AIWorkflow, PromptTemplate
from core.adapters.llm import create_llm
from core.event_service import EventLogger
from core.exceptions import NotFoundError
from core.interfaces import LLMMessage


class AIService:
    """AI capability management — prompts, generation, summarization, extraction."""

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
            conditions = (PromptTemplate.id == template_id) | (PromptTemplate.name == template_id)
        except ValueError:
            conditions = PromptTemplate.name == template_id
        result = await self.session.execute(
            select(PromptTemplate).where(conditions)
        )
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
            select(PromptTemplate).where(PromptTemplate.is_active == True)
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
        if variables:
            system = system.format(**variables)
            user_prompt = user_prompt.format(**variables)

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

    async def summarize(
        self,
        text: str,
        max_length: int = 500,
        format_: str = "paragraph",
    ) -> dict:
        """Summarize a text using the summarization prompt."""
        system = "You are a research analyst. Summarize the following text concisely."
        user = (
            f"Summarize the following text in {format_} format "
            f"(max {max_length} words):\n\n{text}"
        )

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ]

        start = time.time()
        result = await self.llm.generate(messages=messages, temperature=0.3)
        elapsed = (time.time() - start) * 1000

        return {
            "content": result.content,
            "model": result.model,
            "usage": result.usage,
            "processing_time_ms": round(elapsed, 2),
        }

    async def extract(
        self,
        text: str,
        schema: dict,
    ) -> dict:
        """Extract structured data from text using JSON schema."""
        system = "You extract structured information from text. Respond with valid JSON."
        user = (
            f"Extract the following information from the text.\n"
            f"Schema:\n{schema}\n\nText:\n{text}"
        )

        messages = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ]

        start = time.time()
        result = await self.llm.generate_structured(
            messages=messages, schema=schema, temperature=0.1
        )
        elapsed = (time.time() - start) * 1000

        return {
            "data": result,
            "model": self.llm.model_name,
            "processing_time_ms": round(elapsed, 2),
        }

    # ── Workflow Management ──────────────────────────────────────

    async def create_workflow(self, **kwargs) -> AIWorkflow:
        workflow = AIWorkflow(**kwargs)
        self.session.add(workflow)
        await self.session.flush()
        await self.session.refresh(workflow)
        return workflow

    async def execute_workflow(
        self, workflow_id: str, input_data: dict
    ) -> dict:
        """Execute a multi-step AI workflow.

        V1: Simple sequential step execution.
        V2+: LangGraph-based DAG orchestration.
        """
        result = await self.session.execute(
            select(AIWorkflow).where(AIWorkflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise NotFoundError("AIWorkflow", workflow_id)

        steps = workflow.steps or []
        if not steps:
            return {"status": "empty", "output": None}

        context = input_data.copy()
        results = []

        for step in steps:
            step_type = step.get("type", "llm")
            if step_type == "llm":
                messages = [
                    LLMMessage(
                        role="system",
                        content=step.get("system", ""),
                    ),
                    LLMMessage(
                        role="user",
                        content=step.get("prompt", "").format(**context),
                    ),
                ]
                resp = await self.llm.generate(messages=messages)
                context[step.get("output_key", "result")] = resp.content
                results.append({"step": step.get("name"), "output": resp.content})
            elif step_type == "transform":
                context[step.get("output_key", "result")] = step.get("transform", "")

        return {
            "status": "completed",
            "workflow": workflow.name,
            "steps": results,
            "final_context": context,
        }
