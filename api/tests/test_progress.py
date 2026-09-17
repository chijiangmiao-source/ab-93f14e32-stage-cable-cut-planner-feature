"""Cutting-progress endpoints: ordered completion, last-only undo, and the
409 conflicts that must leave every row untouched."""

from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.migrations import run_startup_migrations


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


def make_plan(client):
    resp = client.post("/api/plans", json=valid_payload())
    assert resp.status_code == 201
    return resp.json()


def complete(client, plan_id, roll_position, position):
    return client.post(
        f"/api/plans/{plan_id}/rolls/{roll_position}/complete",
        json={"position": position},
    )


def undo(client, plan_id, roll_position, position):
    return client.post(
        f"/api/plans/{plan_id}/rolls/{roll_position}/undo",
        json={"position": position},
    )


def completed_ids(plan):
    out = {}
    for roll in plan["rolls"]:
        out[roll["position"]] = [
            s["id"] for s in roll["segments"] if s["completed_at"] is not None
        ]
    return out


def test_new_plan_starts_without_any_progress(client):
    plan = make_plan(client)
    assert plan["completed_segment_count"] == 0
    for roll in plan["rolls"]:
        assert roll["completed_count"] == 0
        assert all(s["completed_at"] is None for s in roll["segments"])
    # canonical solution fields are unaffected by progress tracking
    assert [[s["id"] for s in r["segments"]] for r in plan["rolls"]] == [
        ["A"],
        ["B", "C"],
    ]


def test_completion_advances_in_canonical_order_and_persists(client):
    plan = make_plan(client)
    pid = plan["id"]

    resp = complete(client, pid, 2, 1)  # first cut of roll 2 is B
    assert resp.status_code == 200
    updated = resp.json()
    assert completed_ids(updated) == {1: [], 2: ["B"]}
    assert updated["rolls"][1]["completed_count"] == 1
    assert updated["rolls"][0]["completed_count"] == 0
    assert updated["completed_segment_count"] == 1
    b = updated["rolls"][1]["segments"][0]
    assert b["completed_at"] is not None
    assert datetime.fromisoformat(b["completed_at"].replace("Z", "+00:00"))
    # the other roll is untouched
    assert updated["rolls"][0]["segments"][0]["completed_at"] is None

    # persisted: a fresh GET shows exactly the same progress
    fetched = client.get(f"/api/plans/{pid}").json()
    assert fetched == updated

    # advance again: C is next on roll 2
    resp = complete(client, pid, 2, 2)
    assert resp.status_code == 200
    assert completed_ids(resp.json()) == {1: [], 2: ["B", "C"]}
    assert resp.json()["completed_segment_count"] == 2

    # roll 1 progresses independently
    resp = complete(client, pid, 1, 1)
    assert resp.status_code == 200
    assert completed_ids(resp.json()) == {1: ["A"], 2: ["B", "C"]}
    assert resp.json()["completed_segment_count"] == 3


def test_out_of_order_completion_conflicts_and_changes_nothing(client):
    plan = make_plan(client)
    pid = plan["id"]

    resp = complete(client, pid, 2, 2)  # C before B
    assert resp.status_code == 409

    fetched = client.get(f"/api/plans/{pid}").json()
    assert fetched["completed_segment_count"] == 0
    assert completed_ids(fetched) == {1: [], 2: []}


def test_stale_page_recompleting_done_cut_conflicts(client):
    plan = make_plan(client)
    pid = plan["id"]
    assert complete(client, pid, 2, 1).status_code == 200

    # stale page still offers position 1 as the next cut
    resp = complete(client, pid, 2, 1)
    assert resp.status_code == 409

    fetched = client.get(f"/api/plans/{pid}").json()
    assert completed_ids(fetched) == {1: [], 2: ["B"]}


def test_completing_finished_roll_conflicts(client):
    plan = make_plan(client)
    pid = plan["id"]
    assert complete(client, pid, 1, 1).status_code == 200  # roll 1 has one cut

    resp = complete(client, pid, 1, 2)
    assert resp.status_code == 409
    assert completed_ids(client.get(f"/api/plans/{pid}").json()) == {
        1: ["A"],
        2: [],
    }


def test_undo_only_removes_last_completed_cut(client):
    plan = make_plan(client)
    pid = plan["id"]
    complete(client, pid, 2, 1)
    complete(client, pid, 2, 2)

    # undoing B (not the last) is rejected and changes nothing
    resp = undo(client, pid, 2, 1)
    assert resp.status_code == 409
    assert completed_ids(client.get(f"/api/plans/{pid}").json()) == {
        1: [],
        2: ["B", "C"],
    }

    # only the last cut (C) can be undone
    resp = undo(client, pid, 2, 2)
    assert resp.status_code == 200
    assert completed_ids(resp.json()) == {1: [], 2: ["B"]}
    assert resp.json()["completed_segment_count"] == 1

    # now B is the last completed cut and can be undone
    resp = undo(client, pid, 2, 1)
    assert resp.status_code == 200
    assert completed_ids(resp.json()) == {1: [], 2: []}
    assert all(
        s["completed_at"] is None
        for r in resp.json()["rolls"]
        for s in r["segments"]
    )


def test_undo_with_any_completed_cut_conflicts(client):
    plan = make_plan(client)
    pid = plan["id"]
    resp = undo(client, pid, 2, 1)
    assert resp.status_code == 409
    assert client.get(f"/api/plans/{pid}").json()["completed_segment_count"] == 0


