from datetime import datetime

from app.db.session import SessionLocal
from app.services.retention_service import RetentionService


def run_cleanup() -> dict[str, int]:
    session = SessionLocal()
    try:
        return RetentionService(session).cleanup_expired_content(now=datetime.utcnow())
    finally:
        session.close()
