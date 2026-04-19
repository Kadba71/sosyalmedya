import httpx

from app.providers.base import VideoProvider, VideoRequestResult


class DummyVideoProvider(VideoProvider):
    def request_video(
        self,
        *,
        prompt_title: str,
        prompt_body: str,
        market: str,
        initial_frame_url: str | None = None,
        end_frame_url: str | None = None,
    ) -> VideoRequestResult:
        return VideoRequestResult(
            title=prompt_title,
            provider_name="dummy-video-provider",
            provider_job_id=None,
            preview_url=None,
            storage_path=None,
            format_payload={
                "state": "provider_pending",
                "market": market,
                "prompt_excerpt": prompt_body[:140],
                "initial_frame_url": initial_frame_url,
                "end_frame_url": end_frame_url,
            },
        )


class PiAPIKlingVideoProvider(VideoProvider):
    def __init__(self, *, base_url: str, api_key: str, service_mode: str, model: str, version: str, mode: str, duration: int, aspect_ratio: str, enable_audio: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.service_mode = service_mode
        self.model = model
        self.version = version
        self.mode = mode
        self.duration = duration
        self.aspect_ratio = aspect_ratio
        self.enable_audio = enable_audio

    def request_video(
        self,
        *,
        prompt_title: str,
        prompt_body: str,
        market: str,
        initial_frame_url: str | None = None,
        end_frame_url: str | None = None,
    ) -> VideoRequestResult:
        payload = {
            "model": self.model,
            "task_type": "video_generation",
            "input": {
                "prompt": prompt_body,
                "version": self.version,
                "mode": self.mode,
                "duration": self.duration,
                "aspect_ratio": self.aspect_ratio,
                "enable_audio": self.enable_audio,
            },
            "config": {
                "service_mode": self.service_mode,
            },
        }
        if initial_frame_url:
            payload["input"]["image_url"] = initial_frame_url
        if end_frame_url:
            payload["input"]["image_tail_url"] = end_frame_url
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        response = httpx.post(f"{self.base_url}/api/v1/task", headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        body = response.json()
        data = body.get("data", {})
        error = data.get("error") or {}
        if error.get("message"):
            raise RuntimeError(error["message"])

        return VideoRequestResult(
            title=prompt_title,
            provider_name="piapi-kling-3.0",
            provider_job_id=data.get("task_id"),
            preview_url=(data.get("output") or {}).get("video"),
            storage_path=None,
            format_payload={
                "status": data.get("status"),
                "model": data.get("model"),
                "task_type": data.get("task_type"),
                "provider": "piapi",
                "market": market,
                "initial_frame_url": initial_frame_url,
                "end_frame_url": end_frame_url,
                "input": data.get("input") or payload["input"],
                "output": data.get("output") or {},
            },
        )

    def get_task(self, task_id: str) -> dict:
        import httpx

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        response = httpx.get(f"{self.base_url}/api/v1/task/{task_id}", headers=headers, timeout=60.0)
        response.raise_for_status()
        body = response.json()
        return body.get("data", {})
