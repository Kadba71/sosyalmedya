from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Niche, Project, Prompt, Publication, PublicationStatus, SocialAccount, User, Video
from app.services.retention_service import RetentionService


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    return factory()


def test_cleanup_scrubs_prompt_and_deletes_file(tmp_path: Path) -> None:
    session = build_session()
    user = User(telegram_user_id=1, telegram_chat_id=1, display_name="Owner", timezone="Europe/Istanbul")
    session.add(user)
    session.flush()
    project = Project(user_id=user.id, name="Test", market="tr-TR")
    session.add(project)
    session.flush()
    niche = Niche(project_id=project.id, name="Test", description="Desc", source="web", trend_score=90, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Body",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() - timedelta(hours=1),
        metadata_payload={},
    )
    session.add(prompt)
    session.flush()

    file_path = tmp_path / "video.mp4"
    file_path.write_text("fake")
    video = Video(
        prompt_id=prompt.id,
        title="Video",
        provider_name="dummy",
        storage_path=str(file_path),
        expires_at=datetime.utcnow() - timedelta(hours=1),
        format_payload={},
    )
    session.add(video)
    session.flush()
    account = SocialAccount(user_id=user.id, platform="youtube", display_name="YT", external_account_id="1", scopes=[])
    session.add(account)
    session.flush()
    publication = Publication(video_id=video.id, account_id=account.id, status=PublicationStatus.PUBLISHED, caption="")
    session.add(publication)
    session.commit()

    result = RetentionService(session).cleanup_expired_content(now=datetime.utcnow())

    refreshed_prompt = session.get(Prompt, prompt.id)
    refreshed_video = session.get(Video, video.id)
    assert refreshed_prompt is not None
    assert refreshed_prompt.body == "[expired]"
    assert refreshed_video is not None
    assert refreshed_video.storage_path is None
    assert not file_path.exists()
    assert result["files"] == 1
