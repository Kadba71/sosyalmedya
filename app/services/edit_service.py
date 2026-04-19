from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ApprovalTarget, EditRequest, Prompt, PromptStatus, Video, VideoStatus
from app.providers.registry import ProviderRegistry
from app.services.orchestrator import OrchestratorService


class EditService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.providers = ProviderRegistry(settings, session)

    def revise_prompt(self, prompt: Prompt, instruction: str) -> tuple[EditRequest, Prompt]:
        request = self._create_request(ApprovalTarget.PROMPT, prompt.id, instruction)
        revised = self.providers.prompt_provider().revise_prompt(
            niche_name=prompt.niche.name,
            niche_description=prompt.niche.description,
            market=prompt.niche.project.market,
            current_title=prompt.title,
            current_body=prompt.body,
            instruction=instruction,
        )
        new_prompt = Prompt(
            niche_id=prompt.niche_id,
            title=revised.title,
            body=revised.body,
            target_platforms=revised.target_platforms,
            tone=revised.tone,
            rank=revised.rank,
            version=prompt.version + 1,
            status=PromptStatus.GENERATED,
            expires_at=datetime.utcnow() + timedelta(hours=self.settings.prompt_retention_hours),
            metadata_payload={**revised.metadata_payload, "edited_from_prompt_id": prompt.id, "edit_request_id": request.id},
        )
        prompt.status = PromptStatus.REJECTED
        request.resolved = True
        self.session.add(new_prompt)
        self.session.commit()
        self.session.refresh(request)
        self.session.refresh(new_prompt)
        return request, new_prompt

    def regenerate_prompt(self, prompt: Prompt) -> Prompt:
        generated = self.providers.prompt_provider().generate_prompts(
            niche_name=prompt.niche.name,
            niche_description=prompt.niche.description,
            market=prompt.niche.project.market,
            count=1,
        )[0]
        new_prompt = Prompt(
            niche_id=prompt.niche_id,
            title=generated.title,
            body=generated.body,
            target_platforms=generated.target_platforms,
            tone=generated.tone,
            rank=generated.rank,
            version=prompt.version + 1,
            status=PromptStatus.GENERATED,
            expires_at=datetime.utcnow() + timedelta(hours=self.settings.prompt_retention_hours),
            metadata_payload={**generated.metadata_payload, "regenerated_from_prompt_id": prompt.id},
        )
        prompt.status = PromptStatus.REJECTED
        self.session.add(new_prompt)
        self.session.commit()
        self.session.refresh(new_prompt)
        return new_prompt

    def revise_video(self, video: Video, instruction: str) -> tuple[EditRequest, Video]:
        request = self._create_request(ApprovalTarget.VIDEO, video.id, instruction)
        new_video = OrchestratorService(self.session, self.settings).request_video(
            video.prompt,
            title_override=f"{video.prompt.title} - revised",
            body_override=f"{video.prompt.body}\n\nRevision instruction: {instruction}",
        )
        new_video.format_payload = {**new_video.format_payload, "edited_from_video_id": video.id, "edit_request_id": request.id, "revision_instruction": instruction}
        video.status = VideoStatus.REJECTED
        request.resolved = True
        self.session.commit()
        self.session.refresh(request)
        self.session.refresh(new_video)
        return request, new_video

    def regenerate_video(self, video: Video) -> Video:
        new_video = OrchestratorService(self.session, self.settings).request_video(video.prompt)
        new_video.format_payload = {**new_video.format_payload, "regenerated_from_video_id": video.id}
        video.status = VideoStatus.REJECTED
        self.session.commit()
        self.session.refresh(new_video)
        return new_video

    def _create_request(self, target_type: ApprovalTarget, target_id: int, instruction: str) -> EditRequest:
        request = EditRequest(target_type=target_type, target_id=target_id, instruction=instruction, resolved=False)
        self.session.add(request)
        self.session.flush()
        return request