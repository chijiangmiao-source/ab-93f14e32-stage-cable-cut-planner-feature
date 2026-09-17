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


# ---------------------------------------------------------------------------
# Bundles: segments sharing a bundle id never split across rolls.
# ---------------------------------------------------------------------------


def test_bundle_packs_together_even_when_splitting_is_better():
    # Unconstrained optimum: [A,C],[B,D] (2 rolls). Bundling A with B
    # forces them together, so C and D can no longer share a roll.
    segs = [
        Segment("A", 40, bundle="G1"),
        Segment("B", 40, bundle="G1"),
        Segment("C", 50),
        Segment("D", 50),
    ]
    sol = solve(100, 10, segs)
    assert sol.rolls_used == 3
    assert ids_rolls(sol) == (("A", "B"), ("C",), ("D",))

    # The very same segments without bundles keep the legacy 2-roll plan.
    plain = solve(
        100,
        10,
        [Segment("A", 40), Segment("B", 40), Segment("C", 50), Segment("D", 50)],
    )
    assert plain.rolls_used == 2
    assert ids_rolls(plain) == (("A", "C"), ("B", "D"))


def test_bundle_roll_math_counts_allowance_and_internal_kerfs():
    sol = solve(
        100,
        10,
        [
            Segment("B", 35, 5, "G1"),
            Segment("A", 40, 0, "G1"),
            Segment("C", 50),
        ],
    )
    assert ids_rolls(sol) == (("A", "B"), ("C",))
    roll = sol.rolls[0]
    assert roll.bundles == ("G1", "G1")
    # cut lengths 40 + 40 (35+5) and one kerf inside the bundle
    assert roll.used_length == 40 + 40 + 10
    assert roll.leftover == 10
    assert sol.rolls[1].bundles == (None,)
    assert sol.total_kerf_count == 1


def test_bundle_shares_roll_with_independent_segments():
    # The whole bundle plus a loose segment fit one roll together.
    sol = solve(
        200,
        10,
        [Segment("A", 40, bundle="G"), Segment("B", 40, bundle="G"), Segment("C", 50)],
    )
    assert sol.rolls_used == 1
    assert ids_rolls(sol) == (("A", "B", "C"),)
    assert sol.rolls[0].bundles == ("G", "G", None)
    assert sol.rolls[0].used_length == 40 + 40 + 50 + 2 * 10


def test_single_member_bundle_behaves_like_unbundled():
    bundled = solve(100, 10, [Segment("A", 50, bundle="Solo"), Segment("B", 50)])
    plain = solve(100, 10, [Segment("A", 50), Segment("B", 50)])
    assert ids_rolls(bundled) == ids_rolls(plain)
    assert bundled.rolls[0].bundles == ("Solo",)


def test_unfittable_bundle_rejected():
    # 60 + 60 + one kerf of 10 = 130 > 100: the bundle can never fit.
    with pytest.raises(ValueError, match="bundle 'G9'"):
        solve(100, 10, [Segment("A", 60, bundle="G9"), Segment("B", 60, bundle="G9")])


def test_unfittable_bundle_rejected_even_with_allowance():
    # cut lengths 60 + 55 (50+5) + kerf 10 = 125 > 120
    with pytest.raises(ValueError):
        solve(
            120,
            10,
            [Segment("A", 60, bundle="G"), Segment("B", 50, 5, "G")],
        )


def test_bundle_ids_do_not_leak_across_groups():
    sol = solve(
        100,
        10,
        [
            Segment("A", 40, bundle="G1"),
            Segment("B", 40, bundle="G2"),
            Segment("C", 40, bundle="G1"),
            Segment("D", 40, bundle="G2"),
        ],
    )
    # G1 = {A, C}, G2 = {B, D}; each pair fits one roll (40+40+10).
    assert sol.rolls_used == 2
    assert ids_rolls(sol) == (("A", "C"), ("B", "D"))
    assert sol.rolls[0].bundles == ("G1", "G1")
    assert sol.rolls[1].bundles == ("G2", "G2")


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

    # Atomic units: segments sharing a bundle id move together.
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(segments):
        if s.bundle is not None:
            groups.setdefault(s.bundle, []).append(i)
    units = []
    grouped = set()
    for members in groups.values():
        units.append(frozenset(members))
        grouped.update(members)
    for i in range(n):
        if i not in grouped:
            units.append(frozenset({i}))

    def fits(block):
        return sum(cuts[i] for i in block) + kerf * (len(block) - 1) <= roll_length

    best_key = None
    best_canonical = None
    for unit_part in _partitions(len(units)):
        blocks = [
            frozenset().union(*(units[u] for u in block)) for block in unit_part
        ]
        if not all(fits(b) for b in blocks):
            continue
        canonical = tuple(sorted(tuple(sorted(ids[i] for i in b)) for b in blocks))
        key = (len(blocks), canonical)
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


@pytest.mark.parametrize("seed", range(60))
def test_matches_brute_force_with_bundles(seed):
    rng = random.Random(1000 + seed)
    n = rng.randint(2, 8)
    roll_length = rng.randint(30, 120)
    kerf = rng.randint(1, 20)
    segments = []
    for i in range(n):
        length = rng.randint(1, roll_length)
        allowance = rng.randint(0, roll_length - length)
        segments.append(Segment(f"S{i}", length, allowance))

    # Assign random bundles, then unbundle any group whose cut lengths plus
    # internal kerfs cannot fit one roll (the API rejects those with 422).
    names = ["G1", "G2", "G3"]
    bundled = [
        Segment(s.sid, s.length, s.allowance, rng.choice([None, None, *names]))
        for s in segments
    ]
    for name in names:
        members = [s for s in bundled if s.bundle == name]
        needed = sum(s.cut_length for s in members) + kerf * (len(members) - 1)
        if members and needed > roll_length:
            bundled = [
                Segment(
                    s.sid,
                    s.length,
                    s.allowance,
                    None if s.bundle == name else s.bundle,
                )
                for s in bundled
            ]
    # Guarantee every instance exercises at least one bundle: pair up the two
    # shortest segments whenever they can share a roll.
    if all(s.bundle is None for s in bundled):
        pair = sorted(bundled, key=lambda s: s.cut_length)[:2]
        if sum(s.cut_length for s in pair) + kerf <= roll_length:
            paired = {s.sid for s in pair}
            bundled = [
                Segment(
                    s.sid,
                    s.length,
                    s.allowance,
                    "GZ" if s.sid in paired else s.bundle,
                )
                for s in bundled
            ]

    sol = solve(roll_length, kerf, bundled)
    expected = _brute_force(roll_length, kerf, bundled)
    assert ids_rolls(sol) == expected
    assert sol.rolls_used == len(expected)
