from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Base, Niche, Project, Prompt, User, VideoStatus
from app.providers.video.base import PiAPIKlingVideoProvider
from app.services.orchestrator import OrchestratorService
from app.services.video_composition_service import VideoCompositionService


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    return factory()


def seed_prompt(session: Session) -> Prompt:
    user = User(telegram_user_id=1, telegram_chat_id=1, display_name="Owner", timezone="Europe/Istanbul")
    session.add(user)
    session.flush()
    project = Project(user_id=user.id, name="Test", market="tr-TR")
    session.add(project)
    session.flush()
    niche = Niche(project_id=project.id, name="Fitness", description="Desc", source="web", trend_score=90, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Short Prompt",
        body="20 saniyelik short brief",
        target_platforms=["youtube"],
        tone="authoritative",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


def test_orchestrator_creates_two_short_segments() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    prompt = seed_prompt(session)

    video = OrchestratorService(session, settings).request_video(prompt)

    assert video.format_payload["format"] == "vertical-short"
    assert video.format_payload["total_duration_seconds"] == 20
    assert video.format_payload["segment_count"] == 2
    assert len(video.format_payload["segments"]) == 2
    assert video.format_payload["segments"][0]["duration_seconds"] == 10
    assert video.format_payload["segments"][1]["continuation_from_previous_frame"] is True
    assert video.status == VideoStatus.REQUESTED


def test_merge_service_writes_merged_file(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(secret_key="test-secret", storage_path=tmp_path)
    service = VideoCompositionService(settings)
    video = type(
        "VideoStub",
        (),
        {
            "id": 7,
            "format_payload": {
                "segments": [
                    {"segment_index": 1, "preview_url": "https://cdn.example.com/seg-1.mp4"},
                    {"segment_index": 2, "preview_url": "https://cdn.example.com/seg-2.mp4"},
                ]
            },
        },
    )()

    class FakeStream:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield self.content

    monkeypatch.setattr("app.services.video_composition_service.httpx.stream", lambda *args, **kwargs: FakeStream(b"video-bytes"))
    monkeypatch.setattr("app.services.video_composition_service.shutil.which", lambda name: "ffmpeg")

    def fake_run(command, capture_output, text):
        output_path = Path(command[-1])
        output_path.write_bytes(b"merged-video")
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("app.services.video_composition_service.subprocess.run", fake_run)

    result = service.merge_segments(video)

    assert result["status"] == "completed"
    assert result["merged_storage_path"].endswith("merged.mp4")
    assert Path(result["merged_storage_path"]).exists()


def test_extract_last_frame_writes_png(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(secret_key="test-secret", storage_path=tmp_path)
    service = VideoCompositionService(settings)

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"video-bytes"

    monkeypatch.setattr("app.services.video_composition_service.httpx.stream", lambda *args, **kwargs: FakeStream())
    monkeypatch.setattr("app.services.video_composition_service.shutil.which", lambda name: "ffmpeg")

    def fake_run(command, capture_output, text):
        output_path = Path(command[-1])
        output_path.write_bytes(b"png-bytes")
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("app.services.video_composition_service.subprocess.run", fake_run)

    frame_url = service.extract_last_frame(video_id=1, segment_index=1, video_url="https://cdn.example.com/seg-1.mp4")

    assert frame_url.startswith("file://")
    assert (tmp_path / "video-1" / "frames" / "segment-1-last-frame.png").exists()


def test_orchestrator_passes_extracted_frame_to_second_segment(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    prompt = seed_prompt(session)
    orchestrator = OrchestratorService(session, settings)

    calls = []

    class FakeProvider:
        def request_video(self, *, prompt_title, prompt_body, market, initial_frame_url=None, end_frame_url=None):
            calls.append({"title": prompt_title, "initial_frame_url": initial_frame_url})
            preview_url = f"https://cdn.example.com/{len(calls)}.mp4"
            return type(
                "Result",
                (),
                {
                    "title": prompt_title,
                    "provider_name": "fake-provider",
                    "provider_job_id": None,
                    "preview_url": preview_url,
                    "storage_path": None,
                    "format_payload": {},
                },
            )()

    monkeypatch.setattr(orchestrator.providers, "video_provider", lambda: FakeProvider())
    monkeypatch.setattr(orchestrator.video_composition, "extract_last_frame", lambda **kwargs: "file:///tmp/last-frame.png")

    video = orchestrator.request_video(prompt)

    assert len(calls) == 2
    assert calls[0]["initial_frame_url"] is None
    assert calls[1]["initial_frame_url"] == "file:///tmp/last-frame.png"
    assert video.format_payload["segments"][1]["initial_frame_url"] == "file:///tmp/last-frame.png"


def test_orchestrator_polls_until_first_segment_completes(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy", video_segment_poll_attempts=3, video_segment_poll_interval_seconds=0)
    prompt = seed_prompt(session)
    orchestrator = OrchestratorService(session, settings)

    request_calls = []
    task_calls = []

    class FakeProvider:
        def request_video(self, *, prompt_title, prompt_body, market, initial_frame_url=None, end_frame_url=None):
            request_calls.append({"title": prompt_title, "initial_frame_url": initial_frame_url})
            return type(
                "Result",
                (),
                {
                    "title": prompt_title,
                    "provider_name": "fake-provider",
                    "provider_job_id": f"task-{len(request_calls)}",
                    "preview_url": None,
                    "storage_path": None,
                    "format_payload": {},
                },
            )()

        def get_task(self, task_id):
            task_calls.append(task_id)
            if task_id == "task-1":
                if len([item for item in task_calls if item == task_id]) < 3:
                    return {"status": "processing", "output": {}}
                return {"status": "completed", "output": {"video": "https://cdn.example.com/seg-1.mp4"}}
            return {"status": "completed", "output": {"video": "https://cdn.example.com/seg-2.mp4"}}

    monkeypatch.setattr(orchestrator.providers, "video_provider", lambda: FakeProvider())
    monkeypatch.setattr(orchestrator.video_composition, "extract_last_frame", lambda **kwargs: "file:///tmp/last-frame.png")

    video = orchestrator.request_video(prompt)

    assert len(request_calls) == 2
    assert request_calls[1]["initial_frame_url"] == "file:///tmp/last-frame.png"
    assert task_calls.count("task-1") == 3
    assert video.format_payload["segments"][0]["status"] == "ready"
    assert video.format_payload["segments"][1]["status"] == "ready"


def test_orchestrator_blocks_second_segment_when_first_never_ready(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy", video_segment_poll_attempts=2, video_segment_poll_interval_seconds=0)
    prompt = seed_prompt(session)
    orchestrator = OrchestratorService(session, settings)

    request_calls = []

    class FakeProvider:
        def request_video(self, *, prompt_title, prompt_body, market, initial_frame_url=None, end_frame_url=None):
            request_calls.append({"title": prompt_title, "initial_frame_url": initial_frame_url})
            return type(
                "Result",
                (),
                {
                    "title": prompt_title,
                    "provider_name": "fake-provider",
                    "provider_job_id": "task-1",
                    "preview_url": None,
                    "storage_path": None,
                    "format_payload": {},
                },
            )()

        def get_task(self, task_id):
            return {"status": "processing", "output": {}}

    monkeypatch.setattr(orchestrator.providers, "video_provider", lambda: FakeProvider())

    video = orchestrator.request_video(prompt)

    assert len(request_calls) == 1
    assert video.status == VideoStatus.REQUESTED
    assert len(video.format_payload["segments"]) == 2
    assert video.format_payload["segments"][0]["status"] == "processing"
    assert video.format_payload["segments"][1]["status"] == "blocked_waiting_previous_segment"
    assert video.format_payload["continuation"]["status"] == "waiting_previous_segment"


def test_kling_provider_sends_image_url(monkeypatch) -> None:
    provider = PiAPIKlingVideoProvider(
        base_url="https://api.piapi.ai",
        api_key="key",
        service_mode="public",
        model="kling",
        version="3.0",
        mode="std",
        duration=10,
        aspect_ratio="9:16",
        enable_audio=False,
    )
    payloads = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"data": {"task_id": "task-1", "status": "pending", "model": "kling", "task_type": "video_generation", "input": {}, "output": {}}}

    def fake_post(url, headers, json, timeout):
        payloads.append(json)
        return FakeResponse()

    monkeypatch.setattr("app.providers.video.base.httpx.post", fake_post)

    provider.request_video(
        prompt_title="Segment 2",
        prompt_body="Continue the story",
        market="tr-TR",
        initial_frame_url="file:///tmp/frame.png",
    )

    assert payloads[0]["input"]["image_url"] == "file:///tmp/frame.png"