import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

import sonora.cli as cli
from sonora.config import Settings
from sonora.container import Services, build_services
from sonora.db import Base
from sonora.models import TrainingSession, User
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
        assert "ada@example.com (trainer plan)" in out
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
        assert run(capsys, "set-plan", "--email", "A@b.io", "--plan", "starter")[0] == 0
        assert query(settings, select(User.plan)) == "starter"
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
