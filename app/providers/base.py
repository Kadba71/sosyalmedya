from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(slots=True)
class TrendResult:
    name: str
    description: str
    trend_score: int
    source: str = "web-scan"
    context_payload: dict = field(default_factory=dict)


@dataclass(slots=True)
class TopicResult:
    title: str
    summary: str
    interest_score: int
    keywords: list[str] = field(default_factory=list)
    source: str = "topic-research"
    context_payload: dict = field(default_factory=dict)


@dataclass(slots=True)
class PromptResult:
    title: str
    body: str
    target_platforms: list[str]
    tone: str
    rank: int
    metadata_payload: dict = field(default_factory=dict)


@dataclass(slots=True)
class VideoRequestResult:
    title: str
    provider_name: str
    provider_job_id: str | None = None
    preview_url: str | None = None
    storage_path: str | None = None
    format_payload: dict = field(default_factory=dict)
    requested_at: datetime = field(default_factory=datetime.utcnow)


class TrendProvider(Protocol):
    def discover_trends(self, *, market: str) -> list[TrendResult]:
        ...

    def discover_topics(self, *, niche_name: str, niche_description: str, market: str, niche_context: dict | None = None, count: int = 10) -> list[TopicResult]:
        ...


class PromptProvider(Protocol):
    def generate_prompts(self, *, niche_name: str, niche_description: str, market: str, count: int = 10) -> list[PromptResult]:
        ...

    def revise_prompt(
        self,
        *,
        niche_name: str,
        niche_description: str,
        market: str,
        current_title: str,
        current_body: str,
        instruction: str,
    ) -> PromptResult:
        ...


class VideoProvider(Protocol):
    def request_video(
        self,
        *,
        prompt_title: str,
        prompt_body: str,
        market: str,
        duration_seconds: int | None = None,
        aspect_ratio: str | None = None,
        enable_audio: bool | None = None,
        initial_frame_url: str | None = None,
        end_frame_url: str | None = None,
    ) -> VideoRequestResult:
        ...
