# ShopSense

AI shopping assistant for a D2C furniture store. A shopper chats; five engines answer:
intent (classify the request), disambiguation (ask a question or search now),
retrieval + policy RAG (hybrid search over the catalog, grounded policy answers),
curation (3 to 5 structured picks with reasons), escalation (hand off to a human).
Catalog and search eval data: WANDS (Wayfair).

## Repo map

| Path | What | Workspace | Status |
| --- | --- | --- | --- |
| `apps/api` | FastAPI service, the 5 engines, agent loop. Code in `src/api/` | uv | exists, no endpoints yet |
| `packages/mcp-catalog` | MCP server: search_catalog, get_product, order_status | pnpm | package only, no code |
| `evals` | Golden sets, LLM judge, eval runner | uv (not yet a member) | planned, week 2 |
| `infra` | Terraform for AWS and Google | none | planned, week 3 |
| `apps/web` | Next.js chat UI | pnpm | planned, week 4 |
| `docs/specs` | One spec per ticket | none | exists |
| `docs/decisions` | Decision records with numbers | none | exists |

## Commands (run from the repo root)

- Install Python: `uv sync --all-packages`
- Install TypeScript: `pnpm install`
- Test: `uv run --package api pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Add a Python dep to api: `uv add --package api <pkg>` (dev-only: add `--dev`)
- Add a TS dep: `pnpm --filter @shopsense/mcp-catalog add <pkg>` (dev-only: add `-D`)
- Run Python in api's env: `uv run --package api python -c "..."`

## Conventions

- Every API response is `{ "data": ..., "meta": {...}, "error": null | {"code": str, "message": str} }`.
  On success `error` is null. On failure `data` is null and `error` is set. `meta` carries `request_id` and `latency_ms`.
- Python 3.13, src layout. Tests live in `apps/api/tests/`, named `test_<module>.py`.
- TypeScript packages are named `@shopsense/<name>` and are private.
- Dependencies go in the member's own `pyproject.toml` or `package.json`, never the root.

## Workflow

- Spec first. Every change starts with `docs/specs/NNN-short-name.md`: problem, acceptance criteria,
  and the test that proves each criterion. The spec is the first commit of the branch.
- Branch per change: `feat/...`, `fix/...`, `chore/...`. One concern per PR, under 300 changed lines.
- Commits use conventional format: `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`.
- Before opening a PR: tests and lint pass with the commands above.

## Never

- IMPORTANT: never commit to, push to, or merge into `main`. Work on a branch; a human merges the PR.
- Never force push.
- Never read, print, or commit `.env`. Keys come from environment variables, documented in `.env.example`.
- Never hardcode keys, tokens, or URLs with credentials.
- Never edit `uv.lock` or `pnpm-lock.yaml` by hand; change deps through uv or pnpm.
- Never use npm in this repo; pnpm only.

## Gotchas

- Verify Python imports from outside the package folder (e.g. from `apps/web`), or the current
  directory gives a false pass.
- uv workspace members are listed explicitly in the root `pyproject.toml`, not by glob.
  Add `evals` there when it gets a `pyproject.toml`.
- pnpm is pinned to an exact version in root `package.json` (`devEngines`). Keep it exact; a range breaks corepack.