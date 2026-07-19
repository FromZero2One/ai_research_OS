"""LLM adapters — Ollama and OpenAI implementations."""

from __future__ import annotations

import json

import httpx

from core.config import settings
from core.interfaces import LLM, LLMMessage, LLMResponse


class OllamaLLM:
    """Ollama-based LLM adapter."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.OLLAMA_MODEL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": stream,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return LLMResponse(
            content=data["message"]["content"],
            model=self._model,
            usage=data.get("usage"),
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: float = 0.3,
    ) -> dict:
        system_msg = messages[0].content if messages and messages[0].role == "system" else ""
        format_instruction = (
            f"\n\nYou MUST respond with valid JSON conforming to this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        updated_messages = [
            LLMMessage(role="system", content=system_msg + format_instruction),
            *(m for m in messages if m.role != "system"),
        ]
        resp = await self.generate(updated_messages, temperature=temperature)
        return json.loads(resp.content)


class OpenAILLM:
    """OpenAI-compatible LLM adapter."""

    def __init__(
        self,
        api_key: str = settings.OPENAI_API_KEY,
        model: str = settings.OPENAI_MODEL,
    ) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> LLMResponse:
        import openai

        client = openai.AsyncOpenAI(api_key=self._api_key)
        resp = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=self._model,
            usage=resp.usage.model_dump() if resp.usage else None,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: float = 0.3,
    ) -> dict:
        import openai

        client = openai.AsyncOpenAI(api_key=self._api_key)
        resp = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")


def create_llm() -> LLM:
    """Factory — returns the configured LLM adapter."""
    if settings.LLM_PROVIDER == "openai":
        return OpenAILLM()
    return OllamaLLM()
