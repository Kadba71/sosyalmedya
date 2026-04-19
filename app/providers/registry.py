from sqlalchemy.orm import Session

from app.config import Settings
from app.providers.base import PromptProvider, TrendProvider, VideoProvider
from app.providers.ollama_client import OllamaChatClient
from app.providers.prompt.base import DummyPromptProvider
from app.providers.prompt.ollama import OllamaPromptProvider
from app.providers.trend.base import DummyTrendProvider
from app.providers.trend.ollama import OllamaTrendProvider
from app.providers.video.base import DummyVideoProvider, PiAPIKlingVideoProvider
from app.services.web_research_service import WebResearchService


class ProviderRegistry:
    def __init__(self, settings: Settings, session: Session | None = None) -> None:
        self.settings = settings
        self.session = session

    def _ollama_client(self) -> OllamaChatClient:
        return OllamaChatClient(
            base_url=self.settings.ollama_api_base,
            api_key=self.settings.ollama_api_key,
            timeout_seconds=self.settings.ollama_timeout_seconds,
        )

    def trend_provider(self) -> TrendProvider:
        if self.settings.trends_provider.lower() == "ollama":
            selected_model = self._selected_model("trend") or self.settings.ollama_research_model
            return OllamaTrendProvider(
                client=self._ollama_client(),
                model=selected_model,
                fallback_model=self.settings.ollama_fallback_model,
                research_service=WebResearchService(self.settings),
            )
        return DummyTrendProvider()

    def prompt_provider(self) -> PromptProvider:
        if self.settings.prompt_provider.lower() == "ollama":
            selected_model = self._selected_model("prompt") or self.settings.ollama_prompt_model
            return OllamaPromptProvider(
                client=self._ollama_client(),
                model=selected_model,
                fallback_model=self.settings.ollama_fallback_model,
            )
        return DummyPromptProvider()

    def video_provider(self) -> VideoProvider:
        if self.settings.video_provider.lower() == "kling":
            if not self.settings.piapi_api_key:
                raise RuntimeError("PIAPI_API_KEY is required when VIDEO_PROVIDER is set to kling.")
            return PiAPIKlingVideoProvider(
                base_url=self.settings.piapi_base_url,
                api_key=self.settings.piapi_api_key,
                service_mode=self.settings.piapi_service_mode,
                model=self.settings.kling_model,
                version=self.settings.kling_version,
                mode=self.settings.kling_default_mode,
                duration=self.settings.kling_default_duration,
                aspect_ratio=self.settings.kling_default_aspect_ratio,
                enable_audio=self.settings.kling_enable_audio,
            )
        return DummyVideoProvider()

    def _selected_model(self, scope: str) -> str | None:
        if self.session is None or not self.settings.ollama_auto_benchmark:
            return None
        from app.db.models import ProviderConfig

        config = (
            self.session.query(ProviderConfig)
            .filter(ProviderConfig.provider_type == "benchmark_selection", ProviderConfig.provider_name == scope, ProviderConfig.enabled.is_(True))
            .one_or_none()
        )
        if config is None:
            return None
        return config.config_payload.get("selected_model")
