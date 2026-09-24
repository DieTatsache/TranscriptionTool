import pytest

from sonora.ai.chat import LectureAssistant, normalize_answer
from sonora.ai.llm import LLMBadResponse, LLMMessage, LLMUnavailable
from sonora.ai.text import estimate_tokens
from sonora.models import ChatSource
from tests.fakes import SAMPLE, FakeLLM, script_output

STARTS = [float(s["start"]) for s in SAMPLE["transcript"]]
SCRIPT = {
    "summary": "How to handle objections.",
    "takeaways": [
        {"text": "Let silence work.", "at_seconds": 250},
        {"text": "No time.", "at_seconds": None},
    ],
}


class TestNormalizeAnswer:
    def test_lesson_answers_cite_a_real_segment(self) -> None:
        answer = normalize_answer(
            {"answer": " Wait. ", "source": "lesson", "timestamp": "[4:12]"}, STARTS
        )
        assert answer.text == "Wait."
        assert answer.source is ChatSource.LESSON
        assert answer.cite_seconds == 250

    @pytest.mark.parametrize("source", ["knowledge", "web", "banana", None])
    def test_anything_but_lesson_is_general_knowledge_without_citation(
        self, source: object
    ) -> None:
        answer = normalize_answer(
            {"answer": "Paris.", "source": source, "timestamp": "04:10"}, STARTS
        )
        assert answer.source is ChatSource.KNOWLEDGE
        assert answer.cite_seconds is None

    @pytest.mark.parametrize("raw", [{"answer": "  "}, {"answer": 5}, {}])
    def test_empty_answers_are_bad_output(self, raw: dict[str, object]) -> None:
        with pytest.raises(LLMBadResponse):
            normalize_answer(raw, STARTS)

    def test_answers_are_capped(self) -> None:
        assert (
            len(normalize_answer({"answer": "x" * 5000, "source": "lesson"}, STARTS).text) == 2000
        )


class TestMaterial:
    def test_whole_transcript_when_it_fits(self) -> None:
        material = LectureAssistant(FakeLLM(), context_tokens=8192).material(
            "anything", SAMPLE["transcript"], SCRIPT
        )
        assert material.startswith("Summary: How to handle objections.")
        assert "- [04:10] Let silence work." in material
        assert "- No time." in material
        assert "Transcript:\n<transcript>\n[00:12] Welcome back everyone." in material

    def test_only_relevant_passages_for_long_lectures(self) -> None:
        transcript = [
            {
                "start": float(i * 30),
                "text": f"Filler sentence {i} about budgets and planning. " * 3,
            }
            for i in range(400)
        ]
        transcript[250] = {
            "start": 7500.0,
            "text": "Silence is the most underrated negotiation tool.",
        }
        material = LectureAssistant(FakeLLM(), context_tokens=4096).material(
            "Why is silence useful?", transcript, None
        )
        assert "Transcript excerpts:" in material
        assert "[2:05:00] Silence is the most underrated negotiation tool." in material
        assert "Filler sentence 5 " not in material

    def test_excerpts_stay_within_the_budget_best_matches_first(self) -> None:
        transcript = [
            {
                "start": float(i * 30),
                "text": f"Objection handling tip {i}. " + "Price and value matter. " * 8,
            }
            for i in range(300)
        ]
        transcript[120] = {"start": 3600.0, "text": "Objection objection price price value value."}
        assistant = LectureAssistant(FakeLLM(), context_tokens=2048)
        material = assistant.material("objection price value", transcript, None)
        excerpt = material.split("<transcript>", 1)[1]
        assert estimate_tokens(excerpt) <= assistant._material_budget + 10
        assert "[1:00:00] Objection objection price price value value." in material

    def test_no_matching_passage(self) -> None:
        transcript = [{"start": float(i), "text": "budget " * 50} for i in range(300)]
        material = LectureAssistant(FakeLLM(), context_tokens=2048).material(
            "silence?", transcript, None
        )
        assert material.endswith("none matched the question.")


class TestAnswer:
    async def test_history_and_question_are_sent(self) -> None:
        llm = FakeLLM()
        history = [LLMMessage("user", "Earlier?"), LLMMessage("assistant", "Earlier answer.")]
        answer = await LectureAssistant(llm, context_tokens=8192).answer(
            question="Now?",
            transcript=SAMPLE["transcript"],
            script=script_output(),
            history=history,
        )
        assert answer.cite_seconds == 250
        messages, schema = llm.calls[0]
        assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
        assert schema["properties"]["source"]["enum"] == ["lesson", "knowledge"]

    async def test_only_recent_history_is_sent(self) -> None:
        llm = FakeLLM()
        history = [LLMMessage("user", f"q{i}") for i in range(20)]
        await LectureAssistant(llm, context_tokens=8192).answer(
            question="Now?", transcript=SAMPLE["transcript"], script=None, history=history
        )
        assert len(llm.calls[0][0]) == 1 + 6 + 1

    async def test_unavailability_is_not_retried(self) -> None:
        llm = FakeLLM()
        llm.queue.append(LLMUnavailable("down"))
        with pytest.raises(LLMUnavailable):
            await LectureAssistant(llm, context_tokens=8192).answer(
                question="Q", transcript=SAMPLE["transcript"], script=None, history=[]
            )
        assert len(llm.calls) == 1
