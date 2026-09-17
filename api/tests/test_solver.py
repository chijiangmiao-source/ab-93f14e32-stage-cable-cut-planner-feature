"""Solver tests, including differential testing against a brute-force
enumeration of all set partitions."""

import random

import pytest

from app.solver import Segment, solve


def ids_rolls(solution):
    return tuple(roll.segment_ids for roll in solution.rolls)


def test_single_segment_no_kerf():
    sol = solve(1000, 10, [Segment("A", 400)])
    assert sol.rolls_used == 1
    assert sol.rolls[0].kerf_count == 0
    assert sol.rolls[0].leftover == 600
    assert sol.total_leftover == 600
    assert sol.total_kerf_count == 0


def test_kerf_forces_extra_roll():
    # 50 + 50 + kerf 30 = 130 > 100, so two rolls are needed even though
    # the raw lengths alone would fit in one roll.
    sol = solve(100, 30, [Segment("A", 50), Segment("B", 50)])
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A",), ("B",))
    assert sol.total_kerf_count == 0
    assert sol.total_leftover == 200 - 100  # 2 * 100 - 100


def test_exact_fit_with_kerf():
    # 600 + 390 + 1 kerf of 10 = 1000 exactly.
    sol = solve(1000, 10, [Segment("A", 600), Segment("B", 390)])
    assert sol.rolls_used == 1
    assert sol.rolls[0].kerf_count == 1
    assert sol.rolls[0].leftover == 0


def test_tie_break_picks_lexicographically_smallest():
    # Four equal wires, two per roll: {AB,CD} < {AC,BD} < {AD,BC}.
    sol = solve(
        100,
        5,
        [Segment("C", 40), Segment("A", 40), Segment("D", 40), Segment("B", 40)],
    )
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A", "B"), ("C", "D"))
    assert all(r.kerf_count == 1 for r in sol.rolls)
    assert all(r.leftover == 100 - 40 - 40 - 5 for r in sol.rolls)


def test_greedy_must_skip_singleton_when_remainder_infeasible():
    # (A,) is lexicographically smallest but leaves {B,C} unpackable in one
    # roll, so the first roll must grow.
    sol = solve(
        100,
        5,
        [Segment("A", 60), Segment("B", 90), Segment("C", 30)],
    )
    # A+B: 60+90+5 > 100; A+C: 60+30+5 <= 100; B+C: 90+30+5 > 100
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A", "C"), ("B",))


def test_roll_ids_sorted_and_rolls_sorted():
    sol = solve(
        1000,
        10,
        [Segment("W3", 300), Segment("W1", 100), Segment("W2", 200)],
    )
    assert ids_rolls(sol) == (("W1", "W2", "W3"),)


def test_total_leftover_identity():
    segs = [Segment(chr(ord("A") + i), 10 * (i + 1)) for i in range(6)]
    roll_length, kerf = 200, 7
    sol = solve(roll_length, kerf, segs)
    total = sum(s.length for s in segs)
    expected = sol.rolls_used * roll_length - total - kerf * (len(segs) - sol.rolls_used)
    assert sol.total_leftover == expected
    assert sol.total_leftover == sum(r.leftover for r in sol.rolls)
    assert sol.total_kerf_count == len(segs) - sol.rolls_used


def test_segment_equal_to_roll_length_fits_alone():
    sol = solve(500, 10, [Segment("A", 500), Segment("B", 1)])
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A",), ("B",))


def test_oversized_segment_rejected():
    with pytest.raises(ValueError):
        solve(100, 5, [Segment("A", 101)])


# ---------------------------------------------------------------------------
# End-trim allowance: the cut length (length + allowance) occupies the roll.
# ---------------------------------------------------------------------------


def test_allowance_counts_toward_capacity():
    # Cut lengths 60 and 50: 60 + 50 + 5 kerf = 115 > 110, so two rolls.
    # Without the allowance the same segments would share one roll (105 <= 110).
    segs = [Segment("A", 50, 10), Segment("B", 50)]
    assert solve(110, 5, segs).rolls_used == 2
    assert solve(110, 5, [Segment("A", 50), Segment("B", 50)]).rolls_used == 1


def test_allowance_exact_fit_with_kerf():
    # Cut lengths 500 + 490 plus one kerf of 10 fill the roll exactly.
    sol = solve(1000, 10, [Segment("A", 400, 100), Segment("B", 490)])
    assert sol.rolls_used == 1
    assert sol.rolls[0].kerf_count == 1
    assert sol.rolls[0].used_length == 1000
    assert sol.rolls[0].leftover == 0


def test_roll_plan_carries_delivered_lengths_and_allowances():
    sol = solve(1000, 10, [Segment("B", 300), Segment("A", 400, 50)])
    roll = sol.rolls[0]
    assert roll.segment_ids == ("A", "B")
    assert roll.lengths == (400, 300)  # delivered lengths, not cut lengths
    assert roll.allowances == (50, 0)
    assert roll.used_length == 400 + 50 + 300 + 10
    # Totals still close: leftover = rolls * roll_length - cuts - kerfs.
    assert sol.total_leftover == 1000 - 750 - 10


