"""Startup migration support.

The first deployed release created tables directly with
``Base.metadata.create_all`` and had no migration metadata. This runner keeps
three situations working:

* a brand new database  -> build it through the whole migration chain;
* a legacy database (tables exist, no ``alembic_version``) -> stamp the
  baseline revision matching the live schema, then upgrade (historical cuts
  keep NULL ``completed_at`` because the column is added nullable);
* a migrated database -> ``upgrade head`` is a no-op.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

API_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = API_ROOT / "alembic.ini"

BASELINE_REVISION = "0001_baseline"
HEAD_REVISION = "0003_cut_kit_no"


def _config(connection) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # Share the application connection (vital for StaticPool in-memory
    # SQLite); migrations/env.py reads this attribute.
    cfg.attributes["connection"] = connection
    return cfg


def run_startup_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "plans" not in tables:
        with engine.begin() as conn:
            command.upgrade(_config(conn), "head")
        return

    if not {"plans", "rolls", "cuts"} <= tables:
        # A partially initialised legacy database can contain the plans table
        # without its child tables. Fill only the missing tables before
        # deciding which Alembic revision matches the live cuts schema.
        from .db import Base

        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

    if "alembic_version" not in tables:
        # Tests build the current model directly with create_all, and an old
        # release database predates migrations: tell Alembic which revision
        # the live schema already matches.
        cut_columns = {c["name"] for c in inspector.get_columns("cuts")}
        if "completed_at" not in cut_columns:
            stamp = BASELINE_REVISION
        elif "kit_no" not in cut_columns:
            stamp = "0002_cut_completed_at"
        else:
            stamp = HEAD_REVISION
        with engine.begin() as conn:
            command.stamp(_config(conn), stamp)

    with engine.begin() as conn:
        command.upgrade(_config(conn), "head")
