from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Approval, ApprovalAction, ApprovalTarget, Base, Niche, Project, Prompt, PromptStatus, User, Video, VideoStatus
from app.services.approval_service import ApprovalService


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    return factory()


def test_prompt_approval_updates_status() -> None:
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
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    ApprovalService(session).apply(target_type=ApprovalTarget.PROMPT, target_id=prompt.id, action=ApprovalAction.APPROVE)

    refreshed = session.get(Prompt, prompt.id)
    assert refreshed is not None
    assert refreshed.status == PromptStatus.APPROVED


def test_video_rejection_updates_status() -> None:
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
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.flush()
    video = Video(
        prompt_id=prompt.id,
        title="Video",
        provider_name="dummy",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        format_payload={},
    )
    session.add(video)
    session.commit()

    ApprovalService(session).apply(target_type=ApprovalTarget.VIDEO, target_id=video.id, action=ApprovalAction.REJECT)

    refreshed = session.get(Video, video.id)
    assert refreshed is not None
    assert refreshed.status == VideoStatus.REJECTED


def test_invalid_approval_target_does_not_create_orphan_record() -> None:
    session = build_session()

    try:
        ApprovalService(session).apply(target_type=ApprovalTarget.VIDEO, target_id=999, action=ApprovalAction.APPROVE)
    except ValueError as exc:
        assert "Target not found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing target")

    assert session.query(Approval).count() == 0
