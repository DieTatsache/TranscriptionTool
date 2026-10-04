import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

import sonora.cli as cli
from sonora.config import Settings
from sonora.container import Services, build_services
from sonora.db import Base
from sonora.models import FeedbackResponse, QuizAttempt, ShareTab, TrainingSession, User
from sonora.services import shares
from tests.conftest import make_settings
from tests.fakes import FakeLLM

GOOD_PASSWORD = "copper-meadow-signal-9"


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    async def create_tables() -> None:
        services = build_services(settings)
        async with services.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await services.aclose()

    asyncio.run(create_tables())
    return settings


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    fake = FakeLLM()

    def build(settings: Settings, **kwargs: Any) -> Services:
        return build_services(settings, llm=fake)

    monkeypatch.setattr(cli, "build_services", build)
    return fake


def query(settings: Settings, statement: Any) -> Any:
    async def run() -> Any:
        services = build_services(settings)
        async with services.sessionmaker() as db:
            result = await db.scalar(statement)
        await services.aclose()
        return result

    return asyncio.run(run())


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestCreateUser:
    def test_creates_a_user_with_the_default_plan(self, settings: Settings, capsys: Any) -> None:
        code, out, _ = run(
            capsys,
            "create-user",
            "--email",
            "Ada@Example.com",
            "--name",
            "Ada",
            "--password",
            GOOD_PASSWORD,
        )
        assert code == 0
        assert "ada@example.com (plan: Free)" in out
        user = query(settings, select(User))
        assert user.email == "ada@example.com"
        assert user.password_hash.startswith("$argon2id$")

    def test_prompts_for_the_password(
        self, settings: Settings, capsys: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = iter([GOOD_PASSWORD, GOOD_PASSWORD])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
        code, _, _ = run(capsys, "create-user", "--email", "a@b.io", "--name", "A", "--plan", "pro")
        assert code == 0
        assert query(settings, select(User.plan)) == "pro"

    def test_prompted_passwords_must_match(
        self, settings: Settings, capsys: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = iter([GOOD_PASSWORD, "something-else-1"])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
        code, _, err = run(capsys, "create-user", "--email", "a@b.io", "--name", "A")
        assert code == 1
        assert "do not match" in err

    def test_rejects_duplicates_and_weak_passwords(self, settings: Settings, capsys: Any) -> None:
        args = ("create-user", "--email", "a@b.io", "--name", "A", "--password")
        assert run(capsys, *args, GOOD_PASSWORD)[0] == 0
        code, _, err = run(capsys, *args, GOOD_PASSWORD)
        assert code == 1 and "already exists" in err
        code, _, err = run(
            capsys, "create-user", "--email", "c@b.io", "--name", "C", "--password", "short"
        )
        assert code == 1 and "at least 12" in err


class TestPlansAndDemo:
    def test_set_plan(self, settings: Settings, capsys: Any) -> None:
        run(capsys, "create-user", "--email", "a@b.io", "--name", "A", "--password", GOOD_PASSWORD)
        assert run(capsys, "set-plan", "--email", "A@b.io", "--plan", "free")[0] == 0
        assert query(settings, select(User.plan)) == "free"
        code, _, err = run(capsys, "set-plan", "--email", "nobody@b.io", "--plan", "pro")
        assert code == 1 and "No user" in err
        with pytest.raises(SystemExit):
            cli.main(["set-plan", "--email", "a@b.io", "--plan", "platinum"])

    def test_seed_demo_is_idempotent(self, settings: Settings, capsys: Any) -> None:
        code, out, _ = run(capsys, "seed-demo")
        assert code == 0
        assert "4 sample session(s)" in out
        assert run(capsys, "seed-demo")[1].strip().endswith("0 sample session(s) added.")
        assert query(settings, select(func.count()).select_from(TrainingSession)) == 4
        titles = query(
            settings, select(TrainingSession.title).order_by(TrainingSession.created_at.desc())
        )
        assert titles == "Handling Objections — Sales Team Q3"

    def test_seed_demo_refuses_production(
        self, tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        production = make_settings(
            tmp_path,
            environment="production",
            database_url="postgresql+asyncpg://u:p@127.0.0.1:9/x",
            transcription_backend="faster-whisper",
        )
        monkeypatch.setattr(cli, "get_settings", lambda: production)
        code, _, err = run(capsys, "seed-demo")
        assert code == 1
        assert "Refusing" in err


class TestOperations:
    def test_maintenance(self, settings: Settings, capsys: Any) -> None:
        assert run(capsys, "maintenance") == (0, "Maintenance finished.\n", "")

    def test_check_llm(self, settings: Settings, llm: FakeLLM, capsys: Any) -> None:
        code, out, _ = run(capsys, "check-llm")
        assert code == 0 and "LLM OK" in out
        llm.available = False
        code, _, err = run(capsys, "check-llm")
        assert code == 1 and "not available" in err


class TestSeedFeedback:
    """``seed-feedback`` simulates many anonymous listeners on a share link."""

    @staticmethod
    def share(settings: Settings, tabs: list[str]) -> str:
        async def create() -> str:
            services = build_services(settings)
            try:
                user, _ = await cli.seed_demo(services, email="t@example.com", password="x")
                async with services.sessionmaker() as db:
                    session = await db.scalar(
                        select(TrainingSession).where(TrainingSession.owner_id == user.id).limit(1)
                    )
                    link = await shares.create(
                        db, user, session, tabs=[ShareTab(t) for t in tabs], expires_in_days=7
                    )
                    return link.token
            finally:
                await services.aclose()

        return asyncio.run(create())

    def test_adds_listeners_through_the_listener_rules(
        self, settings: Settings, capsys: Any
    ) -> None:
        token = self.share(settings, ["quiz", "feedback"])

        code, out, _ = run(
            capsys,
            "seed-feedback",
            "--link",
            f"http://localhost:8080/share/{token}",
            "--count",
            "25",
        )

        assert code == 0, out
        assert out.startswith('Added 25 listeners to "')
        assert "25 feedback responses (" in out and "25 quiz attempts." in out
        # Each simulated listener has a pseudonym of its own, like a browser of its own.
        assert (
            query(settings, select(func.count(func.distinct(FeedbackResponse.participant_key))))
            == 25
        )
        assert query(settings, select(func.count()).select_from(QuizAttempt)) == 25
        comments = query(
            settings,
            select(func.count())
            .select_from(FeedbackResponse)
            .where(FeedbackResponse.comment.is_not(None)),
        )
        assert f"({comments} with a comment)" in out

    def test_only_fills_what_the_link_shares(self, settings: Settings, capsys: Any) -> None:
        quiz_only = self.share(settings, ["quiz"])
        assert run(capsys, "seed-feedback", "--link", quiz_only, "--count", "3")[0] == 0
        assert query(settings, select(func.count()).select_from(FeedbackResponse)) == 0
        assert query(settings, select(func.count()).select_from(QuizAttempt)) == 3

        script_only = self.share(settings, ["script"])
        code, _, err = run(capsys, "seed-feedback", "--link", script_only)
        assert code == 1 and "neither the feedback form nor the quiz" in err

    def test_stops_at_the_sessions_feedback_limit(
        self, settings: Settings, capsys: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli.feedback_service, "MAX_RESPONSES_PER_SESSION", 10)
        token = self.share(settings, ["feedback"])

        code, out, _ = run(capsys, "seed-feedback", "--link", token, "--count", "15")

        assert code == 0
        assert "10 feedback responses" in out and "limit is reached" in out
        assert query(settings, select(func.count()).select_from(FeedbackResponse)) == 10

    def test_rejects_unknown_links_and_bad_counts(self, settings: Settings, capsys: Any) -> None:
        code, _, err = run(capsys, "seed-feedback", "--link", "http://x/share/" + "a" * 43)
        assert code == 1 and "invalid or has expired" in err
        with pytest.raises(SystemExit):
            cli.main(["seed-feedback", "--link", "x", "--count", "0"])

    def test_refuses_production(
        self, tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        production = make_settings(
            tmp_path,
            environment="production",
            database_url="postgresql+asyncpg://u:p@127.0.0.1:9/x",
            transcription_backend="faster-whisper",
        )
        monkeypatch.setattr(cli, "get_settings", lambda: production)
        code, _, err = run(capsys, "seed-feedback", "--link", "x")
        assert code == 1 and "Refusing" in err
