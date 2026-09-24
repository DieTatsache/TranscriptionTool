import random
from typing import Any

import pytest

from sonora.ai.generation import (
    ContentGenerator,
    GenerationError,
    clean_text,
    normalize_quiz,
    normalize_script,
    notes_to_lines,
    quiz_size,
)
from sonora.ai.llm import LLMBadResponse, LLMMessage, LLMUnavailable
from sonora.ai.text import estimate_tokens
from tests.fakes import SAMPLE, FakeLLM, default_output, quiz_output, script_output

STARTS = [float(s["start"]) for s in SAMPLE["transcript"]]


def test_clean_text() -> None:
    assert clean_text("  many   spaces\nand\tlines ", 100) == "many spaces and lines"
    assert clean_text("one two three four", 10) == "one two…"
    assert clean_text(42, 10) == ""
    assert clean_text(None, 10) == ""


@pytest.mark.parametrize(
    ("seconds", "size"), [(None, 3), (60, 3), (1500, 5), (2400, 8), (99999, 8)]
)
def test_quiz_size_scales_with_duration(seconds: float | None, size: int) -> None:
    assert quiz_size(seconds) == size


class TestNormalizeScript:
    def test_keeps_valid_content_and_snaps_timestamps(self) -> None:
        script = normalize_script(script_output('"Quoted Title"'), STARTS)
        assert script["title"] == "Quoted Title"
        assert [t["at_seconds"] for t in script["takeaways"]] == [41, 250, 330]
        assert script["questions"] == ["What is the three-step sequence?"]

    def test_drops_duplicates_junk_and_invented_timestamps(self) -> None:
        raw = script_output()
        raw["takeaways"] = [
            {"text": "Same point.", "timestamp": "00:41"},
            {"text": "same point.", "timestamp": "00:41"},
            "not an object",
            {"text": "", "timestamp": "00:41"},
            {"text": "Made-up time.", "timestamp": "59:59"},
        ]
        raw["overview"] = ["Paragraph.", "", 7]
        raw["questions"] = "not a list"
        script = normalize_script(raw, STARTS)
        assert script["takeaways"] == [
            {"text": "Same point.", "at_seconds": 41},
            {"text": "Made-up time.", "at_seconds": None},
        ]
        assert script["overview"] == ["Paragraph."]
        assert script["questions"] == []

    def test_bounds_sizes(self) -> None:
        raw = script_output()
        raw["overview"] = [f"P{i}" for i in range(20)]
        raw["takeaways"] = [{"text": f"T{i}", "timestamp": "00:12"} for i in range(20)]
        raw["summary"] = "word " * 500
        script = normalize_script(raw, STARTS)
        assert len(script["overview"]) == 6
        assert len(script["takeaways"]) == 8
        assert len(script["summary"]) <= 600

    @pytest.mark.parametrize("missing", ["title", "summary", "overview", "takeaways"])
    def test_rejects_incomplete_scripts(self, missing: str) -> None:
        raw: dict[str, Any] = {
            **script_output(),
            missing: [] if missing in ("overview", "takeaways") else "",
        }
        with pytest.raises(GenerationError):
            normalize_script(raw, STARTS)


class TestNormalizeQuiz:
    def test_builds_shuffled_options_with_the_correct_index(self) -> None:
        quiz = normalize_quiz(quiz_output(3), STARTS, limit=3, rng=random.Random(7))
        assert len(quiz) == 3
        for i, question in enumerate(quiz):
            assert question["options"][question["correct_option"]] == f"Right {i + 1}"
            assert sorted(question["options"]) == sorted(
                [f"Right {i + 1}", f"Wrong {i + 1}a", f"Wrong {i + 1}b", f"Wrong {i + 1}c"]
            )
            assert question["source_seconds"] == 41
        positions = {
            q["correct_option"]
            for q in normalize_quiz(quiz_output(8), STARTS, limit=8, rng=random.Random(1))
        }
        assert len(positions) > 1  # no position bias

    def test_deduplicates_options_and_skips_broken_questions(self) -> None:
        raw = {
            "questions": [
                {
                    "question": "Dupes?",
                    "correct_answer": "Yes",
                    "wrong_answers": ["yes", "No", "NO", "Maybe"],
                },
                {"question": "Too few options?", "correct_answer": "A", "wrong_answers": ["a", ""]},
                {"question": "", "correct_answer": "A", "wrong_answers": ["B", "C", "D"]},
                {"question": "No answer?", "correct_answer": "", "wrong_answers": ["B", "C", "D"]},
                "garbage",
                {"question": "dupes?", "correct_answer": "X", "wrong_answers": ["Y", "Z", "W"]},
            ]
        }
        quiz = normalize_quiz(raw, STARTS, limit=2, rng=random.Random(0))
        assert len(quiz) == 1
        assert sorted(quiz[0]["options"]) == ["Maybe", "No", "Yes"]
        assert quiz[0]["source_seconds"] is None
        assert quiz[0]["explanation"] == ""

    def test_trailing_periods_do_not_reveal_the_answer(self) -> None:
        raw = {
            "questions": [
                {
                    "question": "How many objections should you track?",
                    "correct_answer": "Three.",
                    "wrong_answers": ["Ten", "One...", "Five ."],
                    "timestamp": "05:30",
                }
            ]
        }
        (question,) = normalize_quiz(raw, STARTS, limit=1, rng=random.Random(0))
        assert sorted(question["options"]) == ["Five", "One...", "Ten", "Three"]
        assert question["options"][question["correct_option"]] == "Three"

    def test_respects_the_limit(self) -> None:
        assert len(normalize_quiz(quiz_output(6), STARTS, limit=4, rng=random.Random(0))) == 4

    def test_requires_at_least_half_of_the_requested_questions(self) -> None:
        with pytest.raises(GenerationError):
            normalize_quiz(quiz_output(1), STARTS, limit=4, rng=random.Random(0))
        with pytest.raises(GenerationError):
            normalize_quiz({"questions": "nope"}, STARTS, limit=3, rng=random.Random(0))


