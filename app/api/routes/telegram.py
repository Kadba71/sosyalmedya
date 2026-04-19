from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.schemas.api import MessageResponse, TelegramWebhookPayload
from app.services.telegram_bot import TelegramBotService


router = APIRouter()


@router.post("/webhook", response_model=MessageResponse)
def telegram_webhook(
    payload: TelegramWebhookPayload,
    session: Session = Depends(get_db_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> MessageResponse:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Telegram secret token.")
    service = TelegramBotService(session, settings)
    result = service.handle_update(payload)
    service.send_reply(payload, result)
    return MessageResponse(message=result.get("message", "processed"), details=result)
