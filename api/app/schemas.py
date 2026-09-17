from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MIN_LEN = 1
MAX_LEN = 100000
MIN_ALLOWANCE = 0
MAX_ALLOWANCE = 10000
MAX_SEGMENTS = 12
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$"


class SegmentIn(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    length: int = Field(ge=MIN_LEN, le=MAX_LEN)
    # Optional end-trim allowance; omitted means 0 (legacy clients).
    allowance: int = Field(default=0, ge=MIN_ALLOWANCE, le=MAX_ALLOWANCE)


class PlanCreate(BaseModel):
    roll_length: int = Field(ge=MIN_LEN, le=MAX_LEN)
    kerf_width: int = Field(ge=MIN_LEN, le=MAX_LEN)
    segments: list[SegmentIn] = Field(min_length=1, max_length=MAX_SEGMENTS)
    # Optional provenance: when present it must reference an existing plan.
    # It never participates in solving; omitted means an ordinary new plan.
    source_plan_id: int | None = Field(default=None, ge=1)


class SegmentOut(BaseModel):
    id: str
    length: int
    allowance: int
    # None while the segment is waiting to be cut; old plans keep None.
    completed_at: datetime | None = None


class RollOut(BaseModel):
    position: int
    segments: list[SegmentOut]
    kerf_count: int
    used_length: int
    leftover: int
    completed_count: int = 0


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    roll_length: int
    kerf_width: int
    rolls_used: int
    total_kerf_count: int
    total_leftover: int
    completed_segment_count: int = 0
    created_at: datetime
    source_plan_id: int | None = None
    rolls: list[RollOut]


class CutAction(BaseModel):
    # The cut position (1-based, canonical order) the page believes it is
    # acting on. The server rejects anything other than the true next/last
    # position with 409 so stale pages cannot advance progress blindly.
    position: int = Field(ge=1)


class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    roll_length: int
    kerf_width: int
    segment_count: int
    rolls_used: int
    total_kerf_count: int
    total_leftover: int
    created_at: datetime
    source_plan_id: int | None = None
