"""Administrative commands: ``python -m sonora.cli <command> --help``."""

import argparse
import asyncio
import getpass
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select

from sonora.config import Settings, get_settings
from sonora.container import Services, build_services
from sonora.demo import demo_sessions
from sonora.models import ActivityType, SessionStatus, TrainingSession, User
from sonora.plans import PLANS
from sonora.services import activity
from sonora.services.auth import ensure_acceptable_password, normalize_email
from sonora.worker.runner import Worker

DEMO_EMAIL = "marie.trainer@example.com"
DEMO_NAME = "Marie Tanner"
DEMO_PASSWORD = "sonora-demo-2026"  # noqa: S105  (public demo login for local development)


class CommandError(Exception):
    pass


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


async def _run(args: argparse.Namespace, settings: Settings) -> str:
    services = build_services(settings)
    try:
        match args.command:
            case "create-user":
                password = args.password or _prompt_password()
                user = await create_user(
                    services, email=args.email, name=args.name, password=password, plan=args.plan
                )
                return f"Created user {user.email} ({user.plan} plan)."
            case "set-plan":
                await set_plan(services, email=args.email, plan=args.plan)
                return f"Plan of {args.email} set to {args.plan}."
            case "seed-demo":
                if settings.is_production and not args.force:
                    raise CommandError("Refusing to seed demo data in production (use --force).")
                user, created = await seed_demo(services, email=args.email, password=args.password)
                return f"Demo user {user.email} ready; {created} sample session(s) added."
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
