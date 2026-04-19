from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import Settings
from app.db.models import Video
from app.providers.video.base import extract_video_url


class VideoCompositionError(Exception):
    pass


class VideoCompositionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_segment_requests(self, *, prompt_title: str, prompt_body: str, metadata_payload: dict) -> list[dict]:
        segment_count = int(metadata_payload.get("segment_count") or self.settings.video_segment_count)
        segment_duration_seconds = int(metadata_payload.get("segment_duration_seconds") or self.settings.video_segment_duration_seconds)
        aspect_ratio = str(metadata_payload.get("aspect_ratio") or self.settings.video_target_aspect_ratio)

        requests: list[dict] = []
        for index in range(1, segment_count + 1):
            continuation_rule = (
                "Start from the exact last visible composition of segment 1 and continue the same subject, camera energy, and lighting. "
                "If an extracted last frame is available, use it as the continuity reference."
                if index > 1
                else "Establish the visual world, subject, and motion cleanly in the first seconds."
            )
            requests.append(
                {
                    "segment_index": index,
                    "title": f"{prompt_title} - segment {index}",
                    "body": (
                        f"Create segment {index} of {segment_count} for a vertical short. "
                        f"Total video target is {segment_count * segment_duration_seconds} seconds, but this segment must be exactly {segment_duration_seconds} seconds. "
                        f"Aspect ratio must be {aspect_ratio}. "
                        "The segment must include audible sound and natural Turkish story narration that advances the plot, not silent visuals. "
                        f"Base creative brief: {prompt_body}\n\n"
                        f"Segment-specific continuity instruction: {continuation_rule}"
                    ),
                    "duration_seconds": segment_duration_seconds,
                    "aspect_ratio": aspect_ratio,
                    "continuation_from_previous_frame": index > 1,
                }
            )
        return requests

    def merge_segments(self, video: Video) -> dict:
        segments = video.format_payload.get("segments") or []
        if len(segments) < 2:
            raise VideoCompositionError("At least two segment outputs are required for merge.")

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise VideoCompositionError("ffmpeg is required to merge video segments.")

        target_dir = self.settings.storage_path / f"video-{video.id}"
        target_dir.mkdir(parents=True, exist_ok=True)

        segment_paths: list[Path] = []
        for segment in segments:
            url = self._segment_url(segment)
            if not url:
                raise VideoCompositionError(f"Segment {segment.get('segment_index')} does not have a downloadable URL yet.")
            segment_path = target_dir / f"segment-{segment['segment_index']}.mp4"
            with httpx.stream("GET", url, timeout=self.settings.llm_timeout_seconds, follow_redirects=True) as response:
                response.raise_for_status()
                with segment_path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            segment_paths.append(segment_path)

        concat_file = target_dir / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segment_paths), encoding="utf-8")
        output_path = target_dir / "merged.mp4"
        command = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise VideoCompositionError(completed.stderr.strip() or "ffmpeg merge failed.")

        return {
            "status": "completed",
            "merged_storage_path": output_path.as_posix(),
            "segment_paths": [path.as_posix() for path in segment_paths],
        }

    def extract_last_frame(self, *, video_id: int, segment_index: int, video_url: str) -> str:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise VideoCompositionError("ffmpeg is required to extract the continuity frame.")

        target_dir = self.settings.storage_path / f"video-{video_id}" / "frames"
        target_dir.mkdir(parents=True, exist_ok=True)
        source_path = target_dir / f"segment-{segment_index}.mp4"
        with httpx.stream("GET", video_url, timeout=self.settings.llm_timeout_seconds, follow_redirects=True) as response:
            response.raise_for_status()
            with source_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

        output_path = target_dir / f"segment-{segment_index}-last-frame.png"
        command = [
            ffmpeg_path,
            "-y",
            "-sseof",
            "-0.1",
            "-i",
            str(source_path),
            "-update",
            "1",
            "-frames:v",
            "1",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise VideoCompositionError(completed.stderr.strip() or "ffmpeg last-frame extraction failed.")
        public_url = self._public_asset_url(output_path)
        return public_url or output_path.as_uri()

    def _public_asset_url(self, asset_path: Path) -> str | None:
        if not self.settings.public_base_url:
            return None
        try:
            relative_path = asset_path.relative_to(self.settings.storage_path).as_posix()
        except ValueError:
            return None
        return f"{self.settings.public_base_url.rstrip('/')}/media/videos/{quote(relative_path, safe='/')}"

    @staticmethod
    def _segment_url(segment: dict) -> str | None:
        task = segment.get("task") or {}
        output = task.get("output") or {}
        return segment.get("preview_url") or extract_video_url(output) or segment.get("storage_path")