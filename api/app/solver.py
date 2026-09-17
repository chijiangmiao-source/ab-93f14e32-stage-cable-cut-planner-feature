"""Exact solver for the signal-wire roll cutting problem.

A roll holds a subset of segments. Each segment occupies its delivered
length plus its end-trim allowance (the actual cutting length) on the
roll. Adjacent segments inside a roll consume one kerf (saw cut) each;
the head and tail of a roll consume nothing. Segments are never split.

Segments may share an optional kit number (套组编号): every segment of
the same kit forms one indivisible group that must be placed on a single
roll (a kit can never span two rolls). Segments without a kit number are
packed independently as before. A kit is feasible on its own only when
its cut lengths plus the kerfs *between its own segments* fit one roll;
inside a shared roll the kerfs between neighbours are counted exactly as
for independent segments.

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
construction is both fast and deterministic. Kitted segments are first
merged into atomic "items", so the DP runs over at most 12 items; with
no kits at all every item is a singleton segment and the result is
byte-for-byte the legacy packing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    sid: str
    length: int  # delivered length
    allowance: int = 0  # end-trim allowance
    # Optional kit number: segments sharing a kit must land on the same
    # roll. None (also the legacy default) packs the segment on its own.
    kit_no: int | None = None

    @property
    def cut_length(self) -> int:
        """Actual length cut from the roll: delivered length + allowance."""
        return self.length + self.allowance


@dataclass(frozen=True)
class RollPlan:
    segment_ids: tuple[str, ...]  # cutting order: ids ascending
    lengths: tuple[int, ...]  # delivered lengths aligned with segment_ids
    allowances: tuple[int, ...]  # allowances aligned with segment_ids
    # Kit numbers aligned with segment_ids; None for independently packed
    # segments and for every historical cut.
    kit_nos: tuple[int | None, ...]
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
    kits = [s.kit_no for s in ordered]
    cuts = [s.cut_length for s in ordered]
    n = len(ordered)

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

    # Merge kitted segments into atomic items (bit masks over segments):
    # each kit becomes one indivisible item; every un-kitted segment stays
    # a singleton item. Items are ordered by their smallest member id so
    # the canonical construction keeps addressing "the smallest remaining
    # id" exactly as in the legacy solver.
    kit_masks: dict[int, int] = {}
    for i, kit in enumerate(kits):
        if kit is not None:
            kit_masks[kit] = kit_masks.get(kit, 0) | (1 << i)
    item_masks: list[int] = list(kit_masks.values())
    kitted_bits = 0
    for bits in kit_masks.values():
        kitted_bits |= bits
    for i in range(n):
        if not ((kitted_bits >> i) & 1):
            item_masks.append(1 << i)
    item_masks.sort(key=lambda bits: (bits & -bits).bit_length() - 1)
    m = len(item_masks)

    # A whole kit must be placeable on one roll by itself (its cut lengths
    # plus the kerfs between its own segments). A singleton item can never
    # fail here because the per-segment check above already passed.
    for kit, bits in kit_masks.items():
        if not fits[bits]:
            needed = sum_len[bits] + kerf_width * (count[bits] - 1)
            raise ValueError(
                f"kit {kit} needs {needed} mm in one roll but the roll "
                f"length is {roll_length} mm (overflow {needed - roll_length} mm)"
            )

    full_items = (1 << m) - 1

    # For every subset of items: the unioned segment mask, whether that
    # union fits one roll, and the ascending-id tuple used as the canonical
    # sort key of the roll it would form.
    union_of = [0] * (1 << m)
    item_fits = [False] * (1 << m)
    item_key: list[tuple[str, ...]] = [()] * (1 << m)
    item_fits[0] = True
    for sub in range(1, 1 << m):
        lsb = sub & -sub
        j = lsb.bit_length() - 1
        prev = sub ^ lsb
        mask = union_of[prev] | item_masks[j]
        union_of[sub] = mask
        item_fits[sub] = fits[mask]
        key: list[str] = []
        bits = mask
        while bits:
            seg_lsb = bits & -bits
            i = seg_lsb.bit_length() - 1
            key.append(ids[i])
            bits ^= seg_lsb
        item_key[sub] = tuple(key)

    # can[mask]: minimum number of rolls needed for the items in `mask`.
    INF = m + 1
    can = [INF] * (1 << m)
    can[0] = 0
    for mask in range(1, 1 << m):
        best = INF
        sub = mask
        while sub:
            if item_fits[sub] and can[mask ^ sub] + 1 < best:
                best = can[mask ^ sub] + 1
            sub = (sub - 1) & mask
        can[mask] = best

    rolls_used = can[full_items]

    # Greedy canonical construction: the item holding the smallest
    # remaining id always sorts first, so pick the lexicographically
    # smallest feasible roll (by the roll's ascending segment-id tuple)
    # such that the remainder still packs into left - 1 rolls.
    rolls: list[RollPlan] = []
    remaining = full_items
    left = rolls_used
    while remaining:
        lo = (remaining & -remaining).bit_length() - 1
        base = 1 << lo
        higher = remaining ^ base
        candidates: list[int] = []
        sub = higher
        while True:
            candidates.append(base | sub)
            if sub == 0:
                break
            sub = (sub - 1) & higher
        candidates.sort(key=lambda cand: item_key[cand])

        chosen = None
        for cand in candidates:
            if item_fits[cand] and can[remaining ^ cand] <= left - 1:
                chosen = cand
                break
        if chosen is None:  # pragma: no cover - unreachable given the DP above
            raise RuntimeError("no feasible roll found during canonical construction")

        rids: list[str] = []
        rlens: list[int] = []
        rallows: list[int] = []
        rkits: list[int | None] = []
        bits = union_of[chosen]
        while bits:
            seg_lsb = bits & -bits
            i = seg_lsb.bit_length() - 1
            rids.append(ids[i])
            rlens.append(lens[i])
            rallows.append(allows[i])
            rkits.append(kits[i])
            bits ^= seg_lsb

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
                kit_nos=tuple(rkits),
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
