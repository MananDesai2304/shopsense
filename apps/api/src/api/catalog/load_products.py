"""Load the WANDS product file into the products table (spec 002b).

Run: uv run --package api python -m api.catalog.load_products [path]
"""

import csv
import os
import sys
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import (
    Connection,
    Engine,
    MetaData,
    Table,
    create_engine,
    literal_column,
)
from sqlalchemy.dialects.postgresql import insert

HEADER = [
    "product_id",
    "product_name",
    "product_class",
    "category hierarchy",
    "product_description",
    "product_features",
    "rating_count",
    "average_rating",
    "review_count",
]


class LoadError(Exception):
    """The input file is malformed. The message starts with the line number."""


class LoadResult(NamedTuple):
    total: int
    inserted: int
    updated: int
    seconds: float


def parse_features(raw: str) -> dict[str, list[str]]:
    """Parse ``key:value|key : value|...`` into each key's distinct values, in order."""
    features: dict[str, list[str]] = {}
    for pair in raw.split("|"):
        key, colon, value = (part.strip() for part in pair.partition(":"))
        if colon and key and value not in (values := features.setdefault(key, [])):
            values.append(value)
    return features


def _number(value: str, line: int, column: str, whole: bool) -> int | Decimal | None:
    """Parse a count (``"69.0"`` -> 69) or a rating (``"4.5"``); empty -> None."""
    if not value:
        return None
    try:
        number = Decimal(value)
        if whole and number == number.to_integral_value():
            return int(number)
        if not whole and 0 <= number <= 5:
            return number
    except (InvalidOperation, OverflowError):  # not a number, NaN, or infinity
        pass
    raise LoadError(f"line {line}: bad {column}: {value!r}")


def parse_row(fields: list[str], line: int) -> dict:
    """Turn one data line into a products row. Empty nullable fields become None."""
    if len(fields) != len(HEADER):
        raise LoadError(f"line {line}: expected 9 columns, got {len(fields)}")
    pid, name, pclass, hierarchy, description, features, ratings, avg, reviews = fields
    if not (pid.isascii() and pid.isdigit()) or not name:
        raise LoadError(f"line {line}: bad product_id or empty name: {pid!r}")
    path = [part.strip() for part in hierarchy.split(" / ")] if hierarchy else None
    return {
        "product_id": int(pid),
        "name": name,
        "product_class": pclass or None,
        "category_hierarchy": hierarchy or None,
        "category_path": path,
        "description": description or None,
        "features_raw": features,
        "features": parse_features(features),
        "rating_count": _number(ratings, line, "rating_count", whole=True),
        "average_rating": _number(avg, line, "average_rating", whole=False),
        "review_count": _number(reviews, line, "review_count", whole=True),
    }


def _upsert(conn: Connection, products: Table, batch: list[dict]) -> int:
    """Insert or update one batch; return how many rows were new (``xmax = 0``)."""
    stmt = insert(products).values(batch)
    update = {c.name: stmt.excluded[c.name] for c in products.c if not c.primary_key}
    stmt = stmt.on_conflict_do_update(index_elements=["product_id"], set_=update)
    return sum(conn.execute(stmt.returning(literal_column("xmax = 0"))).scalars())


def load_products(
    path: Path,
    engine: Engine,
    *,
    batch_size: int = 1000,
    progress_every: int = 5000,
    out: Callable[[str], object] = print,
) -> LoadResult:
    """Upsert every row in one transaction; any error leaves the table unchanged."""
    started = time.perf_counter()
    seen: set[int] = set()
    inserted, batch = 0, []
    with path.open(encoding="utf-8", newline="") as f, engine.begin() as conn:
        reader = csv.reader(f, delimiter="\t")
        if (header := next(reader, None)) != HEADER:
            raise LoadError(f"line 1: header is not the 9 WANDS columns: {header}")
        products = Table("products", MetaData(), autoload_with=conn)
        for fields in reader:
            row = parse_row(fields, reader.line_num)
            if row["product_id"] in seen:
                raise LoadError(f"line {reader.line_num}: duplicate product_id")
            seen.add(row["product_id"])
            batch.append(row)
            if len(batch) == batch_size:
                inserted, batch = inserted + _upsert(conn, products, batch), []
            if len(seen) % progress_every == 0:
                out(f"  {len(seen)} rows")
        if batch:
            inserted += _upsert(conn, products, batch)
    total = len(seen)
    return LoadResult(total, inserted, total - inserted, time.perf_counter() - started)


def main(argv: list[str] | None = None, *, progress_every: int = 5000) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = next(p for p in Path(__file__).resolve().parents if (p / "uv.lock").exists())
    path = Path(args[0]) if args else root / "data" / "wands" / "product.csv"
    if not path.is_file():
        return _fail(f"product file not found: {path}")
    if not (url := os.environ.get("DATABASE_URL")):
        return _fail("DATABASE_URL is not set; see .env.example")
    engine = create_engine(url)
    try:
        r = load_products(path, engine, progress_every=progress_every)
    except (LoadError, csv.Error, UnicodeDecodeError) as exc:
        return _fail(str(exc))
    finally:
        engine.dispose()
    print(f"loaded {r.total} products (inserted {r.inserted}, ", end="")
    print(f"updated {r.updated}) in {r.seconds:.1f}s")
    return 0


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
