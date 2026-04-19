from types import SimpleNamespace

from app.config import get_settings
from app.services.web_research_service import WebResearchService


def test_collect_market_signals_parses_public_sources(monkeypatch) -> None:
    payloads = {
        "https://trends.google.com/trending/rss?geo=TR": """
        <rss xmlns:ht='https://trends.google.com/trends/trendingsearches/daily?geo=TR'>
            <channel>
                <item>
                    <title>Ramazan tarifleri</title>
                    <ht:approx_traffic>200K+</ht:approx_traffic>
                </item>
            </channel>
        </rss>
        """,
        "https://blog.youtube/": "[Festival fashion trends](https://blog.youtube/culture-and-trends/festival-fashion-trends-youtube/)",
        "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en": "[1 # okul](https://ads.tiktok.com/business/creativecenter/hashtag/okul/pc/en)",
        "https://about.instagram.com/blog": "### Instagram Notes Ideas For 2025",
        "https://www.facebook.com/business/news": "### [Performance Spotlight: Trends from Around the World](https://www.facebook.com/business/news/2026-trends-from-around-the-world)",
    }

    def fake_get(url: str, timeout: int, follow_redirects: bool):
        return SimpleNamespace(text=payloads[url], raise_for_status=lambda: None)

    monkeypatch.setattr("app.services.web_research_service.httpx.get", fake_get)

    service = WebResearchService(get_settings())
    signals = service.collect_market_signals("tr-TR")

    assert signals["google_trends"][0]["title"] == "Ramazan tarifleri"
    assert signals["youtube"][0]["title"] == "Festival fashion trends"
    assert signals["tiktok"][0]["title"] == "#okul"
    assert signals["instagram"][0]["title"] == "Instagram Notes Ideas For 2025"
    assert signals["facebook"][0]["title"] == "Performance Spotlight: Trends from Around the World"