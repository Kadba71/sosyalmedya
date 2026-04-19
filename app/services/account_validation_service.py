from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.db.models import Platform, SocialAccount, Video, VideoStatus
from app.publishers.common import PublishHttpClient, PublishValidationError
from app.utils.security import TokenCipher


class AccountValidationService:
    def __init__(self, settings: Settings, cipher: TokenCipher) -> None:
        self.settings = settings
        self.cipher = cipher
        self.client = PublishHttpClient(settings, cipher)

    def validate_account(self, account: SocialAccount, *, remote_check: bool = True) -> dict[str, Any]:
        result = {
            "account_id": account.id,
            "platform": account.platform.value,
            "state": account.state.value,
            "token_present": False,
            "metadata_checks": {},
            "remote_check": None,
            "valid": False,
        }
        try:
            access_token = self.client.get_access_token(account)
            result["token_present"] = True
            result["metadata_checks"] = self._metadata_checks(account)
            if remote_check:
                result["remote_check"] = self._remote_check(account, access_token)
            result["valid"] = all(result["metadata_checks"].values()) and (not remote_check or bool(result["remote_check"].get("ok")))
        except PublishValidationError as exc:
            result["error"] = str(exc)
        except Exception as exc:
            result["error"] = f"Validation failed: {exc}"
        return result

    def validate_publish_readiness(self, *, video: Video, account: SocialAccount, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.validate_account(account, remote_check=True)
        result["status_checks"] = self._video_status_checks(video)
        try:
            video_url = self.client.resolve_video_url(video, overrides)
            result["video_url"] = video_url
            result["cover_url"] = self.client.resolve_cover_url(video, account.platform.value, overrides)
            result["publish_ready"] = result.get("valid", False) and all(result["status_checks"].values())
        except PublishValidationError as exc:
            result["video_error"] = str(exc)
            result["publish_ready"] = False
        return result

    @staticmethod
    def _video_status_checks(video: Video) -> dict[str, bool]:
        merge_payload = (video.format_payload or {}).get("merge") or {}
        merge_required = bool(merge_payload.get("required"))
        return {
            "video_approved": video.status in {VideoStatus.APPROVED, VideoStatus.PUBLISHED},
            "merge_completed": (not merge_required) or merge_payload.get("status") == "completed",
        }

    def _metadata_checks(self, account: SocialAccount) -> dict[str, bool]:
        checks: dict[str, bool] = {}
        metadata = account.metadata_payload or {}
        if account.platform == Platform.INSTAGRAM:
            checks["instagram_user_id"] = bool(metadata.get("instagram_user_id") or account.external_account_id)
            checks["facebook_page_id"] = bool(metadata.get("facebook_page_id"))
        elif account.platform == Platform.FACEBOOK:
            checks["facebook_page_id"] = bool(metadata.get("facebook_page_id") or account.external_account_id)
        elif account.platform == Platform.TIKTOK:
            checks["open_id"] = bool(metadata.get("open_id") or account.external_account_id)
        else:
            checks["external_account_id"] = bool(account.external_account_id)
        return checks

    def _remote_check(self, account: SocialAccount, access_token: str) -> dict[str, Any]:
        if account.platform == Platform.YOUTUBE:
            response = httpx.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            return {"ok": True, "profile": {"sub": payload.get("sub"), "email": payload.get("email"), "name": payload.get("name")}}
        if account.platform == Platform.INSTAGRAM:
            instagram_user_id = account.metadata_payload.get("instagram_user_id") or account.external_account_id
            response = httpx.get(
                f"https://graph.facebook.com/v23.0/{instagram_user_id}",
                params={"fields": "id,username", "access_token": access_token},
                timeout=30,
            )
            response.raise_for_status()
            return {"ok": True, "profile": response.json()}
        if account.platform == Platform.FACEBOOK:
            page_id = account.metadata_payload.get("facebook_page_id") or account.external_account_id
            response = httpx.get(
                f"https://graph.facebook.com/v23.0/{page_id}",
                params={"fields": "id,name", "access_token": access_token},
                timeout=30,
            )
            response.raise_for_status()
            return {"ok": True, "profile": response.json()}
        response = httpx.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={"fields": "open_id,display_name"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        return {"ok": True, "profile": response.json().get("data", {}).get("user", {})}
