import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

# Make the `app` package importable regardless of the current working dir.
API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401  (register metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # Programmatic callers may pass the engine/URL explicitly; otherwise fall
    # back to the same environment variable app.db uses.
    configured = config.get_main_option("sqlalchemy.url")
    return configured or os.getenv("DATABASE_URL", "sqlite:///./plans.db")


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # app.migrations shares the application engine (important for the
    # StaticPool in-memory SQLite used by tests).
    shared = config.attributes.get("connection")
    if shared is not None:
        _configure(shared)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(_url())
    with connectable.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
