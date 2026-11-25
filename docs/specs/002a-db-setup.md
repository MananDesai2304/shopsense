# 002a: Postgres and the products table

## Problem

The repo has no database. Spec 002b loads the WANDS catalog (42,994 products), and later the
retrieval engine and the MCP `get_product` tool will query it, so they all need a Postgres they can
start locally and a `products` table with a known schema. This spec provides both and loads no data.

## Questions and answers

- **Where does Postgres come from?** A `compose.yaml` in the repo, using the
  `pgvector/pgvector:pg16` image so the retrieval spec can add embeddings without changing images.
- **Which port?** Read from `POSTGRES_PORT`, defaulting to 5434. 5432 and 5433 are already in use
  on the dev machine, and other machines may differ.
- **How is the schema managed?** SQLAlchemy 2 (sync) on psycopg 3, with Alembic migrations
  from the start.
- **Is Alembic too big for one PR?** It gets this PR to itself, with `alembic.ini` and `env.py`
  trimmed to essentials.
- **How do tests get a database?** testcontainers starts a throwaway Postgres for the test
  session and applies the migrations.
- **Where does the WANDS file live?** In `data/wands/` inside the repo, and `data/` is gitignored.
  This spec only adds the ignore rule.
- **How are features and categories stored?** Features are kept both as the original string and
  as JSONB where every value is a list. Categories are kept both as the original string and as a
  `text[]` path.
- **Why `numeric(2,1)` for `average_rating`?** It was checked against the real file on 2026-11-24.
  All 33,542 non-empty values have exactly one decimal place and use 9 distinct values, 1.0 to 5.0
  in half-star steps. `numeric(2,1)` holds them all without rounding.

## Scope

What's in:

- `compose.yaml` with a `db` service (`pgvector/pgvector:pg16`), published on
  `127.0.0.1:${POSTGRES_PORT:-5434}`. Credentials come from `POSTGRES_USER`,
  `POSTGRES_PASSWORD`, and `POSTGRES_DB`; nothing is hardcoded.
- `.env.example` documents `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`
  (default `5434`), and `DATABASE_URL`
  (`postgresql+psycopg://<user>:<password>@localhost:<port>/<db>`), all with placeholder values.
- `data/` added to `.gitignore`.
- Dependencies added to `apps/api` through uv: `sqlalchemy`, `psycopg[binary]`, `alembic`;
  dev: `testcontainers[postgres]`.
- Alembic set up in `apps/api`, reading `DATABASE_URL` from the environment.
- A pytest fixture that starts a testcontainers Postgres and runs `alembic upgrade head`, which
  002b's tests reuse.
- One migration that creates `products`:

  | Column | Type |
  | --- | --- |
  | `product_id` | `integer` primary key |
  | `name` | `text not null` |
  | `product_class` | `text null` |
  | `category_hierarchy` | `text null` |
  | `category_path` | `text[] null` |
  | `description` | `text null` |
  | `features_raw` | `text not null` |
  | `features` | `jsonb not null default '{}'` |
  | `rating_count` | `integer null` |
  | `average_rating` | `numeric(2,1) null` |
  | `review_count` | `integer null` |

What's out:

- Reading or loading any data. That is 002b.
- Enabling the pgvector extension, embeddings, and the full-text index (each gets its own spec).
- Any API endpoint or MCP tool that reads products.

## Acceptance criteria

Tests live in `apps/api/tests/test_migrations.py` and run against a testcontainers Postgres.

| # | Criterion | Test |
| --- | --- | --- |
| 1 | `alembic upgrade head` creates `products` with exactly the columns, types, nullability, and primary key in the table above. | `test_migration_creates_products_table` |
| 2 | `alembic downgrade base` drops `products`. | `test_migration_downgrade_drops_products_table` |
| 3 | `data/` is gitignored. `.env.example` documents `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, and `DATABASE_URL` with placeholder values. `compose.yaml` publishes the port from `POSTGRES_PORT` and falls back to 5434: `docker compose config` shows 5434 with the variable unset and 5440 with `POSTGRES_PORT=5440`. | review check |

## Open risks

- **PR size.** Alembic scaffolding and the migration may still approach 300 lines, even trimmed.
- **Docker in tests.** testcontainers needs Docker wherever tests run. There is no CI yet; when
  there is, it needs a Docker-capable runner, or the database tests must skip cleanly.
- **Port drift.** If someone changes `POSTGRES_PORT` but not the port inside `DATABASE_URL`, the
  app and the container disagree. `.env.example` should say both must match.
- **Image choice.** `pgvector/pgvector:pg16` is chosen now but the extension isn't enabled. If the
  retrieval spec picks a different vector store, the image can go back to plain `postgres:16`.
