from app.providers.base import TrendProvider, TrendResult


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
