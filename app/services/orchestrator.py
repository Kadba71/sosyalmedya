from datetime import datetime, timedelta
import time

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AgentRun, AgentRunStatus, AgentType, Niche, Prompt, Project, Publication, PublicationStatus, SocialAccount, Video, VideoStatus
from app.providers.registry import ProviderRegistry
from app.publishers.registry import PublisherRegistry
from app.services.cover_workflow_service import CoverWorkflowService
from app.services.video_composition_service import VideoCompositionService
from app.utils.security import TokenCipher


class OrchestratorService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.providers = ProviderRegistry(settings, session)
        self.publishers = PublisherRegistry(settings, TokenCipher(settings))
        self.video_composition = VideoCompositionService(settings)
        self.cover_workflow = CoverWorkflowService(session, settings)

    def _start_run(self, agent_type: AgentType, payload: dict) -> AgentRun:
        agent_run = AgentRun(agent_type=agent_type, status=AgentRunStatus.RUNNING, input_payload=payload)
        self.session.add(agent_run)
        self.session.flush()
        return agent_run

    def _finish_run(self, agent_run: AgentRun, output_payload: dict) -> None:
        agent_run.status = AgentRunStatus.COMPLETED
        agent_run.output_payload = output_payload
        self.session.commit()

    def _fail_run(self, agent_run: AgentRun, error_message: str) -> None:
        agent_run.status = AgentRunStatus.FAILED
        agent_run.error_message = error_message
        self.session.commit()

    def daily_scan(self, project: Project) -> list[Niche]:
        agent_run = self._start_run(AgentType.SCAN, {"project_id": project.id})
        try:
            trends = self.providers.trend_provider().discover_trends(market=project.market)
            created: list[Niche] = []
            for item in trends:
                niche = Niche(
                    project_id=project.id,
                    name=item.name,
                    description=item.description,
                    source=item.source,
                    trend_score=item.trend_score,
                    context_payload=item.context_payload,
                )
                self.session.add(niche)
                created.append(niche)
            self.session.commit()
            self._finish_run(agent_run, {"niche_count": len(created)})
            return created
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise

    def research_niche_topics(self, niche: Niche, *, count: int = 5) -> list[dict]:
        agent_run = self._start_run(AgentType.SCAN, {"niche_id": niche.id, "mode": "topic_research", "count": count})
        try:
            topics = self.providers.trend_provider().discover_topics(
                niche_name=niche.name,
                niche_description=niche.description,
                market=niche.project.market,
                niche_context=niche.context_payload,
                count=count,
            )
            serialized_topics = [
                {
                    "index": index,
                    "title": item.title,
                    "summary": item.summary,
                    "interest_score": item.interest_score,
                    "keywords": item.keywords,
                    "source": item.source,
                    "context_payload": item.context_payload,
                }
                for index, item in enumerate(topics, start=1)
            ]
            niche.context_payload = {
                **(niche.context_payload or {}),
                "researched_topics": serialized_topics,
            }
            self.session.add(niche)
            self.session.commit()
            self._finish_run(agent_run, {"niche_id": niche.id, "topic_count": len(serialized_topics)})
            return serialized_topics
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise

    def generate_prompt_for_topic(self, niche: Niche, *, topic_index: int) -> Prompt:
        topics = list((niche.context_payload or {}).get("researched_topics") or [])
        if not topics:
            topics = self.research_niche_topics(niche)
        selected_topic = next((item for item in topics if int(item.get("index", 0)) == topic_index), None)
        if selected_topic is None:
            raise ValueError("Secilen konu bulunamadi.")

        agent_run = self._start_run(AgentType.PROMPT, {"niche_id": niche.id, "topic_index": topic_index, "mode": "topic_prompt"})
        try:
            topic_summary = selected_topic.get("summary") or ""
            topic_keywords = ", ".join(selected_topic.get("keywords") or [])
            context_payload = selected_topic.get("context_payload") or {}
            enriched_description = (
                f"{niche.description}\n\n"
                f"Secilen konu: {selected_topic['title']}\n"
                f"Konu ozeti: {topic_summary}\n"
                f"Anahtar kelimeler: {topic_keywords}\n"
                f"Icerik acisi: {context_payload.get('content_angle', '')}\n"
                f"Hook onerisi: {context_payload.get('suggested_hook', '')}\n"
                f"Izleyici problemi: {context_payload.get('viewer_problem', '')}"
            )
            result = self.providers.prompt_provider().generate_prompts(
                niche_name=f"{niche.name} - {selected_topic['title']}",
                niche_description=enriched_description,
                market=niche.project.market,
                count=1,
            )[0]
            prompt = Prompt(
                niche_id=niche.id,
                title=result.title,
                body=result.body,
                target_platforms=result.target_platforms,
                tone=result.tone,
                rank=result.rank,
                expires_at=datetime.utcnow() + timedelta(hours=self.settings.prompt_retention_hours),
                metadata_payload={
                    **result.metadata_payload,
                    "selected_topic": selected_topic,
                    "topic_index": topic_index,
                },
            )
            self.session.add(prompt)
            self.session.commit()
            self._finish_run(agent_run, {"prompt_id": prompt.id, "niche_id": niche.id, "topic_index": topic_index})
            return prompt
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise

    def generate_prompts(self, niche: Niche) -> list[Prompt]:
        agent_run = self._start_run(AgentType.PROMPT, {"niche_id": niche.id})
        try:
            results = self.providers.prompt_provider().generate_prompts(
                niche_name=niche.name,
                niche_description=niche.description,
                market=niche.project.market,
                count=10,
            )
            expires_at = datetime.utcnow() + timedelta(hours=self.settings.prompt_retention_hours)
            created: list[Prompt] = []
            for item in results:
                prompt = Prompt(
                    niche_id=niche.id,
                    title=item.title,
                    body=item.body,
                    target_platforms=item.target_platforms,
                    tone=item.tone,
                    rank=item.rank,
                    expires_at=expires_at,
                    metadata_payload=item.metadata_payload,
                )
                self.session.add(prompt)
                created.append(prompt)
            self.session.commit()
            self._finish_run(agent_run, {"prompt_count": len(created)})
            return created
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise

    def request_video(self, prompt: Prompt, *, title_override: str | None = None, body_override: str | None = None) -> Video:
        agent_run = self._start_run(AgentType.VIDEO, {"prompt_id": prompt.id, "segmented": True})
        try:
            video_provider = self.providers.video_provider()
            segment_requests = self.video_composition.build_segment_requests(
                prompt_title=title_override or prompt.title,
                prompt_body=body_override or prompt.body,
                metadata_payload=prompt.metadata_payload,
            )

            status = VideoStatus.READY
            segments: list[dict] = []
            preview_url: str | None = None
            provider_name: str | None = None
            continuation_frame_url: str | None = None
            for segment_request in segment_requests:
                current_initial_frame_url = continuation_frame_url if segment_request["continuation_from_previous_frame"] else None
                if segment_request["continuation_from_previous_frame"] and not current_initial_frame_url:
                    status = VideoStatus.REQUESTED
                    segments.append(
                        {
                            "segment_index": segment_request["segment_index"],
                            "title": segment_request["title"],
                            "duration_seconds": segment_request["duration_seconds"],
                            "aspect_ratio": segment_request["aspect_ratio"],
                            "continuation_from_previous_frame": True,
                            "prompt_body": segment_request["body"],
                            "provider_job_id": None,
                            "provider_name": provider_name or "segmented-video-pipeline",
                            "preview_url": None,
                            "storage_path": None,
                            "status": "blocked_waiting_previous_segment",
                            "initial_frame_url": None,
                            "task": None,
                            "format_payload": {"reason": "previous_segment_not_ready"},
                        }
                    )
                    break
                result = video_provider.request_video(
                    prompt_title=segment_request["title"],
                    prompt_body=segment_request["body"],
                    market=prompt.niche.project.market,
                    initial_frame_url=current_initial_frame_url,
                )
                provider_name = result.provider_name
                segment_status = "requested"
                segment_preview_url = result.preview_url
                segment_payload = dict(result.format_payload)
                task = None
                if result.provider_job_id and hasattr(video_provider, "get_task"):
                    task = self._poll_video_task(video_provider, result.provider_job_id)
                    output = task.get("output") or {}
                    segment_preview_url = output.get("video") or output.get("video_url") or segment_preview_url
                    segment_payload = {**segment_payload, "task": task}
                    task_status = (task.get("status") or "").lower()
                    if task_status == "completed":
                        segment_status = "ready"
                    elif task_status == "failed":
                        segment_status = "failed"
                    else:
                        segment_status = task_status or "requested"
                elif segment_preview_url:
                    segment_status = "ready"

                if segment_status != "ready":
                    status = VideoStatus.REQUESTED if segment_status != "failed" else VideoStatus.REJECTED
                preview_url = segment_preview_url or preview_url
                if segment_status == "ready" and segment_preview_url:
                    try:
                        continuation_frame_url = self.video_composition.extract_last_frame(
                            video_id=prompt.id,
                            segment_index=segment_request["segment_index"],
                            video_url=segment_preview_url,
                        )
                    except Exception:
                        continuation_frame_url = None
                segments.append(
                    {
                        "segment_index": segment_request["segment_index"],
                        "title": result.title,
                        "duration_seconds": segment_request["duration_seconds"],
                        "aspect_ratio": segment_request["aspect_ratio"],
                        "continuation_from_previous_frame": segment_request["continuation_from_previous_frame"],
                        "prompt_body": segment_request["body"],
                        "provider_job_id": result.provider_job_id,
                        "provider_name": result.provider_name,
                        "preview_url": segment_preview_url,
                        "storage_path": result.storage_path,
                        "status": segment_status,
                        "initial_frame_url": current_initial_frame_url,
                        "task": task,
                        "format_payload": segment_payload,
                    }
                )

            video = Video(
                prompt_id=prompt.id,
                status=status,
                title=title_override or prompt.title,
                storage_path=None,
                preview_url=preview_url,
                provider_name=provider_name or "segmented-video-pipeline",
                provider_job_id=None,
                format_payload={
                    "format": "vertical-short",
                    "aspect_ratio": prompt.metadata_payload.get("aspect_ratio") or self.settings.video_target_aspect_ratio,
                    "total_duration_seconds": prompt.metadata_payload.get("total_duration_seconds") or self.settings.video_total_duration_seconds,
                    "segment_count": len(segments),
                    "segment_duration_seconds": prompt.metadata_payload.get("segment_duration_seconds") or self.settings.video_segment_duration_seconds,
                    "segments": segments,
                    "merge": {
                        "required": True,
                        "status": "pending" if all(item.get("preview_url") for item in segments) else "waiting_segments",
                        "strategy": "ffmpeg_concat",
                    },
                    "continuation": {
                        "poll_attempts": self.settings.video_segment_poll_attempts,
                        "poll_interval_seconds": self.settings.video_segment_poll_interval_seconds,
                        "status": "ready" if continuation_frame_url else "waiting_previous_segment",
                    },
                },
                expires_at=datetime.utcnow() + timedelta(hours=self.settings.video_retention_hours),
            )
            self.session.add(video)
            self.session.commit()
            self._finish_run(agent_run, {"video_id": video.id, "provider": provider_name, "segment_count": len(segments)})
            return video
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise

    def _poll_video_task(self, video_provider, task_id: str) -> dict:
        last_task: dict = {}
        attempts = max(1, self.settings.video_segment_poll_attempts)
        for attempt in range(attempts):
            last_task = video_provider.get_task(task_id)
            task_status = str(last_task.get("status") or "").lower()
            if task_status in {"completed", "failed"}:
                return last_task
            if attempt < attempts - 1:
                time.sleep(max(0.0, self.settings.video_segment_poll_interval_seconds))
        return last_task

    def merge_video_segments(self, video: Video) -> Video:
        merge_payload = self.video_composition.merge_segments(video)
        video.storage_path = merge_payload["merged_storage_path"]
        video.format_payload = {
            **video.format_payload,
            "merge": {
                **(video.format_payload.get("merge") or {}),
                **merge_payload,
            },
        }
        self.session.commit()
        self.session.refresh(video)
        return video

    def generate_cover_prompts(self, video: Video) -> dict:
        return self.cover_workflow.generate_cover_prompts(video)

    def approve_cover_prompts(self, video: Video) -> dict:
        return self.cover_workflow.approve_cover_prompts(video)

    def generate_cover_images(self, video: Video) -> dict:
        return self.cover_workflow.generate_cover_images(video)

    def publish_video(self, *, video: Video, accounts: list[SocialAccount], caption: str, platform_overrides: dict | None = None) -> list[Publication]:
        agent_run = self._start_run(AgentType.PUBLISH, {"video_id": video.id, "account_ids": [account.id for account in accounts]})
        publications: list[Publication] = []
        try:
            for account in accounts:
                publisher = self.publishers.get(account.platform)
                result = publisher.publish(
                    account=account,
                    video=video,
                    caption=caption,
                    overrides=(platform_overrides or {}).get(account.platform.value),
                )
                publication = Publication(
                    video_id=video.id,
                    account_id=account.id,
                    status=PublicationStatus(result.status),
                    platform_post_id=result.platform_post_id,
                    platform_url=result.platform_url,
                    caption=caption,
                    error_message=result.error_message,
                    metadata_payload=result.metadata_payload,
                )
                self.session.add(publication)
                publications.append(publication)
            video.status = VideoStatus.PUBLISHED if any(item.status == PublicationStatus.PUBLISHED for item in publications) else video.status
            self.session.commit()
            self._finish_run(
                agent_run,
                {
                    "publication_count": len(publications),
                    "platform_results": [
                        {
                            "publication_id": item.id,
                            "account_id": item.account_id,
                            "status": item.status.value,
                            "platform_url": item.platform_url,
                            "error_message": item.error_message,
                            "cover": item.metadata_payload.get("cover"),
                        }
                        for item in publications
                    ],
                },
            )
            return publications
        except Exception as exc:
            self._fail_run(agent_run, str(exc))
            raise
