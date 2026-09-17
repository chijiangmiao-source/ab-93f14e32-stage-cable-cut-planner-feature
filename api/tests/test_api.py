def valid_payload(**overrides):
    payload = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 600},
            {"id": "B", "length": 590},
            {"id": "C", "length": 400},
        ],
    }
    payload.update(overrides)
    return payload


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_plan_persists_and_computes(client):
    resp = client.post("/api/plans", json=valid_payload())
    assert resp.status_code == 201
    plan = resp.json()
    # A: 600 alone (600+590+10 > 1000, 600+400+10 > 1000); B+C: 990+10 = 1000.
    assert plan["rolls_used"] == 2
    assert [r["position"] for r in plan["rolls"]] == [1, 2]
    assert [[s["id"] for s in r["segments"]] for r in plan["rolls"]] == [["A"], ["B", "C"]]
    assert [r["kerf_count"] for r in plan["rolls"]] == [0, 1]
    assert [r["leftover"] for r in plan["rolls"]] == [400, 0]
    assert plan["total_leftover"] == 400
    assert plan["total_kerf_count"] == 1

    # persisted and retrievable
    detail = client.get(f"/api/plans/{plan['id']}")
    assert detail.status_code == 200
    assert detail.json() == plan

    listing = client.get("/api/plans")
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()] == [plan["id"]]
    assert listing.json()[0]["segment_count"] == 3


def test_invalid_roll_length_rejected(client):
    resp = client.post("/api/plans", json=valid_payload(roll_length=0))
    assert resp.status_code == 422
    locs = [e["loc"] for e in resp.json()["detail"]]
    assert ["body", "roll_length"] in locs

    resp = client.post("/api/plans", json=valid_payload(roll_length=100001))
    assert resp.status_code == 422

    resp = client.post("/api/plans", json=valid_payload(kerf_width=0))
    assert resp.status_code == 422


def test_invalid_segment_length_rejected(client):
    payload = valid_payload()
    payload["segments"][1]["length"] = 0
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    assert ["body", "segments", 1, "length"] in [
        e["loc"] for e in resp.json()["detail"]
    ]


def test_duplicate_ids_located_and_not_persisted(client):
    payload = valid_payload()
    payload["segments"][2]["id"] = "A"
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(e["loc"] == ["segments", 2, "id"] for e in detail)
    assert client.get("/api/plans").json() == []


def test_segment_exceeding_roll_located_and_not_persisted(client):
    payload = valid_payload(roll_length=500)
    # A=600 and B=590 both exceed 500; C=400 fits.
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    locs = [e["loc"] for e in resp.json()["detail"]]
    assert ["segments", 0, "length"] in locs
    assert ["segments", 1, "length"] in locs
    assert ["segments", 2, "length"] not in locs
    assert client.get("/api/plans").json() == []


def test_too_many_segments_rejected(client):
    payload = valid_payload()
    payload["segments"] = [
        {"id": f"S{i}", "length": 10} for i in range(13)
    ]
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422


def test_missing_plan_404(client):
    assert client.get("/api/plans/999").status_code == 404


def test_ordinary_create_has_null_source_and_unchanged_semantics(client):
    resp = client.post("/api/plans", json=valid_payload())
    assert resp.status_code == 201
    plan = resp.json()
    # no source carried: ordinary creation, provenance stays null
    assert plan["source_plan_id"] is None

    detail = client.get(f"/api/plans/{plan['id']}").json()
    assert detail["source_plan_id"] is None
    assert detail == plan

    summary = client.get("/api/plans").json()[0]
    assert summary["source_plan_id"] is None
    assert "rolls" not in summary


def test_adjustment_carries_source_link_without_changing_solution(client):
    # original plan
    original = client.post("/api/plans", json=valid_payload()).json()

    # start an adjustment from the original: identical inputs, plus the link
    payload = valid_payload()
    payload["source_plan_id"] = original["id"]
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 201
    adjusted = resp.json()
    assert adjusted["id"] != original["id"]
    assert adjusted["source_plan_id"] == original["id"]

    # the solver consumes the edited inputs only: identical inputs must
    # produce identical rolls/kerfs/leftovers; provenance has no effect
    for key in (
        "roll_length",
        "kerf_width",
        "rolls_used",
        "total_kerf_count",
        "total_leftover",
        "rolls",
    ):
        assert adjusted[key] == original[key], key

    # both plans remain independently retrievable; the original stays
    # read-only and never points back at the adjustment
    original_detail = client.get(f"/api/plans/{original['id']}").json()
    assert original_detail["source_plan_id"] is None
    adjusted_detail = client.get(f"/api/plans/{adjusted['id']}").json()
    assert adjusted_detail["source_plan_id"] == original["id"]

    # the list summary carries provenance for the new plan only
    by_id = {p["id"]: p for p in client.get("/api/plans").json()}
    assert by_id[original["id"]]["source_plan_id"] is None
    assert by_id[adjusted["id"]]["source_plan_id"] == original["id"]


def test_edited_segment_recomputes_under_existing_rules(client):
    original = client.post("/api/plans", json=valid_payload()).json()
    assert original["rolls_used"] == 2  # [A], [B,C]
    assert [r["leftover"] for r in original["rolls"]] == [400, 0]

    # change one segment length: B 590 -> 380. The adjustment is re-solved
    # from the edited inputs; roll 2 recomputes to 380+400+10 = 790 (left 210).
    payload = valid_payload()
    payload["segments"][1]["length"] = 380
    payload["source_plan_id"] = original["id"]
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 201
    adjusted = resp.json()
    assert adjusted["source_plan_id"] == original["id"]
    assert adjusted["rolls_used"] == 2
    assert [[s["id"] for s in r["segments"]] for r in adjusted["rolls"]] == [
        ["A"],
        ["B", "C"],
    ]
    assert [r["leftover"] for r in adjusted["rolls"]] == [400, 210]
    assert adjusted["total_leftover"] == 610

    # the original plan stays as it was — provenance never mutates it
    original_detail = client.get(f"/api/plans/{original['id']}").json()
    assert [r["leftover"] for r in original_detail["rolls"]] == [400, 0]
    assert original_detail["total_leftover"] == 400


