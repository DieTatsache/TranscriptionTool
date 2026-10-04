"""free plan

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04 20:00:00

The admin-assigned "starter" plan (one session a month) became the free plan that new
accounts get by default. Plans are stored as plain strings, so only the data moves.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET plan = 'free' WHERE plan = 'starter'")


def downgrade() -> None:
    op.execute("UPDATE users SET plan = 'starter' WHERE plan = 'free'")
