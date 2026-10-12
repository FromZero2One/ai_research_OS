"""Evidence CRUD — add, list, remove, and classify."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from core.interfaces import LLMMessage
from core.logging import logger
from research.models import ResearchEvidence

# LLM 批量分类的输出 schema（evidence_type + 一句话理由 + 自评置信度）
_CLASSIFY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "evidence_type": {
                        "type": "string",
                        "enum": ["supporting", "opposing", "neutral"],
                    },
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["idx", "evidence_type", "confidence"],
            },
        }
    },
    "required": ["classifications"],
}

_CLASSIFY_SYSTEM_PROMPT = (
    "你是一名严谨的投资研究助理。根据研究问题，判断每条证据对结论的方向：\n"
    "- supporting：支持看多/看好的结论（增长、盈利改善、竞争优势、政策利好等）\n"
    "- opposing：反对或预警信号（业绩暴雷、商誉减值、大股东质押、诉讼、"
    "行业下行、应收暴增、现金流恶化等金融语境的反向信号）\n"
    "- neutral：中性事实（单纯行情数据、与方向无关的陈述）\n"
    "要求：逐条判断，不遗漏；confidence 为 0-1 的自评置信度；"
    "输出 JSON，格式为 {\"classifications\": [{\"idx\": 0, "
    "\"evidence_type\": \"...\", \"reason\": \"...\", \"confidence\": 0.9}]}，"
    "idx 对应输入的证据编号。"
)


class EvidenceService:
    """Manage research evidence items."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    async def add(self, session_id: uuid.UUID, **kwargs) -> ResearchEvidence:
        # Verify session exists
        from research.models import ResearchSession

        result = await self.session.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise NotFoundError("ResearchSession", str(session_id))

        evidence = ResearchEvidence(session_id=session_id, **kwargs)
        self.session.add(evidence)

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

    async def list(self, session_id: uuid.UUID) -> list[ResearchEvidence]:
        result = await self.session.execute(
            select(ResearchEvidence)
            .where(ResearchEvidence.session_id == session_id)
            .order_by(ResearchEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def remove(self, evidence_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(ResearchEvidence).where(ResearchEvidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        if not evidence:
            raise NotFoundError("ResearchEvidence", str(evidence_id))
        await self.session.delete(evidence)

    @staticmethod
    def classify(content: str, query: str) -> str:
        """Simple heuristic to classify evidence type.

        V1: keyword-based. V2+ will use LLM for nuanced classification.
        """
        content_lower = content.lower()
        positive_words = {
            "growth",
            "increase",
            "profit",
            "record",
            "strong",
            "positive",
            "expanded",
            "leadership",
            "advantage",
            "opportunity",
        }
        negative_words = {
            "decline",
            "decrease",
            "loss",
            "risk",
            "threat",
            "weak",
            "challenge",
            "uncertainty",
            "regulation",
            "competition",
        }

        pos_count = sum(1 for w in positive_words if w in content_lower)
        neg_count = sum(1 for w in negative_words if w in content_lower)

        if pos_count > neg_count + 1:
            return "supporting"
        elif neg_count > pos_count + 1:
            return "opposing"
        return "neutral"

    async def classify_batch(
        self,
        evidences: list[ResearchEvidence],
        question: str,
    ) -> None:
        """批量 LLM 分类：就地覆盖 evidence_type，失败静默降级保留 keyword 初值。

        GatherService 先用关键词 classify() 写入初值，收集完成后调本方法
        用 LLM 结果覆盖（settings.EVIDENCE_CLASSIFIER 控制，非 llm 直接跳过）。
        """
        if not evidences:
            return
        from core.config import settings

        if settings.EVIDENCE_CLASSIFIER != "llm":
            return

        from core.adapters.llm import create_llm

        items = "\n".join(
            f"[{i}] {ev.content[:400]}" for i, ev in enumerate(evidences)
        )
        try:
            llm = create_llm(tier="light")
            result = await llm.generate_structured(
                messages=[
                    LLMMessage(role="system", content=_CLASSIFY_SYSTEM_PROMPT),
                    LLMMessage(
                        role="user",
                        content=f"研究问题：{question}\n\n证据列表：\n{items}",
                    ),
                ],
                schema=_CLASSIFY_SCHEMA,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("LLM evidence classification failed, keeping keyword labels: %s", e)
            return

        valid_types = {"supporting", "opposing", "neutral"}
        updated = 0
        for c in result.get("classifications", []):
            idx = c.get("idx")
            etype = c.get("evidence_type")
            if not isinstance(idx, int) or not (0 <= idx < len(evidences)):
                continue
            if etype not in valid_types:
                continue
            ev = evidences[idx]
            ev.evidence_type = etype
            ev.classification_source = "llm"
            conf = c.get("confidence")
            ev.classification_confidence = (
                round(float(conf), 2) if isinstance(conf, (int, float)) else None
            )
            updated += 1

        await self.events.record(
            source="research",
            event_type="evidence.classified",
            entity_type="research_evidence_batch",
            payload={
                "question": question[:200],
                "total": len(evidences),
                "llm_updated": updated,
                "keyword_fallback": len(evidences) - updated,
            },
        )
        logger.info("Evidence classification: %d/%d updated by LLM", updated, len(evidences))
