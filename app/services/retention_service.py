from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Prompt, PromptStatus, PublicationStatus, Video, VideoStatus


class RetentionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def cleanup_expired_content(self, *, now: datetime | None = None) -> dict[str, int]:
        current_time = now or datetime.utcnow()
        prompt_updates = 0
        video_updates = 0
        file_deletes = 0

        expired_prompts = self.session.query(Prompt).filter(Prompt.expires_at <= current_time).all()
        for prompt in expired_prompts:
            has_publication = any(video.publications for video in prompt.videos)
            if has_publication:
                prompt.title = f"expired-prompt-{prompt.id}"
                prompt.body = "[expired]"
                prompt.metadata_payload = {"expired": True}
                prompt.status = PromptStatus.EXPIRED
                prompt_updates += 1
            else:
                self.session.delete(prompt)
                prompt_updates += 1

        expired_videos = self.session.query(Video).filter(Video.expires_at <= current_time).all()
        for video in expired_videos:
            published = any(publication.status == PublicationStatus.PUBLISHED for publication in video.publications)
            if video.storage_path:
                file_path = Path(video.storage_path)
                if file_path.exists() and file_path.is_file():
                    file_path.unlink(missing_ok=True)
                    file_deletes += 1
            video.storage_path = None
            video.preview_url = None
            video.status = VideoStatus.EXPIRED if not published else VideoStatus.PUBLISHED
            video_updates += 1

        self.session.commit()
        return {"prompts": prompt_updates, "videos": video_updates, "files": file_deletes}
