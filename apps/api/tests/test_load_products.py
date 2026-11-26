"""Tests for the WANDS product loader (spec 002b). Criterion numbers refer to the spec."""

import csv
import re
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from api.catalog.load_products import (
    HEADER,
    LoadError,
    load_products,
    main,
    parse_features,
)

FIXTURE = Path(__file__).parent / "fixtures" / "products_sample.tsv"
WANDS_FILE = Path(__file__).parents[3] / "data" / "wands" / "product.csv"


def _load(engine: Engine, path: Path = FIXTURE, **kwargs):
    return load_products(path, engine, out=lambda _: None, **kwargs)


def _rows(engine: Engine) -> dict[int, dict]:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM products"))
        return {row.product_id: dict(row._mapping) for row in result}


def _line(pid: str = "100", rating_count: str = "3.0") -> str:
    fields = [pid, "test chair", "Chairs", "Furniture", "a chair", "color:red"]
    return "\t".join([*fields, rating_count, "4.0", "3.0"])


def _write(tmp_path: Path, header: list[str], *lines: str) -> Path:
    path = tmp_path / "products.tsv"
    path.write_text("\n".join(["\t".join(header), *lines]) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def loaded(migrated_db: Engine) -> dict[int, dict]:
    _load(migrated_db)
    return _rows(migrated_db)


def test_load_inserts_all_rows(migrated_db: Engine):  # 1
    data_lines = len(FIXTURE.read_text(encoding="utf-8").splitlines()) - 1
    result = _load(migrated_db)
    rows = _rows(migrated_db)
    assert result.total == result.inserted == len(rows) == data_lines
    assert sorted(rows) == list(range(data_lines))


def test_empty_fields_become_null(loaded):  # 2
    assert loaded[1]["product_class"] is None
    assert loaded[1]["category_hierarchy"] is None
    assert loaded[2]["description"] is None
    ratings = ("rating_count", "average_rating", "review_count")
    assert [loaded[2][column] for column in ratings] == [None, None, None]


def test_rating_columns_are_typed(loaded):  # 3
    assert loaded[1]["rating_count"] == 69 and type(loaded[1]["rating_count"]) is int
    assert loaded[0]["average_rating"] == Decimal("4.5")


def test_quoted_category_is_unescaped(loaded):  # 4
    tail = 'Bar (28"-33") Bar Stools & Counter Stools'
    assert loaded[3]["category_hierarchy"].endswith(" / " + tail)
    assert loaded[3]["category_path"][-1] == tail


def test_category_path_split(loaded):  # 5
    assert loaded[0]["category_path"] == [
        "Furniture",
        "Bedroom Furniture",
        "Beds & Headboards",
        "Beds",
        "Twin Beds",
    ]
    assert len(loaded[3]["category_path"]) == 6
    assert loaded[4]["category_path"] == ["Rugs"]
    assert loaded[5]["category_path"] == ["Outdoor", "Patio Furniture", "Patio Seating"]
    assert loaded[1]["category_path"] is None


def test_features_raw_preserved(loaded):  # 6, plus the parsed JSONB round trip
    with FIXTURE.open(encoding="utf-8", newline="") as f:
        source = {int(r[0]): r[5] for r in list(csv.reader(f, delimiter="\t"))[1:]}
    assert {pid: row["features_raw"] for pid, row in loaded.items()} == source
    assert loaded[0]["features"] == {
        "mattresssize": ["queen", "twin"],
        "color": ["brown"],
    }
    assert loaded[4]["features"] == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            "mattresssize:queen|mattresssize : twin|mattresssize:queen",
            {"mattresssize": ["queen", "twin"]},
            id="groups_duplicate_keys",  # 7
        ),
        pytest.param(
            "color:red|:orphan| : blank|warranty:1 year parts| labor not covered",
            {"color": ["red"], "warranty": ["1 year parts"]},
            id="drops_empty_keys_and_fragments",  # 8
        ),
        pytest.param(
            "time:10:30", {"time": ["10:30"]}, id="splits_on_first_colon"
        ),  # 9
    ],
)
def test_parse_features(raw: str, expected: dict[str, list[str]]):
    assert parse_features(raw) == expected


def test_load_twice_is_idempotent(migrated_db: Engine):  # 10
    first = _load(migrated_db)
    second = _load(migrated_db)
    assert (second.total, second.inserted, second.updated) == (
        first.total,
        0,
        first.total,
    )
    assert len(_rows(migrated_db)) == first.total


def test_reload_updates_changed_row(migrated_db: Engine, tmp_path: Path):  # 11
    _load(migrated_db)
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("solid wood platform bed", "solid oak platform bed")
    changed = _write(tmp_path, HEADER, *lines[1:])
    result = _load(migrated_db, changed)
    rows = _rows(migrated_db)
    assert rows[0]["name"] == "solid oak platform bed"
    assert (result.inserted, len(rows)) == (0, len(lines) - 1)


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        pytest.param("101\tshort row", "expected 9 columns", id="wrong_column_count"),
        pytest.param(_line("101", "many"), "rating_count", id="non_numeric_count"),
        pytest.param(_line("101", "2.5"), "rating_count", id="non_whole_count"),
        pytest.param(_line("x1"), "product_id", id="bad_id"),
        pytest.param(_line("2147483648"), "product_id", id="id_out_of_range"),
        pytest.param(_line("101", "-3.0"), "rating_count", id="negative_count"),
    ],
)
def test_bad_row_aborts_without_writing(  # 12
    migrated_db: Engine, tmp_path: Path, bad: str, reason: str
):
    _load(migrated_db)
    before = _rows(migrated_db)
    # batch_size=1 writes the good row before the bad one, so this proves the rollback.
    path = _write(tmp_path, HEADER, _line(), bad)
    with pytest.raises(LoadError, match=rf"^line 3: .*{reason}"):
        _load(migrated_db, path, batch_size=1)
    assert _rows(migrated_db) == before


def test_wrong_header_aborts(migrated_db: Engine, tmp_path: Path):  # 13
    path = _write(tmp_path, [*HEADER[:-1], "reviews"], _line())
    with pytest.raises(LoadError, match="^line 1: header"):
        _load(migrated_db, path)
    assert _rows(migrated_db) == {}


def test_missing_file_exits_1(tmp_path: Path, capsys):  # 14
    assert main([str(tmp_path / "missing.csv")]) == 1
    captured = capsys.readouterr()
    assert "product file not found" in captured.err and captured.out == ""


def test_cli_prints_progress_and_summary(  # 15
    migrated_db: Engine, postgres_url: str, monkeypatch, capsys
):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    assert main([str(FIXTURE)], progress_every=3) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:-1] == ["  3 rows", "  6 rows"]
    summary = r"loaded 8 products \(inserted 8, updated 0\) in \d+\.\ds"
    assert re.fullmatch(summary, lines[-1])


@pytest.mark.wands
def test_full_wands_load(migrated_db: Engine):  # 16; run with -m wands
    if not WANDS_FILE.is_file():
        pytest.fail(
            f"{WANDS_FILE} is missing; put WANDS product.csv there to run -m wands"
        )
    assert _load(migrated_db, WANDS_FILE).total == 42_994
    with migrated_db.connect() as conn:
        total = conn.scalar(text("SELECT count(*) FROM products"))
        no_rating = conn.scalar(
            text("SELECT count(*) FROM products WHERE rating_count IS NULL")
        )
        sizes = conn.scalar(
            text("SELECT features->'mattresssize' FROM products WHERE product_id = 0")
        )
    assert (total, no_rating, sizes) == (42_994, 9_452, ["queen", "twin"])
