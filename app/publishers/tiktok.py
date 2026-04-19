from app.db.models import Platform, SocialAccount, Video
from app.publishers.base import PublishResult, Publisher
from app.publishers.common import PublishHttpClient, PublishValidationError


class TikTokPublisher(Publisher):
    platform = Platform.TIKTOK

    def __init__(self, client: PublishHttpClient) -> None:
        self.client = client

    def publish(self, *, account: SocialAccount, video: Video, caption: str, overrides: dict | None = None) -> PublishResult:
        if account.state.value != "active":
            return PublishResult(status="failed", error_message="TikTok account is not active.")
        try:
            overrides = overrides or {}
            access_token = self.client.get_access_token(account)
            video_url = self.client.resolve_video_url(video, overrides)
            publish_response = self.client.request_json(
                method="POST",
                url="https://open.tiktokapis.com/v2/post/publish/video/init/",
                access_token=access_token,
                json_payload={
                    "post_info": {
                        "title": overrides.get("title", video.title),
                        "description": overrides.get("description", caption),
                        "privacy_level": overrides.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                        "disable_duet": bool(overrides.get("disable_duet", False)),
                        "disable_comment": bool(overrides.get("disable_comment", False)),
                        "disable_stitch": bool(overrides.get("disable_stitch", False)),
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": video_url,
                    },
                },
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            data = publish_response.get("data", {})
            publish_id = data.get("publish_id") or data.get("task_id")
            return PublishResult(
                status="published" if publish_id else "pending",
                platform_post_id=publish_id,
                platform_url=data.get("share_url"),
                metadata_payload={
                    "tiktok_response": publish_response,
                    "source_video_url": video_url,
                    "cover": self._cover_metadata(video, overrides),
                },
            )
        except PublishValidationError as exc:
            return PublishResult(status="failed", error_message=str(exc))
        except Exception as exc:
            return PublishResult(status="failed", error_message=f"TikTok publish failed: {exc}")

    def _cover_metadata(self, video: Video, overrides: dict | None = None) -> dict:
        cover_url = self.client.resolve_cover_url(video, self.platform.value, overrides)
        if not cover_url:
            return {"status": "missing"}
        return {"status": "ignored", "cover_url": cover_url, "reason": "platform_cover_selection_requires_creator_side_flow"}