def test_oversized_cut_length_rejected():
    with pytest.raises(ValueError):
        solve(100, 5, [Segment("A", 100, 1)])


def test_twelve_segments_run_quickly():
    segs = [Segment(f"S{i:02d}", 97 + 3 * i) for i in range(12)]
    sol = solve(400, 11, segs)
    assert sol.rolls_used >= 3
    # every roll feasible and every segment delivered exactly once
    delivered = sorted(sid for r in sol.rolls for sid in r.segment_ids)
    assert delivered == sorted(s.sid for s in segs)
    for roll in sol.rolls:
        assert roll.used_length <= 400


# ---------------------------------------------------------------------------
# Kits: segments sharing a kit number are indivisible across rolls.
# ---------------------------------------------------------------------------


def test_kit_segments_stay_on_one_roll():
    # Without the kit the canonical packing is [A], [B,C] (A+C: 910 > 900;
    # B+C = 800 + 10 fits). The kit on A,B forbids that split: A+B fill
    # 400+300+10 = 710 on roll 1, C is alone on roll 2.
    segs = [
        Segment("A", 400, kit_no=7),
        Segment("B", 300, kit_no=7),
        Segment("C", 500),
    ]
    sol = solve(900, 10, segs)
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A", "B"), ("C",))
    assert sol.rolls[0].kit_nos == (7, 7)
    assert sol.rolls[1].kit_nos == (None,)
    # capacity closes with the internal kit kerf counted once
    assert sol.rolls[0].used_length == 400 + 300 + 10
    assert sol.rolls[0].leftover == 190


def test_kit_can_share_a_roll_with_independent_segments():
    # Kit AB occupies 20+20+5 = 45; adding C (50) costs one more kerf:
    # 45 + 50 + 5 = 100 exactly, so one roll suffices and the lex-tie-break
    # packs the independent segment together with the kit.
    segs = [
        Segment("A", 20, kit_no=1),
        Segment("B", 20, kit_no=1),
        Segment("C", 50),
    ]
    sol = solve(100, 5, segs)
    assert sol.rolls_used == 1
    assert ids_rolls(sol) == (("A", "B", "C"),)
    assert sol.rolls[0].kerf_count == 2
    assert sol.rolls[0].leftover == 0


def test_kit_forces_a_different_partition_than_unguided_packing():
    # Un-kitted, A=30,B=60,C=30,D=60 pack into two rolls: (A,B) and
    # (C,D) both cost 95. Kit {A,C} forbids that partition: A+C (65) must
    # share one roll and cannot take B or D along (65+60+5 > 100), while
    # B+D do not share either (60+60+5 > 100), so three rolls are needed.
    segs = [
        Segment("A", 30, kit_no=1),
        Segment("B", 60),
        Segment("C", 30, kit_no=1),
        Segment("D", 60),
    ]
    assert solve(100, 5, [Segment(s.sid, s.length) for s in segs]).rolls_used == 2
    sol = solve(100, 5, segs)
    assert sol.rolls_used == 3
    assert ids_rolls(sol) == (("A", "C"), ("B",), ("D",))
    # both kit members land on the very same roll, never split across rolls
    member_rolls = [r for r in ids_rolls(sol) if "A" in r or "C" in r]
    assert member_rolls == [("A", "C")]

    # With a longer roll the lexicographically smallest first roll absorbs B
    # into the kit's roll (A,B,C fills 30+60+30+2*5 = 130 exactly) and D is
    # left alone: still two rolls, kits never split.
    roomy = solve(130, 5, segs)
    assert roomy.rolls_used == 2
    assert ids_rolls(roomy) == (("A", "B", "C"), ("D",))


def test_multiple_kits_pack_independently():
    segs = [
        Segment("A", 40, kit_no=1),
        Segment("a", 40, kit_no=1),
        Segment("B", 40, kit_no=2),
        Segment("b", 40, kit_no=2),
    ]
    sol = solve(100, 5, segs)
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A", "a"), ("B", "b"))
    assert sol.rolls[0].kit_nos == (1, 1)
    assert sol.rolls[1].kit_nos == (2, 2)


def test_kit_counts_allowances_and_internal_kerfs():
    # A cut length 70 + B cut length 40 + 1 internal kerf of 10 = 120 > 100.
    with pytest.raises(ValueError, match="overflow 20"):
        solve(100, 10, [Segment("A", 60, 10, kit_no=3), Segment("B", 40, kit_no=3)])


