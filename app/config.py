from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Telegram AI Video Automation"
    app_env: str = "development"
    secret_key: str = "change-me"
    app_encryption_key: str | None = None
    public_base_url: str | None = None
    database_url: str = "sqlite:///./app.db"
    storage_path: Path = Field(default=Path("storage/videos"))
    prompt_retention_hours: int = 24
    video_retention_hours: int = 24
    default_telegram_user_id: int = 123456789
    default_telegram_chat_id: int = 123456789
    default_timezone: str = "Europe/Istanbul"
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None
    telegram_webhook_secret: str | None = None
    trends_provider: str = "dummy"
    prompt_provider: str = "dummy"
    video_provider: str = "dummy"
    llm_api_base: str = Field(default="https://api.piapi.ai/v1", validation_alias=AliasChoices("LLM_API_BASE", "OLLAMA_API_BASE"))
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "OLLAMA_API_KEY"))
    llm_research_model: str = Field(default="gpt-4o", validation_alias=AliasChoices("LLM_RESEARCH_MODEL", "OLLAMA_RESEARCH_MODEL"))
    llm_prompt_model: str = Field(default="gpt-4o", validation_alias=AliasChoices("LLM_PROMPT_MODEL", "OLLAMA_PROMPT_MODEL"))
    llm_fallback_model: str = Field(default="gpt-4o-mini", validation_alias=AliasChoices("LLM_FALLBACK_MODEL", "OLLAMA_FALLBACK_MODEL"))
    llm_timeout_seconds: int = Field(default=180, validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "OLLAMA_TIMEOUT_SECONDS"))
    llm_auto_benchmark: bool = Field(default=True, validation_alias=AliasChoices("LLM_AUTO_BENCHMARK", "OLLAMA_AUTO_BENCHMARK"))
    internal_agent_token: str = "change-internal-agent-token"
    research_fetch_timeout_seconds: int = 20
    research_youtube_blog_url: str = "https://blog.youtube/"
    research_tiktok_creative_center_url: str = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"
    research_instagram_blog_url: str = "https://about.instagram.com/blog"
    research_facebook_news_url: str = "https://www.facebook.com/business/news"
    research_google_trends_rss_url: str = "https://trends.google.com/trending/rss?geo=TR"
    piapi_base_url: str = "https://api.piapi.ai"
    piapi_api_key: str | None = None
    piapi_service_mode: str = "public"
    kling_model: str = "kling"
    kling_version: str = "3.0"
    kling_default_mode: str = "std"
    kling_default_duration: int = 10
    kling_default_aspect_ratio: str = "9:16"
    kling_enable_audio: bool = True
    video_total_duration_seconds: int = 20
    video_segment_duration_seconds: int = 10
    video_segment_count: int = 2
    video_target_aspect_ratio: str = "9:16"
    video_segment_poll_attempts: int = 6
    video_segment_poll_interval_seconds: float = 5.0
    cover_image_provider: str = "flux"
    flux_model: str = "Qubico/flux1-schnell"
    cover_image_poll_attempts: int = 10
    cover_image_poll_interval_seconds: float = 3.0
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None
    youtube_redirect_uri: str | None = None
    instagram_client_id: str | None = None
    instagram_client_secret: str | None = None
    instagram_redirect_uri: str | None = None
    facebook_client_id: str | None = None
    facebook_client_secret: str | None = None
    facebook_redirect_uri: str | None = None
    tiktok_client_id: str | None = None
    tiktok_client_secret: str | None = None
    tiktok_redirect_uri: str | None = None

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    def validate_runtime_configuration(self) -> None:
        insecure_values = {
            "secret_key": self.secret_key == "change-me",
            "internal_agent_token": self.internal_agent_token == "change-internal-agent-token",
            "app_encryption_key": self.app_encryption_key in {None, "", "change-me-too"},
        }
        if not self.is_development:
            insecure_keys = [name for name, is_insecure in insecure_values.items() if is_insecure]
            if insecure_keys:
                raise ValueError(f"Insecure production configuration: {', '.join(insecure_keys)}")
            provider_values = {self.trends_provider.lower(), self.prompt_provider.lower(), self.video_provider.lower()}
            if "dummy" in provider_values:
                raise ValueError("Dummy providers cannot be used in production configuration.")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime_configuration()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    return settings