def test_undo_stale_position_conflicts(client):
    plan = make_plan(client)
    pid = plan["id"]
    complete(client, pid, 2, 1)
    complete(client, pid, 2, 2)
    complete(client, pid, 2, 2)  # already finished -> 409, ignored

    # stale page believes position 1 is still the last completed
    assert undo(client, pid, 2, 1).status_code == 409
    assert completed_ids(client.get(f"/api/plans/{pid}").json()) == {
        1: [],
        2: ["B", "C"],
    }


def test_progress_does_not_change_solution_fields(client):
    plan = make_plan(client)
    pid = plan["id"]
    complete(client, pid, 2, 1)
    after = client.get(f"/api/plans/{pid}").json()

    for key in (
        "roll_length",
        "kerf_width",
        "rolls_used",
        "total_kerf_count",
        "total_leftover",
    ):
        assert after[key] == plan[key]
    assert [r["kerf_count"] for r in after["rolls"]] == [0, 1]
    assert [r["used_length"] for r in after["rolls"]] == [600, 1000]
    assert [r["leftover"] for r in after["rolls"]] == [400, 0]
    assert [
        [(s["id"], s["length"]) for s in r["segments"]] for r in after["rolls"]
    ] == [[("A", 600)], [("B", 590), ("C", 400)]]


def test_unknown_plan_and_roll_are_404(client):
    make_plan(client)
    assert complete(client, 999, 1, 1).status_code == 404
    assert undo(client, 999, 1, 1).status_code == 404

    plan = make_plan(client)
    assert complete(client, plan["id"], 99, 1).status_code == 404
    assert undo(client, plan["id"], 99, 1).status_code == 404


def test_missing_position_is_422(client):
    plan = make_plan(client)
    resp = client.post(f"/api/plans/{plan['id']}/rolls/1/complete", json={})
    assert resp.status_code == 422


# --- migrations -------------------------------------------------------------

LEGACY_SCHEMA_SQL = """
CREATE TABLE plans (
    id INTEGER PRIMARY KEY,
    roll_length INTEGER NOT NULL,
    kerf_width INTEGER NOT NULL,
    segment_count INTEGER NOT NULL,
    rolls_used INTEGER NOT NULL,
    total_kerf_count INTEGER NOT NULL,
    total_leftover INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE rolls (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kerf_count INTEGER NOT NULL,
    used_length INTEGER NOT NULL,
    leftover INTEGER NOT NULL
);
CREATE TABLE cuts (
    id INTEGER PRIMARY KEY,
    roll_id INTEGER NOT NULL REFERENCES rolls(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    segment_id VARCHAR(32) NOT NULL,
    length INTEGER NOT NULL
);
"""


def test_migration_upgrades_legacy_database_keeping_history_unfinished(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy = create_engine(f"sqlite:///{db_path}")
    with legacy.begin() as conn:
        for stmt in LEGACY_SCHEMA_SQL.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.execute(
            text(
                "INSERT INTO plans VALUES (1, 1000, 10, 1, 1, 0, 900, "
                "'2026-01-01 00:00:00')"
            )
        )
        conn.execute(text("INSERT INTO rolls VALUES (1, 1, 1, 0, 100, 900)"))
        conn.execute(text("INSERT INTO cuts VALUES (1, 1, 1, 'A', 100)"))

    run_startup_migrations(legacy)

    columns = {c["name"] for c in inspect(legacy).get_columns("cuts")}
    assert "completed_at" in columns
    # the nullable kit column is added too; historical cuts keep NULL
    assert "kit_no" in columns
    with legacy.connect() as conn:
        completed_at = conn.execute(text("SELECT completed_at FROM cuts")).scalar()
        assert completed_at is None  # historical records stay unfinished
        kit_no = conn.execute(text("SELECT kit_no FROM cuts")).scalar()
        assert kit_no is None  # historical cuts belong to no kit
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert revision == "0003_cut_kit_no"


def test_migration_builds_fresh_database(tmp_path):
    fresh = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    run_startup_migrations(fresh)
    tables = set(inspect(fresh).get_table_names())
    assert {"plans", "rolls", "cuts", "alembic_version"} <= tables
    assert "completed_at" in {
        c["name"] for c in inspect(fresh).get_columns("cuts")
    }


def test_migration_stamps_0002_schema_then_adds_kit_column(tmp_path):
    # An old release built the schema through 0002 (cuts.completed_at
    # exists) but never recorded an alembic version, and it predates the
    # kit column. Startup must stamp 0002 first, then upgrade to 0003.
    db_path = tmp_path / "at0002.db"
    old = create_engine(f"sqlite:///{db_path}")
    with old.begin() as conn:
        for stmt in LEGACY_SCHEMA_SQL.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.execute(text("ALTER TABLE cuts ADD COLUMN completed_at DATETIME"))
        conn.execute(
            text(
                "INSERT INTO plans VALUES (1, 1000, 10, 1, 1, 0, 900, "
                "'2026-01-01 00:00:00')"
            )
        )
        conn.execute(text("INSERT INTO rolls VALUES (1, 1, 1, 0, 100, 900)"))
        conn.execute(
            text("INSERT INTO cuts (id, roll_id, position, segment_id, length) "
                 "VALUES (1, 1, 1, 'A', 100)")
        )

    run_startup_migrations(old)
    cut_cols = {c["name"] for c in inspect(old).get_columns("cuts")}
    assert "completed_at" in cut_cols
    assert "kit_no" in cut_cols
    with old.connect() as conn:
        assert conn.execute(text("SELECT kit_no FROM cuts")).scalar() is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003_cut_kit_no"


def test_migration_is_idempotent_on_current_database():
    # An in-memory database built straight from the current models (as the
    # test fixture does) must be recognised and never double-migrated.
    from app.db import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    run_startup_migrations(engine)
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "0003_cut_kit_no"
        )
