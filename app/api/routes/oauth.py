import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.schemas.api import MessageResponse
from app.services.account_service import AccountService
from app.services.bootstrap import bootstrap_single_user
from app.services.oauth_service import OAuthService
from app.utils.security import TokenCipher


router = APIRouter()


@router.get("/{platform}/connect", response_model=MessageResponse)
def connect_url(platform: str, display_name: str = Query(...), external_account_id: str | None = Query(None)) -> MessageResponse:
    settings = get_settings()
    try:
        details = OAuthService(settings).build_connect_details(
            platform_name=platform,
            display_name=display_name,
            external_account_id=external_account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message="OAuth baslangic baglanti bilgisi hazirlandi.", details=details)


@router.get("/{platform}/callback", response_model=MessageResponse)
def oauth_callback(
    platform: str,
    code: str | None = None,
    state: str | None = None,
    session: Session = Depends(get_db_session),
) -> MessageResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required.")
    settings = get_settings()
    user, _ = bootstrap_single_user(session, settings)
    try:
        exchange_result = OAuthService(settings).exchange_callback(platform_name=platform, code=code, state=state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OAuth provider request failed: {exc}") from exc

    account = AccountService(session, TokenCipher(settings)).connect_account(user, exchange_result.payload)
    return MessageResponse(
        message="OAuth callback tamamlandi.",
        details={
            "account_id": account.id,
            "state": account.state.value,
            "platform": platform,
            "external_account_id": account.external_account_id,
            "display_name": account.display_name,
            "provider_payload": exchange_result.provider_payload,
        },
    )