def test_notes_to_lines() -> None:
    raw = {
        "points": [
            {"timestamp": "1:02", "point": "Point."},
            {"timestamp": "x", "point": "No time."},
            "junk",
        ]
    }
    assert notes_to_lines(raw) == ["[01:02] Point."]
    with pytest.raises(GenerationError):
        notes_to_lines({"points": []})


class TestContentGenerator:
    async def test_short_transcripts_take_one_script_and_one_quiz_call(self) -> None:
        llm = FakeLLM()
        content = await ContentGenerator(llm, context_tokens=8192, rng=random.Random(3)).generate(
            SAMPLE["transcript"], language="de", duration_seconds=1500
        )
        assert content.title == "Handling Objections"
        assert len(content.quiz) == 5
        assert len(llm.calls) == 2
        system = llm.calls[0][0][0].content
        assert "Write every text field in German." in system

    async def test_long_transcripts_are_condensed_first(self) -> None:
        llm = FakeLLM()
        long_transcript = [
            {
                "start": float(i * 10),
                "end": float(i * 10 + 9),
                "text": f"Sentence number {i} " + "word " * 40,
            }
            for i in range(200)
        ]
        await ContentGenerator(llm, context_tokens=4096).generate(
            long_transcript, language=None, duration_seconds=2000
        )
        kinds = [sorted(schema["properties"]) for _, schema in llm.calls]
        notes_calls = kinds.count(["points"])
        assert notes_calls > 1
        assert kinds[-2:] == [
            ["overview", "questions", "summary", "takeaways", "title"],
            ["questions"],
        ]
        # The final prompts contain condensed notes, not the raw transcript.
        assert "Sentence number 150" not in llm.calls[-1][0][1].content

    async def test_retries_bad_output_then_gives_up(self) -> None:
        llm = FakeLLM()
        llm.queue.extend([LLMBadResponse("x"), {"title": ""}])  # two unusable scripts
        content = await ContentGenerator(llm, context_tokens=8192).generate(
            SAMPLE["transcript"], language="en", duration_seconds=60
        )
        assert content.title
        assert len(llm.calls) == 4

        failing = FakeLLM()
        failing.handler = lambda _m, _s: LLMBadResponse("always")
        with pytest.raises(GenerationError, match="after 3 attempts"):
            await ContentGenerator(failing, context_tokens=8192).generate(
                SAMPLE["transcript"], language="en", duration_seconds=60
            )

    async def test_unavailability_is_not_retried_here(self) -> None:
        llm = FakeLLM()
        llm.queue.append(LLMUnavailable("down"))
        with pytest.raises(LLMUnavailable):
            await ContentGenerator(llm, context_tokens=8192).generate(
                SAMPLE["transcript"], language="en", duration_seconds=60
            )
        assert len(llm.calls) == 1

    async def test_empty_transcripts_are_rejected(self) -> None:
        with pytest.raises(GenerationError):
            await ContentGenerator(FakeLLM(), context_tokens=8192).generate(
                [], language=None, duration_seconds=0
            )

    async def test_extreme_lengths_are_sampled_when_notes_do_not_shrink(self) -> None:
        def verbose_notes(_messages: list[LLMMessage], schema: dict[str, Any]) -> dict[str, Any]:
            if "points" in schema["properties"]:  # notes as long as the input: no progress
                return {"points": [{"timestamp": "00:01", "point": "word " * 60}] * 15}
            return default_output(schema)

        llm = FakeLLM()
        llm.handler = verbose_notes
        transcript = [
            {"start": float(i), "end": float(i + 1), "text": "word " * 60} for i in range(80)
        ]

        content = await ContentGenerator(llm, context_tokens=2048).generate(
            transcript, language=None, duration_seconds=80
        )

        assert content.quiz
        final_prompt = llm.calls[-1][0][1].content
        assert estimate_tokens(final_prompt) < 1100  # thinned to fit the budget
