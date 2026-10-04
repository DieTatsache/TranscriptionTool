from typing import Any

import pytest

from sonora.ai import analysis
from sonora.ai.analysis import (
    LectureAnalyzer,
    median_judgement,
    normalize_scores,
    normalize_topics,
    speaking_metrics,
)
from sonora.ai.generation import GenerationError
from sonora.ai.llm import LLMBadResponse, LLMUnavailable
from sonora.ai.prompts import scores_messages
from tests.fakes import SAMPLE, FakeLLM, scores_output

SEGMENTS = SAMPLE["transcript"]  # starts 12, 41, 80, 88, 125, ...
END = int(SEGMENTS[-1]["end"])  # 350


def segments(*spans: tuple[float, float], words: int = 10) -> list[dict[str, Any]]:
    return [{"start": s, "end": e, "text": " ".join(["word"] * words)} for s, e in spans]


class TestSpeakingMetrics:
    def test_words_per_minute_over_the_spoken_span(self) -> None:
        # 3 x 50 words between 0 s and 60 s.
        metrics = speaking_metrics(segments((0, 20), (20, 40), (40, 60), words=50))
        assert metrics == {"words": 150, "words_per_minute": 150}

    def test_no_pace_for_very_short_recordings(self) -> None:
        assert speaking_metrics(segments((0, 30), words=40))["words_per_minute"] is None

    def test_segments_without_end_use_their_start(self) -> None:
        metrics = speaking_metrics([{"start": 0.0, "text": "a b"}, {"start": 120.0, "text": "c"}])
        assert metrics == {"words": 3, "words_per_minute": 2}


class TestPaceInTheScoresPrompt:
    @pytest.mark.parametrize(
        ("pace", "verdict"),
        [
            (109, "slower than"),
            (110, "within"),
            (157, "within"),
            (160, "within"),
            (161, "faster than"),
        ],
    )
    def test_states_the_verdict_instead_of_leaving_the_comparison_to_the_model(
        self, pace: int, verdict: str
    ) -> None:
        # Seen live: "157 is slightly faster than the typical range (110 to 160)".
        task = scores_messages(["[00:00] Hello."], "en", words_per_minute=pace)[1].content
        assert (
            f"Measured speaking pace: {pace} words per minute, {verdict} the typical range "
            "for lectures (110 to 160)." in task
        )

    def test_says_nothing_about_the_pace_of_very_short_recordings(self) -> None:
        task = scores_messages(["[00:00] Hello."], "en", words_per_minute=None)[1].content
        assert "pace:" not in task


class TestNormalizeScores:
    def test_keeps_valid_scores_and_cleans_text(self) -> None:
        raw = scores_output(content=9, rhetoric=4, structure=7)
        raw["content"]["assessment"] = "  Clear   explanations\n with examples. "
        raw["structure"]["score"] = 7.0  # integral floats are fine
        scores = normalize_scores(raw)
        assert scores["content"] == {
            "score": 9,
            "assessment": "Clear explanations with examples.",
            "tip": "Polish your content.",
        }
        assert [scores[c]["score"] for c in ("content", "rhetoric", "structure")] == [9, 4, 7]

    @pytest.mark.parametrize("bad", [0, 11, -3, 7.5, "8", True, None])
    def test_rejects_scores_outside_1_to_10(self, bad: object) -> None:
        raw = scores_output()
        raw["rhetoric"]["score"] = bad
        with pytest.raises(GenerationError, match="rhetoric"):
            normalize_scores(raw)

    def test_rejects_missing_categories_and_assessments(self) -> None:
        raw = scores_output()
        del raw["structure"]
        with pytest.raises(GenerationError, match="structure"):
            normalize_scores(raw)
        raw = scores_output()
        raw["content"]["assessment"] = "   "
        with pytest.raises(GenerationError, match="content assessment"):
            normalize_scores(raw)

    def test_bounds_text_length(self) -> None:
        raw = scores_output()
        raw["content"]["assessment"] = "word " * 500
        raw["content"]["tip"] = "tip " * 500
        scores = normalize_scores(raw)
        assert len(scores["content"]["assessment"]) <= 700
        assert len(scores["content"]["tip"]) <= 300


