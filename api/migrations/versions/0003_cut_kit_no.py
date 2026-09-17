"""add cuts.kit_no

Optional kit number (套组编号): cuts created from segments sharing a kit
number were solved as one indivisible group on a single roll. The column
is nullable with no default, so every historical cut keeps NULL (= packed
independently); kits never change delivered length, allowance or cutting
progress.

Revision ID: 0003_cut_kit_no
Revises: 0002_cut_completed_at
Create Date: 2026-09-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_cut_kit_no"
down_revision: Union[str, None] = "0002_cut_completed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cuts",
        sa.Column("kit_no", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cuts", "kit_no")
