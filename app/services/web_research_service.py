from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass(slots=True)
class ResearchSignal:
    platform: str
    title: str
    summary: str
    url: str


class WebResearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def collect_market_signals(self, market: str) -> dict[str, list[dict[str, str]]]:
        return {
            "google_trends": [self._to_dict(item) for item in self._collect_google_trends(market)],
            "youtube": [self._to_dict(item) for item in self._collect_youtube_signals()],
            "tiktok": [self._to_dict(item) for item in self._collect_tiktok_signals()],
            "instagram": [self._to_dict(item) for item in self._collect_instagram_signals()],
            "facebook": [self._to_dict(item) for item in self._collect_facebook_signals()],
        }

    def _fetch_text(self, url: str) -> str:
        response = httpx.get(url, timeout=self.settings.research_fetch_timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def _collect_google_trends(self, market: str) -> list[ResearchSignal]:
        url = self.settings.research_google_trends_rss_url
        if market != "tr-TR":
            geo = market.split("-")[-1]
            url = f"https://trends.google.com/trending/rss?geo={geo}"
        xml_text = self._fetch_text(url)
        root = ET.fromstring(xml_text)
        items: list[ResearchSignal] = []
        for item in root.findall("./channel/item")[:10]:
            title = (item.findtext("title") or "").strip()
            approx_traffic = ""
            for child in item:
                if child.tag.endswith("approx_traffic"):
                    approx_traffic = (child.text or "").strip()
                    break
            if title:
                items.append(
                    ResearchSignal(
                        platform="google_trends",
                        title=title,
                        summary=f"Approx traffic: {approx_traffic}",
                        url=url,
                    )
                )
        return items

    def _collect_youtube_signals(self) -> list[ResearchSignal]:
        text = self._fetch_text(self.settings.research_youtube_blog_url)
        matches = re.findall(r"\[(.*?)\]\((https://blog\.youtube/[^)]+)\)", text)
        items: list[ResearchSignal] = []
        seen: set[str] = set()
        for title, url in matches:
            clean = title.strip()
            if len(clean) < 8 or clean in seen:
                continue
            seen.add(clean)
            items.append(ResearchSignal(platform="youtube", title=clean, summary="YouTube creator or culture trend signal.", url=url))
            if len(items) >= 10:
                break
        return items

    def _collect_tiktok_signals(self) -> list[ResearchSignal]:
        text = self._fetch_text(self.settings.research_tiktok_creative_center_url)
        matches = re.findall(
            r"\[(?:\d+\s+)?(?:new\s+)?#\s*([^\]]+)\]\((https://ads\.tiktok\.com/business/creativecenter/hashtag/[^)]+)\)",
            text,
            flags=re.IGNORECASE,
        )
        items: list[ResearchSignal] = []
        for hashtag, url in matches[:10]:
            items.append(ResearchSignal(platform="tiktok", title=f"#{hashtag.strip()}", summary="TikTok Creative Center trending hashtag signal.", url=url))
        return items

    def _collect_instagram_signals(self) -> list[ResearchSignal]:
        text = self._fetch_text(self.settings.research_instagram_blog_url)
        matches = re.findall(r"###\s+([^\n]+)", text)
        items: list[ResearchSignal] = []
        seen: set[str] = set()
        for title in matches:
            clean = title.strip()
            if len(clean) < 8 or clean in seen:
                continue
            seen.add(clean)
            items.append(ResearchSignal(platform="instagram", title=clean, summary="Instagram official product or creator trend signal.", url=self.settings.research_instagram_blog_url))
            if len(items) >= 10:
                break
        return items

    def _collect_facebook_signals(self) -> list[ResearchSignal]:
        text = self._fetch_text(self.settings.research_facebook_news_url)
        matches = re.findall(r"###\s+\[(.*?)\]\((https://www\.facebook\.com/business/news/[^)]+)\)", text)
        items: list[ResearchSignal] = []
        seen: set[str] = set()
        for title, url in matches:
            clean = title.strip()
            if clean in seen:
                continue
            seen.add(clean)
            items.append(ResearchSignal(platform="facebook", title=clean, summary="Meta/Facebook business trend signal.", url=url))
            if len(items) >= 10:
                break
        return items

    @staticmethod
    def _to_dict(signal: ResearchSignal) -> dict[str, str]:
        return {
            "platform": signal.platform,
            "title": signal.title,
            "summary": signal.summary,
            "url": signal.url,
        }
