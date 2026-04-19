from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.db.models import Platform
from app.schemas.api import ConnectAccountRequest


@dataclass(slots=True)
class OAuthExchangeResult:
    payload: ConnectAccountRequest
    provider_payload: dict


class OAuthService:
    _SCOPES: dict[Platform, list[str]] = {
        Platform.YOUTUBE: [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
        Platform.INSTAGRAM: [
            "pages_show_list",
            "pages_read_engagement",
            "business_management",
            "instagram_basic",
            "instagram_content_publish",
        ],
        Platform.FACEBOOK: [
            "pages_show_list",
            "pages_manage_posts",
            "pages_read_engagement",
            "pages_manage_metadata",
        ],
        Platform.TIKTOK: [
            "user.info.basic",
            "video.publish",
        ],
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_connect_details(self, *, platform_name: str, display_name: str, external_account_id: str | None) -> dict:
        platform = Platform(platform_name)
        client_id, _, redirect_uri = self._platform_credentials(platform)
        if not client_id or not redirect_uri:
            raise ValueError("Platform is not configured.")
        state = self._encode_state(
            {
                "platform": platform.value,
                "display_name": display_name,
                "external_account_id": external_account_id,
            }
        )
        return {
            "platform": platform.value,
            "redirect_uri": redirect_uri,
            "authorization_url": self._build_authorization_url(platform, client_id=client_id, redirect_uri=redirect_uri, state=state),
            "scopes": self._SCOPES[platform],
            "state": state,
            "display_name": display_name,
            "external_account_id": external_account_id,
        }

    def exchange_callback(self, *, platform_name: str, code: str, state: str | None) -> OAuthExchangeResult:
        platform = Platform(platform_name)
        state_payload = self._decode_state(state)
        if state_payload.get("platform") != platform.value:
            raise ValueError("OAuth state is invalid for the requested platform.")
        token_payload = self._exchange_code_for_tokens(platform, code)
        profile_payload = self._fetch_profile(platform, token_payload, state_payload)
        return OAuthExchangeResult(
            payload=ConnectAccountRequest(
                platform=platform.value,
                display_name=profile_payload["display_name"],
                external_account_id=profile_payload["external_account_id"],
                access_token=profile_payload["access_token"],
                refresh_token=profile_payload.get("refresh_token"),
                scopes=profile_payload.get("scopes", self._SCOPES[platform]),
                expires_at=profile_payload.get("expires_at"),
                metadata_payload=profile_payload.get("metadata_payload", {}),
            ),
            provider_payload={
                "token_payload": token_payload,
                "profile_payload": profile_payload,
                "state_payload": state_payload,
            },
        )

    def _build_authorization_url(self, platform: Platform, *, client_id: str, redirect_uri: str, state: str) -> str:
        if platform == Platform.YOUTUBE:
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "access_type": "offline",
                "prompt": "consent",
                "scope": " ".join(self._SCOPES[platform]),
                "state": state,
            }
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        if platform in {Platform.INSTAGRAM, Platform.FACEBOOK}:
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": ",".join(self._SCOPES[platform]),
                "state": state,
            }
            return f"https://www.facebook.com/v23.0/dialog/oauth?{urlencode(params)}"
        params = {
            "client_key": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(self._SCOPES[platform]),
            "state": state,
        }
        return f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"

    def _exchange_code_for_tokens(self, platform: Platform, code: str) -> dict:
        client_id, client_secret, redirect_uri = self._platform_credentials(platform)
        if not client_id or not client_secret or not redirect_uri:
            raise ValueError("OAuth client credentials are not fully configured.")
        if platform == Platform.YOUTUBE:
            response = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
        elif platform in {Platform.INSTAGRAM, Platform.FACEBOOK}:
            response = httpx.get(
                "https://graph.facebook.com/v23.0/oauth/access_token",
                params={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                timeout=30,
            )
        else:
            response = httpx.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        response.raise_for_status()
        return response.json()

    def _fetch_profile(self, platform: Platform, token_payload: dict, state_payload: dict) -> dict:
        if platform == Platform.YOUTUBE:
            access_token = token_payload["access_token"]
            userinfo = httpx.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            userinfo.raise_for_status()
            user_payload = userinfo.json()
            return {
                "display_name": state_payload.get("display_name") or user_payload.get("name") or "YouTube Account",
                "external_account_id": state_payload.get("external_account_id") or user_payload.get("sub") or user_payload.get("email"),
                "access_token": access_token,
                "refresh_token": token_payload.get("refresh_token"),
                "scopes": token_payload.get("scope", "").split(),
                "expires_at": self._expires_at(token_payload.get("expires_in")),
                "metadata_payload": {
                    "email": user_payload.get("email"),
                    "name": user_payload.get("name"),
                    "picture": user_payload.get("picture"),
                    "provider": "google",
                },
            }
        if platform == Platform.FACEBOOK:
            user_token = token_payload["access_token"]
            pages_response = httpx.get(
                "https://graph.facebook.com/v23.0/me/accounts",
                params={"fields": "id,name,access_token", "access_token": user_token},
                timeout=30,
            )
            pages_response.raise_for_status()
            pages = pages_response.json().get("data", [])
            selected = self._select_graph_target(pages, state_payload.get("external_account_id"), id_keys=("id",))
            return {
                "display_name": state_payload.get("display_name") or selected.get("name") or "Facebook Page",
                "external_account_id": str(selected["id"]),
                "access_token": selected.get("access_token", user_token),
                "refresh_token": token_payload.get("refresh_token"),
                "scopes": self._SCOPES[platform],
                "expires_at": self._expires_at(token_payload.get("expires_in")),
                "metadata_payload": {
                    "facebook_page_id": str(selected["id"]),
                    "facebook_page_name": selected.get("name"),
                    "provider": "meta",
                },
            }
        if platform == Platform.INSTAGRAM:
            user_token = token_payload["access_token"]
            pages_response = httpx.get(
                "https://graph.facebook.com/v23.0/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account{id,username,name}",
                    "access_token": user_token,
                },
                timeout=30,
            )
            pages_response.raise_for_status()
            pages = pages_response.json().get("data", [])
            candidates = [page for page in pages if page.get("instagram_business_account")]
            selected = self._select_graph_target(candidates, state_payload.get("external_account_id"), id_keys=("instagram_business_account.id", "id"))
            instagram_account = selected["instagram_business_account"]
            return {
                "display_name": state_payload.get("display_name") or instagram_account.get("username") or instagram_account.get("name") or "Instagram Account",
                "external_account_id": str(instagram_account["id"]),
                "access_token": selected.get("access_token", user_token),
                "refresh_token": token_payload.get("refresh_token"),
                "scopes": self._SCOPES[platform],
                "expires_at": self._expires_at(token_payload.get("expires_in")),
                "metadata_payload": {
                    "instagram_user_id": str(instagram_account["id"]),
                    "instagram_username": instagram_account.get("username"),
                    "facebook_page_id": str(selected["id"]),
                    "facebook_page_name": selected.get("name"),
                    "provider": "meta",
                },
            }
        token_data = token_payload.get("data", token_payload)
        access_token = token_data["access_token"]
        userinfo = httpx.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={"fields": "open_id,display_name,avatar_url"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        userinfo.raise_for_status()
        user_payload = userinfo.json().get("data", {}).get("user", {})
        return {
            "display_name": state_payload.get("display_name") or user_payload.get("display_name") or "TikTok Account",
            "external_account_id": state_payload.get("external_account_id") or token_data.get("open_id") or user_payload.get("open_id"),
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token"),
            "scopes": (token_data.get("scope") or "").split(",") if token_data.get("scope") else self._SCOPES[platform],
            "expires_at": self._expires_at(token_data.get("expires_in")),
            "metadata_payload": {
                "open_id": token_data.get("open_id") or user_payload.get("open_id"),
                "display_name": user_payload.get("display_name"),
                "avatar_url": user_payload.get("avatar_url"),
                "provider": "tiktok",
            },
        }

    def _platform_credentials(self, platform: Platform) -> tuple[str | None, str | None, str | None]:
        if platform == Platform.YOUTUBE:
            return self.settings.youtube_client_id, self.settings.youtube_client_secret, self.settings.youtube_redirect_uri
        if platform == Platform.INSTAGRAM:
            return self.settings.instagram_client_id, self.settings.instagram_client_secret, self.settings.instagram_redirect_uri
        if platform == Platform.FACEBOOK:
            return self.settings.facebook_client_id, self.settings.facebook_client_secret, self.settings.facebook_redirect_uri
        return self.settings.tiktok_client_id, self.settings.tiktok_client_secret, self.settings.tiktok_redirect_uri

    @staticmethod
    def _encode_state(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8")

    @staticmethod
    def _decode_state(state: str | None) -> dict:
        if not state:
            raise ValueError("OAuth state is required.")
        padded = state + "=" * (-len(state) % 4)
        try:
            return json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        except Exception as exc:
            raise ValueError("OAuth state could not be decoded.") from exc

    @staticmethod
    def _expires_at(expires_in: int | str | None) -> datetime | None:
        if expires_in is None:
            return None
        return datetime.utcnow() + timedelta(seconds=int(expires_in))

    @staticmethod
    def _select_graph_target(items: list[dict], requested_id: str | None, *, id_keys: tuple[str, ...]) -> dict:
        if not items:
            raise ValueError("No publishable account was returned by the provider.")
        if not requested_id:
            return items[0]
        for item in items:
            for id_key in id_keys:
                current = item
                for part in id_key.split("."):
                    current = current.get(part) if isinstance(current, dict) else None
                if str(current) == str(requested_id):
                    return item
        return items[0]
