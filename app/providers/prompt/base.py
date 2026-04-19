from app.providers.base import PromptProvider, PromptResult


class DummyPromptProvider(PromptProvider):
    def generate_prompts(self, *, niche_name: str, niche_description: str, market: str, count: int = 10) -> list[PromptResult]:
        prompts: list[PromptResult] = []
        for index in range(1, count + 1):
            prompts.append(
                PromptResult(
                    title=f"{niche_name} video fikri {index}",
                    body=(
                        f"{market} pazari icin {niche_name} konusunda 9:16 short formatinda toplam 20 saniyelik dikey video senaryosu uret. "
                        f"Hikaye 2 adet 10 saniyelik bolumden olussun. 2. bolum, 1. bolumun son karesindeki ana kompozisyonu koruyarak devam etsin. "
                        f"Video mutlaka sesli olsun; dogal ortam sesiyle birlikte Turkce hikaye anlatici voice-over hissi versin. "
                        f"Net acilis, hizli akis ve CTA ile bitis zorunlu. Baglam: {niche_description}."
                    ),
                    target_platforms=["youtube", "instagram", "tiktok", "facebook"],
                    tone="authoritative",
                    rank=index,
                    metadata_payload={
                        "strategy": "hook-problem-solution-cta",
                        "format": "vertical-short",
                        "aspect_ratio": "9:16",
                        "total_duration_seconds": 20,
                        "segment_count": 2,
                        "segment_duration_seconds": 10,
                        "enable_audio": True,
                        "narration_style": "turkish_storytelling_voiceover",
                        "continuation_rule": "segment_2_continues_from_segment_1_last_frame",
                    },
                )
            )
        return prompts

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
        return PromptResult(
            title=f"{current_title} - revize",
            body=f"{current_body}\n\nRevizyon talimati: {instruction}",
            target_platforms=["youtube", "instagram", "tiktok", "facebook"],
            tone="authoritative",
            rank=1,
            metadata_payload={
                "strategy": "revision",
                "instruction": instruction,
                "format": "vertical-short",
                "aspect_ratio": "9:16",
                "total_duration_seconds": 20,
                "segment_count": 2,
                "segment_duration_seconds": 10,
                "enable_audio": True,
                "narration_style": "turkish_storytelling_voiceover",
                "continuation_rule": "segment_2_continues_from_segment_1_last_frame",
            },
        )
