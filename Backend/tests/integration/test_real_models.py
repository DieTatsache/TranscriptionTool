"""Checks against real models (skipped by default; run with ``pytest -m integration``).

Configuration (plain environment variables, independent of the app's SONORA_ settings):
  IT_OLLAMA_URL      default http://localhost:11434
  IT_OLLAMA_MODEL    default llama3.2:3b
  IT_WHISPER_MODEL   faster-whisper model name or local model directory (Whisper tests)
  IT_AUDIO_FILE      a short speech recording (Whisper tests)

These verify that prompts, schemas and output validation work with an actual model; they
assert structure, not wording, because model output varies.
"""

import os
import random
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sonora.ai.chat import LectureAssistant
from sonora.ai.generation import ContentGenerator
from sonora.ai.llm import OllamaClient
from sonora.models import ChatSource
from tests.fakes import SAMPLE

pytestmark = pytest.mark.integration

OLLAMA_URL = os.environ.get("IT_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("IT_OLLAMA_MODEL", "llama3.2:3b")
WHISPER_MODEL = os.environ.get("IT_WHISPER_MODEL")
AUDIO_FILE = os.environ.get("IT_AUDIO_FILE")
CONTEXT = 8192


@pytest.fixture
async def ollama() -> AsyncIterator[OllamaClient]:
    client = OllamaClient(
        OLLAMA_URL,
        OLLAMA_MODEL,
        context_tokens=CONTEXT,
        timeout_seconds=900,
        temperature=0.2,
        keep_alive="10m",
        max_concurrency=1,
    )
    if not await client.is_available():
        await client.aclose()
        pytest.skip(f"{OLLAMA_MODEL} not available at {OLLAMA_URL}")
    yield client
    await client.aclose()


async def test_generates_a_valid_script_and_quiz(ollama: OllamaClient) -> None:
    content = await ContentGenerator(ollama, context_tokens=CONTEXT, rng=random.Random(1)).generate(
        SAMPLE["transcript"], language="en", duration_seconds=SAMPLE["duration_seconds"]
    )

    script = content.script
    assert script["title"]
    assert script["summary"]
    assert len(script["overview"]) >= 1
    assert len(script["takeaways"]) >= 1
    starts = {int(s["start"]) for s in SAMPLE["transcript"]}
    cited = [t["at_seconds"] for t in script["takeaways"] if t["at_seconds"] is not None]
    assert all(at in starts for at in cited)
    assert len(content.quiz) >= 4  # 42-minute sample -> 8 requested, at least half usable
    for question in content.quiz:
        assert 3 <= len(question["options"]) <= 5
        assert 0 <= question["correct_option"] < len(question["options"])


async def test_answers_a_question_about_the_lecture(ollama: OllamaClient) -> None:
    answer = await LectureAssistant(ollama, context_tokens=CONTEXT).answer(
        question="How long should I wait after asking a follow-up question?",
        transcript=SAMPLE["transcript"],
        script=SAMPLE["script"],
        history=[],
    )
    assert answer.text
    if answer.source is ChatSource.LESSON and answer.cite_seconds is not None:
        assert answer.cite_seconds in {int(s["start"]) for s in SAMPLE["transcript"]}


@pytest.mark.skipif(
    not (WHISPER_MODEL and AUDIO_FILE), reason="set IT_WHISPER_MODEL and IT_AUDIO_FILE"
)
def test_transcribes_real_speech() -> None:
    from sonora.transcription.whisper import FasterWhisperTranscriber

    assert WHISPER_MODEL and AUDIO_FILE
    result = FasterWhisperTranscriber(WHISPER_MODEL).transcribe(
        Path(AUDIO_FILE), language=None, max_duration_seconds=3 * 3600
    )
    assert result.segments
    assert result.language
    assert all(s.end >= s.start for s in result.segments)
