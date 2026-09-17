"""One-shot acceptance checks against the running Docker Compose stack.

Exercises the real integration path: browser-facing nginx (web) -> FastAPI
(api) -> PostgreSQL. Exits 0 only if every check passes.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("API_URL", "http://api:8000").rstrip("/")
WEB_URL = os.environ.get("WEB_URL", "http://web:80").rstrip("/")

failures: list[str] = []


def _decode(raw):
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw


def request(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, _decode(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, _decode(exc.read().decode())


def check(name, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}"
          + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def locs_of(body):
    if isinstance(body, dict):
        return [e.get("loc") for e in body.get("detail", []) if isinstance(e, dict)]
    return []


def wait_for(name, url, attempts=90):
    for _ in range(attempts):
        try:
            status, _ = request("GET", url)
            if status == 200:
                print(f"[ OK ] {name} healthy at {url}")
                return True
        except Exception:
            pass
        time.sleep(1)
    print(f"[FAIL] {name} never became healthy at {url}")
    return False


def main():
    ok = wait_for("api", f"{API_URL}/api/health")
    ok = wait_for("web", f"{WEB_URL}/") and ok
    if not ok:
        sys.exit(1)

    # --- invalid input: 422 with field locations, nothing persisted ---------
    dup = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 100},
            {"id": "A", "length": 200},
        ],
    }
    status, body = request("POST", f"{WEB_URL}/api/plans", dup)
    check("duplicate id -> 422 via web proxy", status == 422, str(body))
    check("duplicate id error locates the segment",
          ["segments", 1, "id"] in locs_of(body), str(body))

    oversized = {
        "roll_length": 500,
        "kerf_width": 10,
        "segments": [{"id": "BIG", "length": 600}],
    }
    status, body = request("POST", f"{API_URL}/api/plans", oversized)
    check("oversized segment -> 422", status == 422, str(body))
    check("oversized error locates segment length",
          ["segments", 0, "length"] in locs_of(body), str(body))

    status, plans = request("GET", f"{API_URL}/api/plans")
    check("nothing persisted after invalid submissions",
          status == 200 and plans == [], str(plans))

    # --- kerf accounting: 50 + 50 + 30 kerf > 100 forces two rolls ----------
    case1 = {
        "roll_length": 100,
        "kerf_width": 30,
        "segments": [
            {"id": "X", "length": 50},
            {"id": "Y", "length": 50},
        ],
    }
    status, plan1 = request("POST", f"{WEB_URL}/api/plans", case1)
    check("kerf case created", status == 201 and isinstance(plan1, dict), str(plan1))
    if not isinstance(plan1, dict):
        sys.exit(1)
    check("kerf case uses 2 rolls", plan1.get("rolls_used") == 2, str(plan1))
    check("kerf case total leftover is 100",
          plan1.get("total_leftover") == 100, str(plan1))

    # --- canonical tie-break: [[A,B],[C,D]] ----------------------------------
    case2 = {
        "roll_length": 100,
        "kerf_width": 5,
        "segments": [{"id": c, "length": 40} for c in ("C", "A", "D", "B")],
    }
    status, plan2 = request("POST", f"{WEB_URL}/api/plans", case2)
    check("tie-break case created", status == 201 and isinstance(plan2, dict), str(plan2))
    if not isinstance(plan2, dict):
        sys.exit(1)
    got = [[s["id"] for s in r["segments"]] for r in plan2.get("rolls", [])]
    check("tie-break order is [[A,B],[C,D]]", got == [["A", "B"], ["C", "D"]], str(got))
    check("tie-break kerf counts are [1, 1]",
          [r["kerf_count"] for r in plan2.get("rolls", [])] == [1, 1])
    check("tie-break leftovers are [15, 15]",
          [r["leftover"] for r in plan2.get("rolls", [])] == [15, 15])

    # --- every roll recomputes by hand ---------------------------------------
    for roll in plan2.get("rolls", []):
        total = (sum(s["length"] for s in roll["segments"])
                 + roll["kerf_count"] * plan2["kerf_width"]
                 + roll["leftover"])
        check(f"roll {roll['position']} recomputes: segments + kerfs + leftover = roll length",
              total == plan2["roll_length"])

    # --- persistence: detail and list endpoints ------------------------------
    status, fetched = request("GET", f"{WEB_URL}/api/plans/{plan2['id']}")
    check("detail endpoint returns the persisted plan",
          status == 200 and fetched == plan2)

    status, plans = request("GET", f"{API_URL}/api/plans")
    ids = [p["id"] for p in plans] if status == 200 and isinstance(plans, list) else []
    check("plan list contains both created plans",
          plan1["id"] in ids and plan2["id"] in ids, str(ids))

    # ordinary creation carries no provenance link and keeps old semantics
    check("ordinary plan 1 has no source", plan1.get("source_plan_id") is None,
          str(plan1.get("source_plan_id")))
    check("ordinary plan 2 has no source", plan2.get("source_plan_id") is None,
          str(plan2.get("source_plan_id")))
    ordinary = plans[[p["id"] for p in plans].index(plan2["id"])]
    check("ordinary plan summary has no source and unchanged fields",
          ordinary.get("source_plan_id") is None
          and ordinary.get("segment_count") == 4
          and "rolls" not in ordinary, str(ordinary))

    # --- adjustment from a saved plan ----------------------------------------
    source_payload = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 600},
            {"id": "B", "length": 590},
            {"id": "C", "length": 400},
        ],
    }
    status, source_plan = request("POST", f"{WEB_URL}/api/plans", source_payload)
    check("source plan created for adjustment",
          status == 201 and isinstance(source_plan, dict), str(source_plan))
    if not isinstance(source_plan, dict):
        sys.exit(1)
    source_id = source_plan["id"]
    check("source plan has no provenance of its own",
          source_plan.get("source_plan_id") is None, str(source_plan))
    check("source plan result is [A] / [B,C]",
          [[s["id"] for s in r["segments"]] for r in source_plan["rolls"]]
          == [["A"], ["B", "C"]], str(source_plan))

    # start the adjustment carrying the source id; edit one segment (B 590 -> 380)
    adjusted_payload = {
        "roll_length": 1000,
        "kerf_width": 10,
        "source_plan_id": source_id,
        "segments": [
            {"id": "A", "length": 600},
            {"id": "B", "length": 380},
            {"id": "C", "length": 400},
        ],
    }
    status, adjusted = request("POST", f"{WEB_URL}/api/plans", adjusted_payload)
    check("adjustment created with source link",
          status == 201 and isinstance(adjusted, dict), str(adjusted))
    if not isinstance(adjusted, dict):
        sys.exit(1)
    adjusted_id = adjusted["id"]
    check("adjustment is a distinct new plan", adjusted_id != source_id,
          f"{adjusted_id} vs {source_id}")
    check("adjustment stores the source id",
          adjusted.get("source_plan_id") == source_id, str(adjusted))

    # the solver consumes edited inputs only: roll 2 recomputes to
    # 380+400+10 = 790 (leftover 210), total leftover 610; roll count still 2
    check("adjustment re-solves from the edited segment",
          adjusted["rolls_used"] == 2
          and [r["leftover"] for r in adjusted["rolls"]] == [400, 210]
          and adjusted["total_leftover"] == 610, str(adjusted))

    # old and new are each retrievable; the source link target resolves
    status, adjusted_detail = request("GET", f"{API_URL}/api/plans/{adjusted_id}")
    check("adjusted plan retrievable", status == 200 and adjusted_detail == adjusted)
    status, source_detail = request("GET", f"{WEB_URL}/api/plans/{source_id}")
    check("source link jumps to the original plan",
          status == 200 and source_detail.get("id") == source_id, str(status))
    check("original plan stays unchanged and read-only after adjustment",
          source_detail == source_plan
          and [r["leftover"] for r in source_detail["rolls"]] == [400, 0],
          "original mutated")

    # history list shows provenance for the adjustment only
    status, plans = request("GET", f"{API_URL}/api/plans")
    by_id = {p["id"]: p for p in plans}
    check("list summary links adjustment to source",
          by_id[adjusted_id]["source_plan_id"] == source_id, str(by_id[adjusted_id]))
    check("list summary leaves the source without provenance",
          by_id[source_id]["source_plan_id"] is None, str(by_id[source_id]))

    # --- invalid source: located 422, edits preserved server-side as no row --
    before_ids = {p["id"] for p in plans}
    bad_source = dict(adjusted_payload)
    bad_source["source_plan_id"] = 999999
    status, body = request("POST", f"{WEB_URL}/api/plans", bad_source)
    check("invalid source -> 422", status == 422, str(body))
    check("invalid source error locates source_plan_id",
          ["source_plan_id"] in locs_of(body), str(body))
    status, plans_after = request("GET", f"{API_URL}/api/plans")
    after_ids = {p["id"] for p in plans_after}
    check("invalid source creates no orphan link or half record",
          after_ids == before_ids, f"{before_ids} -> {after_ids}")

    # an omitted source still follows the ordinary flow
    status, ordinary_plan = request("POST", f"{API_URL}/api/plans", source_payload)
    check("source-less creation still works",
          status == 201 and ordinary_plan.get("source_plan_id") is None,
          str(ordinary_plan))
    # --- cutting progress: ordered completion, last-only undo, conflicts ------
    pid = plan2["id"]

    def action(kind, roll, position, base):
        return request("POST", f"{base}/api/plans/{pid}/rolls/{roll}/{kind}",
                       {"position": position})

    def completed(plan, roll):
        r = next(x for x in plan["rolls"] if x["position"] == roll)
        return [s["id"] for s in r["segments"] if s["completed_at"] is not None]

    # fresh plans start with no progress and canonical order intact
    check("new plan has zero completed segments",
          plan2.get("completed_segment_count") == 0, str(plan2.get("completed_segment_count")))

    status, after_a = action("complete", 1, 1, WEB_URL)  # A first on roll 1
    check("complete first cut -> 200", status == 200 and completed(after_a, 1) == ["A"],
          str(status))
    check("completion timestamp persisted",
          after_a["rolls"][0]["segments"][0]["completed_at"] is not None)
    check("other roll untouched by completion",
          completed(after_a, 2) == [])

    # out-of-order completion (B is next, but a stale page asks for nothing else
    # than the front pending cut): re-asking for the already-done position conflicts
    status, body = action("complete", 1, 1, API_URL)
    check("re-complete the done cut -> 409 conflict", status == 409, str(body))

    status, after_b = action("complete", 1, 2, API_URL)  # B is now next
    check("complete second cut in order -> 200",
          status == 200 and completed(after_b, 1) == ["A", "B"], str(status))

    status, after_c = action("complete", 2, 1, WEB_URL)  # C first on roll 2
    check("rolls progress independently",
          status == 200 and completed(after_c, 2) == ["C"]
          and completed(after_c, 1) == ["A", "B"], str(status))

    # non-last undo (A while A,B are done on roll 1) is rejected, data unchanged
    status, body = action("undo", 1, 1, API_URL)
    check("undo of a non-last cut -> 409 conflict", status == 409, str(body))
    status, unchanged = request("GET", f"{API_URL}/api/plans/{pid}")
    check("data unchanged after rejected undo",
          completed(unchanged, 1) == ["A", "B"] and completed(unchanged, 2) == ["C"])

    # only the last completed cut of the roll (B) can be undone
    status, undone = action("undo", 1, 2, WEB_URL)
    check("undo last cut -> 200 and only that cut is cleared",
          status == 200 and completed(undone, 1) == ["A"]
          and completed(undone, 2) == ["C"], str(status))

    # solution figures and canonical order are independent of progress
    status, final = request("GET", f"{WEB_URL}/api/plans/{pid}")
    check("progress never changes the solution or canonical order",
          status == 200
          and [[s["id"] for s in r["segments"]] for r in final["rolls"]]
              == [["A", "B"], ["C", "D"]]
          and [r["kerf_count"] for r in final["rolls"]] == [1, 1]
          and [r["leftover"] for r in final["rolls"]] == [15, 15])

    # unknown plan / roll are 404; missing position is 422
    status, _ = request("POST", f"{API_URL}/api/plans/999999/rolls/1/complete",
                        {"position": 1})
    check("progress on unknown plan -> 404", status == 404, str(status))
    status, body = action("complete", 99, 1, WEB_URL)
    check("progress on unknown roll -> 404", status == 404, str(status))
    status, _ = request("POST", f"{API_URL}/api/plans/{pid}/rolls/1/complete", {})
    check("missing position -> 422", status == 422, str(status))

    # --- allowance: omission keeps the legacy plan ---------------------------
    # case1/case2 above already omitted the field; an explicit zero must
    # produce the identical packing.
    case3 = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 600},
            {"id": "B", "length": 590},
            {"id": "C", "length": 400},
        ],
    }
    status, plan3 = request("POST", f"{API_URL}/api/plans", case3)
    check("no-allowance case created", status == 201 and isinstance(plan3, dict), str(plan3))
    if not isinstance(plan3, dict):
        sys.exit(1)
    check("omitted allowance keeps the legacy packing [[A],[B,C]]",
          [[s["id"] for s in r["segments"]] for r in plan3.get("rolls", [])]
          == [["A"], ["B", "C"]],
          str(plan3.get("rolls")))
    check("omitted allowance is reported as 0",
          all(s.get("allowance") == 0
              for r in plan3.get("rolls", []) for s in r["segments"]))

    # --- allowance: changes the packing, detail recomputes, persists ---------
    case4 = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 600},
            {"id": "B", "length": 590},
            {"id": "C", "length": 400, "allowance": 50},
        ],
    }
    status, plan4 = request("POST", f"{WEB_URL}/api/plans", case4)
    check("allowance case created", status == 201 and isinstance(plan4, dict), str(plan4))
    if not isinstance(plan4, dict):
        sys.exit(1)
    # C's cut length becomes 450, so B + C (590 + 450 + 10) no longer fits:
    # the packing grows from 2 rolls to 3.
    check("allowance changes the packing to [[A],[B],[C]]",
          [[s["id"] for s in r["segments"]] for r in plan4.get("rolls", [])]
          == [["A"], ["B"], ["C"]],
          str(plan4.get("rolls")))
    check("allowance case leftovers recompute from cut lengths",
          [r["leftover"] for r in plan4.get("rolls", [])] == [400, 410, 550],
          str(plan4.get("rolls")))
    check("allowance persisted on the segment",
          plan4["rolls"][2]["segments"][0].get("allowance") == 50, str(plan4))
    for roll in plan4.get("rolls", []):
        cut_sum = sum(s["length"] + s["allowance"] for s in roll["segments"])
        total = cut_sum + roll["kerf_count"] * plan4["kerf_width"] + roll["leftover"]
        check(f"allowance roll {roll['position']} closes: cut lengths + kerfs + leftover = roll length",
              total == plan4["roll_length"] and roll["used_length"] + roll["leftover"] == plan4["roll_length"])

    status, fetched4 = request("GET", f"{WEB_URL}/api/plans/{plan4['id']}")
    check("allowance plan detail survives a refetch unchanged",
          status == 200 and fetched4 == plan4)

    # --- allowance: invalid submissions are located and not persisted --------
    status, before = request("GET", f"{API_URL}/api/plans")
    before_count = len(before) if status == 200 and isinstance(before, list) else -1

    bad_range = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [{"id": "A", "length": 100, "allowance": 10001}],
    }
    status, body = request("POST", f"{API_URL}/api/plans", bad_range)
    check("allowance > 10000 -> 422", status == 422, str(body))
    check("allowance range error locates the allowance input",
          ["body", "segments", 0, "allowance"] in locs_of(body)
          or ["segments", 0, "allowance"] in locs_of(body), str(body))

    bad_sum = {
        "roll_length": 500,
        "kerf_width": 10,
        "segments": [{"id": "A", "length": 400, "allowance": 150}],
    }
    status, body = request("POST", f"{WEB_URL}/api/plans", bad_sum)
    check("length + allowance > roll -> 422", status == 422, str(body))
    check("cut-length overflow locates the allowance input",
          ["segments", 0, "allowance"] in locs_of(body), str(body))

    status, after = request("GET", f"{API_URL}/api/plans")
    after_count = len(after) if status == 200 and isinstance(after, list) else -1
    check("invalid allowance submissions persisted nothing",
          before_count >= 0 and after_count == before_count,
          f"before={before_count} after={after_count}")

    # --- kits: omitted field keeps the legacy plan ---------------------------
    legacy_kit_payload = {
        "roll_length": 900,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 400},
            {"id": "B", "length": 300},
            {"id": "C", "length": 500},
        ],
    }
    status, legacy_kit_plan = request("POST", f"{API_URL}/api/plans", legacy_kit_payload)
    check("no-kit case created", status == 201 and isinstance(legacy_kit_plan, dict),
          str(legacy_kit_plan))
    if isinstance(legacy_kit_plan, dict):
        check("no-kit request keeps the independent packing [[A],[B,C]]",
              [[s["id"] for s in r["segments"]] for r in legacy_kit_plan["rolls"]]
              == [["A"], ["B", "C"]], str(legacy_kit_plan.get("rolls")))
        check("no-kit cuts report null kit numbers",
              all(s.get("kit_no") is None
                  for r in legacy_kit_plan["rolls"] for s in r["segments"]))

    # --- kits: a fittable kit never spans rolls; capacity closes -------------
    kit_payload = {
        "roll_length": 900,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 400, "kit_no": 7},
            {"id": "B", "length": 300, "kit_no": 7},
            {"id": "C", "length": 500},
        ],
    }
    status, kit_plan = request("POST", f"{WEB_URL}/api/plans", kit_payload)
    check("fittable kit plan created via the web proxy",
          status == 201 and isinstance(kit_plan, dict), str(kit_plan))
    if not isinstance(kit_plan, dict):
        sys.exit(1)
    check("fittable kit never spans rolls: [[A,B],[C]]",
          [[s["id"] for s in r["segments"]] for r in kit_plan["rolls"]]
          == [["A", "B"], ["C"]], str(kit_plan.get("rolls")))
    check("kit members carry the kit number, independent segment is null",
          [s["kit_no"] for s in kit_plan["rolls"][0]["segments"]] == [7, 7]
          and [s["kit_no"] for s in kit_plan["rolls"][1]["segments"]] == [None],
          str(kit_plan))
    for roll in kit_plan["rolls"]:
        cut_sum = sum(s["length"] + s.get("allowance", 0) for s in roll["segments"])
        total = cut_sum + roll["kerf_count"] * kit_plan["kerf_width"] + roll["leftover"]
        check(f"kit roll {roll['position']} capacity recomputes and closes",
              total == kit_plan["roll_length"]
              and roll["used_length"] + roll["leftover"] == kit_plan["roll_length"],
              str(roll))
    check("kit internal kerf counted once on the shared roll",
          kit_plan["rolls"][0]["used_length"] == 400 + 300 + 10
          and kit_plan["rolls"][0]["leftover"] == 190, str(kit_plan["rolls"][0]))

    # refresh the detail (as the page does after reload): same roll order and
    # the same kit markers survive
    status, kit_refetch = request("GET", f"{WEB_URL}/api/plans/{kit_plan['id']}")
    check("kit plan detail keeps the same roll order and kit numbers after refresh",
          status == 200 and kit_refetch == kit_plan, str(status))

    # --- kits: an unfittable kit is located on every member and not saved ----
    status, plans_before_kit_fail = request("GET", f"{API_URL}/api/plans")
    before_kit_ids = {p["id"] for p in plans_before_kit_fail}
    bad_kit = {
        "roll_length": 1000,
        "kerf_width": 10,
        "segments": [
            {"id": "A", "length": 600, "kit_no": 3},
            {"id": "B", "length": 590, "kit_no": 3},
            {"id": "C", "length": 400},
        ],
    }
    status, body = request("POST", f"{WEB_URL}/api/plans", bad_kit)
    check("unfittable kit -> 422", status == 422, str(body))
    check("unfittable kit error locates every member kit input",
          ["segments", 0, "kit_no"] in locs_of(body)
          and ["segments", 1, "kit_no"] in locs_of(body)
          and ["segments", 2, "kit_no"] not in locs_of(body), str(body))
    overflow_msgs = [e.get("msg", "") for e in body.get("detail", [])
                     if isinstance(e, dict) and e.get("loc", [None])[-1] == "kit_no"]
    check("unfittable kit error states the overflow in millimetres",
          len(overflow_msgs) == 2
          and all("needs 1200 mm" in m and "overflows by 200 mm" in m
                  for m in overflow_msgs), str(overflow_msgs))
    status, plans_after_kit_fail = request("GET", f"{API_URL}/api/plans")
    after_kit_ids = {p["id"] for p in plans_after_kit_fail}
    check("unfittable kit submission persisted no plan",
          after_kit_ids == before_kit_ids,
          f"{before_kit_ids} -> {after_kit_ids}")

    print()
    if failures:
        print(f"VERIFY FAILED: {len(failures)} check(s) failed")
        sys.exit(1)
    print("VERIFY PASSED: all acceptance checks succeeded")


if __name__ == "__main__":
    main()