def test_invalid_source_rejected_with_located_error_and_not_persisted(client):
    payload = valid_payload()
    payload["source_plan_id"] = 999
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(e["loc"] == ["source_plan_id"] for e in detail)
    # no orphan link and no half-finished record
    assert client.get("/api/plans").json() == []


def test_invalid_source_and_invalid_segment_both_reported(client):
    # Endpoint-level checks are accumulated in one pass: a missing source and
    # a segment longer than the roll are reported together.
    payload = valid_payload(roll_length=500)
    payload["source_plan_id"] = 4242
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    locs = [e["loc"] for e in resp.json()["detail"]]
    assert ["source_plan_id"] in locs
    assert ["segments", 0, "length"] in locs
    assert client.get("/api/plans").json() == []


def test_non_positive_source_rejected_by_schema(client):
    payload = valid_payload()
    payload["source_plan_id"] = 0
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    assert client.get("/api/plans").json() == []


def test_chains_of_adjustments_keep_direct_source(client):
    first = client.post("/api/plans", json=valid_payload()).json()
    second_payload = valid_payload()
    second_payload["source_plan_id"] = first["id"]
    second = client.post("/api/plans", json=second_payload).json()

    third_payload = valid_payload()
    third_payload["source_plan_id"] = second["id"]
    third = client.post("/api/plans", json=third_payload).json()

    # only the directly named source is stored (no derived semantics)
    assert second["source_plan_id"] == first["id"]
    assert third["source_plan_id"] == second["id"]
    assert client.get(f"/api/plans/{first['id']}").json()["source_plan_id"] is None
# ---------------------------------------------------------------------------
# End-trim allowance (端头加工余量)
# ---------------------------------------------------------------------------


def test_allowance_omitted_matches_legacy_behavior(client):
    # Old clients send no allowance: the plan must be identical to the
    # pre-allowance behavior, with allowance reported as 0.
    resp = client.post("/api/plans", json=valid_payload())
    assert resp.status_code == 201
    plan = resp.json()
    assert plan["rolls_used"] == 2
    assert [[s["id"] for s in r["segments"]] for r in plan["rolls"]] == [
        ["A"],
        ["B", "C"],
    ]
    assert [r["leftover"] for r in plan["rolls"]] == [400, 0]
    assert all(
        s["allowance"] == 0 for r in plan["rolls"] for s in r["segments"]
    )

    # Explicit zeros must produce exactly the same plan.
    payload = valid_payload()
    for seg in payload["segments"]:
        seg["allowance"] = 0
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 201
    again = resp.json()
    assert [[s["id"] for s in r["segments"]] for r in again["rolls"]] == [
        ["A"],
        ["B", "C"],
    ]
    assert again["total_leftover"] == plan["total_leftover"]


def test_allowance_changes_packing_and_detail_closes(client):
    # C's allowance pushes its cut length to 450, so B+C (590+450+10) no
    # longer fits one roll: the packing changes from 2 rolls to 3.
    payload = valid_payload()
    payload["segments"][2]["allowance"] = 50
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 201
    plan = resp.json()
    assert plan["rolls_used"] == 3
    assert [[s["id"] for s in r["segments"]] for r in plan["rolls"]] == [
        ["A"],
        ["B"],
        ["C"],
    ]
    # Roll math closes on cut lengths: sum(length+allowance) + kerfs + leftover
    # == roll_length for every roll.
    for roll in plan["rolls"]:
        cut_sum = sum(s["length"] + s["allowance"] for s in roll["segments"])
        assert roll["used_length"] == cut_sum + roll["kerf_count"] * plan["kerf_width"]
        assert roll["used_length"] + roll["leftover"] == plan["roll_length"]
    assert [r["leftover"] for r in plan["rolls"]] == [400, 410, 550]
    assert plan["total_leftover"] == 1360
    # The allowance is persisted and returned by the detail endpoint.
    assert plan["rolls"][2]["segments"][0]["allowance"] == 50

    detail = client.get(f"/api/plans/{plan['id']}")
    assert detail.status_code == 200
    assert detail.json() == plan


def test_allowance_out_of_range_rejected_and_not_persisted(client):
    for bad in (-1, 10001):
        payload = valid_payload()
        payload["segments"][1]["allowance"] = bad
        resp = client.post("/api/plans", json=payload)
        assert resp.status_code == 422
        locs = [e["loc"] for e in resp.json()["detail"]]
        assert ["body", "segments", 1, "allowance"] in locs
    assert client.get("/api/plans").json() == []


def test_length_plus_allowance_exceeding_roll_located_at_allowance(client):
    payload = valid_payload(roll_length=500)
    payload["segments"] = [
        {"id": "A", "length": 400, "allowance": 150},  # 550 > 500: allowance's fault
        {"id": "B", "length": 600, "allowance": 10},  # 600 > 500: length's fault
        {"id": "C", "length": 450, "allowance": 50},  # 500 <= 500: fits exactly
    ]
    resp = client.post("/api/plans", json=payload)
    assert resp.status_code == 422
    locs = [e["loc"] for e in resp.json()["detail"]]
    assert ["segments", 0, "allowance"] in locs
    assert ["segments", 1, "length"] in locs
    # C fits, so no error points at it at all.
    assert all(loc[1] != 2 for loc in locs if len(loc) == 3)
    assert client.get("/api/plans").json() == []
