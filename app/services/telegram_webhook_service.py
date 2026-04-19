from __future__ import annotations

import httpx

from app.config import Settings


class TelegramWebhookService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def sync_webhook(self) -> dict:
        if not self.settings.telegram_bot_token:
            raise ValueError("Telegram bot token is not configured.")
        if not self.settings.public_base_url:
            raise ValueError("PUBLIC_BASE_URL is required to register Telegram webhook.")
        webhook_url = f"{self.settings.public_base_url.rstrip('/')}/api/telegram/webhook"
        payload = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        if self.settings.telegram_webhook_secret:
            payload["secret_token"] = self.settings.telegram_webhook_secret
        set_response = httpx.post(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/setWebhook",
            json=payload,
            timeout=30,
        )
        set_response.raise_for_status()
        set_payload = set_response.json()
        info_response = httpx.get(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getWebhookInfo",
            timeout=30,
        )
        info_response.raise_for_status()
        info_payload = info_response.json()
        return {
            "set_webhook": set_payload,
            "webhook_info": info_payload,
            "target_url": webhook_url,
        }
