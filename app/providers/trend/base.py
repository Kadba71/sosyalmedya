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

    def discover_topics(self, *, niche_name: str, niche_description: str, market: str, niche_context: dict | None = None, count: int = 10) -> list[TopicResult]:
        base_keywords = list((niche_context or {}).get("keywords") or [])
        topic_blueprints = [
            ("icin en hizli buyuyen konu basliklari", "listeleme", "Bu alanda patlayan 3 konu", 92),
            ("basliginda en cok izlenen hata ve yanilgilar", "mistakes", "Cogu kisinin yaptigi hata", 90),
            ("alaninda hizli uygulanabilir taktikler", "how-to", "Bunu bugun dene", 88),
            ("ile ilgili en sasirtici istatistikler", "data", "Bu rakam herkesi sasirtiyor", 87),
            ("izleyicinin en cok sordugu sorular", "faq", "Herkes ayni seyi soruyor", 86),
            ("icin kisa surede sonuc veren stratejiler", "strategy", "En hizli sonucu veren yol bu", 85),
            ("konusunda viral olan yanlis bilgiler", "myth-busting", "Bu bilgi tamamen yanlis olabilir", 84),
            ("alaninda once-sonra donusum fikirleri", "transformation", "Degisimi 20 saniyede goster", 83),
            ("ile ilgili gundemdeki yeni firsatlar", "opportunity", "Su anda firsat penceresi acildi", 82),
            ("icin gercek hayatta calisan mini rehber", "guide", "Bunu boyle yapanlar one geciyor", 81),
            ("konusunda bir gunde uygulanacak plan", "action-plan", "Bugun bununla basla", 80),
            ("alaninda izlenmeyi arttiran 3 hikaye acisi", "story-angle", "Bu acilar daha cok izleniyor", 79),
        ]
        topics = [
            TopicResult(
                title=f"{niche_name} {suffix}",
                summary=f"{market} izleyicisi icin {niche_name} alaninda dikkat ceken ve kisa video formatina uygun guncel bir konu akisi sunar.",
                interest_score=score,
                keywords=base_keywords[:3] or ["trend", "analiz", "firsat"],
                context_payload={"content_angle": angle, "suggested_hook": hook},
            )
            for suffix, angle, hook, score in topic_blueprints
        ]
        return topics[:count]
