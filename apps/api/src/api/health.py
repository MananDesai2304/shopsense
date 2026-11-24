import time

from fastapi import APIRouter
from pydantic import BaseModel

from api.envelope import Envelope, ok

router = APIRouter()


class HealthStatus(BaseModel):
    status: str


@router.get("/health", response_model=Envelope[HealthStatus])
def health() -> Envelope[HealthStatus]:
    """Liveness probe. Touches no dependencies, so it only fails if the process is broken."""
    started = time.perf_counter()
    return ok(HealthStatus(status="ok"), started)
