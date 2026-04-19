from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AiderTask, AiderTaskStatus, Project
from app.schemas.api import AiderTaskCreateRequest, AiderTaskUpdateRequest


class AiderTaskService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_task(self, project: Project, payload: AiderTaskCreateRequest) -> AiderTask:
        task = AiderTask(
            project_id=project.id,
            title=payload.title,
            instruction=payload.instruction,
            preferred_model=payload.preferred_model,
            branch_name=payload.branch_name,
            files_in_scope=payload.files_in_scope,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def claim_next_task(self) -> AiderTask | None:
        task = (
            self.session.query(AiderTask)
            .filter(AiderTask.status == AiderTaskStatus.PENDING)
            .order_by(AiderTask.created_at.asc())
            .first()
        )
        if task is None:
            return None
        task.status = AiderTaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task

    def update_task(self, task_id: int, payload: AiderTaskUpdateRequest) -> AiderTask:
        task = self.session.get(AiderTask, task_id)
        if task is None:
            raise ValueError("Aider task not found.")
        task.status = AiderTaskStatus(payload.status)
        task.output_summary = payload.output_summary
        task.output_payload = payload.output_payload
        task.error_message = payload.error_message
        if task.status in {AiderTaskStatus.COMPLETED, AiderTaskStatus.FAILED, AiderTaskStatus.CANCELLED}:
            task.completed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task
