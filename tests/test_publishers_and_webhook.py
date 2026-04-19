from datetime import datetime, timedelta
from types import SimpleNamespace

from app.config import Settings
from app.db.models import AccountConnectionState, Platform, SocialAccount, Video
from app.publishers.common import PublishHttpClient
from app.publishers.meta import InstagramPublisher
from app.publishers.tiktok import TikTokPublisher
from app.publishers.youtube import YouTubePublisher
from app.services.telegram_webhook_service import TelegramWebhookService
from app.utils.security import TokenCipher


def build_account(settings: Settings, *, platform: Platform, metadata_payload: dict | None = None) -> SocialAccount:
    cipher = TokenCipher(settings)
    return SocialAccount(
        user_id=1,
        platform=platform,
        display_name="Test Account",
        external_account_id="external-1",
        access_token_encrypted=cipher.encrypt("token-123"),
        refresh_token_encrypted=None,
        scopes=["publish"],
        state=AccountConnectionState.ACTIVE,
        expires_at=None,
        metadata_payload=metadata_payload or {},
    )


def build_video() -> Video:
    return Video(
        prompt_id=1,
        status="ready",
        title="Trend Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )


def test_instagram_publisher_calls_graph_api(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    publisher = InstagramPublisher(client)
    account = build_account(settings, platform=Platform.INSTAGRAM, metadata_payload={"instagram_user_id": "ig-user-1"})
    video = build_video()

    calls: list[tuple[str, str, dict]] = []

    def fake_request_json(**kwargs):
        calls.append((kwargs["method"], kwargs["url"], kwargs.get("form_payload") or kwargs.get("json_payload") or {}))
        if kwargs["url"].endswith("/media"):
            return {"id": "container-1"}
        return {"id": "ig-post-1"}

    monkeypatch.setattr(client, "request_json", fake_request_json)

    result = publisher.publish(account=account, video=video, caption="caption")

    assert result.status == "published"
    assert result.platform_post_id == "ig-post-1"
    assert calls[0][1].endswith("/ig-user-1/media")
    assert calls[1][1].endswith("/ig-user-1/media_publish")


def test_tiktok_publisher_initializes_real_publish(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    publisher = TikTokPublisher(client)
    account = build_account(settings, platform=Platform.TIKTOK)
    video = build_video()

    monkeypatch.setattr(
        client,
        "request_json",
        lambda **kwargs: {"data": {"publish_id": "tt-post-1", "share_url": "https://www.tiktok.com/@user/video/1"}},
    )

    result = publisher.publish(account=account, video=video, caption="caption")

    assert result.status == "published"
    assert result.platform_post_id == "tt-post-1"
    assert result.platform_url == "https://www.tiktok.com/@user/video/1"


def test_youtube_publisher_uploads_video(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    publisher = YouTubePublisher(client)
    account = build_account(settings, platform=Platform.YOUTUBE)
    video = build_video()

    monkeypatch.setattr(client, "download_media_bytes", lambda url: b"video-bytes")

    def fake_request_response(**kwargs):
        if kwargs["method"] == "POST":
            return SimpleNamespace(headers={"location": "https://upload.example.com/1"}, json=lambda: {})
        return SimpleNamespace(headers={}, json=lambda: {"id": "yt-1"})

    monkeypatch.setattr(client, "request_response", fake_request_response)

    result = publisher.publish(account=account, video=video, caption="caption")

    assert result.status == "published"
    assert result.platform_post_id == "yt-1"
    assert result.platform_url == "https://www.youtube.com/watch?v=yt-1"


def test_youtube_publisher_uploads_thumbnail_when_cover_exists(monkeypatch) -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    publisher = YouTubePublisher(client)
    account = build_account(settings, platform=Platform.YOUTUBE)
    video = build_video()
    video.format_payload = {
        "covers": {
            "assets": {
                "youtube": {
                    "image_url": "https://cdn.example.com/cover.png",
                }
            }
        }
    }

    monkeypatch.setattr(client, "download_media_bytes", lambda url: b"image-bytes" if url.endswith("cover.png") else b"video-bytes")

    calls: list[tuple[str, str]] = []

    def fake_request_response(**kwargs):
        calls.append((kwargs["method"], kwargs["url"]))
        if kwargs["method"] == "POST" and "thumbnails/set" not in kwargs["url"]:
            return SimpleNamespace(headers={"location": "https://upload.example.com/1"}, json=lambda: {})
        if kwargs["method"] == "POST" and "thumbnails/set" in kwargs["url"]:
            return SimpleNamespace(headers={}, json=lambda: {"items": []})
        return SimpleNamespace(headers={}, json=lambda: {"id": "yt-1"})

    monkeypatch.setattr(client, "request_response", fake_request_response)

    result = publisher.publish(account=account, video=video, caption="caption")

    assert result.metadata_payload["cover"]["status"] == "uploaded"
    assert any("thumbnails/set" in url for _, url in calls)


def test_telegram_webhook_service_syncs_webhook(monkeypatch) -> None:
    settings = Settings(
        secret_key="test-secret",
        telegram_bot_token="bot-token",
        telegram_webhook_secret="secret-token",
        public_base_url="https://example.up.railway.app",
    )

    monkeypatch.setattr(
        "app.services.telegram_webhook_service.httpx.post",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": True}),
    )
    monkeypatch.setattr(
        "app.services.telegram_webhook_service.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": {"url": "https://example.up.railway.app/api/telegram/webhook"}}),
    )

    result = TelegramWebhookService(settings).sync_webhook()

    assert result["target_url"] == "https://example.up.railway.app/api/telegram/webhook"
    assert result["set_webhook"]["ok"] is True
    assert result["webhook_info"]["result"]["url"].endswith("/api/telegram/webhook")


def test_publish_http_client_rejects_expired_token() -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    account = build_account(settings, platform=Platform.YOUTUBE)
    account.expires_at = datetime.utcnow() - timedelta(minutes=1)

    try:
        client.get_access_token(account)
    except Exception as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("Expected expired token validation error")


def test_publish_http_client_rejects_undecryptable_token() -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    account = build_account(settings, platform=Platform.YOUTUBE)
    account.access_token_encrypted = "not-a-valid-fernet-token"

    try:
        client.get_access_token(account)
    except Exception as exc:
        assert "decrypted" in str(exc)
    else:
        raise AssertionError("Expected decryption validation error")


def test_publish_http_client_prefers_merged_public_video_url() -> None:
    settings = Settings(secret_key="test-secret")
    client = PublishHttpClient(settings, TokenCipher(settings))
    video = build_video()
    video.storage_path = "https://cdn.example.com/merged.mp4"
    video.preview_url = "https://cdn.example.com/segment-1.mp4"
    video.format_payload = {"merge": {"required": True, "status": "completed"}}

    resolved = client.resolve_video_url(video)

    assert resolved == "https://cdn.example.com/merged.mp4"