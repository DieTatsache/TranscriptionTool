"""LLM client.

Talks to Ollama's native ``/api/chat`` endpoint, which (unlike the OpenAI-compatible one)
lets us set the context window per request and constrain the output to a JSON schema.
Everything else in the app depends only on the ``LLMClient`` protocol.
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMUnavailable(LLMError):
    """Transient: server unreachable, overloaded, timed out or model missing."""


class LLMBadResponse(LLMError):
    """The model answered, but not with usable JSON (retrying may help)."""


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    async def complete_json(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    async def is_available(self) -> bool: ...

    async def aclose(self) -> None: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        context_tokens: int,
        timeout_seconds: float,
        temperature: float,
        keep_alive: str,
        max_concurrency: int,
        think: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._context_tokens = context_tokens
        self._temperature = temperature
        self._keep_alive = keep_alive
        self._think = think
        # Local model servers handle few requests at once; queue here instead of overloading.
        self._slots = asyncio.Semaphore(max_concurrency)
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    async def complete_json(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": self._temperature if temperature is None else temperature,
            "num_ctx": self._context_tokens,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "format": schema,
            "options": options,
            "keep_alive": self._keep_alive,
        }
        if self._think is not None:
            body["think"] = self._think

        async with self._slots:
            try:
                response = await self._http.post("/api/chat", json=body)
            except httpx.TimeoutException as exc:
                raise LLMUnavailable("LLM request timed out") from exc
            except httpx.HTTPError as exc:
                raise LLMUnavailable(f"LLM server unreachable: {type(exc).__name__}") from exc

        if response.status_code == 404:
            raise LLMUnavailable(f"Model {self.model!r} is not available (run `ollama pull`)")
        if response.status_code in (408, 429) or response.status_code >= 500:
            raise LLMUnavailable(f"LLM server returned HTTP {response.status_code}")
        if response.status_code >= 400:
            raise LLMBadResponse(f"LLM server rejected the request (HTTP {response.status_code})")

        try:
            data = response.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMBadResponse("Malformed LLM server response") from exc
        if data.get("done_reason") == "length":
            raise LLMBadResponse("LLM output was truncated")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMBadResponse("LLM output is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMBadResponse("LLM output is not a JSON object")
        logger.debug(
            "llm call ok: prompt_tokens=%s output_tokens=%s",
            data.get("prompt_eval_count"),
            data.get("eval_count"),
        )
        return parsed

    async def is_available(self) -> bool:
        """True if the server answers and has the configured model."""
        try:
            response = await self._http.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            names = {m.get("name") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        return self.model in names or f"{self.model}:latest" in names

    async def aclose(self) -> None:
        await self._http.aclose()
