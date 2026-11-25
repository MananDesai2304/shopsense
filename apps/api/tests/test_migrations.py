from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

# (column_name, udt_name, is_nullable) in table order, as spec 002a defines it.
EXPECTED_COLUMNS = [
    ("product_id", "int4", "NO"),
    ("name", "text", "NO"),
    ("product_class", "text", "YES"),
    ("category_hierarchy", "text", "YES"),
    ("category_path", "_text", "YES"),
    ("description", "text", "YES"),
    ("features_raw", "text", "NO"),
    ("features", "jsonb", "NO"),
    ("rating_count", "int4", "YES"),
    ("average_rating", "numeric", "YES"),
    ("review_count", "int4", "YES"),
]


def _columns(engine: Engine) -> list[dict]:
    query = text(
        """
        SELECT column_name, udt_name, is_nullable, numeric_precision, numeric_scale,
               column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'products'
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]


def test_migration_creates_products_table(migrated_db: Engine):
    cols = _columns(migrated_db)
    assert [
        (c["column_name"], c["udt_name"], c["is_nullable"]) for c in cols
    ] == EXPECTED_COLUMNS

    by_name = {c["column_name"]: c for c in cols}
    assert by_name["average_rating"]["numeric_precision"] == 2
    assert by_name["average_rating"]["numeric_scale"] == 1
    assert "'{}'::jsonb" in by_name["features"]["column_default"]

    pk = inspect(migrated_db).get_pk_constraint("products")
    assert pk["constrained_columns"] == ["product_id"]


def test_migration_downgrade_drops_products_table(
    migrated_db: Engine, alembic_cfg: Config
):
    assert inspect(migrated_db).has_table("products")

    command.downgrade(alembic_cfg, "base")

    assert not inspect(migrated_db).has_table("products")
