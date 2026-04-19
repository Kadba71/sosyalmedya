from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Platform, Video
from app.providers.llm_client import LLMChatClient


@dataclass(frozen=True, slots=True)
class CoverSpec:
    width: int
    height: int
    aspect_ratio: str
    upload_supported: bool
    usage_note: str


PLATFORM_COVER_SPECS: dict[str, CoverSpec] = {
    Platform.YOUTUBE.value: CoverSpec(1280, 720, "16:9", True, "YouTube custom thumbnail upload is supported."),
    Platform.INSTAGRAM.value: CoverSpec(1080, 1920, "9:16", False, "Instagram Reels cover upload is not applied automatically by this API flow."),
    Platform.TIKTOK.value: CoverSpec(1080, 1920, "9:16", False, "TikTok cover selection remains creator-side in the current API flow."),
    Platform.FACEBOOK.value: CoverSpec(1080, 1920, "9:16", False, "Facebook custom cover upload is not wired in this publish flow yet."),
}


class CoverWorkflowService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def generate_cover_prompts(self, video: Video) -> dict:
        prompts = self._llm_cover_prompts(video) or self._fallback_cover_prompts(video)
        covers_payload = self._covers_payload(video)
        covers_payload["prompt_status"] = "draft"
        covers_payload["prompts"] = prompts
        covers_payload["assets"] = {}
        covers_payload["image_status"] = "pending_prompt_approval"
        video.format_payload = {**video.format_payload, "covers": covers_payload}
        self.session.commit()
        self.session.refresh(video)
        return prompts

    def approve_cover_prompts(self, video: Video) -> dict:
        covers_payload = self._covers_payload(video)
        if not covers_payload.get("prompts"):
            self.generate_cover_prompts(video)
            covers_payload = self._covers_payload(video)
        covers_payload["prompt_status"] = "approved"
        covers_payload["image_status"] = "pending_generation"
        video.format_payload = {**video.format_payload, "covers": covers_payload}
        self.session.commit()
        self.session.refresh(video)
        return covers_payload.get("prompts", {})

    def generate_cover_images(self, video: Video) -> dict:
        covers_payload = self._covers_payload(video)
        if covers_payload.get("prompt_status") != "approved":
            raise ValueError("Cover prompts must be approved before image generation.")
        prompts = covers_payload.get("prompts") or {}
        if not prompts:
            raise ValueError("Cover prompts are missing; generate and approve prompts before image generation.")
        assets = dict(covers_payload.get("assets") or {})
        generated_assets: dict[str, dict] = {}
        for platform, prompt_info in prompts.items():
            if platform not in PLATFORM_COVER_SPECS:
                continue
            spec = PLATFORM_COVER_SPECS[platform]
            prompt_text = str(prompt_info.get("prompt") or "").strip()
            if not prompt_text:
                raise ValueError(f"Cover prompt is empty for platform: {platform}")
            asset = self._generate_flux_cover(prompt_text, spec.width, spec.height)
            generated_assets[platform] = {
                **asset,
                "platform": platform,
                "aspect_ratio": spec.aspect_ratio,
                "upload_supported": spec.upload_supported,
                "usage_note": spec.usage_note,
                "approved_prompt": prompt_info,
            }
        covers_payload["assets"] = {**assets, **generated_assets}
        covers_payload["image_status"] = "generated"
        video.format_payload = {**video.format_payload, "covers": covers_payload}
        self.session.commit()
        self.session.refresh(video)
        return generated_assets

    def build_cover_report(self, video: Video) -> list[dict]:
        covers_payload = self._covers_payload(video)
        prompts = covers_payload.get("prompts") or {}
        assets = covers_payload.get("assets") or {}
        report: list[dict] = []
        for platform, spec in PLATFORM_COVER_SPECS.items():
            platform_asset = assets.get(platform) or {}
            report.append(
                {
                    "platform": platform,
                    "prompt_ready": platform in prompts,
                    "prompt_status": covers_payload.get("prompt_status"),
                    "image_status": platform_asset.get("status") or ("generated" if platform in assets else covers_payload.get("image_status", "missing")),
                    "upload_supported": spec.upload_supported,
                    "image_url": platform_asset.get("image_url"),
                    "usage_note": spec.usage_note,
                }
            )
        return report

    def _llm_cover_prompts(self, video: Video) -> dict[str, dict] | None:
        if self.settings.prompt_provider.lower() not in {"llm", "piapi", "ollama"}:
            return None
        client = LLMChatClient(
            base_url=self.settings.llm_api_base,
            api_key=self.settings.llm_api_key,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        system_prompt = "You are an elite social cover-image prompt engineer. Return only valid JSON with a top-level key named covers."
        user_prompt = (
            f"Create platform-specific cover image prompts for the video titled '{video.title}'. "
            f"Video creative brief: {video.prompt.body}. "
            "Return one item for youtube, instagram, tiktok, and facebook. "
            "Each item must include platform, prompt, hook_text, visual_style, and focus_subject. "
            "Youtube should optimize for 16:9 thumbnail. Instagram, TikTok and Facebook should optimize for 9:16 vertical reel cover. "
            "Avoid embedded long text in the image itself."
        )
        try:
            payload = client.complete_json(model=self.settings.llm_prompt_model, system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            return None
        results: dict[str, dict] = {}
        for item in payload.get("covers", []):
            platform = str(item.get("platform", "")).lower()
            if platform not in PLATFORM_COVER_SPECS:
                continue
            results[platform] = {
                "prompt": item.get("prompt", ""),
                "hook_text": item.get("hook_text", ""),
                "visual_style": item.get("visual_style", ""),
                "focus_subject": item.get("focus_subject", ""),
            }
        return results or None

    def _fallback_cover_prompts(self, video: Video) -> dict[str, dict]:
        body = video.prompt.body
        title = video.title
        prompts: dict[str, dict] = {}
        for platform, spec in PLATFORM_COVER_SPECS.items():
            prompts[platform] = {
                "prompt": (
                    f"Create a high-CTR social cover image for platform {platform}. "
                    f"Title context: {title}. Video brief: {body}. "
                    f"Aspect ratio {spec.aspect_ratio}, clean focal subject, bold composition, mobile-first readability, no watermark, no small text blocks."
                ),
                "hook_text": title[:80],
                "visual_style": "high contrast cinematic social cover",
                "focus_subject": video.prompt.niche.name,
            }
        return prompts

    def _generate_flux_cover(self, prompt: str, width: int, height: int) -> dict:
        if not self.settings.piapi_api_key:
            raise ValueError("PIAPI_API_KEY is required for cover image generation.")
        response = httpx.post(
            f"{self.settings.piapi_base_url.rstrip('/')}/api/v1/task",
            headers={"X-API-Key": self.settings.piapi_api_key, "Content-Type": "application/json"},
            json={
                "model": self.settings.flux_model,
                "task_type": "txt2img",
                "input": {"prompt": prompt, "width": width, "height": height},
                "config": {"service_mode": self.settings.piapi_service_mode},
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json().get("data", {})
        task_id = payload.get("task_id")
        if not task_id:
            raise ValueError("Flux cover task_id was not returned.")
        task = self._poll_flux_task(task_id)
        output = task.get("output") or {}
        image_url = output.get("image_url")
        if not image_url:
            raise ValueError("Flux cover generation did not return image_url.")
        return {"task_id": task_id, "status": task.get("status"), "image_url": image_url, "output": output}

    def _poll_flux_task(self, task_id: str) -> dict:
        last_payload: dict = {}
        attempts = max(1, self.settings.cover_image_poll_attempts)
        for attempt in range(attempts):
            response = httpx.get(
                f"{self.settings.piapi_base_url.rstrip('/')}/api/v1/task/{task_id}",
                headers={"X-API-Key": self.settings.piapi_api_key or ""},
                timeout=30.0,
            )
            response.raise_for_status()
            last_payload = response.json().get("data", {})
            status = str(last_payload.get("status") or "").lower()
            if status in {"success", "failed"}:
                return last_payload
            if attempt < attempts - 1:
                time.sleep(max(0.0, self.settings.cover_image_poll_interval_seconds))
        return last_payload

    @staticmethod
    def _covers_payload(video: Video) -> dict:
        return dict((video.format_payload or {}).get("covers") or {})