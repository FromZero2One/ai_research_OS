"""LLM adapters — Ollama and OpenAI implementations."""

from __future__ import annotations

import json
import os

# Strip proxy env vars that interfere with local Ollama connections.
# Must run BEFORE any httpx client is created, as httpx caches proxy
# config from env vars at import time.
for _var in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
              "https_proxy", "HTTPS_PROXY", "ftp_proxy", "FTP_PROXY"):
    os.environ.pop(_var, None)
os.environ["no_proxy"] = "localhost,127.0.0.0/8,::1"
os.environ["NO_PROXY"] = "localhost,127.0.0.0/8,::1"

import httpx
from httpx import AsyncHTTPTransport

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
        # Convert chat messages to prompt for Ollama /api/generate
        system_msgs = [m.content for m in messages if m.role == "system"]
        user_msgs = [m.content for m in messages if m.role == "user"]
        prompt_parts = []
        if system_msgs:
            prompt_parts.append(system_msgs[0])
        if user_msgs:
            prompt_parts.append(user_msgs[0])
        prompt = "\n\n".join(prompt_parts) + "\n\nGenerate your response now:"

        payload = {
            "model": self._model,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": stream,
        }
        # Use subprocess curl to bypass proxy issues + combine all streaming lines
        import asyncio as _asyncio
        import json as _json
        import os as _os
        _os.environ.pop("all_proxy", None)
        _os.environ.pop("ALL_PROXY", None)
        _cmd = [
            "curl", "--noproxy", "*", "-s", "--max-time", "120",
            "-H", "Content-Type: application/json",
            "-d", _json.dumps({**payload, "stream": False}),
            f"{self._base_url}/api/generate",
        ]
        _proc = await _asyncio.create_subprocess_exec(
            *_cmd, stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
        )
        _stdout, _stderr = await _proc.communicate()
        if _proc.returncode != 0:
            raise RuntimeError(f"Ollama request failed (exit={_proc.returncode}): {_stderr.decode()[:200]}")
        # Debug: write raw response to /tmp/llm_debug.log
        with open("/tmp/llm_debug.log", "a") as _f:
            _f.write(f"\n--- LLM Response ({len(_stdout)} bytes) ---\n{_stdout.decode()[:1000]}\n")
        # The /api/generate endpoint with stream=false returns a single JSON object
        data = _json.loads(_stdout.decode().strip())
        return LLMResponse(
            content=data["response"],
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

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
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
