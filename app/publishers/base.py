from dataclasses import dataclass, field
from typing import Protocol

from app.db.models import Platform, SocialAccount, Video


@dataclass(slots=True)
class PublishResult:
    status: str
    platform_post_id: str | None = None
    platform_url: str | None = None
    error_message: str | None = None
    metadata_payload: dict = field(default_factory=dict)


class Publisher(Protocol):
    platform: Platform

    def publish(self, *, account: SocialAccount, video: Video, caption: str, overrides: dict | None = None) -> PublishResult:
        ...
