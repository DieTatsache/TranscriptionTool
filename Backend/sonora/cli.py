"""Administrative commands: ``python -m sonora.cli <command> --help``."""

import argparse
import asyncio
import getpass
import random
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from sonora.config import Settings, get_settings
from sonora.container import Services, build_services
from sonora.demo import demo_sessions
from sonora.errors import AppError
from sonora.feedback import RATING_QUESTIONS
from sonora.models import ActivityType, SessionStatus, ShareTab, TrainingSession, User
from sonora.plans import PLANS, get_plan
from sonora.security import new_token, participant_key
from sonora.services import activity
from sonora.services import feedback as feedback_service
from sonora.services import quiz as quiz_service
from sonora.services import shares as shares_service
from sonora.services.auth import ensure_acceptable_password, normalize_email
from sonora.worker.runner import Worker

DEMO_EMAIL = "marie.trainer@example.com"
DEMO_NAME = "Marie Tanner"
DEMO_PASSWORD = "sonora-demo-2026"  # noqa: S105  (public demo login for local development)


# Test data for seed-feedback: what listeners might write in the open question.
SAMPLE_COMMENTS = (
    "The examples made the theory click for me.",
    "A bit fast in the second half.",
    "Could you share the slides afterwards?",
    "More time for questions would be great.",
    "Clear structure, I always knew where we were.",
    "The summary at the end was really helpful.",
    "Some terms were new to me, a short glossary would help.",
    "Best session of the course so far!",
    "I would have liked one more practical exercise.",
    "The audio in the room was hard to hear at the back.",
)
MAX_SEED_LISTENERS = feedback_service.MAX_RESPONSES_PER_SESSION


class CommandError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SeedResult:
    title: str
    listeners: int
    responses: int
    comments: int
    attempts: int
    full: bool  # the session's feedback limit was reached


async def create_user(
    services: Services,
    *,
    email: str,
    name: str,
    password: str,
    plan: str,
    check_policy: bool = True,
) -> User:
    email = normalize_email(email)
    if check_policy:
        ensure_acceptable_password(services, password, email)
    async with services.sessionmaker() as db:
        if await db.scalar(select(User.id).where(User.email == email)):
            raise CommandError(f"A user with email {email} already exists.")
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            password_hash=await services.passwords.hash(password),
            plan=plan,
        )
        db.add(user)
        activity.record(db, user.id, ActivityType.ACCOUNT_CREATED)
        await db.commit()
        return user


async def set_plan(services: Services, *, email: str, plan: str) -> None:
    async with services.sessionmaker() as db:
        user = await db.scalar(select(User).where(User.email == normalize_email(email)))
        if user is None:
            raise CommandError(f"No user with email {email}.")
        user.plan = plan
        await db.commit()


async def seed_demo(services: Services, *, email: str, password: str) -> tuple[User, int]:
    """Creates the demo trainer with the four sample sessions (idempotent)."""
    async with services.sessionmaker() as db:
        user = await db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        user = await create_user(
            services,
            email=email,
            name=DEMO_NAME,
            password=password,
            plan="trainer",
            check_policy=False,
        )
    async with services.sessionmaker() as db:
        existing = set(
            await db.scalars(
                select(TrainingSession.title).where(TrainingSession.owner_id == user.id)
            )
        )
        created = 0
        for sample in demo_sessions():
            if sample["title"] in existing:
                continue
            created_at = datetime.strptime(sample["date"], "%b %d, %Y").replace(hour=10, tzinfo=UTC)
            db.add(
                TrainingSession(
                    owner_id=user.id,
                    title=sample["title"],
                    auto_title=False,
                    status=SessionStatus.READY,
                    language=sample["language"],
                    duration_seconds=sample["duration_seconds"],
                    transcript=sample["transcript"],
                    script=sample["script"],
                    quiz=sample["quiz"],
                    quiz_count=len(sample["quiz"]),
                    created_at=created_at,
                    ready_at=created_at,
                )
            )
            created += 1
        await db.commit()
    return user, created


def _share_token(link: str) -> str:
    """The token of a share link given as URL (…/share/<token>) or as the bare token."""
    return link.rstrip("/").rsplit("/share/", 1)[-1].split("?", 1)[0]


