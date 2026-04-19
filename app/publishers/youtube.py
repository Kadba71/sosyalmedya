from typing import Any

from app.db.models import Platform, SocialAccount, Video
from app.publishers.base import PublishResult, Publisher
from app.publishers.common import PublishHttpClient, PublishValidationError


class YouTubePublisher(Publisher):
    platform = Platform.YOUTUBE

    def __init__(self, client: PublishHttpClient) -> None:
        self.client = client

    def publish(self, *, account: SocialAccount, video: Video, caption: str, overrides: dict | None = None) -> PublishResult:
        if account.state.value != "active":
            return PublishResult(status="failed", error_message="YouTube account is not active.")
        try:
            access_token = self.client.get_access_token(account)
            video_url = self.client.resolve_video_url(video, overrides)
            media_bytes = self.client.download_media_bytes(video_url)
            payload = self._build_payload(video, caption, overrides)
            init_response = self.client.request_response(
                method="POST",
                url="https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                access_token=access_token,
                json_payload=payload,
                headers={
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": str((overrides or {}).get("mime_type", "video/mp4")),
                    "X-Upload-Content-Length": str(len(media_bytes)),
                },
            )
            upload_url = init_response.headers.get("location")
            if not upload_url:
                return PublishResult(status="failed", error_message="YouTube resumable upload URL was not returned.")
            upload_response = self.client.request_response(
                method="PUT",
                url=upload_url,
                access_token=access_token,
                content=media_bytes,
                headers={"Content-Type": str((overrides or {}).get("mime_type", "video/mp4"))},
            )
            response_payload = upload_response.json()
            video_id = response_payload.get("id")
            cover_result = self._upload_thumbnail_if_available(access_token, video_id, video, overrides)
            return PublishResult(
                status="published" if video_id else "pending",
                platform_post_id=video_id,
                platform_url=f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                metadata_payload={"youtube_response": response_payload, "source_video_url": video_url, "cover": cover_result},
            )
        except PublishValidationError as exc:
            return PublishResult(status="failed", error_message=str(exc))
        except Exception as exc:
            return PublishResult(status="failed", error_message=f"YouTube publish failed: {exc}")

    @staticmethod
    def _build_payload(video: Video, caption: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
        overrides = overrides or {}
        return {
            "snippet": {
                "title": overrides.get("title", video.title),
                "description": overrides.get("description", caption),
                "categoryId": str(overrides.get("category_id", "22")),
                "tags": overrides.get("tags", []),
            },
            "status": {
                "privacyStatus": overrides.get("privacy_status", "public"),
                "selfDeclaredMadeForKids": bool(overrides.get("made_for_kids", False)),
            },
        }

    def _upload_thumbnail_if_available(self, access_token: str, video_id: str | None, video: Video, overrides: dict[str, Any] | None) -> dict[str, Any]:
        if not video_id:
            return {"status": "skipped", "reason": "video_not_published"}
        cover_url = self.client.resolve_cover_url(video, self.platform.value, overrides)
        if not cover_url:
            return {"status": "skipped", "reason": "cover_missing"}
        image_bytes = self.client.download_media_bytes(cover_url)
        response = self.client.request_response(
            method="POST",
            url=f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
            access_token=access_token,
            content=image_bytes,
            headers={"Content-Type": str((overrides or {}).get("cover_mime_type", "image/png"))},
        )
        return {"status": "uploaded", "cover_url": cover_url, "thumbnail_response": response.json()}
