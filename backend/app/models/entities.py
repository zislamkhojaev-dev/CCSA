import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    supervisor = "supervisor"


class CallStatus(str, enum.Enum):
    pending = "pending"
    downloading = "downloading"
    transcribing = "transcribing"
    analyzing = "analyzing"
    analyzed = "analyzed"
    error = "error"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.supervisor.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    webitel_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    team_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    calls: Mapped[list["Call"]] = relationship(back_populates="operator")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    criteria: Mapped[list["Criterion"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="Criterion.sort_order"
    )


class Criterion(Base):
    __tablename__ = "criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    weight_percent: Mapped[int] = mapped_column(Integer, default=10)
    max_score: Mapped[int] = mapped_column(Integer, default=10)
    prompt: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    scenario: Mapped["Scenario"] = relationship(back_populates="criteria")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=CallStatus.pending.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="webitel")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operator: Mapped["Operator | None"] = relationship(back_populates="calls")
    scenario: Mapped["Scenario | None"] = relationship()
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    tags: Mapped[list["CallTag"]] = relationship(back_populates="call", cascade="all, delete-orphan")
    notes: Mapped[list["SupervisorNote"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    utterances: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call: Mapped["Call"] = relationship(back_populates="transcriptions")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    llm_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_violation: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_pains: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_outcome: Mapped[str | None] = mapped_column(String(100), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    criteria_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call: Mapped["Call"] = relationship(back_populates="analysis_results")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("name", name="uq_tag_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call_links: Mapped[list["CallTag"]] = relationship(back_populates="tag")


class CallTag(Base):
    __tablename__ = "call_tags"
    __table_args__ = (UniqueConstraint("call_id", "tag_id", name="uq_call_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"))

    call: Mapped["Call"] = relationship(back_populates="tags")
    tag: Mapped["Tag"] = relationship(back_populates="call_links")


class SupervisorNote(Base):
    __tablename__ = "supervisor_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call: Mapped["Call"] = relationship(back_populates="notes")
    user: Mapped["User"] = relationship()


class PlaygroundJob(Base):
    __tablename__ = "playground_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)
    use_scenario_prompt: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    files: Mapped[list["PlaygroundFile"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class PlaygroundFile(Base):
    __tablename__ = "playground_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("playground_jobs.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["PlaygroundJob"] = relationship(back_populates="files")
    result: Mapped["PlaygroundResult | None"] = relationship(
        back_populates="file", uselist=False, cascade="all, delete-orphan"
    )


class PlaygroundResult(Base):
    __tablename__ = "playground_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("playground_files.id", ondelete="CASCADE"), unique=True)
    transcription: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    file: Mapped["PlaygroundFile"] = relationship(back_populates="result")


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value_encrypted: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_cron: Mapped[str] = mapped_column(String(100), default="*/30 * * * *")
    batch_size: Mapped[int] = mapped_column(Integer, default=10)
    active_days: Mapped[list] = mapped_column(JSONB, default=list)
    time_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    time_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    default_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"), nullable=True)


class ResearchStudy(Base):
    __tablename__ = "research_studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    filters_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    call_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
