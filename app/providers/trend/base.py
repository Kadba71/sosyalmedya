from app.providers.base import TopicResult, TrendProvider, TrendResult


class DummyTrendProvider(TrendProvider):
    def discover_trends(self, *, market: str) -> list[TrendResult]:
        market_label = "Turkiye" if market == "tr-TR" else market
        return [
            TrendResult(
                name="Mikro girisim otomasyonu",
                description=f"{market_label} icin AI destekli verimlilik ve ek gelir odakli dikey icerikler.",
                trend_score=94,
                context_payload={"keywords": ["otomasyon", "AI", "verimlilik"]},
            ),
            TrendResult(
                name="Kisa format finans okuryazarligi",
                description=f"{market_label} izleyicisi icin anlasilir yatirim ve butce anlatimlari.",
                trend_score=89,
                context_payload={"keywords": ["finans", "yatirim", "butce"]},
            ),
            TrendResult(
                name="Yapay zeka ile isletme ipuclari",
                description=f"{market_label} pazarinda KOBI odakli AI kullanim senaryolari.",
                trend_score=86,
                context_payload={"keywords": ["KOBI", "AI", "isletme"]},
            ),
        ]

    def discover_topics(self, *, niche_name: str, niche_description: str, market: str, niche_context: dict | None = None, count: int = 5) -> list[TopicResult]:
        base_keywords = list((niche_context or {}).get("keywords") or [])
        topics = [
            TopicResult(
                title=f"{niche_name} icin en hizli buyuyen konu basliklari",
                summary=f"{market} izleyicisi icin {niche_name} alaninda son donemde en cok ilgi ceken alt konularin kisa analizi.",
                interest_score=92,
                keywords=base_keywords[:3] or ["trend", "analiz", "firsat"],
                context_payload={"content_angle": "listeleme", "suggested_hook": "Bu alanda patlayan 3 konu"},
            ),
            TopicResult(
                title=f"{niche_name} basliginda en cok izlenen hata ve yanilgilar",
                summary=f"{niche_name} ile ilgilenen kitle icin sik yapilan hatalar ve dikkat ceken yanlis inanclar.",
                interest_score=88,
                keywords=base_keywords[:2] or ["hata", "yanilgi"],
                context_payload={"content_angle": "mistakes", "suggested_hook": "Cogu kisinin yaptigi hata"},
            ),
            TopicResult(
                title=f"{niche_name} alaninda hizli uygulanabilir taktikler",
                summary=f"{niche_name} konusunda izleyicinin hemen uygulayabilecegi pratik taktiklere odaklanir.",
                interest_score=85,
                keywords=base_keywords[:2] or ["taktik", "uygulama"],
                context_payload={"content_angle": "how-to", "suggested_hook": "Bunu bugun dene"},
            ),
        ]
        return topics[:count]