async def seed_feedback(services: Services, *, link: str, count: int) -> SeedResult:
    """Simulates ``count`` anonymous listeners on a share link (local testing only).

    Each one gets its own pseudonym, as a browser of its own would, and goes through the
    same services as real listeners: validation, one response per listener and the
    session's limits apply.
    """
    rng = random.Random()  # noqa: S311  (test data, not security relevant)
    async with services.sessionmaker() as db:
        try:
            share, session = await shares_service.resolve(db, _share_token(link))
        except AppError as exc:
            raise CommandError(exc.message) from None
        tabs = set(share.tabs)
        if not tabs & {ShareTab.FEEDBACK, ShareTab.QUIZ}:
            raise CommandError("This link shares neither the feedback form nor the quiz.")
        responses = comments = attempts = 0
        full = False
        for _ in range(count):
            listener = participant_key(session.id, new_token())
            if ShareTab.QUIZ in tabs and session.quiz:
                # Mostly right, like a listener who followed the lecture.
                answers = [
                    int(q["correct_option"])
                    if rng.random() < 0.7
                    else rng.randrange(len(q["options"]))
                    for q in session.quiz
                ]
                result = quiz_service.grade(session.quiz, answers)
                if await quiz_service.record_first_attempt(db, session, listener, answers, result):
                    attempts += 1
            if ShareTab.FEEDBACK in tabs and not full:
                ratings = {
                    q.id: min(
                        len(q.options) - 1,
                        max(0, round(rng.gauss(0.7, 0.2) * (len(q.options) - 1))),
                    )
                    for q in RATING_QUESTIONS
                }
                comment = rng.choice(SAMPLE_COMMENTS) if rng.random() < 0.4 else None
                try:
                    await feedback_service.submit(
                        db, session, listener, ratings=ratings, comment=comment
                    )
                except AppError as exc:
                    if exc.code != "feedback_closed":
                        raise
                    full = True
                else:
                    responses += 1
                    comments += comment is not None
        return SeedResult(session.title, count, responses, comments, attempts, full)


async def _run(args: argparse.Namespace, settings: Settings) -> str:
    services = build_services(settings)
    try:
        match args.command:
            case "create-user":
                password = args.password or _prompt_password()
                user = await create_user(
                    services, email=args.email, name=args.name, password=password, plan=args.plan
                )
                return f"Created user {user.email} (plan: {get_plan(user.plan).name})."
            case "set-plan":
                await set_plan(services, email=args.email, plan=args.plan)
                return f"Plan of {args.email} set to {args.plan}."
            case "seed-demo":
                if settings.is_production and not args.force:
                    raise CommandError("Refusing to seed demo data in production (use --force).")
                user, created = await seed_demo(services, email=args.email, password=args.password)
                return f"Demo user {user.email} ready; {created} sample session(s) added."
            case "seed-feedback":
                if settings.is_production and not args.force:
                    raise CommandError("Refusing to add test feedback in production (use --force).")
                seeded = await seed_feedback(services, link=args.link, count=args.count)
                message = (
                    f'Added {seeded.listeners} listeners to "{seeded.title}": '
                    f"{seeded.responses} feedback responses ({seeded.comments} with a comment), "
                    f"{seeded.attempts} quiz attempts."
                )
                if seeded.full:
                    message += " The session's feedback limit is reached."
                return message
            case "maintenance":
                await Worker(services).maintenance()
                return "Maintenance finished."
            case "check-llm":
                if not await services.llm.is_available():
                    raise CommandError(
                        f"Model {settings.llm_model!r} is not available at {settings.llm_base_url}."
                    )
                return f"LLM OK: {settings.llm_model} at {settings.llm_base_url}."
        raise CommandError(f"Unknown command {args.command}")  # pragma: no cover
    finally:
        await services.aclose()


def _prompt_password() -> str:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise CommandError("Passwords do not match.")
    return password


def _listener_count(value: str) -> int:
    count = int(value)
    if not 1 <= count <= MAX_SEED_LISTENERS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_SEED_LISTENERS}")
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sonora.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="create a trainer account")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--password", help="prompted for when omitted (preferred: keeps it out of shell history)"
    )
    create.add_argument("--plan", choices=sorted(PLANS), default=None)

    plan = commands.add_parser("set-plan", help="change a user's plan")
    plan.add_argument("--email", required=True)
    plan.add_argument("--plan", choices=sorted(PLANS), required=True)

    seed = commands.add_parser("seed-demo", help="create the demo trainer and sample sessions")
    seed.add_argument("--email", default=DEMO_EMAIL)
    seed.add_argument("--password", default=DEMO_PASSWORD)
    seed.add_argument("--force", action="store_true", help="allow in production")

    listeners = commands.add_parser(
        "seed-feedback",
        help="add simulated anonymous listeners (feedback and quiz answers) to a share link",
    )
    listeners.add_argument("--link", required=True, help="share link URL or its token")
    listeners.add_argument(
        "--count",
        type=_listener_count,
        default=200,
        help=f"1 to {MAX_SEED_LISTENERS} (default 200)",
    )
    listeners.add_argument("--force", action="store_true", help="allow in production")

    commands.add_parser("maintenance", help="purge expired sign-ins, dead jobs and orphaned audio")
    commands.add_parser("check-llm", help="verify the LLM server is reachable and has the model")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if getattr(args, "plan", "") is None:
        args.plan = settings.default_plan
    try:
        print(asyncio.run(_run(args, settings)))
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # e.g. password policy violations
        message = getattr(exc, "message", None) or str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
