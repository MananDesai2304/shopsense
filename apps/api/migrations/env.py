"""Alembic environment: online migrations only, URL from config or DATABASE_URL."""

import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

config = context.config


def database_url() -> str:
    # Tests set sqlalchemy.url on the Config; everything else uses the environment.
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; see .env.example")
    return url


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
