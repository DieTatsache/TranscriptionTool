"""LLM client.

Talks to Ollama's native ``/api/chat`` endpoint, which (unlike the OpenAI-compatible one)
lets us set the context window per request and constrain the output to a JSON schema.
Everything else in the app depends only on the ``LLMClient`` protocol.

Reasoning ("thinking") is chosen per call. Thinking calls use the model's own recommended
sampling (from its Modelfile); all other calls use the configured ``Sampling``, optionally
adjusted per call. ``think`` is always sent explicitly, because models such as Qwen3.5
think by default.
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


@dataclass(frozen=True, slots=True)
class Sampling:
    """Decoding parameters for non-thinking calls; ``None`` keeps the model's default."""

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    presence_penalty: float | None = None

    def options(self) -> dict[str, Any]:
        values = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "presence_penalty": self.presence_penalty,
        }
        return {name: value for name, value in values.items() if value is not None}

    def merged(self, override: "Sampling | None") -> dict[str, Any]:
        """These options with the fields set in ``override`` replaced."""
        return self.options() | (override.options() if override else {})


class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    async def complete_json(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        think: bool = False,
        max_tokens: int | None = None,
        sampling: Sampling | None = None,
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
        max_concurrency: int,
        keep_alive: str | None = None,
        sampling: Sampling | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._context_tokens = context_tokens
        self._keep_alive = keep_alive
        self._sampling = sampling or Sampling()
        # Cleared when the server reports that the model can't think (e.g. gemma3).
        self._model_thinks = True
        # Local model servers handle few requests at once; queue here instead of overloading.
        self._slots = asyncio.Semaphore(max_concurrency)
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    async def complete_json(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        think: bool = False,
        max_tokens: int | None = None,
        sampling: Sampling | None = None,
    ) -> dict[str, Any]:
        """``sampling`` adjusts the configured sampling of non-thinking calls."""
        think = think and self._model_thinks
        options = {} if think else self._sampling.merged(sampling)
        response = await self._post(
            messages, schema, think=think, options=options, max_tokens=max_tokens
        )
        if think and _lacks_thinking(response):
            logger.warning("model %r does not support thinking; continuing without", self._model)
            self._model_thinks = False
            options = self._sampling.merged(sampling)
            response = await self._post(
                messages, schema, think=False, options=options, max_tokens=max_tokens
            )

        if response.status_code == 404:
            raise LLMUnavailable(f"Model {self._model!r} is not available (run `ollama pull`)")
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
            "llm call ok: think=%s prompt_tokens=%s output_tokens=%s",
            think,
            data.get("prompt_eval_count"),
            data.get("eval_count"),
        )
        return parsed

    async def _post(
        self,
        messages: Sequence[LLMMessage],
        schema: dict[str, Any],
        *,
        think: bool,
        options: dict[str, Any],
        max_tokens: int | None,
    ) -> httpx.Response:
        # num_ctx must not vary between calls: a different value makes Ollama reload the model.
        options = {"num_ctx": self._context_tokens, **options}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "format": schema,
            "options": options,
        }
        keep_alive = self._keep_alive
        if keep_alive is not None:
            # Ollama reads a number as seconds and a string as a Go duration ("10m").
            body["keep_alive"] = int(keep_alive) if keep_alive.lstrip("-").isdigit() else keep_alive
        if self._model_thinks:
            body["think"] = think  # explicit "false" too: Qwen3.5 thinks unless told otherwise

        async with self._slots:
            try:
                return await self._http.post("/api/chat", json=body)
            except httpx.TimeoutException as exc:
                raise LLMUnavailable("LLM request timed out") from exc
            except httpx.HTTPError as exc:
                raise LLMUnavailable(f"LLM server unreachable: {type(exc).__name__}") from exc

    async def is_available(self) -> bool:
        """True if the server answers and has the configured model."""
        try:
            response = await self._http.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            names = {m.get("name") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        return self._model in names or f"{self._model}:latest" in names

    async def aclose(self) -> None:
        await self._http.aclose()


def _lacks_thinking(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        error = response.json().get("error", "")
    except (ValueError, AttributeError):
        return False
    return isinstance(error, str) and "does not support thinking" in error
