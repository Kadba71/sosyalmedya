from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path

from app.config import Settings
from app.db.models import Prompt, Video
from app.providers.llm_client import LLMChatClient


class NarrationServiceError(Exception):
    pass


class NarrationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = LLMChatClient(
            base_url=settings.llm_api_base,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    def create_dubbed_video(self, video: Video) -> dict:
        if not video.storage_path:
            raise NarrationServiceError("Merged video path is missing.")

        source_path = Path(video.storage_path)
        if not source_path.exists():
            raise NarrationServiceError("Merged video file could not be found for dubbing.")

        target_dir = self.settings.storage_path / f"video-{video.id}" / "tts"
        target_dir.mkdir(parents=True, exist_ok=True)
        narration_script = self._generate_narration_script(video.prompt)
        audio_path = target_dir / "narration.mp3"
        output_path = target_dir / "merged-tr-dubbed.mp4"

        self._synthesize_speech(narration_script, audio_path)
        self._mux_video_with_tts(source_path=source_path, audio_path=audio_path, output_path=output_path)

        return {
            "status": "completed",
            "script": narration_script,
            "audio_path": audio_path.as_posix(),
            "dubbed_storage_path": output_path.as_posix(),
            "voice": self.settings.tts_voice,
        }

    def _generate_narration_script(self, prompt: Prompt) -> str:
        selected_topic = (prompt.metadata_payload or {}).get("selected_topic") or {}
        topic_title = selected_topic.get("title") or prompt.title
        system_prompt = (
            "You write concise Turkish voice-over scripts for 20-second short videos. "
            "Return only the final narration text. No headings, no bullet points, no stage directions."
        )
        user_prompt = (
            f"Konu: {topic_title}. "
            f"Prompt basligi: {prompt.title}. "
            f"Video briefi: {prompt.body}. "
            f"Tamamlanmis video icin en fazla {self.settings.tts_max_words} kelimelik tek parca bir Turkce anlatici metni yaz. "
            "Metin ilk saniyede guclu bir giris yapmali, ortada bilgi ve gerilim tasimali, sonda net bir kapanis ya da mini CTA ile bitmeli. "
            "Cok uzun cumle kurma, dogal konusma ritmi kullan, yalnizca okunacak metni don."
        )
        text = ""
        if self.settings.llm_api_key:
            try:
                text = self.client.complete_text(
                    model=self.settings.llm_prompt_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.5,
                )
            except Exception:
                text = ""
        if not text:
            text = self._fallback_script(prompt, topic_title)
        return self._normalize_script(text)

    def _fallback_script(self, prompt: Prompt, topic_title: str) -> str:
        hook = (prompt.metadata_payload or {}).get("hook") or topic_title
        cta = (prompt.metadata_payload or {}).get("cta") or "Devami icin takip etmeyi unutma."
        return (
            f"{hook}. Simdi {topic_title} icinde gercekten dikkat ceken noktayi goruyorsun. "
            f"Bu detay fark yaratiyor ve izleyenlerin en cok merak ettigi seyi acikliyor. {cta}"
        )

    def _synthesize_speech(self, text: str, audio_path: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise NarrationServiceError("edge-tts package is required for Turkish TTS dubbing.") from exc

        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text,
                voice=self.settings.tts_voice,
                rate=self.settings.tts_rate,
                volume=self.settings.tts_volume,
            )
            await communicate.save(str(audio_path))

        asyncio.run(_run())

    def _mux_video_with_tts(self, *, source_path: Path, audio_path: Path, output_path: Path) -> None:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise NarrationServiceError("ffmpeg is required to create the dubbed video.")

        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise NarrationServiceError(completed.stderr.strip() or "ffmpeg TTS mux failed.")

    @staticmethod
    def _normalize_script(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = cleaned.strip('"')
        return cleaned