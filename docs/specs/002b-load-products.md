# 002b: Load WANDS products into Postgres

Depends on 002a (Postgres, Alembic, and the `products` table).

## Problem

The five engines need a product catalog to search, curate from, and cite. After 002a the
`products` table exists but is empty, and the catalog still only exists as a 90 MB file
(`product.csv` from WANDS). Until the rows are loaded with clean types, retrieval, curation, and the
MCP `get_product` tool have nothing to query.

What the file actually contains (profiled 2026-11-24):

- 42,994 products, 9 columns. `product_id` is a unique integer, 0 to 42993.
- Despite the `.csv` name it is **tab-separated**, with standard CSV quoting: 214 category
  values are wrapped in `"..."` with `""` escapes (e.g. `Bar (28""-33"") Bar Stools`).
- Gaps: `product_class` empty in 2,852 rows, `category hierarchy` in 1,556,
  `product_description` in 6,008, all three rating columns in 9,452.
- Counts are written as floats (`69.0`) but are always whole. `average_rating` always has one
  decimal place, 1.0 to 5.0 in half-star steps.
- `product_features` is a `key:value|key : value|...` blob, up to 11 KB. In 32,184 rows the
  same key repeats with different values because a listing bundles its variants
  (`mattresssize: queen` and `mattresssize: twin`). There are also ~50k pairs with an empty key
  and 10 fragments with no colon (warranty text that contains a `|`).
- `category hierarchy` is 1 to 6 levels joined by ` / `. Only 16,039 products are under
  `Furniture`; the rest are decor, lighting, rugs, outdoor, kitchen, and so on.

## Questions and answers

- **Which rows go in?** All 42,994. The eval files reference product ids across the whole set,
  so filtering to furniture would break those joins.
- **What happens on duplicate feature keys?** Every value is a list, keeping all variants:
  `{"mattresssize": ["queen", "twin"]}`. One shape for every key, nothing lost.
- **How is the loader run?** A CLI module inside the api package, with a plain function
  underneath that tests can call.
- **Where does it find the file?** At `data/wands/product.csv` in the repo (gitignored by 002a).
  The data is never committed.
- **What if it runs twice?** Idempotent upsert on `product_id`. A second run leaves the same
  42,994 rows and updates any that changed.
- **Empty fields?** Empty string becomes NULL. Rows are never dropped for gaps.
- **Malformed row?** Abort. The whole load is one transaction, the error names the line number,
  and the database is left unchanged.
- **Speed target?** None for now.
- **CLI output?** Progress lines while loading, then a one-line summary.
- **Do the full-text index, embeddings, and a product-read endpoint belong here?** No. Each gets its
  own spec and PR.

## Scope

What's in:

- Loader module `api.catalog.load_products`:
  - Reads UTF-8, tab-delimited, standard double-quote quoting.
  - The header must be exactly the 9 WANDS columns, in order.
  - Maps fields to columns: `product_name` → `name`; `category hierarchy` → `category_hierarchy`,
    plus `category_path` (split on ` / `, parts trimmed); `product_description` → `description`;
    `product_features` → `features_raw` (unchanged) and `features` (parsed). The other columns keep
    their names.
  - Empty string becomes NULL for every nullable column.
  - Counts: `"69.0"` becomes `69`; a non-whole or non-numeric value is a malformed row.
    `average_rating` is stored as `numeric(2,1)`.
  - Feature parsing: split on `|`, then split each pair on the **first** `:`, then trim the key
    and the value. Drop pairs with no colon or an empty key. Group values by key into a list in
    file order, with exact duplicates removed.
  - Upserts in batches inside one transaction (`INSERT ... ON CONFLICT (product_id) DO UPDATE`).
  - Run with `uv run --package api python -m api.catalog.load_products [path]`. It reads
    `DATABASE_URL` from the environment. The optional `path` argument names the input file;
    without it the file is `data/wands/product.csv` (resolved from the repo root). The function
    underneath takes the path as an argument.
  - Prints a progress line every 5,000 rows, then
    `loaded N products (inserted I, updated U) in S.Ss`. Exit 0. On error it writes to stderr
    and exits 1.
- Fixture `apps/api/tests/fixtures/products_sample.tsv`: about 10 rows covering every edge case
  above.

