from __future__ import annotations

from app.providers.base import PromptProvider, PromptResult
from app.providers.ollama_client import OllamaChatClient


class OllamaPromptProvider(PromptProvider):
    def __init__(self, *, client: OllamaChatClient, model: str, fallback_model: str) -> None:
        self.client = client
        self.model = model
        self.fallback_model = fallback_model

    def generate_prompts(self, *, niche_name: str, niche_description: str, market: str, count: int = 10) -> list[PromptResult]:
        system_prompt = (
            "You are an elite short-form video prompt engineer. "
            "Return only valid JSON with a top-level key named prompts."
        )
        user_prompt = (
            f"Create {count} high-conversion AI video prompts for the niche '{niche_name}' in market {market}. "
            f"Niche context: {niche_description}. "
            "Each prompt must be distinct, production-ready, and optimized for automation. "
            "Every prompt must describe a 9:16 vertical short with a total runtime of 20 seconds split into exactly 2 scenes of 10 seconds each. "
            "Scene 2 must continue from the final visual composition of scene 1. "
            "For each item include: title, body, target_platforms, tone, rank, hook, cta, visual_style. "
            "Target platforms should be arrays chosen from youtube, instagram, tiktok, facebook."
        )
        try:
            payload = self.client.complete_json(model=self.model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.model
        except Exception:
            payload = self.client.complete_json(model=self.fallback_model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.fallback_model

        prompts = payload.get("prompts", [])
        results: list[PromptResult] = []
        for item in prompts:
            results.append(
                PromptResult(
                    title=item["title"],
                    body=item["body"],
                    target_platforms=item.get("target_platforms", ["youtube", "instagram", "tiktok", "facebook"]),
                    tone=item.get("tone", "authoritative"),
                    rank=int(item.get("rank", 1)),
                    metadata_payload={
                        "hook": item.get("hook", ""),
                        "cta": item.get("cta", ""),
                        "visual_style": item.get("visual_style", ""),
                        "provider_model": used_model,
                        "format": "vertical-short",
                        "aspect_ratio": "9:16",
                        "total_duration_seconds": 20,
                        "segment_count": 2,
                        "segment_duration_seconds": 10,
                        "continuation_rule": "segment_2_continues_from_segment_1_last_frame",
                    },
                )
            )
        return results

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
        system_prompt = (
            "You are an elite short-form video prompt editor. "
            "Return only valid JSON with a top-level key named prompt."
        )
        user_prompt = (
            f"Revise an existing AI video prompt for the niche '{niche_name}' in market {market}. "
            f"Niche context: {niche_description}. Current title: {current_title}. Current body: {current_body}. "
            f"User revision instruction: {instruction}. "
            "The revised prompt must remain a 9:16 vertical short with a total runtime of 20 seconds split into exactly 2 scenes of 10 seconds each. "
            "Scene 2 must continue from the final visual composition of scene 1. "
            "Return one revised prompt with: title, body, target_platforms, tone, rank, hook, cta, visual_style."
        )
        try:
            payload = self.client.complete_json(model=self.model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.model
        except Exception:
            payload = self.client.complete_json(model=self.fallback_model, system_prompt=system_prompt, user_prompt=user_prompt)
            used_model = self.fallback_model

        item = payload.get("prompt") or {}
        return PromptResult(
            title=item.get("title", f"{current_title} - revised"),
            body=item.get("body", f"{current_body}\n\nRevision instruction: {instruction}"),
            target_platforms=item.get("target_platforms", ["youtube", "instagram", "tiktok", "facebook"]),
            tone=item.get("tone", "authoritative"),
            rank=int(item.get("rank", 1)),
            metadata_payload={
                "hook": item.get("hook", ""),
                "cta": item.get("cta", ""),
                "visual_style": item.get("visual_style", ""),
                "provider_model": used_model,
                "revision_instruction": instruction,
                "format": "vertical-short",
                "aspect_ratio": "9:16",
                "total_duration_seconds": 20,
                "segment_count": 2,
                "segment_duration_seconds": 10,
                "continuation_rule": "segment_2_continues_from_segment_1_last_frame",
            },
        )