def test_kit_plan_carries_kit_numbers_aligned_with_segments():
    # Kit AB occupies 450 + 300 + 10 = 760; C=400 cannot join (760+400+10
    # > 1000), so the kit takes one roll and C the other.
    segs = [
        Segment("B", 300, kit_no=7),
        Segment("A", 400, 50, kit_no=7),
        Segment("C", 400),
    ]
    sol = solve(1000, 10, segs)
    roll = next(r for r in sol.rolls if "A" in r.segment_ids)
    assert roll.segment_ids == ("A", "B")
    assert roll.lengths == (400, 300)
    assert roll.allowances == (50, 0)
    assert roll.kit_nos == (7, 7)
    other = next(r for r in sol.rolls if "C" in r.segment_ids)
    assert other.segment_ids == ("C",)
    assert other.kit_nos == (None,)


def test_un_kitted_segments_keep_none_kit_numbers():
    sol = solve(1000, 10, [Segment("B", 300), Segment("A", 400, 50)])
    assert all(kit is None for r in sol.rolls for kit in r.kit_nos)


def _brute_force_with_kits(roll_length, kerf, segments):
    """Brute force over atomic items: each kit is one indivisible item."""
    n = len(segments)
    ids = [s.sid for s in segments]
    cuts = [s.cut_length for s in segments]

    kit_of: dict[str, int] = {}
    for s in segments:
        if s.kit_no is not None:
            kit_of[s.sid] = s.kit_no
    kit_groups: dict[int, list[int]] = {}
    singletons: list[int] = []
    for i, s in enumerate(segments):
        if s.kit_no is None:
            singletons.append(i)
        else:
            kit_groups.setdefault(s.kit_no, []).append(i)
    # an item is a frozenset of segment indices
    items = [frozenset(idxs) for idxs in kit_groups.values()]
    items.extend(frozenset({i}) for i in singletons)
    k = len(items)

    def fits(member_idxs):
        return (
            sum(cuts[i] for i in member_idxs) + kerf * (len(member_idxs) - 1)
            <= roll_length
        )

    best_key = None
    best_canonical = None
    for part in _partitions(k):
        blocks = [frozenset(i for item in (items[j] for j in block) for i in item)
                  for block in part]
        if not all(fits(b) for b in blocks):
            continue
        canonical = tuple(sorted(tuple(sorted(ids[i] for i in b)) for b in blocks))
        key = (len(part), canonical)
        if best_key is None or key < best_key:
            best_key = key
            best_canonical = canonical
    return best_canonical


@pytest.mark.parametrize("seed", range(80))
def test_matches_brute_force_with_kits(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    roll_length = rng.randint(30, 120)
    kerf = rng.randint(1, 20)
    segments = []
    next_kit = 1
    for i in range(n):
        length = rng.randint(1, roll_length)
        allowance = rng.randint(0, roll_length - length)
        kit_no = None
        # 40% of segments join one of the existing small kits or open one.
        if i > 0 and rng.random() < 0.4:
            existing = sorted({s.kit_no for s in segments if s.kit_no is not None})
            if existing and rng.random() < 0.7:
                kit_no = rng.choice(existing)
            else:
                kit_no = next_kit
                next_kit += 1
        segments.append(Segment(f"S{i}", length, allowance, kit_no))
    expected = _brute_force_with_kits(roll_length, kerf, segments)
    if expected is None:
        # Some kit is infeasible on its own: the solver must say so too.
        with pytest.raises(ValueError, match="kit"):
            solve(roll_length, kerf, segments)
        return
    sol = solve(roll_length, kerf, segments)
    assert ids_rolls(sol) == expected
    assert sol.rolls_used == len(expected)


# ---------------------------------------------------------------------------
# Differential testing against brute force.
# ---------------------------------------------------------------------------

def _partitions(n):
    """Yield every set partition of range(n) as a list of frozensets."""
    if n == 0:
        yield []
        return
    for rest in _partitions(n - 1):
        yield rest + [frozenset({n - 1})]
        for i in range(len(rest)):
            yield rest[:i] + [rest[i] | {n - 1}] + rest[i + 1 :]


def _brute_force(roll_length, kerf, segments):
    n = len(segments)
    ids = [s.sid for s in segments]
    cuts = [s.cut_length for s in segments]

    def fits(block):
        return sum(cuts[i] for i in block) + kerf * (len(block) - 1) <= roll_length

    best_key = None
    best_canonical = None
    for part in _partitions(n):
        if not all(fits(b) for b in part):
            continue
        canonical = tuple(sorted(tuple(sorted(ids[i] for i in b)) for b in part))
        key = (len(part), canonical)
        if best_key is None or key < best_key:
            best_key = key
            best_canonical = canonical
    return best_canonical


@pytest.mark.parametrize("seed", range(60))
def test_matches_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    roll_length = rng.randint(30, 120)
    kerf = rng.randint(1, 20)
    segments = []
    for i in range(n):
        length = rng.randint(1, roll_length)
        # Random allowance, always keeping the segment deliverable.
        allowance = rng.randint(0, roll_length - length)
        segments.append(Segment(f"S{i}", length, allowance))
    sol = solve(roll_length, kerf, segments)
    expected = _brute_force(roll_length, kerf, segments)
    assert ids_rolls(sol) == expected
    assert sol.rolls_used == len(expected)