class TestMedianJudgement:
    def test_one_stray_judgement_cannot_skew_a_score(self) -> None:
        judgements = [
            normalize_scores(scores_output(content=8, rhetoric=10, structure=7)),
            normalize_scores(scores_output(content=7, rhetoric=3, structure=7)),
            normalize_scores(scores_output(content=9, rhetoric=4, structure=6)),
        ]
        judgements[2]["rhetoric"]["assessment"] = "Frequent filler words."
        combined = median_judgement(judgements)
        assert {c: s["score"] for c, s in combined.items()} == {
            "content": 8,
            "rhetoric": 4,
            "structure": 7,
        }
        # Text and score always come from the same judgement.
        assert combined["rhetoric"]["assessment"] == "Frequent filler words."

    async def test_the_analyzer_reports_the_median(self) -> None:
        llm = FakeLLM()
        llm.handler = None
        llm.queue.extend(
            [
                {"topics": [{"title": "All of it", "start": "00:12"}]},
                scores_output(content=2, rhetoric=9, structure=5),
                scores_output(content=8, rhetoric=8, structure=5),
                scores_output(content=7, rhetoric=1, structure=6),
            ]
        )
        result = await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language=None)
        assert {c: s["score"] for c, s in result.scores.items()} == {
            "content": 7,
            "rhetoric": 8,
            "structure": 5,
        }


class TestNormalizeTopics:
    def test_computes_durations_that_cover_the_whole_lecture(self) -> None:
        topics = normalize_topics(
            {
                "topics": [
                    {"title": "Opening", "start": "00:12"},
                    {"title": "The sequence", "start": "02:05"},
                    {"title": "Silence", "start": "[4:10]"},
                ]
            },
            SEGMENTS,
        )
        assert topics == [
            {"title": "Opening", "start_seconds": 12, "end_seconds": 125, "duration_seconds": 113},
            {
                "title": "The sequence",
                "start_seconds": 125,
                "end_seconds": 250,
                "duration_seconds": 125,
            },
            {"title": "Silence", "start_seconds": 250, "end_seconds": END, "duration_seconds": 100},
        ]
        assert sum(t["duration_seconds"] for t in topics) == END - 12

    def test_timestamps_snap_to_real_segments_and_the_first_topic_opens_the_lecture(
        self,
    ) -> None:
        topics = normalize_topics(
            {
                "topics": [
                    {"title": "Late start", "start": "01:30"},
                    {"title": "B", "start": "04:20"},
                ]
            },
            SEGMENTS,
        )
        assert [(t["start_seconds"], t["end_seconds"]) for t in topics] == [(12, 250), (250, END)]

    def test_sorts_and_drops_invented_duplicate_and_junk_topics(self) -> None:
        raw = {
            "topics": [
                {"title": "Third", "start": "04:10"},
                {"title": "First", "start": "00:12"},
                {"title": "Made up", "start": "59:00"},  # nowhere near a real segment
                {"title": "Same start", "start": "00:12"},
                {"title": "first", "start": "00:41"},  # the same topic split in two
                {"title": "", "start": "01:20"},
                {"title": "No time", "start": "soon"},
                "junk",
                {"title": "Second", "start": "02:05"},
            ]
        }
        topics = normalize_topics(raw, SEGMENTS)
        assert [t["title"] for t in topics] == ["First", "Second", "Third"]

    def test_caps_the_number_of_topics(self) -> None:
        many = segments(*((i * 60.0, i * 60.0 + 50) for i in range(20)))
        raw = {"topics": [{"title": f"T{i}", "start": f"{i:02d}:00"} for i in range(20)]}
        topics = normalize_topics(raw, many)
        assert len(topics) == analysis.MAX_TOPICS
        assert topics[-1]["end_seconds"] == 1190  # the last kept topic runs to the end

    def test_a_zero_length_final_topic_is_dropped(self) -> None:
        spans = segments((0, 30), (30, 60), (60, 60))
        raw = {"topics": [{"title": "A", "start": "00:00"}, {"title": "B", "start": "01:00"}]}
        assert [t["title"] for t in normalize_topics(raw, spans)] == ["A"]

    @pytest.mark.parametrize(
        "raw", [{"topics": []}, {"topics": "nope"}, {"topics": [{"title": "X", "start": "99:00"}]}]
    )
    def test_rejects_output_without_usable_topics(self, raw: dict[str, Any]) -> None:
        with pytest.raises(GenerationError):
            normalize_topics(raw, SEGMENTS)


