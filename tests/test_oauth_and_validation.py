from datetime import datetime, timedelta
from types import SimpleNamespace

from app.config import Settings
from app.db.models import AccountConnectionState, Niche, Platform, Prompt, Project, SocialAccount, User, Video, VideoStatus
from app.services.account_validation_service import AccountValidationService
from app.services.cover_workflow_service import CoverWorkflowService
from app.services.oauth_service import OAuthService
from app.utils.security import TokenCipher


def build_account(settings: Settings, *, platform: Platform, metadata_payload: dict | None = None) -> SocialAccount:
    cipher = TokenCipher(settings)
    return SocialAccount(
        id=1,
        user_id=1,
        platform=platform,
        display_name="Connected Account",
        external_account_id="external-1",
        access_token_encrypted=cipher.encrypt("token-123"),
        refresh_token_encrypted=cipher.encrypt("refresh-123"),
        scopes=["publish"],
        state=AccountConnectionState.ACTIVE,
        expires_at=None,
        metadata_payload=metadata_payload or {},
    )


def build_video() -> Video:
    return Video(
        id=1,
        prompt_id=1,
        status="ready",
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )


def test_oauth_service_builds_youtube_authorization_url() -> None:
    settings = Settings(
        youtube_client_id="youtube-client",
        youtube_redirect_uri="https://example.com/api/oauth/youtube/callback",
    )

    details = OAuthService(settings).build_connect_details(
        platform_name="youtube",
        display_name="My Channel",
        external_account_id=None,
    )

    assert details["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "youtube-client" in details["authorization_url"]
    assert details["state"]


def test_oauth_service_exchanges_instagram_callback(monkeypatch) -> None:
    settings = Settings(
        instagram_client_id="ig-client",
        instagram_client_secret="ig-secret",
        instagram_redirect_uri="https://example.com/api/oauth/instagram/callback",
    )
    service = OAuthService(settings)
    state = service.build_connect_details(platform_name="instagram", display_name="IG Brand", external_account_id="ig-42")["state"]

    def fake_get(url, params=None, timeout=30, headers=None):
        if "oauth/access_token" in url:
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"access_token": "meta-user-token", "expires_in": 3600})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {
                        "id": "page-1",
                        "name": "Page Name",
                        "access_token": "page-token",
                        "instagram_business_account": {"id": "ig-42", "username": "igbrand", "name": "IG Brand"},
                    }
                ]
            },
        )

    monkeypatch.setattr("app.services.oauth_service.httpx.get", fake_get)

    result = service.exchange_callback(platform_name="instagram", code="auth-code", state=state)

    assert result.payload.platform == "instagram"
    assert result.payload.external_account_id == "ig-42"
    assert result.payload.access_token == "page-token"
    assert result.payload.metadata_payload["facebook_page_id"] == "page-1"


def test_account_validation_service_checks_publish_readiness(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    account = build_account(
        settings,
        platform=Platform.INSTAGRAM,
        metadata_payload={"instagram_user_id": "ig-42", "facebook_page_id": "page-1"},
    )
    video = build_video()
    video.status = VideoStatus.APPROVED

    def fake_get(url, params=None, headers=None, timeout=30):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id": "ig-42", "username": "igbrand"})

    monkeypatch.setattr("app.services.account_validation_service.httpx.get", fake_get)

    result = AccountValidationService(settings, TokenCipher(settings)).validate_publish_readiness(video=video, account=account)

    assert result["valid"] is True
    assert result["publish_ready"] is True
    assert result["video_url"] == "https://cdn.example.com/video.mp4"


def test_account_validation_service_requires_approved_and_merged_video(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    account = build_account(settings, platform=Platform.YOUTUBE)
    video = build_video()
    video.status = VideoStatus.READY
    video.format_payload = {"merge": {"required": True, "status": "pending"}}

    def fake_get(url, params=None, headers=None, timeout=30):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"sub": "sub-1", "email": "owner@example.com", "name": "Owner"})

    monkeypatch.setattr("app.services.account_validation_service.httpx.get", fake_get)

    result = AccountValidationService(settings, TokenCipher(settings)).validate_publish_readiness(video=video, account=account)

    assert result["valid"] is True
    assert result["publish_ready"] is False
    assert result["status_checks"]["video_approved"] is False
    assert result["status_checks"]["merge_completed"] is False


def test_cover_workflow_resets_stale_assets_when_prompts_regenerated() -> None:
    settings = Settings(secret_key="test-secret", prompt_provider="dummy")
    video = build_video()
    user = User(telegram_user_id=1, telegram_chat_id=1, display_name="Owner", timezone="Europe/Istanbul")
    project = Project(user=user, name="Project", market="tr-TR")
    niche = Niche(project=project, name="Niche", description="Desc", source="web", trend_score=90, context_payload={})
    prompt = Prompt(
        niche=niche,
        title="Prompt",
        body="Brief",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    video.prompt = prompt
    video.format_payload = {
        "covers": {
            "prompt_status": "approved",
            "image_status": "generated",
            "prompts": {"youtube": {"prompt": "old"}},
            "assets": {"youtube": {"image_url": "https://cdn.example.com/old-cover.png", "status": "generated"}},
        }
    }

    class FakeSession:
        def commit(self):
            return None

        def refresh(self, _video):
            return None

    service = CoverWorkflowService(FakeSession(), settings)
    prompts = service.generate_cover_prompts(video)

    assert "youtube" in prompts
    assert video.format_payload["covers"]["assets"] == {}
    assert video.format_payload["covers"]["image_status"] == "pending_prompt_approval"


def test_oauth_service_rejects_invalid_state() -> None:
    settings = Settings(
        youtube_client_id="youtube-client",
        youtube_client_secret="youtube-secret",
        youtube_redirect_uri="https://example.com/api/oauth/youtube/callback",
    )

    try:
        OAuthService(settings).exchange_callback(platform_name="youtube", code="auth-code", state="broken-state")
    except ValueError as exc:
        assert "state" in str(exc).lower()
    else:
        raise AssertionError("Expected invalid OAuth state error")