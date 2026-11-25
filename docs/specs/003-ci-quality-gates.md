# Spec 003: CI quality gates

## Goal

Every PR to `main` is checked automatically for format, lint, tests, PR size and
gate-mixing. A PR cannot merge unless the required checks pass.

## Context

- Until now, checks ran only on the developer's machine, so nothing stopped an
  unformatted or failing change from reaching `main`.
- The devx AI SDLC sets PR size limits (warn above 300 lines or 10 files, fail
  above 400 lines or 20 files, lockfiles excluded) and requires gate changes to
  live in their own commit.
- Tests use testcontainers (`pgvector/pgvector:pg16`), which needs a Docker
  daemon. GitHub's `ubuntu-latest` runners provide one.

## Scope

In:
- `.github/workflows/ci.yml` with three jobs: `quality`, `pr-size`, `gate-mix`
- A PostToolUse hook that formats Python files after Claude edits them
- Branch protection on `main` requiring the three jobs

Out:
- Type checking (pyright or mypy)
- Frontend checks (pnpm, web app)
- Deployment, release or Docker image builds
- Dependency caching tuning beyond the defaults

## Job names

These names are matched by branch protection, so they do not change without a
new spec.

| Job | Runs on | Purpose |
|---|---|---|
| `quality` | pull_request, push to main | Format, lint, tests |
| `pr-size` | pull_request only | Enforce PR size limits |
| `gate-mix` | pull_request only | Enforce gate-only commits |

## Acceptance criteria

### Workflow

- AC1: The workflow runs on `pull_request` targeting `main` and on `push` to `main`.
- AC2: The workflow sets `permissions: contents: read` at the top level. No job
  gets write access.
- AC3: Each job sets `timeout-minutes: 10`.
- AC4: Every third-party action is pinned to a current major version (or a
  commit SHA) checked against the action's own README, never `@main` or `@latest`.

### Job `quality`

- AC5: Installs dependencies with `uv sync --all-packages --locked`. The job
  fails if `uv.lock` is out of date with `pyproject.toml`.
- AC6: Fails if `uv run ruff format --check .` would change any file.
- AC7: Fails if `uv run ruff check .` reports any violation.
- AC8: Runs `uv run --package api pytest`, including the migration tests
  against a real Postgres started by testcontainers. Fails if any test fails.
- AC9: If Docker is unavailable, the tests fail loudly. They are never skipped.

### Job `pr-size`

- AC10: Counts changed lines (additions plus deletions) and changed files
  between the PR's merge base with `main` and the PR head.
- AC11: Excludes `uv.lock` and `pnpm-lock.yaml` from both the line and file counts.
- AC12: Emits a GitHub warning annotation, without failing, when lines are
  above 300 or files are above 10.
- AC13: Fails when lines are above 400 or files are above 20, and prints the
  totals and the top 5 files by lines changed.

### Job `gate-mix`

- AC14: Gate paths are `CLAUDE.md`, anything under `.claude/` and anything
  under `.github/`.
- AC15: Checks each non-merge commit in the PR separately, not the PR as a whole.
- AC16: Fails if any single commit touches both a gate path and a non-gate
  path, and names the offending commit SHA and its files.
- AC17: A PR can contain gate commits and non-gate commits, as long as each
  commit is one or the other.

### PostToolUse format hook

- AC18: Configured in `.claude/settings.json` as a `PostToolUse` hook with
  matcher `Edit|Write`.
- AC19: The hook script (`.claude/hooks/format-python.sh`) reads the hook JSON
  from stdin, takes `tool_input.file_path`, and runs
  `uv run ruff format <file>` only when the path ends in `.py`. It parses JSON
  with `python3` (stdlib only), so it needs no extra tools.
- AC20: For non-Python files the hook does nothing and exits 0.
- AC21: If ruff fails (for example on a syntax error), the hook exits 2 with
  the ruff error on stderr so Claude sees it and fixes the file.

### Branch protection

- AC22: The `main` protection rule requires `quality`, `pr-size` and
  `gate-mix` to pass before merging.
- AC23: "Require branches to be up to date before merging" stays off for now
  (solo repo). Revisit when there is a second contributor.

## Verification

- V1: This PR (spec, workflow, hook) shows all three checks green.
- V2: Throwaway branch `test/size-gate` adds a 450-line file. `pr-size` fails
  with the totals printed. Close the PR without merging.
- V3: Throwaway branch `test/gate-mix` has one commit editing both
  `.github/workflows/ci.yml` (a comment) and a file under `apps/`. `gate-mix`
  fails and names the commit. Close the PR without merging.
- V4 (optional): Throwaway branch with one badly formatted `.py` file.
  `quality` fails at the format step.
- V5: Ask Claude to edit a `.py` file with messy formatting. After the edit,
  `git diff` shows the file already formatted.

## Commit plan

Each commit stays on one side of the gate rule, so this PR passes its own
`gate-mix` check.

1. `docs: add spec 003 for ci quality gates`: only `docs/specs/`
2. `ci: add quality, pr-size and gate-mix workflow`: only `.github/`
3. `chore: add postToolUse ruff format hook`: only `.claude/`

After the PR's first run: add the three required checks in branch protection
(AC22), then squash merge.

## Open questions

- Should `pr-size` and `gate-mix` move into a reusable workflow once a second
  repo needs them? (Not now.)
- Add type checking as a fourth required job in a later spec?