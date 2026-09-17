from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from .db import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    roll_length = Column(Integer, nullable=False)
    kerf_width = Column(Integer, nullable=False)
    segment_count = Column(Integer, nullable=False)
    rolls_used = Column(Integer, nullable=False)
    total_kerf_count = Column(Integer, nullable=False)
    total_leftover = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Nullable link to the plan this one was adjusted from. Never read by the
    # solver; it is provenance only. ON DELETE SET NULL keeps every plan
    # reachable on its own even if the source plan is later removed.
    source_plan_id = Column(
        Integer,
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rolls = relationship(
        "Roll",
        back_populates="plan",
        order_by="Roll.position",
        cascade="all, delete-orphan",
    )


class Roll(Base):
    __tablename__ = "rolls"

    id = Column(Integer, primary_key=True)
    plan_id = Column(
        Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, nullable=False)  # 1-based, canonical order
    kerf_count = Column(Integer, nullable=False)
    used_length = Column(Integer, nullable=False)
    leftover = Column(Integer, nullable=False)

    plan = relationship("Plan", back_populates="rolls")
    cuts = relationship(
        "Cut",
        back_populates="roll",
        order_by="Cut.position",
        cascade="all, delete-orphan",
    )


class Cut(Base):
    __tablename__ = "cuts"

    id = Column(Integer, primary_key=True)
    roll_id = Column(
        Integer, ForeignKey("rolls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, nullable=False)  # 1-based cutting order
    segment_id = Column(String(32), nullable=False)
    length = Column(Integer, nullable=False)  # delivered length
    allowance = Column(Integer, nullable=False, default=0)  # end-trim allowance
    # Optional bundle id shared by segments that must stay on one roll.
    # NULL for unbundled segments and for every historical row.
    bundle = Column(String(32), nullable=True)
    # Null while the segment is still waiting to be cut; set when the
    # foreman records "complete this segment". Historical rows stay NULL.
    completed_at = Column(DateTime(timezone=True), nullable=True)

    roll = relationship("Roll", back_populates="cuts")
