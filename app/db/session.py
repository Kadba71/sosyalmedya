from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def initialize_database() -> None:
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    initialize_database()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
