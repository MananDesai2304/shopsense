"""The response envelope every API endpoint returns: ``{data, meta, error}``."""

import time
import uuid

from pydantic import BaseModel


class Meta(BaseModel):
    request_id: str
    latency_ms: float


class ErrorBody(BaseModel):
    code: str
    message: str


class Envelope[T](BaseModel):
    data: T | None
    meta: Meta
    error: ErrorBody | None = None


def ok[T](data: T, started: float) -> Envelope[T]:
    """Wrap a successful result. ``started`` is a ``time.perf_counter()`` reading."""
    return Envelope(
        data=data,
        meta=Meta(
            request_id=str(uuid.uuid4()),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        ),
    )
