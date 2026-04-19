from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ApprovalAction, ApprovalTarget, BenchmarkScope, Niche, Platform, Prompt, Project, SocialAccount, Video
from app.db.session import get_db_session
from app.schemas.api import (
    AccountValidationRequest,
    ApprovalRequest,
    AiderTaskCreateRequest,
    BenchmarkRequest,
    ConnectAccountRequest,
    EditPromptRequest,
    EditVideoRequest,
    GeneratePromptsRequest,
    GenerateVideoRequest,
    MessageResponse,
    PublishProfileCreate,
    PublishVideoRequest,
)
from app.services.aider_service import AiderTaskService
from app.services.account_validation_service import AccountValidationService
from app.services.account_service import AccountService
from app.services.approval_service import ApprovalService
from app.services.benchmark_service import BenchmarkService
from app.services.bootstrap import bootstrap_single_user
from app.services.edit_service import EditService
from app.services.orchestrator import OrchestratorService
from app.services.retention_service import RetentionService
from app.services.telegram_webhook_service import TelegramWebhookService
from app.services.web_research_service import WebResearchService
from app.utils.security import TokenCipher


router = APIRouter()


def _resolve_publish_targets(session: Session, settings, payload: PublishVideoRequest) -> tuple[Video, list[SocialAccount], dict]:
    video = session.get(Video, payload.video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    accounts: list[SocialAccount] = []
    overrides: dict = {}
    if payload.publish_profile_id is not None:
        _, project = bootstrap_single_user(session, settings)
        profile = next((item for item in project.publish_profiles if item.id == payload.publish_profile_id), None)
        if profile is None:
            raise HTTPException(status_code=404, detail="Publish profile not found.")
        accounts.extend(session.query(SocialAccount).filter(SocialAccount.id.in_(profile.account_ids)).all())
        overrides = profile.platform_overrides

    if payload.account_ids:
        manual_accounts = session.query(SocialAccount).filter(SocialAccount.id.in_(payload.account_ids)).all()
        accounts.extend([item for item in manual_accounts if item.id not in {account.id for account in accounts}])

    if not accounts:
        raise HTTPException(status_code=400, detail="At least one target account or publish profile is required.")
    return video, accounts, overrides


@router.post("/bootstrap", response_model=MessageResponse)
def bootstrap(session: Session = Depends(get_db_session)) -> MessageResponse:
    user, project = bootstrap_single_user(session, get_settings())
    return MessageResponse(message="Single-user workspace hazirlandi.", details={"user_id": user.id, "project_id": project.id})


@router.post("/scan", response_model=MessageResponse)
def run_scan(session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    _, project = bootstrap_single_user(session, settings)
    niches = OrchestratorService(session, settings).daily_scan(project)
    return MessageResponse(message="Gunluk niche taramasi tamamlandi.", details={"count": len(niches), "ids": [item.id for item in niches]})


@router.post("/prompts", response_model=MessageResponse)
def generate_prompts(payload: GeneratePromptsRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    niche = session.get(Niche, payload.niche_id)
    if niche is None:
        raise HTTPException(status_code=404, detail="Niche not found.")
    prompts = OrchestratorService(session, settings).generate_prompts(niche)
    return MessageResponse(message="Promptlar uretildi.", details={"count": len(prompts), "ids": [item.id for item in prompts]})


@router.post("/video", response_model=MessageResponse)
def request_video(payload: GenerateVideoRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    prompt = session.get(Prompt, payload.prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    video = OrchestratorService(session, settings).request_video(prompt)
    return MessageResponse(message="Video istegi olusturuldu.", details={"video_id": video.id, "status": video.status.value})


@router.post("/prompts/edit", response_model=MessageResponse)
def edit_prompt(payload: EditPromptRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    prompt = session.get(Prompt, payload.prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    edit_request, revised_prompt = EditService(session, settings).revise_prompt(prompt, payload.instruction)
    return MessageResponse(
        message="Prompt revize edildi.",
        details={"edit_request_id": edit_request.id, "prompt_id": revised_prompt.id, "version": revised_prompt.version},
    )


@router.post("/prompts/{prompt_id}/regenerate", response_model=MessageResponse)
def regenerate_prompt(prompt_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    revised_prompt = EditService(session, settings).regenerate_prompt(prompt)
    return MessageResponse(message="Prompt yeniden uretildi.", details={"prompt_id": revised_prompt.id, "version": revised_prompt.version})


@router.post("/videos/edit", response_model=MessageResponse)
def edit_video(payload: EditVideoRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, payload.video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    edit_request, revised_video = EditService(session, settings).revise_video(video, payload.instruction)
    return MessageResponse(
        message="Video revize istegi olusturuldu.",
        details={"edit_request_id": edit_request.id, "video_id": revised_video.id, "status": revised_video.status.value},
    )


@router.post("/videos/{video_id}/regenerate", response_model=MessageResponse)
def regenerate_video(video_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    revised_video = EditService(session, settings).regenerate_video(video)
    return MessageResponse(message="Video yeniden uretim istegi olusturuldu.", details={"video_id": revised_video.id, "status": revised_video.status.value})


@router.post("/videos/{video_id}/cover-prompts", response_model=MessageResponse)
def generate_cover_prompts(video_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    prompts = OrchestratorService(session, settings).generate_cover_prompts(video)
    return MessageResponse(message="Kapak promptlari uretildi.", details={"video_id": video.id, "prompts": prompts})


@router.post("/videos/{video_id}/cover-prompts/approve", response_model=MessageResponse)
def approve_cover_prompts(video_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    prompts = OrchestratorService(session, settings).approve_cover_prompts(video)
    return MessageResponse(message="Kapak promptlari onaylandi.", details={"video_id": video.id, "prompts": prompts})


@router.post("/videos/{video_id}/covers/generate", response_model=MessageResponse)
def generate_cover_images(video_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    try:
        assets = OrchestratorService(session, settings).generate_cover_images(video)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message="Kapak gorselleri uretildi.", details={"video_id": video.id, "assets": assets})


@router.post("/videos/{video_id}/merge", response_model=MessageResponse)
def merge_video(video_id: int, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    try:
        merged_video = OrchestratorService(session, settings).merge_video_segments(video)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(
        message="Video segmentleri birlestirildi.",
        details={"video_id": merged_video.id, "storage_path": merged_video.storage_path, "merge": merged_video.format_payload.get("merge", {})},
    )


@router.post("/approve", response_model=MessageResponse)
def approve(payload: ApprovalRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    try:
        approval = ApprovalService(session).apply(
            target_type=ApprovalTarget(payload.target_type),
            target_id=payload.target_id,
            action=ApprovalAction(payload.action),
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageResponse(message="Onay islemi kaydedildi.", details={"approval_id": approval.id})


@router.post("/accounts", response_model=MessageResponse)
def connect_account(payload: ConnectAccountRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    cipher = TokenCipher(settings)
    user, _ = bootstrap_single_user(session, settings)
    account = AccountService(session, cipher).connect_account(user, payload)
    return MessageResponse(message="Sosyal hesap kaydedildi.", details={"account_id": account.id, "state": account.state.value})


@router.post("/publish-profiles", response_model=MessageResponse)
def create_publish_profile(payload: PublishProfileCreate, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    _, project = bootstrap_single_user(session, settings)
    profile = AccountService(session, TokenCipher(settings)).create_publish_profile(project, payload)
    return MessageResponse(message="Yayin profili olusturuldu.", details={"publish_profile_id": profile.id})


@router.post("/publish", response_model=MessageResponse)
def publish_video(payload: PublishVideoRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    video, accounts, overrides = _resolve_publish_targets(session, settings, payload)
    publications = OrchestratorService(session, settings).publish_video(video=video, accounts=accounts, caption=payload.caption, platform_overrides=overrides)
    return MessageResponse(
        message="Yayin islem kayitlari olusturuldu.",
        details={
            "count": len(publications),
            "ids": [item.id for item in publications],
            "results": [
                {
                    "publication_id": item.id,
                    "account_id": item.account_id,
                    "status": item.status.value,
                    "platform_url": item.platform_url,
                    "error_message": item.error_message,
                    "cover": item.metadata_payload.get("cover"),
                }
                for item in publications
            ],
        },
    )


@router.post("/publish/validate", response_model=MessageResponse)
def validate_publish(payload: PublishVideoRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    validator = AccountValidationService(settings, TokenCipher(settings))
    video, accounts, overrides = _resolve_publish_targets(session, settings, payload)
    validations = []
    for account in accounts:
        account_overrides = (overrides or {}).get(account.platform.value)
        validations.append(validator.validate_publish_readiness(video=video, account=account, overrides=account_overrides))
    return MessageResponse(
        message="Publish dry-run tamamlandi.",
        details={
            "video_id": video.id,
            "all_ready": all(item.get("publish_ready") for item in validations),
            "validations": validations,
        },
    )


@router.post("/cleanup", response_model=MessageResponse)
def cleanup_content(session: Session = Depends(get_db_session)) -> MessageResponse:
    result = RetentionService(session).cleanup_expired_content()
    return MessageResponse(message="Retention cleanup tamamlandi.", details=result)


@router.get("/dashboard", response_model=MessageResponse)
def dashboard(session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    _, project = bootstrap_single_user(session, settings)
    details = {
        "project_id": project.id,
        "niche_count": session.query(Niche).count(),
        "prompt_count": session.query(Prompt).count(),
        "video_count": session.query(Video).count(),
        "account_count": session.query(SocialAccount).count(),
        "accounts_by_platform": {
            platform.value: session.query(SocialAccount).filter(SocialAccount.platform == platform).count() for platform in Platform
        },
    }
    return MessageResponse(message="Dashboard ozeti.", details=details)


@router.post("/benchmark", response_model=MessageResponse)
def run_benchmark(payload: BenchmarkRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    benchmark = BenchmarkService(session, get_settings()).run(
        scope=BenchmarkScope(payload.scope),
        market=payload.market,
        sample_count=payload.sample_count,
    )
    return MessageResponse(
        message="Benchmark tamamlandi.",
        details={
            "benchmark_run_id": benchmark.id,
            "scope": benchmark.scope.value,
            "selected_model": benchmark.selected_model,
            "scores": benchmark.output_payload.get("scores", {}),
        },
    )


@router.get("/research/signals", response_model=MessageResponse)
def research_signals(market: str = "tr-TR") -> MessageResponse:
    signals = WebResearchService(get_settings()).collect_market_signals(market)
    totals = {name: len(items) for name, items in signals.items()}
    return MessageResponse(message="Ham web arastirma sinyalleri getirildi.", details={"market": market, "totals": totals, "signals": signals})


@router.post("/accounts/{account_id}/validate", response_model=MessageResponse)
def validate_account(account_id: int, payload: AccountValidationRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    account = session.get(SocialAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    result = AccountValidationService(settings, TokenCipher(settings)).validate_account(account, remote_check=payload.remote_check)
    return MessageResponse(message="Hesap dogrulama tamamlandi.", details=result)


@router.post("/aider/tasks", response_model=MessageResponse)
def create_aider_task(payload: AiderTaskCreateRequest, session: Session = Depends(get_db_session)) -> MessageResponse:
    settings = get_settings()
    _, project = bootstrap_single_user(session, settings)
    task = AiderTaskService(session).create_task(project, payload)
    return MessageResponse(message="Aider gorevi kuyruga eklendi.", details={"task_id": task.id, "status": task.status.value})


@router.get("/telegram/diagnostics", response_model=MessageResponse)
def telegram_diagnostics() -> MessageResponse:
    settings = get_settings()
    return MessageResponse(
        message="Telegram konfigurasyon ozeti.",
        details={
            "bot_username": settings.telegram_bot_username,
            "token_configured": bool(settings.telegram_bot_token),
            "webhook_secret_configured": bool(settings.telegram_webhook_secret),
            "public_base_url": settings.public_base_url,
        },
    )


@router.post("/telegram/webhook/sync", response_model=MessageResponse)
def telegram_webhook_sync() -> MessageResponse:
    details = TelegramWebhookService(get_settings()).sync_webhook()
    return MessageResponse(message="Telegram webhook senkronize edildi.", details=details)
