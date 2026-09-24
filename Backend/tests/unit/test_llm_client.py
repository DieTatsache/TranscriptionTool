import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sonora.ai.llm import LLMBadResponse, LLMMessage, LLMUnavailable, OllamaClient

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}
MESSAGES = [LLMMessage("system", "rules"), LLMMessage("user", "question")]


def client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> OllamaClient:
    options: dict[str, Any] = {
        "context_tokens": 16384,
        "timeout_seconds": 30,
        "temperature": 0.2,
        "keep_alive": "5m",
        "max_concurrency": 1,
    }
    options.update(kwargs)
    return OllamaClient(
        "http://ollama:11434/", "gemma3:12b", transport=httpx.MockTransport(handler), **options
    )


def reply(content: str, **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}, **extra})


async def test_sends_a_schema_constrained_chat_request() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://ollama:11434/api/chat"
        seen.append(json.loads(request.content))
        return reply('{"answer": "42"}')

    llm = client(handler, think=False)
    assert await llm.complete_json(MESSAGES, SCHEMA, temperature=0.0, max_tokens=100) == {
        "answer": "42"
    }
    body = seen[0]
    assert body["model"] == "gemma3:12b"
    assert body["stream"] is False
    assert body["format"] == SCHEMA
    assert body["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "question"},
    ]
    assert body["options"] == {"temperature": 0.0, "num_ctx": 16384, "num_predict": 100}
    assert body["keep_alive"] == "5m"
    assert body["think"] is False
    await llm.aclose()


async def test_think_and_num_predict_are_omitted_by_default() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return reply("{}")

    await client(handler).complete_json(MESSAGES, SCHEMA)
    assert "think" not in seen[0]
    assert seen[0]["options"] == {"temperature": 0.2, "num_ctx": 16384}


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={"error": "model not found"}), LLMUnavailable),
        (httpx.Response(503), LLMUnavailable),
        (httpx.Response(429), LLMUnavailable),
        (httpx.Response(400, json={"error": "bad schema"}), LLMBadResponse),
        (httpx.Response(200, text="not json"), LLMBadResponse),
        (httpx.Response(200, json={"unexpected": True}), LLMBadResponse),
        (reply("not json at all"), LLMBadResponse),
        (reply("[1, 2, 3]"), LLMBadResponse),
        (reply('{"answer": "cut', done_reason="length"), LLMBadResponse),
    ],
)
async def test_maps_failures(response: httpx.Response, error: type[Exception]) -> None:
    with pytest.raises(error):
        await client(lambda _r: response).complete_json(MESSAGES, SCHEMA)


@pytest.mark.parametrize("exception", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_transport_errors_mean_unavailable(exception: Exception) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(LLMUnavailable):
        await client(handler).complete_json(MESSAGES, SCHEMA)


@pytest.mark.parametrize(
    ("response", "available"),
    [
        (httpx.Response(200, json={"models": [{"name": "gemma3:12b"}]}), True),
        (httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]}), False),
        (httpx.Response(500), False),
        (httpx.Response(200, text="oops"), False),
    ],
)
async def test_is_available(response: httpx.Response, available: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return response

    assert await client(handler).is_available() is available


async def test_latest_tag_counts_as_available() -> None:
    llm = OllamaClient(
        "http://x",
        "mistral",
        context_tokens=2048,
        timeout_seconds=5,
        temperature=0,
        keep_alive="1m",
        max_concurrency=1,
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"models": [{"name": "mistral:latest"}]})
        ),
    )
    assert await llm.is_available()