class TestLectureAnalyzer:
    async def test_analyses_topics_and_scores_from_one_shared_prefix(self) -> None:
        llm = FakeLLM()
        result = await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language="de")

        assert result.scores["rhetoric"]["score"] == 6
        assert [t["title"] for t in result.topics] == [
            "What an objection is",
            "Acknowledge, ask, reframe",
            "Silence and follow-up",
        ]
        assert result.metrics["words"] > 0
        assert result.to_dict() == {
            "scores": result.scores,
            "topics": result.topics,
            "metrics": result.metrics,
        }
        (topics_messages, _), *judgements = llm.calls
        assert len(judgements) == analysis.SCORE_JUDGEMENTS
        scores_messages = judgements[0][0]
        assert "Write every text field in German." in topics_messages[0].content
        assert topics_messages[0].content == scores_messages[0].content
        assert "Measured speaking pace:" in scores_messages[1].content
        # Repeated judgements send the identical prompt (served from the model's cache).
        assert all(messages == scores_messages for messages, _ in judgements)

    async def test_judgements_use_precise_sampling_without_reasoning(self) -> None:
        llm = FakeLLM()
        await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language=None)
        for think, max_tokens, sampling in llm.settings:
            assert think is False
            assert max_tokens is not None
            assert sampling is not None and sampling.presence_penalty == 0.0

    async def test_retries_unusable_output(self) -> None:
        llm = FakeLLM()
        llm.queue.extend([{"topics": []}, LLMBadResponse("x")])
        result = await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language=None)
        assert result.topics
        assert len(llm.calls) == 3 + analysis.SCORE_JUDGEMENTS  # two bad topic answers first

    async def test_gives_up_after_repeated_bad_output(self) -> None:
        llm = FakeLLM()
        llm.handler = lambda _m, schema: (
            {"content": {}} if "rhetoric" in schema["properties"] else {"topics": []}
        )
        with pytest.raises(GenerationError, match="after 3 attempts"):
            await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language=None)

    async def test_unavailability_propagates(self) -> None:
        llm = FakeLLM()
        llm.queue.append(LLMUnavailable("down"))
        with pytest.raises(LLMUnavailable):
            await LectureAnalyzer(llm, context_tokens=8192).analyze(SEGMENTS, language=None)

    async def test_empty_transcripts_are_rejected(self) -> None:
        with pytest.raises(GenerationError):
            await LectureAnalyzer(FakeLLM(), context_tokens=8192).analyze([], language=None)

    async def test_long_lectures_are_condensed_first(self) -> None:
        llm = FakeLLM()
        long_transcript = [
            {"start": float(i * 10), "end": float(i * 10 + 9), "text": "word " * 40}
            for i in range(200)
        ]
        await LectureAnalyzer(llm, context_tokens=4096).analyze(long_transcript, language=None)
        kinds = [sorted(schema["properties"]) for _, schema in llm.calls]
        assert kinds.count(["points"]) > 1
        assert kinds[-1 - analysis.SCORE_JUDGEMENTS :] == [
            ["topics"],
            *[["content", "rhetoric", "structure"]] * analysis.SCORE_JUDGEMENTS,
        ]
