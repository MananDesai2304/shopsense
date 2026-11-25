"""Shared database fixtures: a throwaway Postgres (testcontainers) with Alembic migrations.

These need Docker. If Docker is not running, the tests that use them fail rather than skip.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg16", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def engine(postgres_url: str) -> Iterator[Engine]:
    eng = create_engine(postgres_url)
    yield eng
    eng.dispose()


@pytest.fixture
def alembic_cfg(postgres_url: str) -> Config:
    cfg = Config(ALEMBIC_INI)
    # configparser treats % as interpolation, so escape it.
    cfg.set_main_option("sqlalchemy.url", postgres_url.replace("%", "%%"))
    return cfg


@pytest.fixture
def migrated_db(alembic_cfg: Config, engine: Engine) -> Iterator[Engine]:
    """An empty, fully migrated schema; torn back down to base after each test."""
    command.upgrade(alembic_cfg, "head")
    yield engine
    command.downgrade(alembic_cfg, "base")
