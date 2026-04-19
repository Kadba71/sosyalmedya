from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, health, internal, oauth, telegram
from app.config import get_settings
from app.db.session import initialize_database
from app.workers.scheduler import scheduler_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    scheduler_service.start()
    try:
        yield
    finally:
        scheduler_service.shutdown()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(internal.router, prefix="/api/internal", tags=["internal"])
app.include_router(oauth.router, prefix="/api/oauth", tags=["oauth"])
app.include_router(telegram.router, prefix="/api/telegram", tags=["telegram"])
app.mount("/media/videos", StaticFiles(directory=settings.storage_path), name="video-media")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat(),
    }
