from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import AccountConnectionState, Base, Niche, Platform, Project, Prompt, PromptStatus, SocialAccount, User, Video, VideoStatus
from app.schemas.api import TelegramWebhookPayload
from app.services.telegram_bot import TelegramBotService
from app.utils.security import TokenCipher


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    return factory()


def test_connect_command_returns_authorization_url() -> None:
    session = build_session()
    settings = Settings(
        youtube_client_id="youtube-client",
        youtube_client_secret="youtube-secret",
        youtube_redirect_uri="https://example.com/api/oauth/youtube/callback",
    )
    service = TelegramBotService(session, settings)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/connect youtube Kanalim",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "authorization_url" in result
    assert result["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")


def test_accounts_command_lists_connected_accounts() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/accounts",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Bagli sosyal hesap yok" in result["message"]


def test_send_reply_uses_telegram_api(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", telegram_bot_token="bot-token")
    service = TelegramBotService(session, settings)
    sent = {}

    def fake_post(url, json, timeout):
        sent["url"] = url
        sent["json"] = json

    monkeypatch.setattr("app.services.telegram_bot.httpx.post", fake_post)

    payload = TelegramWebhookPayload(message={"text": "/start", "chat": {"id": 555}, "from": {"id": 222, "first_name": "Owner"}})
    service.send_reply(payload, {"message": "Merhaba"})

    assert sent["url"] == "https://api.telegram.org/botbot-token/sendMessage"
    assert sent["json"]["chat_id"] == 555
    assert sent["json"]["text"] == "Merhaba"


def test_send_reply_uses_send_photo_when_photo_url_exists(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", telegram_bot_token="bot-token")
    service = TelegramBotService(session, settings)
    sent = {}

    def fake_post(url, json, timeout):
        sent["url"] = url
        sent["json"] = json

    monkeypatch.setattr("app.services.telegram_bot.httpx.post", fake_post)

    payload = TelegramWebhookPayload(message={"text": "/start", "chat": {"id": 555}, "from": {"id": 222, "first_name": "Owner"}})
    service.send_reply(payload, {"message": "Kapak hazir", "photo_url": "https://cdn.example.com/cover.png"})

    assert sent["url"] == "https://api.telegram.org/botbot-token/sendPhoto"
    assert sent["json"]["photo"] == "https://cdn.example.com/cover.png"


def test_send_reply_supports_inline_keyboard_and_callback_answer(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", telegram_bot_token="bot-token")
    service = TelegramBotService(session, settings)
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))

    monkeypatch.setattr("app.services.telegram_bot.httpx.post", fake_post)

    payload = TelegramWebhookPayload(
        callback_query={
            "id": "cb-1",
            "data": "approve:prompt:1",
            "message": {"chat": {"id": 555}},
            "from": {"id": 222, "first_name": "Owner"},
        }
    )
    service.send_reply(
        payload,
        {
            "message": "Kart mesaji",
            "callback_message": "Kisa cevap",
            "reply_markup": {"inline_keyboard": [[{"text": "Onayla", "callback_data": "approve:prompt:1"}]]},
        },
    )

    assert calls[0][0] == "https://api.telegram.org/botbot-token/answerCallbackQuery"
    assert calls[0][1]["callback_query_id"] == "cb-1"
    assert calls[1][0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert calls[1][1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Onayla"


def test_help_command_contains_detailed_descriptions() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/help",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Komut Rehberi" in result["message"]
    assert "/publish_check <video_id> <account_id>" in result["message"]
    assert "/publish <video_id> <account_id> [caption]" in result["message"]
    assert "/history <prompt|video> <id>" in result["message"]
    assert "/edit_prompt <prompt_id> <duzenleme_talimati>" in result["message"]
    assert "/regenerate_video <video_id>" in result["message"]
    assert "/merge_video <video_id>" in result["message"]


def test_scan_command_lists_discovered_niches(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    first_niche = Niche(id=10, project_id=1, name="Kripto Ozeti", description="desc", source="llm", trend_score=88, context_payload={})
    second_niche = Niche(id=11, project_id=1, name="Teknoloji Firsatlari", description="desc", source="llm", trend_score=81, context_payload={})
    monkeypatch.setattr(service.orchestrator, "daily_scan", lambda project: [first_niche, second_niche])

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/scan",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "2 trend nis bulundu." in result["message"]
    assert "Bulunan nisler:" in result["message"]
    assert "- 10: Kripto Ozeti | skor 88" in result["message"]
    assert "- 11: Teknoloji Firsatlari | skor 81" in result["message"]
    assert "/select_niche <niche_id>" in result["message"]


def test_topics_command_lists_researched_topics_with_buttons(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="AI otomasyon", description="desc", source="llm", trend_score=90, context_payload={})
    session.add(niche)
    session.commit()

    monkeypatch.setattr(
        service.orchestrator,
        "research_niche_topics",
        lambda current_niche: [
            {"index": 1, "title": "En cok izlenen 3 otomasyon", "summary": "ilk", "interest_score": 94},
            {"index": 2, "title": "Yeni baslayanlarin hatalari", "summary": "ikinci", "interest_score": 89},
        ],
    )

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/topics {niche.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Niche secildi: AI otomasyon" in result["message"]
    assert "1. En cok izlenen 3 otomasyon | skor 94" in result["message"]
    assert result["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"topicprompt:{niche.id}:1"


def test_select_niche_persists_active_niche_and_prompts_use_it(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Turk Futbol Gundemi", description="desc", source="llm", trend_score=90, context_payload={})
    session.add(niche)
    session.commit()

    select_result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/select_niche {niche.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Aktif nis" in select_result["message"]

    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt 1",
        body="Metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    monkeypatch.setattr(service.orchestrator, "generate_prompts", lambda current_niche: [prompt])

    prompt_result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/prompts",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Turk Futbol Gundemi icin 1 prompt uretildi." in prompt_result["message"]


def test_change_niche_updates_current_niche() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche_one = Niche(project_id=project.id, name="Birinci Nis", description="desc", source="llm", trend_score=90, context_payload={})
    niche_two = Niche(project_id=project.id, name="Ikinci Nis", description="desc", source="llm", trend_score=80, context_payload={})
    session.add_all([niche_one, niche_two])
    session.commit()

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/select_niche {niche_one.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    change_result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/change_niche {niche_two.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    current_result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/current_niche",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Aktif nis degistirildi." in change_result["message"]
    assert f"Aktif nis: {niche_two.id} - Ikinci Nis" in current_result["message"]


def test_topic_prompt_command_generates_topic_specific_prompt(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="AI otomasyon", description="desc", source="llm", trend_score=90, context_payload={})
    session.add(niche)
    session.commit()

    prompt = Prompt(
        niche_id=niche.id,
        title="Secilen konu promptu",
        body="Metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={"selected_topic": {"title": "En cok izlenen otomasyon"}},
    )
    session.add(prompt)
    session.commit()

    monkeypatch.setattr(service.orchestrator, "generate_prompt_for_topic", lambda current_niche, topic_index: prompt)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/topic_prompt {niche.id} 1",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Secilen konu icin prompt hazirlandi." in result["message"]
    assert "Konu: En cok izlenen otomasyon" in result["message"]
    assert result["reply_markup"]["inline_keyboard"][1][0]["callback_data"] == f"makevideo:prompt:{prompt.id}"


def test_callback_query_makevideo_creates_video_card(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={"selected_topic": {"title": "Hizli buyuyen konu"}},
    )
    session.add(prompt)
    session.flush()
    video = Video(
        prompt_id=prompt.id,
        status=VideoStatus.READY,
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    monkeypatch.setattr(service.orchestrator, "request_video", lambda current_prompt: video)

    result = service.handle_update(
        TelegramWebhookPayload(
            callback_query={
                "id": "cb-makevideo-1",
                "data": f"makevideo:prompt:{prompt.id}",
                "message": {"chat": {"id": 111}},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Prompttan video uretim istegi olusturuldu." in result["message"]
    assert result["callback_message"] == "Video istegi baslatildi."


def test_publish_check_command_reports_readiness(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    cipher = TokenCipher(settings)
    account = SocialAccount(
        user_id=owner.id,
        platform=Platform.YOUTUBE,
        display_name="YT",
        external_account_id="channel-1",
        access_token_encrypted=cipher.encrypt("token-123"),
        refresh_token_encrypted=None,
        scopes=["publish"],
        state=AccountConnectionState.ACTIVE,
        expires_at=None,
        metadata_payload={},
    )
    session.add(account)
    session.flush()
    video = Video(
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
    session.add(video)
    session.commit()

    monkeypatch.setattr(
        service.account_validator,
        "validate_publish_readiness",
        lambda **kwargs: {
            "publish_ready": True,
            "video_url": "https://cdn.example.com/video.mp4",
            "metadata_checks": {"external_account_id": True},
        },
    )

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/publish_check {video.id} {account.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Hazirlik: tamam" in result["message"]


def test_publish_command_calls_orchestrator(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    cipher = TokenCipher(settings)
    account = SocialAccount(
        user_id=owner.id,
        platform=Platform.YOUTUBE,
        display_name="YT",
        external_account_id="channel-1",
        access_token_encrypted=cipher.encrypt("token-123"),
        refresh_token_encrypted=None,
        scopes=["publish"],
        state=AccountConnectionState.ACTIVE,
        expires_at=None,
        metadata_payload={},
    )
    session.add(account)
    session.flush()
    video = Video(
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
    session.add(video)
    session.commit()

    monkeypatch.setattr(service.account_validator, "validate_publish_readiness", lambda **kwargs: {"publish_ready": True})

    class FakePublication:
        id = 99
        status = type("Status", (), {"value": "published"})()
        platform_url = "https://youtube.com/watch?v=1"
        error_message = None

    monkeypatch.setattr(service.orchestrator, "publish_video", lambda **kwargs: [FakePublication()])

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/publish {video.id} {account.id} test caption",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Durum: published" in result["message"]
    assert result["publication_id"] == 99


def test_prompts_command_handles_missing_id() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/prompts",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Aktif nis secilmemis. Once /select_niche <niche_id> kullan." == result["message"]


def test_approve_command_handles_invalid_target_type() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/approve foo 1",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Gecersiz hedef tipi" in result["message"]


def test_video_command_handles_missing_prompt() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/video 999",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert result["message"] == "Prompt bulunamadi."


def test_edit_prompt_command_creates_revised_prompt() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", prompt_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Orijinal Prompt",
        body="Ilk metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/edit_prompt {prompt.id} daha agresif bir acilis ekle",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    revised_prompt = session.get(Prompt, result["prompt_id"])
    assert revised_prompt is not None
    assert revised_prompt.version == 2
    assert revised_prompt.metadata_payload["edited_from_prompt_id"] == prompt.id
    assert result["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"approve:prompt:{revised_prompt.id}"
    assert "onay bekliyor" in result["message"]


def test_regenerate_video_command_creates_new_video() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status="ready",
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/regenerate_video {video.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    regenerated_video = session.get(Video, result["video_id"])
    assert regenerated_video is not None
    assert regenerated_video.id != video.id
    assert regenerated_video.format_payload["regenerated_from_video_id"] == video.id
    assert result["reply_markup"]["inline_keyboard"][1][0]["callback_data"] == f"regenerate:video:{regenerated_video.id}"


def test_callback_query_approves_prompt() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            callback_query={
                "id": "cb-approve-1",
                "data": f"approve:prompt:{prompt.id}",
                "message": {"chat": {"id": 111}},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    refreshed_prompt = session.get(Prompt, prompt.id)
    assert refreshed_prompt is not None
    assert refreshed_prompt.status == PromptStatus.APPROVED
    assert result["callback_message"] == "Onaylandi."
    assert "/video <prompt_id>" in result["message"]


def test_callback_query_approves_video_and_returns_cover_prompt_card() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status=VideoStatus.READY,
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            callback_query={
                "id": "cb-approve-video-1",
                "data": f"approve:video:{video.id}",
                "message": {"chat": {"id": 111}},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    refreshed_video = session.get(Video, video.id)
    assert refreshed_video is not None
    assert refreshed_video.status == VideoStatus.APPROVED
    assert "kapak promptlari" in result["message"].lower()
    assert result["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"approvecover:video:{video.id}"


def test_generate_covers_command_returns_photo_url(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status=VideoStatus.APPROVED,
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={"covers": {"prompt_status": "approved", "prompts": {"youtube": {"prompt": "kapak"}}}},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    monkeypatch.setattr(
        service.covers,
        "generate_cover_images",
        lambda current_video: {
            "youtube": {
                "image_url": "https://cdn.example.com/cover.png",
                "upload_supported": True,
            }
        },
    )

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/generate_covers {video.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert result["photo_url"] == "https://cdn.example.com/cover.png"
    assert "Kapak gorselleri uretildi" in result["message"]


def test_callback_query_regenerates_video() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status="ready",
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            callback_query={
                "id": "cb-regenerate-1",
                "data": f"regenerate:video:{video.id}",
                "message": {"chat": {"id": 111}},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    regenerated_id = result["video_id"]
    regenerated_video = session.get(Video, regenerated_id)
    original_video = session.get(Video, video.id)
    assert regenerated_video is not None
    assert regenerated_video.format_payload["regenerated_from_video_id"] == video.id
    assert original_video is not None
    assert original_video.status == VideoStatus.REJECTED
    assert result["callback_message"] == "Yeni video hazir."


def test_merge_video_command_reports_merge_result(monkeypatch) -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status="ready",
        title="Video",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id=None,
        format_payload={"segments": [{"segment_index": 1}, {"segment_index": 2}]},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    monkeypatch.setattr(
        service.orchestrator,
        "merge_video_segments",
        lambda current_video: type("MergedVideo", (), {"id": current_video.id, "storage_path": "storage/videos/video-1/merged.mp4"})(),
    )

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/merge_video {video.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Video birlestirildi." in result["message"]
    assert "merged.mp4" in result["message"]


def test_video_card_mentions_segment_plan() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/video {prompt.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "2x10 saniye" in result["message"]
    assert "/merge_video" in result["message"]


def test_history_command_lists_prompt_revision_chain() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", prompt_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt-1",
        body="Metin-1",
        target_platforms=["youtube"],
        tone="engaging",
        rank=1,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        metadata_payload={},
    )
    session.add(prompt)
    session.commit()

    _, edited_prompt = service.editor.revise_prompt(prompt, "hook daha sert olsun")
    regenerated_prompt = service.editor.regenerate_prompt(edited_prompt)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/history prompt {regenerated_prompt.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Prompt gecmisi" in result["message"]
    assert f"Prompt {prompt.id}" in result["message"]
    assert f"Prompt {edited_prompt.id}" in result["message"]
    assert f"Prompt {regenerated_prompt.id}" in result["message"]
    assert "talimat: hook daha sert olsun" in result["message"]
    assert "regenerate <-" in result["message"]


def test_history_command_lists_video_revision_chain() -> None:
    session = build_session()
    settings = Settings(secret_key="test-secret", video_provider="dummy")
    service = TelegramBotService(session, settings)

    service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": "/start",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    owner = session.query(User).first()
    project = session.query(Project).filter(Project.user_id == owner.id).one()
    niche = Niche(project_id=project.id, name="Trend", description="Desc", source="web", trend_score=91, context_payload={})
    session.add(niche)
    session.flush()
    prompt = Prompt(
        niche_id=niche.id,
        title="Prompt",
        body="Metin",
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
        status="ready",
        title="Video-1",
        storage_path=None,
        preview_url="https://cdn.example.com/video.mp4",
        provider_name="kling",
        provider_job_id="job-1",
        format_payload={},
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(video)
    session.commit()

    _, edited_video = service.editor.revise_video(video, "tempoyu artir")
    regenerated_video = service.editor.regenerate_video(edited_video)

    result = service.handle_update(
        TelegramWebhookPayload(
            message={
                "text": f"/history video {regenerated_video.id}",
                "chat": {"id": 111},
                "from": {"id": 222, "first_name": "Owner", "username": "owner"},
            }
        )
    )

    assert "Video gecmisi" in result["message"]
    assert f"Video {video.id}" in result["message"]
    assert f"Video {edited_video.id}" in result["message"]
    assert f"Video {regenerated_video.id}" in result["message"]
    assert "talimat: tempoyu artir" in result["message"]
    assert "regenerate <-" in result["message"]