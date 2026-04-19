from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.db.models import SocialAccount, Video
from app.utils.security import TokenCipher


class PublishValidationError(Exception):
    pass


class PublishHttpClient:
    def __init__(self, settings: Settings, cipher: TokenCipher) -> None:
        self.settings = settings
        self.cipher = cipher

    def get_access_token(self, account: SocialAccount) -> str:
        if account.expires_at and account.expires_at <= datetime.utcnow():
            raise PublishValidationError("Account access token is expired and requires re-authentication.")
        try:
            token = self.cipher.decrypt(account.access_token_encrypted)
        except ValueError as exc:
            raise PublishValidationError(str(exc)) from exc
        if not token:
            raise PublishValidationError("Active account is missing an access token.")
        return token

    def resolve_video_url(self, video: Video, overrides: dict[str, Any] | None = None) -> str:
        overrides = overrides or {}
        merge_payload = (video.format_payload or {}).get("merge") or {}
        storage_path = video.storage_path
        preview_url = video.preview_url
        if overrides.get("video_url"):
            url = overrides["video_url"]
        elif merge_payload.get("status") == "completed" and str(storage_path or "").startswith(("http://", "https://")):
            url = storage_path
        else:
            url = preview_url or storage_path
        if not url or not str(url).startswith(("http://", "https://")):
            raise PublishValidationError("A public video URL is required for platform publishing.")
        return str(url)

    def resolve_cover_url(self, video: Video, platform: str, overrides: dict[str, Any] | None = None) -> str | None:
        overrides = overrides or {}
        if overrides.get("cover_url"):
            return str(overrides["cover_url"])
        cover_payload = ((video.format_payload or {}).get("covers") or {}).get("assets") or {}
        platform_cover = cover_payload.get(platform) or {}
        return platform_cover.get("image_url") or platform_cover.get("storage_path")

    def download_media_bytes(self, url: str) -> bytes:
        if str(url).startswith(("http://", "https://")):
            response = httpx.get(url, timeout=self.settings.ollama_timeout_seconds, follow_redirects=True)
            response.raise_for_status()
            return response.content
        path = Path(str(url).replace("file://", ""))
        if not path.exists():
            raise PublishValidationError(f"Media file not found: {path}")
        return path.read_bytes()

    def request_json(
        self,
        *,
        method: str,
        url: str,
        access_token: str | None = None,
        json_payload: dict[str, Any] | None = None,
        form_payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or {})
        if access_token:
            request_headers.setdefault("Authorization", f"Bearer {access_token}")
        response = httpx.request(
            method,
            url,
            json=json_payload,
            data=form_payload,
            headers=request_headers,
            timeout=self.settings.ollama_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    def request_response(
        self,
        *,
        method: str,
        url: str,
        access_token: str | None = None,
        json_payload: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = dict(headers or {})
        if access_token:
            request_headers.setdefault("Authorization", f"Bearer {access_token}")
        response = httpx.request(
            method,
            url,
            json=json_payload,
            content=content,
            headers=request_headers,
            timeout=self.settings.ollama_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response
