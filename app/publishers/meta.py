from typing import Any

from app.db.models import Platform, SocialAccount, Video
from app.publishers.base import PublishResult, Publisher
from app.publishers.common import PublishHttpClient, PublishValidationError


class InstagramPublisher(Publisher):
    platform = Platform.INSTAGRAM

    def __init__(self, client: PublishHttpClient) -> None:
        self.client = client

    def publish(self, *, account: SocialAccount, video: Video, caption: str, overrides: dict | None = None) -> PublishResult:
        if account.state.value != "active":
            return PublishResult(status="failed", error_message="Instagram account is not active.")
        try:
            overrides = overrides or {}
            access_token = self.client.get_access_token(account)
            ig_user_id = str(overrides.get("instagram_user_id") or account.metadata_payload.get("instagram_user_id") or account.external_account_id)
            video_url = self.client.resolve_video_url(video, overrides)
            create_response = self.client.request_json(
                method="POST",
                url=f"https://graph.facebook.com/v23.0/{ig_user_id}/media",
                access_token=access_token,
                form_payload={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": overrides.get("caption", caption),
                    "share_to_feed": "true" if overrides.get("share_to_feed", True) else "false",
                },
            )
            creation_id = create_response.get("id")
            if not creation_id:
                return PublishResult(status="failed", error_message="Instagram media container was not created.", metadata_payload={"instagram_response": create_response})
            publish_response = self.client.request_json(
                method="POST",
                url=f"https://graph.facebook.com/v23.0/{ig_user_id}/media_publish",
                access_token=access_token,
                form_payload={"creation_id": creation_id},
            )
            post_id = publish_response.get("id")
            permalink = overrides.get("platform_url") or create_response.get("permalink")
            return PublishResult(
                status="published" if post_id else "pending",
                platform_post_id=post_id,
                platform_url=permalink,
                metadata_payload={
                    "container_id": creation_id,
                    "instagram_response": publish_response,
                    "source_video_url": video_url,
                    "cover": self._cover_metadata(video, overrides),
                },
            )
        except PublishValidationError as exc:
            return PublishResult(status="failed", error_message=str(exc))
        except Exception as exc:
            return PublishResult(status="failed", error_message=f"Instagram publish failed: {exc}")

    def _cover_metadata(self, video: Video, overrides: dict | None = None) -> dict[str, Any]:
        cover_url = self.client.resolve_cover_url(video, self.platform.value, overrides)
        if not cover_url:
            return {"status": "missing"}
        return {"status": "ignored", "cover_url": cover_url, "reason": "platform_upload_not_supported_in_current_api_flow"}


class FacebookPublisher(Publisher):
    platform = Platform.FACEBOOK

    def __init__(self, client: PublishHttpClient) -> None:
        self.client = client

    def publish(self, *, account: SocialAccount, video: Video, caption: str, overrides: dict | None = None) -> PublishResult:
        if account.state.value != "active":
            return PublishResult(status="failed", error_message="Facebook account is not active.")
        try:
            overrides = overrides or {}
            access_token = self.client.get_access_token(account)
            page_id = str(overrides.get("facebook_page_id") or account.metadata_payload.get("facebook_page_id") or account.external_account_id)
            video_url = self.client.resolve_video_url(video, overrides)
            publish_response = self.client.request_json(
                method="POST",
                url=f"https://graph.facebook.com/v23.0/{page_id}/videos",
                access_token=access_token,
                form_payload={
                    "file_url": video_url,
                    "description": overrides.get("description", caption),
                    "title": overrides.get("title", video.title),
                    "published": "true",
                },
            )
            post_id = publish_response.get("id")
            return PublishResult(
                status="published" if post_id else "pending",
                platform_post_id=post_id,
                platform_url=f"https://www.facebook.com/{page_id}/videos/{post_id}" if post_id else None,
                metadata_payload={"facebook_response": publish_response, "source_video_url": video_url, "cover": self._cover_metadata(video, overrides)},
            )
        except PublishValidationError as exc:
            return PublishResult(status="failed", error_message=str(exc))
        except Exception as exc:
            return PublishResult(status="failed", error_message=f"Facebook publish failed: {exc}")

    def _cover_metadata(self, video: Video, overrides: dict | None = None) -> dict[str, Any]:
        cover_url = self.client.resolve_cover_url(video, self.platform.value, overrides)
        if not cover_url:
            return {"status": "missing"}
        return {"status": "ignored", "cover_url": cover_url, "reason": "platform_upload_not_supported_in_current_api_flow"}
