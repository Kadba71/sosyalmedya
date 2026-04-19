from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    timestamp: datetime


class TelegramWebhookPayload(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None
    callback_query: dict[str, Any] | None = None


class ConnectAccountRequest(BaseModel):
    platform: str
    display_name: str
    external_account_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class PublishProfileCreate(BaseModel):
    name: str
    description: str = ""
    account_ids: list[int] = Field(default_factory=list)
    platform_overrides: dict[str, Any] = Field(default_factory=dict)


class GeneratePromptsRequest(BaseModel):
    niche_id: int


class GenerateVideoRequest(BaseModel):
    prompt_id: int


class EditPromptRequest(BaseModel):
    prompt_id: int
    instruction: str


class EditVideoRequest(BaseModel):
    video_id: int
    instruction: str


class PublishVideoRequest(BaseModel):
    video_id: int
    account_ids: list[int] = Field(default_factory=list)
    publish_profile_id: int | None = None
    caption: str = ""


class AccountValidationRequest(BaseModel):
    remote_check: bool = True


class ApprovalRequest(BaseModel):
    target_type: str
    target_id: int
    action: str
    notes: str = ""


class BenchmarkRequest(BaseModel):
    scope: str
    market: str = "tr-TR"
    sample_count: int = 2


class ResearchSignalsRequest(BaseModel):
    market: str = "tr-TR"


class AiderTaskCreateRequest(BaseModel):
    title: str
    instruction: str
    preferred_model: str | None = None
    branch_name: str | None = None
    files_in_scope: list[str] = Field(default_factory=list)


class AiderTaskUpdateRequest(BaseModel):
    status: str
    output_summary: str = ""
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
