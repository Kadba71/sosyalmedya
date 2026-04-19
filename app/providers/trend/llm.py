from __future__ import annotations

from app.providers.base import TopicResult, TrendProvider, TrendResult
from app.providers.llm_client import LLMChatClient
from app.services.web_research_service import WebResearchService


class LLMTrendProvider(TrendProvider):
    def __init__(self, *, client: LLMChatClient, model: str, fallback_model: str, research_service: WebResearchService) -> None:
        self.client = client
        self.model = model
        self.fallback_model = fallback_model
        self.research_service = research_service

    def discover_trends(self, *, market: str) -> list[TrendResult]:
        system_prompt = (
            "You are an expert Turkish-first trend researcher for short-form social media. "
            "Return only valid JSON with a top-level key named niches."
        )
        signals = self.research_service.collect_market_signals(market)
        user_prompt = (
            f"Analyze the most promising daily social video niches for market {market}. "
            "Use the supplied web-based multi-platform signals from Google Trends, YouTube, TikTok, Instagram and Facebook. "
            "Return exactly 5 niche candidates ranked by opportunity. "
            "For each item include: name, description, trend_score (0-100), source, keywords, audience, monetization_angle, platform_signals. "
            "All niche names and descriptions must be written in Turkish, even if source signals are English. "
            "Prefer niches suitable for automated daily video production and Turkish audience relevance. "
            f"Signals JSON: {signals}"
        )
        try:
            payload = self.client.complete_json(model=self.model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.model
        except Exception:
            payload = self.client.complete_json(model=self.fallback_model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.fallback_model

        niches = payload.get("niches", [])
        results: list[TrendResult] = []
        for item in niches:
            results.append(
                TrendResult(
                    name=item["name"],
                    description=item["description"],
                    trend_score=int(item.get("trend_score", 50)),
                    source=item.get("source", "llm-research"),
                    context_payload={
                        "market_signals": signals,
                        "platform_signals": item.get("platform_signals", []),
                        "keywords": item.get("keywords", []),
                        "audience": item.get("audience", ""),
                        "monetization_angle": item.get("monetization_angle", ""),
                        "provider_model": used_model,
                    },
                )
            )
        return results

    def discover_topics(self, *, niche_name: str, niche_description: str, market: str, niche_context: dict | None = None, count: int = 5) -> list[TopicResult]:
        system_prompt = (
            "You are an expert Turkish-first topic researcher for short-form social media. "
            "Return only valid JSON with a top-level key named topics."
        )
        signals = (niche_context or {}).get("market_signals") or self.research_service.collect_market_signals(market)
        user_prompt = (
            f"A niche was selected for market {market}. Niche name: {niche_name}. "
            f"Niche description: {niche_description}. "
            "Find the most watched and most clickable content topics inside this niche right now. "
            f"Return exactly {count} topics ranked by likely view potential. "
            "For each item include: title, summary, interest_score (0-100), keywords, content_angle, suggested_hook, viewer_problem, source. "
            "All topic titles and summaries must be written in Turkish. "
            "Prefer topics suitable for short Turkish social video automation. "
            f"Niche context JSON: {niche_context or {}}. Signals JSON: {signals}"
        )
        try:
            payload = self.client.complete_json(model=self.model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.model
        except Exception:
            payload = self.client.complete_json(model=self.fallback_model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.fallback_model

        topics = payload.get("topics", [])
        results: list[TopicResult] = []
        for item in topics:
            results.append(
                TopicResult(
                    title=item["title"],
                    summary=item.get("summary", ""),
                    interest_score=int(item.get("interest_score", 50)),
                    keywords=item.get("keywords", []),
                    source=item.get("source", "llm-topic-research"),
                    context_payload={
                        "content_angle": item.get("content_angle", ""),
                        "suggested_hook": item.get("suggested_hook", ""),
                        "viewer_problem": item.get("viewer_problem", ""),
                        "provider_model": used_model,
                    },
                )
            )
        return results