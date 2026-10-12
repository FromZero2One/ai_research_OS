"""Research Planner — generates structured research plans using LLM."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from core.adapters.llm import create_llm
from core.interfaces import LLM, LLMMessage
from core.logging import logger

RESEARCH_PLAN_SYSTEM_PROMPT = (
    "You are a professional investment research analyst. "
    "Given a research question, create a structured research plan.\n\n"
    "Your plan must include:\n"
    "1. **research_goal**: A clear restatement of what needs to be researched\n"
    "2. **sub_questions**: 3-6 specific questions that must be answered "
    "to reach a conclusion. Each sub-question should have a unique ID, "
    "priority level (high/medium/low), and status (pending/in_progress/completed)\n"
    "3. **analysis_dimensions**: Key dimensions to analyze (e.g., financial "
    "health, competitive position, industry trends, management quality, "
    "valuation, risks)\n"
    "4. **data_requirements**: What specific data points are needed\n"
    "5. **suggested_sources**: Types of documents or data sources to consult"
    "\nRespond with valid JSON only, no markdown formatting."
)

PLAN_KEY = "research_plan"


class ResearchPlanner:
    """Generates structured research plans from questions using LLM."""

    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or create_llm()

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
            "research_goal, sub_questions (list of objects with id/text/priority/status), "
            "analysis_dimensions (list), data_requirements (list), suggested_sources (list)."
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
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
            if content.startswith("json"):
                content = content[4:].strip()
            plan = json.loads(content)
        except (json.JSONDecodeError, AttributeError):
            return {
                "research_goal": question,
                "sub_questions": [
                    {
                        "id": str(uuid4())[:8],
                        "text": question,
                        "priority": "medium",
                        "status": "pending",
                    }
                ],
                "analysis_dimensions": [
                    "Financial Analysis",
                    "Industry Analysis",
                    "Competitive Position",
                    "Risk Factors",
                ],
                "data_requirements": ["Revenue and earnings trends", "Market share data"],
                "suggested_sources": ["Annual reports", "Industry reports", "News"],
                "version": 1,
                "created_at": datetime.now().isoformat(),
            }

        # Transform sub_questions to ResearchPlanItem format
        raw_sq = plan.get("sub_questions", [])
        if raw_sq and isinstance(raw_sq, list) and isinstance(raw_sq[0], str):
            # Old format: just strings
            plan["sub_questions"] = [
                {
                    "id": str(uuid4())[:8],
                    "text": q,
                    "priority": "medium",
                    "status": "pending",
                }
                for q in raw_sq
            ]
        elif raw_sq and isinstance(raw_sq, list) and isinstance(raw_sq[0], dict):
            # New format or partially filled - ensure required fields
            enriched: list[dict] = []
            for sq in raw_sq:
                enriched.append(
                    {
                        "id": sq.get("id", str(uuid4())[:8]),
                        "text": sq.get("text", ""),
                        "priority": sq.get("priority", "medium"),
                        "status": sq.get("status", "pending"),
                    }
                )
            plan["sub_questions"] = enriched

        # Ensure required fields with defaults
        plan.setdefault("research_goal", question)
        plan.setdefault("data_requirements", plan.get("data_requirements", []))
        plan.setdefault("suggested_sources", plan.get("suggested_sources", []))
        plan.setdefault("version", plan.get("version", 1))
        plan.setdefault("created_at", plan.get("created_at", datetime.now().isoformat()))

        return plan

    async def generate_structured_thesis(
        self, thesis: str, decision: str, report_content: str
    ) -> dict:
        """Extract structured thesis fields via LLM."""
        prompt = f"""Based on this investment thesis and report, extract as JSON:
{{"bull_case": ["..."], "bear_case": ["..."], "key_drivers": ["..."], "risks": ["..."]}}

Decision: {decision}
Thesis: {thesis[:1500]}
Report: {report_content[:3000]}"""

        try:
            response = await self.llm.generate(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=1024,
            )
            result = json.loads(response.content)
            for key in ("bull_case", "bear_case", "key_drivers", "risks"):
                if key not in result or not isinstance(result[key], list):
                    result[key] = []
            return result
        except Exception:
            logger.warning("LLM structured thesis extraction failed, using fallback")
            return {
                "bull_case": [thesis[:200]] if thesis else [],
                "bear_case": [],
                "key_drivers": [],
                "risks": [],
            }
