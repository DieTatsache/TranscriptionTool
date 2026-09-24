from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from sonora.ai.llm import LLMBadResponse, LLMUnavailable
from tests.conftest import Account, upload
from tests.fakes import FakeLLM

ReadySession = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture
async def chat_path(ready_session: ReadySession, llm: FakeLLM) -> str:
    detail = await ready_session()
    llm.calls.clear()
    return f"/api/v1/sessions/{detail['id']}/chat"


async def test_answers_from_the_lesson_and_keeps_history(
    account: Account, chat_path: str, llm: FakeLLM
) -> None:
    response = await account.client.post(chat_path, json={"message": "How long should I pause?"})

    assert response.status_code == 200
    reply = response.json()
    assert reply["role"] == "assistant"
    assert reply["content"] == "Wait a **full breath**."
    assert reply["source"] == "lesson"
    assert reply["cite_seconds"] == 250

    history = (await account.client.get(chat_path)).json()
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "How long should I pause?"),
        ("assistant", "Wait a **full breath**."),
    ]
    # The model was given the transcript and the question.
    messages, _ = llm.calls[0]
    assert "[04:10] A full breath." in messages[0].content
    assert messages[-1].content == "How long should I pause?"


async def test_sends_recent_history_to_the_model(
    account: Account, chat_path: str, llm: FakeLLM
) -> None:
    await account.client.post(chat_path, json={"message": "First question?"})
    await account.client.post(chat_path, json={"message": "Follow-up?"})
    messages, _ = llm.calls[-1]
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1].content == "First question?"


async def test_general_knowledge_answers_have_no_citation(
    account: Account, chat_path: str, llm: FakeLLM
) -> None:
    llm.queue.append(
        {
            "answer": "The lecture did not cover this. Paris.",
            "source": "knowledge",
            "timestamp": "04:10",
        }
    )
    reply = (await account.client.post(chat_path, json={"message": "Capital of France?"})).json()
    assert reply["source"] == "knowledge"
    assert reply["cite_seconds"] is None


async def test_invented_timestamps_are_dropped(
    account: Account, chat_path: str, llm: FakeLLM
) -> None:
    llm.queue.append({"answer": "Somewhere.", "source": "lesson", "timestamp": "59:00"})
    reply = (await account.client.post(chat_path, json={"message": "When?"})).json()
    assert reply["source"] == "lesson"
    assert reply["cite_seconds"] is None


async def test_retries_malformed_model_output_once(
    account: Account, chat_path: str, llm: FakeLLM
) -> None:
    llm.queue.append(LLMBadResponse("not json"))
    response = await account.client.post(chat_path, json={"message": "Q?"})
    assert response.status_code == 200
    assert len(llm.calls) == 2


@pytest.mark.parametrize("error", [LLMUnavailable("down"), LLMBadResponse("garbage")])
async def test_model_failures_return_503_and_store_nothing(
    account: Account, chat_path: str, llm: FakeLLM, error: Exception
) -> None:
    llm.queue.extend([error, error])
    response = await account.client.post(chat_path, json={"message": "Anyone there?"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "assistant_unavailable"
    assert (await account.client.get(chat_path)).json() == []


@pytest.mark.parametrize("message", ["", "   \n  ", "x" * 1001])
async def test_validates_the_message(account: Account, chat_path: str, message: str) -> None:
    response = await account.client.post(chat_path, json={"message": message})
    assert response.status_code == 422


async def test_is_unavailable_while_processing(account: Account) -> None:
    created = (await upload(account.client)).json()
    response = await account.client.post(
        f"/api/v1/sessions/{created['id']}/chat", json={"message": "Too early?"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_ready"


async def test_is_rate_limited(account: Account, chat_path: str) -> None:
    for _ in range(10):
        assert (await account.client.post(chat_path, json={"message": "Q?"})).status_code == 200
    limited = await account.client.post(chat_path, json={"message": "Q?"})
    assert limited.status_code == 429
    assert "retry-after" in limited.headers
