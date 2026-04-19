from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import AiderTaskStatus, Base, Project, ProviderConfig, User
from app.providers.base import PromptResult, TrendResult
from app.providers.registry import ProviderRegistry
from app.services.aider_service import AiderTaskService
from app.schemas.api import AiderTaskCreateRequest, AiderTaskUpdateRequest


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    return factory()


def test_registry_uses_benchmark_selected_model() -> None:
    session = build_session()
    config = ProviderConfig(
        provider_type="benchmark_selection",
        provider_name="trend",
        enabled=True,
        config_payload={"selected_model": "qwen3:32b"},
    )
    session.add(config)
    session.commit()

    provider = ProviderRegistry(get_settings(), session).trend_provider()

    assert getattr(provider, "model", None) == "qwen3:32b"


def test_aider_task_queue_lifecycle() -> None:
    session = build_session()
    user = User(telegram_user_id=1, telegram_chat_id=1, display_name="Owner", timezone="Europe/Istanbul")
    session.add(user)
    session.flush()
    project = Project(user_id=user.id, name="Test", market="tr-TR")
    session.add(project)
    session.commit()

    service = AiderTaskService(session)
    task = service.create_task(
        project,
        AiderTaskCreateRequest(
            title="Implement queue",
            instruction="Add queue support",
            preferred_model="openai/gpt-4o-mini",
            files_in_scope=["app/main.py"],
        ),
    )
    claimed = service.claim_next_task()

    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == AiderTaskStatus.RUNNING

    updated = service.update_task(
        task.id,
        AiderTaskUpdateRequest(
            status="completed",
            output_summary="Done",
            output_payload={"stdout": "ok"},
        ),
    )

    assert updated.status == AiderTaskStatus.COMPLETED
    assert updated.output_summary == "Done"


def test_llm_trend_provider_keeps_market_signals(monkeypatch) -> None:
    provider = ProviderRegistry(get_settings(), build_session()).trend_provider()

    monkeypatch.setattr(
        provider.research_service,
        "collect_market_signals",
        lambda market: {"youtube": [{"title": "Festival fashion", "platform": "youtube", "summary": "trend", "url": "https://blog.youtube/"}]},
    )
    monkeypatch.setattr(
        provider.client,
        "complete_json",
        lambda **kwargs: {
            "niches": [
                {
                    "name": "Festival moda",
                    "description": "Moda ve festival kombinleri",
                    "trend_score": 87,
                    "source": "web-research",
                    "keywords": ["festival", "moda"],
                    "audience": "Gen Z",
                    "monetization_angle": "Affiliate",
                    "platform_signals": ["youtube"],
                }
            ]
        },
    )

    result = provider.discover_trends(market="tr-TR")

    assert isinstance(result[0], TrendResult)
    assert result[0].context_payload["market_signals"]["youtube"][0]["title"] == "Festival fashion"
    assert result[0].context_payload["platform_signals"] == ["youtube"]


def test_llm_prompt_provider_normalizes_non_string_fields(monkeypatch) -> None:
    settings = get_settings()
    provider = ProviderRegistry(settings, build_session()).prompt_provider()

    monkeypatch.setattr(
        provider.client,
        "complete_json",
        lambda **kwargs: {
            "prompts": [
                {
                    "title": ["Osmanli'nin Kayip Hazineleri"],
                    "body": [
                        {"scene": 1, "description": "Acilis sahnesi"},
                        "Kapanista gizemi acikla",
                    ],
                    "target_platforms": "youtube",
                    "tone": ["dramatic"],
                    "rank": 1,
                    "hook": ["Bu hazine neden bulunamadi?"],
                    "cta": {"text": "devami icin takip et"},
                    "visual_style": ["sinematik", "karanlik"],
                }
            ]
        },
    )

    results = provider.generate_prompts(niche_name="Tarih", niche_description="Desc", market="tr-TR", count=1)

    assert isinstance(results[0], PromptResult)
    assert results[0].title == "Osmanli'nin Kayip Hazineleri"
    assert "Acilis sahnesi" in results[0].body
    assert "yalnizca Turkce" in results[0].body
    assert "sinematik, detayli ve zengin" in results[0].body
    assert results[0].target_platforms == ["youtube"]
    assert results[0].tone == "dramatic"
    assert results[0].metadata_payload["hook"] == "Bu hazine neden bulunamadi?"
