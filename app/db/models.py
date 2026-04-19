import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Platform(str, enum.Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"


class NicheStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    APPROVED = "approved"
    ARCHIVED = "archived"


class PromptStatus(str, enum.Enum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class VideoStatus(str, enum.Enum):
    REQUESTED = "requested"
    GENERATING = "generating"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    EXPIRED = "expired"


class PublicationStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class ApprovalTarget(str, enum.Enum):
    NICHE = "niche"
    PROMPT = "prompt"
    VIDEO = "video"


class ApprovalAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REGENERATE = "regenerate"


class AccountConnectionState(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    REAUTH_REQUIRED = "reauth_required"


class AgentType(str, enum.Enum):
    SCAN = "scan"
    PROMPT = "prompt"
    VIDEO = "video"
    PUBLISH = "publish"
    CLEANUP = "cleanup"
    AIDER = "aider"
    BENCHMARK = "benchmark"


class AgentRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AiderTaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BenchmarkScope(str, enum.Enum):
    TREND = "trend"
    PROMPT = "prompt"


class BenchmarkRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="Owner", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="user")
    social_accounts: Mapped[list["SocialAccount"]] = relationship(back_populates="user")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    market: Mapped[str] = mapped_column(String(64), default="tr-TR", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="projects")
    niches: Mapped[list["Niche"]] = relationship(back_populates="project")
    publish_profiles: Mapped[list["PublishProfile"]] = relationship(back_populates="project")


class Niche(Base, TimestampMixin):
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="web-scan", nullable=False)
    trend_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    status: Mapped[NicheStatus] = mapped_column(Enum(NicheStatus), default=NicheStatus.DISCOVERED, nullable=False)
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="niches")
    prompts: Mapped[list["Prompt"]] = relationship(back_populates="niche")


class Prompt(Base, TimestampMixin):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_platforms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tone: Mapped[str] = mapped_column(String(80), default="engaging", nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[PromptStatus] = mapped_column(Enum(PromptStatus), default=PromptStatus.GENERATED, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    niche: Mapped[Niche] = relationship(back_populates="prompts")
    videos: Mapped[list["Video"]] = relationship(back_populates="prompt")


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    status: Mapped[VideoStatus] = mapped_column(Enum(VideoStatus), default=VideoStatus.REQUESTED, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    format_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    prompt: Mapped[Prompt] = relationship(back_populates="videos")
    publications: Mapped[list["Publication"]] = relationship(back_populates="video")


class SocialAccount(Base, TimestampMixin):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("user_id", "platform", "external_account_id", name="uq_social_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(180), nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[AccountConnectionState] = mapped_column(Enum(AccountConnectionState), default=AccountConnectionState.PENDING, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="social_accounts")
    publications: Mapped[list["Publication"]] = relationship(back_populates="account")


class PublishProfile(Base, TimestampMixin):
    __tablename__ = "publish_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    account_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    platform_overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project: Mapped[Project] = relationship(back_populates="publish_profiles")


class Publication(Base, TimestampMixin):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("social_accounts.id"), nullable=False)
    status: Mapped[PublicationStatus] = mapped_column(Enum(PublicationStatus), default=PublicationStatus.PENDING, nullable=False)
    platform_post_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    video: Mapped[Video] = relationship(back_populates="publications")
    account: Mapped[SocialAccount] = relationship(back_populates="publications")


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[ApprovalTarget] = mapped_column(Enum(ApprovalTarget), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[ApprovalAction] = mapped_column(Enum(ApprovalAction), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EditRequest(Base, TimestampMixin):
    __tablename__ = "edit_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[ApprovalTarget] = mapped_column(Enum(ApprovalTarget), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus), default=AgentRunStatus.PENDING, nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderConfig(Base, TimestampMixin):
    __tablename__ = "provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BenchmarkRun(Base, TimestampMixin):
    __tablename__ = "benchmark_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[BenchmarkScope] = mapped_column(Enum(BenchmarkScope), nullable=False)
    status: Mapped[BenchmarkRunStatus] = mapped_column(Enum(BenchmarkRunStatus), default=BenchmarkRunStatus.PENDING, nullable=False)
    market: Mapped[str] = mapped_column(String(64), default="tr-TR", nullable=False)
    selected_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiderTask(Base, TimestampMixin):
    __tablename__ = "aider_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    status: Mapped[AiderTaskStatus] = mapped_column(Enum(AiderTaskStatus), default=AiderTaskStatus.PENDING, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    files_in_scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    output_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
