from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_health_body_uses_envelope():
    body = client.get("/health").json()
    assert body["data"] == {"status": "ok"}
    assert body["error"] is None


def test_health_meta_has_request_id_and_latency():
    meta = client.get("/health").json()["meta"]
    assert isinstance(meta["request_id"], str) and meta["request_id"]
    assert isinstance(meta["latency_ms"], int | float) and meta["latency_ms"] >= 0


def test_health_request_ids_are_unique():
    ids = {client.get("/health").json()["meta"]["request_id"] for _ in range(5)}
    assert len(ids) == 5


def test_health_needs_no_auth():
    # Plain GET: no headers, no body, no credentials.
    assert client.get("/health", headers={}).status_code == 200