What's out (each gets its own spec and PR):

- `query.csv` and `label.csv` (eval data, belongs to `evals` in week 2).
- Full-text search index (`tsvector` + GIN).
- Embeddings and enabling the pgvector extension.
- Any API endpoint or MCP tool that reads products.
- Speed targets and COPY-based loading.
- Downloading WANDS automatically.

## Acceptance criteria

Tests live in `apps/api/tests/test_load_products.py`. Database tests use 002a's testcontainers
fixture, with migrations applied.

| # | Criterion | Test |
| --- | --- | --- |
| 1 | Loading the fixture inserts one row per `product_id`, and the row count equals the fixture's data-line count. | `test_load_inserts_all_rows` |
| 2 | Empty `product_class`, `category hierarchy`, `product_description`, and rating fields become NULL; the row is still loaded. | `test_empty_fields_become_null` |
| 3 | `"69.0"` loads as integer `69`; `"4.5"` loads as `numeric` `4.5`. | `test_rating_columns_are_typed` |
| 4 | A quoted category like `"... Bar (28""-33"") Bar Stools"` loads unescaped as `... Bar (28"-33") Bar Stools`. | `test_quoted_category_is_unescaped` |
| 5 | `category_path` is the hierarchy split on ` / ` with parts trimmed; NULL when the hierarchy is empty. | `test_category_path_split` |
| 6 | `features_raw` equals the source field exactly. | `test_features_raw_preserved` |
| 7 | Repeated keys collect all values in file order with exact duplicates removed: `mattresssize:queen\|mattresssize : twin` gives `{"mattresssize": ["queen", "twin"]}`. | `test_parse_features[groups_duplicate_keys]` |
| 8 | Pairs with an empty key, and fragments with no colon, are left out of `features`. | `test_parse_features[drops_empty_keys_and_fragments]` |
| 9 | A pair is split on the first colon only (`time:10:30` gives `{"time": ["10:30"]}`). | `test_parse_features[splits_on_first_colon]` |
| 10 | Loading the same file twice leaves the same row count and no duplicates; the second run reports 0 inserted. | `test_load_twice_is_idempotent` |
| 11 | Reloading after a field changes in the file updates that row in place. | `test_reload_updates_changed_row` |
| 12 | A malformed row (wrong column count, non-numeric or non-whole count, bad id) aborts the load: the error names the line number, and the table is unchanged from before the run. | `test_bad_row_aborts_without_writing` |
| 13 | A header that is not exactly the 9 WANDS columns aborts before any write. | `test_wrong_header_aborts` |
| 14 | A missing input file gives a clear stderr message and exit code 1. | `test_missing_file_exits_1` |
| 15 | The CLI prints progress lines and the final `loaded N products (inserted I, updated U) in S.Ss` line, then exits 0. | `test_cli_prints_progress_and_summary` |
| 16 | Loading the real `data/wands/product.csv` gives 42,994 rows; 9,452 have NULL `rating_count`; product 0's `features->'mattresssize'` is `["queen", "twin"]`. The test carries a `wands` marker, registered in the root `pyproject.toml` and excluded by default (`addopts = -m "not wands"`), so CI never runs it. Run it with `uv run --package api pytest -m wands`; it fails, not skips, when the file is missing. | `test_full_wands_load` |
| 17 | `uv run --package api pytest` and `uv run ruff check .` pass. | pre-PR check |

## Open risks

- **Feature values are strings.** `overallwidth-sidetoside: ["64.7", "43.3"]` is text, and the
  multiple values are variants of the same listing. Numeric filtering (e.g. "under 60 inches
  wide") will need casting and a rule for which variant counts. That belongs to the retrieval spec.
- **Not a furniture-only catalog.** About 63% of products sit outside `Furniture`. Retrieval and
  curation may need to filter on `category_path[1]`.
- **Batch upsert speed is unknown.** No target was set. If a full load is painfully slow, a COPY
  into a staging table is the follow-up.
- **Inserted vs updated counts.** These depend on Postgres's `xmax = 0` trick in `RETURNING`, which
  is reliable but Postgres-specific.
- **Docker in tests.** Same as 002a: database tests need Docker wherever they run.
