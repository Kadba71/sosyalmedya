from __future__ import annotations

from app.providers.base import TrendProvider, TrendResult
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