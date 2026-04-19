from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import BenchmarkScope
from app.db.session import get_db_session
from app.schemas.api import AiderTaskUpdateRequest, MessageResponse
from app.services.aider_service import AiderTaskService


router = APIRouter(tags=["internal"])


def _authorize(x_internal_agent_token: str | None) -> None:
    settings = get_settings()
    if settings.internal_agent_token == "change-internal-agent-token":
        raise HTTPException(status_code=500, detail="Internal agent token is not configured securely.")
    if not x_internal_agent_token or not compare_digest(x_internal_agent_token, settings.internal_agent_token):
        raise HTTPException(status_code=401, detail="Invalid internal agent token.")


@router.post("/aider/next", response_model=MessageResponse)
def claim_aider_task(
    session: Session = Depends(get_db_session),
    x_internal_agent_token: str | None = Header(default=None),
) -> MessageResponse:
    _authorize(x_internal_agent_token)
    task = AiderTaskService(session).claim_next_task()
    if task is None:
        return MessageResponse(message="No pending aider task.", details={})
    return MessageResponse(
        message="Aider task claimed.",
        details={
            "task_id": task.id,
            "title": task.title,
            "instruction": task.instruction,
            "preferred_model": task.preferred_model,
            "branch_name": task.branch_name,
            "files_in_scope": task.files_in_scope,
        },
    )


@router.post("/aider/{task_id}", response_model=MessageResponse)
def update_aider_task(
    task_id: int,
    payload: AiderTaskUpdateRequest,
    session: Session = Depends(get_db_session),
    x_internal_agent_token: str | None = Header(default=None),
) -> MessageResponse:
    _authorize(x_internal_agent_token)
    task = AiderTaskService(session).update_task(task_id, payload)
    return MessageResponse(message="Aider task updated.", details={"task_id": task.id, "status": task.status.value})
