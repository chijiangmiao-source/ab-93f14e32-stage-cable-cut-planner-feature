import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./plans.db")

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL or DATABASE_URL in ("sqlite://", "sqlite:///"):
        # Keep a single shared connection so an in-memory database survives
        # across sessions (used by the test suite).
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def run_migrations():
    """Apply compatibility upgrades that predate the Alembic chain.

    ``Base.metadata.create_all`` creates missing tables but never alters an
    existing one. The provenance link stays NULL for historical plans, and
    historical cuts receive allowance 0 so their packing remains unchanged.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "plans" in tables:
        columns = {c["name"] for c in inspector.get_columns("plans")}
        if "source_plan_id" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE plans ADD COLUMN source_plan_id INTEGER "
                        "REFERENCES plans(id) ON DELETE SET NULL"
                    )
                )
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_plans_source_plan_id "
                         "ON plans (source_plan_id)")
                )

    if "cuts" in tables:
        columns = {c["name"] for c in inspector.get_columns("cuts")}
        if "allowance" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE cuts "
                        "ADD COLUMN allowance INTEGER NOT NULL DEFAULT 0"
                    )
                )
