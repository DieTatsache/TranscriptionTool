import pytest

from sonora.errors import Conflict, RateLimited, ValidationFailed
from sonora.ratelimit import RateLimiter
from sonora.services.quiz import grade, public_questions

QUIZ = [
    {
        "question": "Q1",
        "options": ["a", "b", "c", "d"],
        "correct_option": 1,
        "explanation": "E1",
        "source_seconds": 41,
    },
    {
        "question": "Q2",
        "options": ["a", "b", "c"],
        "correct_option": 0,
        "explanation": "E2",
        "source_seconds": None,
    },
]


class TestRateLimiter:
    async def test_allows_up_to_the_limit_then_raises_with_retry_after(self) -> None:
        limiter = RateLimiter("memory://")
        for _ in range(3):
            await limiter.hit("3/minute", "login", "1.2.3.4")
        with pytest.raises(RateLimited) as caught:
            await limiter.hit("3/minute", "login", "1.2.3.4", message="Slow down", code="custom")
        assert caught.value.code == "custom"
        assert caught.value.message == "Slow down"
        assert 0 < int(caught.value.headers["Retry-After"]) <= 60

    async def test_keys_are_independent(self) -> None:
        limiter = RateLimiter("async+memory://")
        await limiter.hit("1/minute", "login", "a")
        await limiter.hit("1/minute", "login", "b")
        await limiter.hit("1/minute", "upload", "a")
        with pytest.raises(RateLimited):
            await limiter.hit("1/minute", "login", "a")

    async def test_allows_does_not_consume_and_reset_clears(self) -> None:
        limiter = RateLimiter("memory://")
        assert await limiter.allows("1/minute", "k")
        assert await limiter.allows("1/minute", "k")
        await limiter.hit("1/minute", "k")
        assert not await limiter.allows("1/minute", "k")
        assert await limiter.retry_after("1/minute", "k") > 0
        await limiter.reset("1/minute", "k")
        assert await limiter.allows("1/minute", "k")

    async def test_can_be_disabled(self) -> None:
        limiter = RateLimiter("memory://", enabled=False)
        for _ in range(5):
            await limiter.hit("1/minute", "k")
        assert await limiter.allows("1/minute", "k")


class TestQuiz:
    def test_public_questions_hide_answers(self) -> None:
        assert public_questions(QUIZ) == [
            {"question": "Q1", "options": ["a", "b", "c", "d"]},
            {"question": "Q2", "options": ["a", "b", "c"]},
        ]

    def test_grading(self) -> None:
        result = grade(QUIZ, [1, None])
        assert (result.score, result.total) == (1, 2)
        first, second = result.results
        assert first.is_correct and first.explanation == "E1" and first.source_seconds == 41
        assert not second.is_correct and second.selected is None and second.correct_option == 0

    @pytest.mark.parametrize("answers", [[1], [1, 0, 0], [1, 3]])
    def test_rejects_invalid_answer_sheets(self, answers: list[int | None]) -> None:
        with pytest.raises(ValidationFailed):
            grade(QUIZ, answers)

    @pytest.mark.parametrize("quiz", [None, []])
    def test_requires_a_quiz(self, quiz: list[dict[str, object]] | None) -> None:
        with pytest.raises(Conflict):
            grade(quiz, [])
