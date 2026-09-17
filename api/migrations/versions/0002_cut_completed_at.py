"""add cuts.completed_at

Records when each segment was actually cut. The column is nullable and has no
default, so every historical cut keeps NULL (= still pending) after the
upgrade; only explicit completion actions set a timestamp.

Revision ID: 0002_cut_completed_at
Revises: 0001_baseline
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_cut_completed_at"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cuts",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cuts", "completed_at")
