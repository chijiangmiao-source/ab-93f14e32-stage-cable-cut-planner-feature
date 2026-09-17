"""The provenance column must be addable to a database created by an older
release: existing plans keep working and their source stays NULL.
"""

import os

# Must be set before any app module is imported so the engine picks it up.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy import inspect, text

from app.db import Base, engine, run_migrations


# Legacy DDL, exactly as the previous release created the plans table.
LEGACY_PLANS_DDL = """
CREATE TABLE plans (
    id INTEGER NOT NULL PRIMARY KEY,
    roll_length INTEGER NOT NULL,
    kerf_width INTEGER NOT NULL,
    segment_count INTEGER NOT NULL,
    rolls_used INTEGER NOT NULL,
    total_kerf_count INTEGER NOT NULL,
    total_leftover INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# Legacy rolls/cuts as the previous release had them: cuts carries allowance
# and completed_at but no bundle column yet.
LEGACY_ROLLS_DDL = """
CREATE TABLE rolls (
    id INTEGER NOT NULL PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kerf_count INTEGER NOT NULL,
    used_length INTEGER NOT NULL,
    leftover INTEGER NOT NULL
)
"""

LEGACY_CUTS_DDL = """
CREATE TABLE cuts (
    id INTEGER NOT NULL PRIMARY KEY,
    roll_id INTEGER NOT NULL REFERENCES rolls(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    segment_id VARCHAR(32) NOT NULL,
    length INTEGER NOT NULL,
    allowance INTEGER NOT NULL DEFAULT 0,
    completed_at DATETIME
)
"""


@pytest.fixture
def legacy_db():
    # Build a database containing only the old-schema plans table.
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(LEGACY_PLANS_DDL))
    yield
    Base.metadata.drop_all(bind=engine)


def test_migration_adds_nullable_source_to_legacy_schema(legacy_db):
    cols = {c["name"] for c in inspect(engine).get_columns("plans")}
    assert "source_plan_id" not in cols

    # Seed a legacy row directly (NOT NULL columns only, as the old app did).
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plans (roll_length, kerf_width, segment_count, "
                "rolls_used, total_kerf_count, total_leftover, created_at) "
                "VALUES (1000, 10, 3, 2, 1, 400, '2026-09-01 00:00:00+00')"
            )
        )

    # Startup upgrade path; running it twice must be a no-op.
    run_migrations()
    run_migrations()

    cols = {c["name"] for c in inspect(engine).get_columns("plans")}
    assert "source_plan_id" in cols

    # Every pre-existing plan has an empty provenance link...
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id, source_plan_id FROM plans")).first()
    assert row is not None
    assert row.source_plan_id is None

    # ...and normal access patterns (list/detail) are unaffected.
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        listing = client.get("/api/plans").json()
        assert [p["id"] for p in listing] == [row.id]
        assert listing[0]["source_plan_id"] is None
        detail = client.get(f"/api/plans/{row.id}")
        assert detail.status_code == 200
        assert detail.json()["source_plan_id"] is None


@pytest.fixture
def legacy_cuts_db():
    # Build a database whose cuts table predates the bundle column.
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(LEGACY_PLANS_DDL))
        conn.execute(text(LEGACY_ROLLS_DDL))
        conn.execute(text(LEGACY_CUTS_DDL))
    yield
    Base.metadata.drop_all(bind=engine)


def test_migration_adds_nullable_bundle_to_legacy_cuts(legacy_cuts_db):
    cols = {c["name"] for c in inspect(engine).get_columns("cuts")}
    assert "bundle" not in cols

    # Seed one historical plan/roll/cut exactly as the old app did.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plans (id, roll_length, kerf_width, segment_count, "
                "rolls_used, total_kerf_count, total_leftover, created_at) "
                "VALUES (1, 1000, 10, 1, 1, 0, 900, '2026-09-01 00:00:00+00')"
            )
        )
        conn.execute(
            text("INSERT INTO rolls (id, plan_id, position, kerf_count, "
                 "used_length, leftover) VALUES (1, 1, 1, 0, 100, 900)")
        )
        conn.execute(
            text("INSERT INTO cuts (id, roll_id, position, segment_id, length, "
                 "allowance, completed_at) VALUES (1, 1, 1, 'A', 100, 0, NULL)")
        )

    # Startup upgrade path; running it twice must be a no-op.
    run_migrations()
    run_migrations()

    cols = {c["name"] for c in inspect(engine).get_columns("cuts")}
    assert "bundle" in cols

    # The historical cut has no bundle...
    with engine.begin() as conn:
        row = conn.execute(text("SELECT segment_id, bundle FROM cuts")).first()
    assert row is not None
    assert row.bundle is None

    # ...and the detail endpoint reports it as an ordinary unbundled segment.
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        detail = client.get("/api/plans/1")
        assert detail.status_code == 200
        segment = detail.json()["rolls"][0]["segments"][0]
        assert segment["id"] == "A"
        assert segment["bundle"] is None
