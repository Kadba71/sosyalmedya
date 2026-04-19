from datetime import datetime

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.api import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        timestamp=datetime.utcnow(),
    )