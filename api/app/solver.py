"""Exact solver for the signal-wire roll cutting problem.

A roll holds a subset of segments. Each segment occupies its delivered
length plus its end-trim allowance (the actual cutting length) on the
roll. Adjacent segments inside a roll consume one kerf (saw cut) each;
the head and tail of a roll consume nothing. Segments are never split.

Objectives, applied in strict lexicographic order:

1. minimize the number of rolls used;
2. minimize total leftover material
   (note: total leftover == rolls * roll_length - sum(cut lengths)
    - kerf * (n - rolls), so once the roll count is fixed the total
    leftover is already determined);
3. tie-break for uniqueness: sort segment ids ascending inside each roll,
   sort the rolls lexicographically by their id sequences, then pick the
   overall lexicographically smallest plan.

With at most 12 segments an exact subset DP plus a greedy canonical
construction is both fast and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    sid: str
    length: int  # delivered length
    allowance: int = 0  # end-trim allowance

    @property
    def cut_length(self) -> int:
        """Actual length cut from the roll: delivered length + allowance."""
        return self.length + self.allowance


@dataclass(frozen=True)
class RollPlan:
    segment_ids: tuple[str, ...]  # cutting order: ids ascending
    lengths: tuple[int, ...]  # delivered lengths aligned with segment_ids
    allowances: tuple[int, ...]  # allowances aligned with segment_ids
    kerf_count: int  # len(segment_ids) - 1
    used_length: int  # sum(cut lengths) + kerf_width * kerf_count
    leftover: int  # roll_length - used_length


@dataclass(frozen=True)
class Solution:
    rolls: tuple[RollPlan, ...]  # already in canonical (sorted) order
    rolls_used: int
    total_kerf_count: int
    total_leftover: int


def solve(roll_length: int, kerf_width: int, segments: list[Segment]) -> Solution:
    if not segments:
        raise ValueError("at least one segment is required")
    for seg in segments:
        if seg.cut_length > roll_length:
            raise ValueError(
                f"segment {seg.sid!r} (cut length {seg.cut_length}) "
                f"exceeds roll length {roll_length}"
            )

    # Canonical index order: ids ascending.
    ordered = sorted(segments, key=lambda s: s.sid)
    ids = [s.sid for s in ordered]
    lens = [s.length for s in ordered]
    allows = [s.allowance for s in ordered]
    cuts = [s.cut_length for s in ordered]
    n = len(ordered)
    full = (1 << n) - 1

    # fits[mask]: can the segments in `mask` share one roll?
    fits = [False] * (1 << n)
    fits[0] = True
    sum_len = [0] * (1 << n)
    count = [0] * (1 << n)
    for mask in range(1, 1 << n):
        lsb = mask & -mask
        i = lsb.bit_length() - 1
        prev = mask ^ lsb
        sum_len[mask] = sum_len[prev] + cuts[i]
        count[mask] = count[prev] + 1
        fits[mask] = sum_len[mask] + kerf_width * (count[mask] - 1) <= roll_length

    # can[mask]: minimum number of rolls needed for the segments in `mask`.
    INF = n + 1
    can = [INF] * (1 << n)
    can[0] = 0
    for mask in range(1, 1 << n):
        best = INF
        sub = mask
        while sub:
            if fits[sub] and can[mask ^ sub] + 1 < best:
                best = can[mask ^ sub] + 1
            sub = (sub - 1) & mask
        can[mask] = best

    rolls_used = can[full]

    # Greedy canonical construction: the roll holding the smallest remaining
    # id always sorts first, so pick the lexicographically smallest feasible
    # id tuple for it such that the remainder still packs into left - 1 rolls.
    rolls: list[RollPlan] = []
    remaining = full
    left = rolls_used
    while remaining:
        lo = (remaining & -remaining).bit_length() - 1
        chosen = None
        for cand in _enum_candidates(remaining, lo):
            if fits[cand] and can[remaining ^ cand] <= left - 1:
                chosen = cand
                break
        if chosen is None:  # pragma: no cover - unreachable given the DP above
            raise RuntimeError("no feasible roll found during canonical construction")

        rids: list[str] = []
        rlens: list[int] = []
        rallows: list[int] = []
        bits = chosen
        while bits:
            lsb = bits & -bits
            i = lsb.bit_length() - 1
            rids.append(ids[i])
            rlens.append(lens[i])
            rallows.append(allows[i])
            bits ^= lsb

        kerf_count = len(rids) - 1
        used = (
            sum(length + allowance for length, allowance in zip(rlens, rallows))
            + kerf_width * kerf_count
        )
        rolls.append(
            RollPlan(
                segment_ids=tuple(rids),
                lengths=tuple(rlens),
                allowances=tuple(rallows),
                kerf_count=kerf_count,
                used_length=used,
                leftover=roll_length - used,
            )
        )
        remaining ^= chosen
        left -= 1

    return Solution(
        rolls=tuple(rolls),
        rolls_used=rolls_used,
        total_kerf_count=sum(r.kerf_count for r in rolls),
        total_leftover=sum(r.leftover for r in rolls),
    )


def _enum_candidates(mask: int, lo: int):
    """Yield subsets of `mask` containing bit `lo`, ordered by the
    lexicographic order of their ascending-id tuples."""
    base = 1 << lo
    yield base
    higher = mask & ~((1 << (lo + 1)) - 1)
    yield from _extend(base, higher)


def _extend(prefix: int, higher: int):
    bits = higher
    while bits:
        lsb = bits & -bits
        j = lsb.bit_length() - 1
        new_prefix = prefix | lsb
        yield new_prefix
        yield from _extend(new_prefix, higher & ~((1 << (j + 1)) - 1))
        bits ^= lsb
