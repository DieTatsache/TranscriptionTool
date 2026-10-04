"""listener input, lecture analysis and payments

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 16:00:00

New job type ``analyze_session`` and activity types ``plan_activated``/``plan_canceled``
need no schema change: enums are stored as plain strings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL, JSON (text) on SQLite; mirrors sonora.db.types.JSONType.
JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _session_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["session_id"],
        ["training_sessions.id"],
        name=op.f(f"fk_{table}_session_id_training_sessions"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "succeeded", "failed", name="paymentstatus", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("card_brand", sa.String(length=20), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_payments_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index("ix_payments_user_created", "payments", ["user_id", "created_at"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("participant_key", sa.String(length=64), nullable=False),
        sa.Column("answers", JSON_DOCUMENT, nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _session_fk("quiz_attempts"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_attempts")),
        sa.UniqueConstraint(
            "session_id", "participant_key", name=op.f("uq_quiz_attempts_session_id")
        ),
    )

    op.create_table(
        "feedback_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("participant_key", sa.String(length=64), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("ratings", JSON_DOCUMENT, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _session_fk("feedback_responses"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback_responses")),
        sa.UniqueConstraint(
            "session_id", "participant_key", name=op.f("uq_feedback_responses_session_id")
        ),
    )
    op.create_index(
        "ix_feedback_responses_session_created",
        "feedback_responses",
        ["session_id", "created_at"],
    )

    op.create_table(
        "session_analyses",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "ready",
                "failed",
                name="analysisstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("result", JSON_DOCUMENT, nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=300), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _session_fk("session_analyses"),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_session_analyses")),
    )


def downgrade() -> None:
    for table in ("session_analyses", "feedback_responses", "quiz_attempts", "payments"):
        op.drop_table(table)  # indexes are dropped with their tables
