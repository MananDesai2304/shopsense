# 001 — Health check endpoint

## Problem

The API has no endpoints. Deploy targets (load balancer, container health probe, uptime
monitor) need a cheap way to ask "is the process up and serving requests?".

## Scope

Liveness only. `GET /health` touches no dependencies (no LLM, no database, no search index),
so a slow or broken dependency can never make the probe fail and trigger a restart loop.
A readiness check can be added in its own spec once the API has dependencies to check.

## Acceptance criteria

| # | Criterion | Test |
| --- | --- | --- |
| 1 | `GET /health` returns HTTP 200. | `test_health_returns_200` |
| 2 | The body follows the response convention: `data` is `{"status": "ok"}`, `error` is `null`. | `test_health_body_uses_envelope` |
| 3 | `meta` carries a `request_id` (string) and `latency_ms` (number >= 0). | `test_health_meta_has_request_id_and_latency` |
| 4 | Each request gets a different `request_id`. | `test_health_request_ids_are_unique` |
| 5 | The endpoint needs no authentication or request body. | `test_health_needs_no_auth` (plain GET, no headers) |
