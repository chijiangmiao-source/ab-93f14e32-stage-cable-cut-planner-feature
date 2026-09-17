"""baseline schema

Original schema as deployed before cut-completion tracking:
plans / rolls / cuts without any completion timestamp. This revision exists
so a pre-existing production database can be stamped at it and then upgraded,
while a fresh database builds straight through both revisions.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roll_length", sa.Integer(), nullable=False),
        sa.Column("kerf_width", sa.Integer(), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("rolls_used", sa.Integer(), nullable=False),
        sa.Column("total_kerf_count", sa.Integer(), nullable=False),
        sa.Column("total_leftover", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "rolls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kerf_count", sa.Integer(), nullable=False),
        sa.Column("used_length", sa.Integer(), nullable=False),
        sa.Column("leftover", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rolls_plan_id", "rolls", ["plan_id"])
    op.create_table(
        "cuts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roll_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.String(length=32), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["roll_id"], ["rolls.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_cuts_roll_id", "cuts", ["roll_id"])


def downgrade() -> None:
    op.drop_index("ix_cuts_roll_id", table_name="cuts")
    op.drop_table("cuts")
    op.drop_index("ix_rolls_plan_id", table_name="rolls")
    op.drop_table("rolls")
    op.drop_table("plans")
