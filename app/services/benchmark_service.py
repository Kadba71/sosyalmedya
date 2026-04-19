from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import BenchmarkRun, BenchmarkRunStatus, BenchmarkScope, ProviderConfig
from app.providers.ollama_client import OllamaChatClient


class BenchmarkService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.client = OllamaChatClient(
            base_url=settings.ollama_api_base,
            api_key=settings.ollama_api_key,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    def run(self, *, scope: BenchmarkScope, market: str, sample_count: int = 2) -> BenchmarkRun:
        benchmark = BenchmarkRun(scope=scope, status=BenchmarkRunStatus.RUNNING, market=market, input_payload={"sample_count": sample_count})
        self.session.add(benchmark)
        self.session.flush()

        candidates = [self.settings.ollama_research_model, self.settings.ollama_prompt_model]
        scores: dict[str, dict] = {}

        try:
            for model in candidates:
                scores[model] = self._score_model(model=model, scope=scope, market=market, sample_count=sample_count)

            selected_model = max(scores.items(), key=lambda item: item[1]["score"])[0]
            benchmark.status = BenchmarkRunStatus.COMPLETED
            benchmark.selected_model = selected_model
            benchmark.summary = f"Selected {selected_model} for {scope.value} workload."
            benchmark.output_payload = {"scores": scores}

            config = (
                self.session.query(ProviderConfig)
                .filter(ProviderConfig.provider_type == "benchmark_selection", ProviderConfig.provider_name == scope.value)
                .one_or_none()
            )
            if config is None:
                config = ProviderConfig(provider_type="benchmark_selection", provider_name=scope.value)
                self.session.add(config)

            config.enabled = True
            config.config_payload = {"selected_model": selected_model, "scores": scores, "market": market}
            self.session.commit()
            self.session.refresh(benchmark)
            return benchmark
        except Exception as exc:
            benchmark.status = BenchmarkRunStatus.FAILED
            benchmark.error_message = str(exc)
            self.session.commit()
            raise

    def get_selected_model(self, scope: BenchmarkScope) -> str | None:
        config = (
            self.session.query(ProviderConfig)
            .filter(ProviderConfig.provider_type == "benchmark_selection", ProviderConfig.provider_name == scope.value, ProviderConfig.enabled.is_(True))
            .one_or_none()
        )
        if config is None:
            return None
        return config.config_payload.get("selected_model")

    def _score_model(self, *, model: str, scope: BenchmarkScope, market: str, sample_count: int) -> dict:
        if scope == BenchmarkScope.TREND:
            payload = self.client.complete_json(
                model=model,
                system_prompt="Return only JSON with key niches.",
                user_prompt=(
                    f"Generate {sample_count} trend niche candidates for {market}. "
                    "Each item must include name, description, trend_score, source, keywords, audience, monetization_angle."
                ),
            )
            items = payload.get("niches", [])
            completeness = sum(
                1
                for item in items
                if all(key in item for key in ["name", "description", "trend_score", "keywords", "audience", "monetization_angle"])
            )
            diversity = len({item.get("name", "").strip().lower() for item in items if item.get("name")})
            score = completeness * 10 + diversity * 5 + min(len(items), sample_count) * 10
            return {"score": score, "item_count": len(items), "diversity": diversity, "preview": items[:2]}

        payload = self.client.complete_json(
            model=model,
            system_prompt="Return only JSON with key prompts.",
            user_prompt=(
                f"Generate {sample_count} production-ready video prompts for Turkish short-form content. "
                "Each item must include title, body, target_platforms, tone, rank, hook, cta, visual_style."
            ),
        )
        items = payload.get("prompts", [])
        completeness = sum(
            1
            for item in items
            if all(key in item for key in ["title", "body", "target_platforms", "tone", "hook", "cta", "visual_style"])
        )
        diversity = len({item.get("title", "").strip().lower() for item in items if item.get("title")})
        score = completeness * 10 + diversity * 5 + min(len(items), sample_count) * 10
        return {"score": score, "item_count": len(items), "diversity": diversity, "preview": items[:2]}
