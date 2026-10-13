"""LLM adapters — Ollama and OpenAI implementations."""

from __future__ import annotations

import asyncio
import json
from typing import Literal, cast

import httpx
from openai.types.chat import ChatCompletionMessageParam

from core.config import settings
from core.interfaces import LLM, LLMMessage, LLMResponse
from core.llm_usage import record_usage


def _sdk_messages(messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
    """Convert internal LLMMessage list to OpenAI SDK chat message params."""
    return [
        cast(ChatCompletionMessageParam, {"role": m.role, "content": m.content}) for m in messages
    ]


# Shared httpx client with connection pooling — avoids TCP handshake per call.
# Cached per event loop (see embedding.py for why cross-loop reuse is unsafe).
_shared_client: httpx.AsyncClient | None = None
_shared_client_loop: asyncio.AbstractEventLoop | None = None


async def _get_client() -> httpx.AsyncClient:
    global _shared_client, _shared_client_loop
    loop = asyncio.get_running_loop()
    if _shared_client is None or _shared_client_loop is not loop:
        old = _shared_client
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
            proxy=None,  # explicit — avoid env proxy leaks
        )
        _shared_client_loop = loop
        if old is not None:
            try:
                await old.aclose()
            except Exception:
                pass
    return _shared_client


class OllamaLLM:
    """Ollama-based LLM adapter using /api/chat (preserves multi-turn context)."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.OLLAMA_MODEL,
        think: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # qwen3-family models default to a long internal "thinking" chain that
        # can consume the whole token budget and return an empty final answer.
        # Disable it by default; callers can opt into reasoning with think=True.
        self._think = think

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
        # Use /api/chat — supports multi-turn, preserves all messages
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "think": self._think,
            "stream": stream,
        }

        client = await _get_client()
        resp = await client.post(
            f"{self._base_url}/api/chat",
            json={**payload, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()

        # Ollama 原生 /api/chat 的用量在顶层 prompt_eval_count/eval_count，
        # 归一化为 OpenAI 风格的 usage 字典
        usage = data.get("usage")
        if usage is None and (data.get("prompt_eval_count") or data.get("eval_count")):
            prompt_n = data.get("prompt_eval_count") or 0
            completion_n = data.get("eval_count") or 0
            usage = {
                "prompt_tokens": prompt_n,
                "completion_tokens": completion_n,
                "total_tokens": prompt_n + completion_n,
            }
        record_usage(self._model, usage)

        return LLMResponse(
            content=data["message"]["content"],
            model=self._model,
            usage=usage,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: float = 0.3,
    ) -> dict:
        """Generate structured JSON output.

        Appends JSON schema to the last user message and parses response.
        Note: /api/chat does not natively support structured output — this
        uses prompt-based enforcement + json.loads parsing.
        """
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
        try:
            return json.loads(resp.content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Ollama returned invalid JSON for structured output: {e}\n"
                f"Raw response: {resp.content[:200]}"
            )


class OpenAILLM:
    """OpenAI-compatible LLM adapter."""

    def __init__(
        self,
        api_key: str = settings.OPENAI_API_KEY,
        model: str = settings.OPENAI_MODEL,
        base_url: str = settings.OPENAI_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

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

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = await client.chat.completions.create(
            model=self._model,
            messages=_sdk_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        usage = resp.usage.model_dump() if resp.usage else None
        record_usage(self._model, usage)
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=self._model,
            usage=usage,
        )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: float = 0.3,
    ) -> dict:
        import openai

        system_msg = messages[0].content if messages and messages[0].role == "system" else ""
        format_hint = (
            f"\n\nRespond with JSON conforming to this schema:\n{json.dumps(schema, indent=2)}"
        )
        updated = [
            LLMMessage(role="system", content=system_msg + format_hint),
            *(m for m in messages if m.role != "system"),
        ]

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = await client.chat.completions.create(
            model=self._model,
            messages=_sdk_messages(updated),
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        usage = resp.usage.model_dump() if resp.usage else None
        record_usage(self._model, usage)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"OpenAI returned invalid JSON for structured output: {e}\n"
                f"Raw response: {raw[:200]}"
            )


def create_llm(tier: Literal["light", "heavy"] = "heavy") -> LLM:
    """Factory — returns the configured LLM adapter for the given task tier.

    light：分类/抽取等高频轻任务（默认本地小模型，零 API 成本）；
    heavy：报告/晨报等重任务，未配置时跟随主 LLM_PROVIDER。
    """
    if tier == "light":
        provider = settings.LLM_TIER_LIGHT_PROVIDER
        model = settings.LLM_TIER_LIGHT_MODEL
    else:
        provider = settings.LLM_TIER_HEAVY_PROVIDER
        model = settings.LLM_TIER_HEAVY_MODEL

    effective_provider = provider or settings.LLM_PROVIDER
    if effective_provider == "openai":
        return OpenAILLM(model=model) if model else OpenAILLM()
    return OllamaLLM(model=model) if model else OllamaLLM()
