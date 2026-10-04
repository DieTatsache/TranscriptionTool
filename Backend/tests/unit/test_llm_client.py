import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sonora.ai.llm import LLMBadResponse, LLMMessage, LLMUnavailable, OllamaClient, Sampling

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}
MESSAGES = [LLMMessage("system", "rules"), LLMMessage("user", "question")]
SAMPLING = Sampling(temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5)


def client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> OllamaClient:
    options: dict[str, Any] = {
        "context_tokens": 16384,
        "timeout_seconds": 30,
        "keep_alive": "5m",
        "max_concurrency": 1,
        "sampling": SAMPLING,
    }
    options.update(kwargs)
    return OllamaClient(
        "http://ollama:11434/", "qwen3.5:9b", transport=httpx.MockTransport(handler), **options
    )


def reply(content: str, **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}, **extra})


def recording(seen: list[dict[str, Any]], *responses: httpx.Response) -> Any:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://ollama:11434/api/chat"
        seen.append(json.loads(request.content))
        return queue.pop(0) if queue else reply('{"answer": "42"}')

    return handler


class TestRequests:
    async def test_sends_a_schema_constrained_chat_request(self) -> None:
        seen: list[dict[str, Any]] = []
        llm = client(recording(seen))

        assert await llm.complete_json(MESSAGES, SCHEMA, max_tokens=100) == {"answer": "42"}

        body = seen[0]
        assert body["model"] == "qwen3.5:9b"
        assert body["stream"] is False
        assert body["format"] == SCHEMA
        assert body["messages"] == [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "question"},
        ]
        assert body["options"] == {
            "num_ctx": 16384,
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "presence_penalty": 1.5,
            "num_predict": 100,
        }
        assert body["keep_alive"] == "5m"
        # Sent even when off: Qwen3.5 would otherwise think by default.
        assert body["think"] is False
        assert llm.model == "qwen3.5:9b"
        await llm.aclose()

    @pytest.mark.parametrize(("keep_alive", "sent"), [("24h", "24h"), ("-1", -1), ("3600", 3600)])
    async def test_keep_alive_is_sent_the_way_ollama_reads_it(
        self, keep_alive: str, sent: str | int
    ) -> None:
        seen: list[dict[str, Any]] = []
        await client(recording(seen), keep_alive=keep_alive).complete_json(MESSAGES, SCHEMA)
        assert seen[0]["keep_alive"] == sent

    async def test_without_keep_alive_the_server_default_applies(self) -> None:
        # Otherwise every request would override OLLAMA_KEEP_ALIVE of the Docker stack.
        seen: list[dict[str, Any]] = []
        await client(recording(seen), keep_alive=None).complete_json(MESSAGES, SCHEMA)
        assert "keep_alive" not in seen[0]

    async def test_a_call_can_adjust_the_sampling(self) -> None:
        seen: list[dict[str, Any]] = []
        await client(recording(seen)).complete_json(
            MESSAGES, SCHEMA, sampling=Sampling(temperature=0.2, presence_penalty=0.0)
        )
        assert seen[0]["options"] == {
            "num_ctx": 16384,
            "temperature": 0.2,
            "top_p": 0.8,
            "top_k": 20,
            "presence_penalty": 0.0,
        }
        assert "num_predict" not in seen[0]["options"]

    async def test_thinking_calls_use_the_models_own_sampling(self) -> None:
        seen: list[dict[str, Any]] = []
        await client(recording(seen)).complete_json(
            MESSAGES, SCHEMA, think=True, sampling=Sampling(temperature=0.1)
        )
        assert seen[0]["think"] is True
        assert seen[0]["options"] == {"num_ctx": 16384}

    async def test_without_configured_sampling_the_model_defaults_apply(self) -> None:
        seen: list[dict[str, Any]] = []
        await client(recording(seen), sampling=None).complete_json(MESSAGES, SCHEMA)
        assert seen[0]["options"] == {"num_ctx": 16384}


async def test_models_without_thinking_support_are_used_without_it() -> None:
    seen: list[dict[str, Any]] = []
    unsupported = httpx.Response(400, json={"error": '"gemma3:12b" does not support thinking'})
    llm = client(recording(seen, unsupported))

    assert await llm.complete_json(MESSAGES, SCHEMA, think=True) == {"answer": "42"}
    assert [body.get("think") for body in seen] == [True, None]  # retried without the flag
    assert seen[1]["options"]["temperature"] == 0.7

    await llm.complete_json(MESSAGES, SCHEMA, think=True)
    assert len(seen) == 3  # remembered: no failing first attempt any more
    assert "think" not in seen[2]


async def test_other_bad_requests_are_not_retried() -> None:
    seen: list[dict[str, Any]] = []
    rejected = httpx.Response(400, json={"error": "invalid format schema"})
    with pytest.raises(LLMBadResponse):
        await client(recording(seen, rejected)).complete_json(MESSAGES, SCHEMA, think=True)
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={"error": "model not found"}), LLMUnavailable),
        (httpx.Response(503), LLMUnavailable),
        (httpx.Response(429), LLMUnavailable),
        (httpx.Response(400, json={"error": "bad schema"}), LLMBadResponse),
        (httpx.Response(400, text="not json"), LLMBadResponse),
        (httpx.Response(400, json=["not", "an", "object"]), LLMBadResponse),
        (httpx.Response(200, text="not json"), LLMBadResponse),
        (httpx.Response(200, json={"unexpected": True}), LLMBadResponse),
        (reply("not json at all"), LLMBadResponse),
        (reply("[1, 2, 3]"), LLMBadResponse),
        (reply('{"answer": "cut', done_reason="length"), LLMBadResponse),
    ],
)
async def test_maps_failures(response: httpx.Response, error: type[Exception]) -> None:
    with pytest.raises(error):
        await client(lambda _r: response).complete_json(MESSAGES, SCHEMA, think=True)


@pytest.mark.parametrize("exception", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_transport_errors_mean_unavailable(exception: Exception) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(LLMUnavailable):
        await client(handler).complete_json(MESSAGES, SCHEMA)


@pytest.mark.parametrize(
    ("response", "available"),
    [
        (httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]}), True),
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
        keep_alive="1m",
        max_concurrency=1,
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"models": [{"name": "mistral:latest"}]})
        ),
    )
    assert await llm.is_available()


def test_sampling_options() -> None:
    assert Sampling().options() == {}
    assert SAMPLING.merged(None) == SAMPLING.options()
    assert SAMPLING.merged(Sampling(top_k=5)) == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 5,
        "presence_penalty": 1.5,
    }
