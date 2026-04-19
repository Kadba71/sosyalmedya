from app.config import Settings
from app.db.models import Platform
from app.publishers.base import Publisher
from app.publishers.common import PublishHttpClient
from app.publishers.meta import FacebookPublisher, InstagramPublisher
from app.publishers.tiktok import TikTokPublisher
from app.publishers.youtube import YouTubePublisher
from app.utils.security import TokenCipher


class PublisherRegistry:
    def __init__(self, settings: Settings, cipher: TokenCipher) -> None:
        client = PublishHttpClient(settings, cipher)
        self._publishers: dict[Platform, Publisher] = {
            Platform.YOUTUBE: YouTubePublisher(client),
            Platform.INSTAGRAM: InstagramPublisher(client),
            Platform.TIKTOK: TikTokPublisher(client),
            Platform.FACEBOOK: FacebookPublisher(client),
        }

    def get(self, platform: Platform) -> Publisher:
        return self._publishers[platform]
