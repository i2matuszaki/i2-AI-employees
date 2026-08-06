from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base
from app.utilities.datetime import UTCDateTime, utc_now
from app.utilities.identifiers import generate_uuid

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.transcript_segment import TranscriptSegment
    from app.models.user import User


class TranscriptRunStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranscriptSourceType(str, Enum):
    MANUAL = "manual"
    FILE = "file"
    REALTIME = "realtime"
    EXTERNAL = "external"


class TranscriptRun(Base):
    __tablename__ = "transcript_runs"
    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_transcript_runs_id_length"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_transcript_runs_status",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'file', 'realtime', 'external')",
            name="ck_transcript_runs_source_type",
        ),
        CheckConstraint(
            "provider IS NULL OR length(provider) BETWEEN 1 AND 50",
            name="ck_transcript_runs_provider_length",
        ),
        CheckConstraint(
            "provider IS NULL OR provider = trim(provider)",
            name="ck_transcript_runs_provider_trimmed",
        ),
        CheckConstraint(
            "model_name IS NULL OR length(model_name) BETWEEN 1 AND 100",
            name="ck_transcript_runs_model_name_length",
        ),
        CheckConstraint(
            "model_name IS NULL OR model_name = trim(model_name)",
            name="ck_transcript_runs_model_name_trimmed",
        ),
        CheckConstraint(
            "language IS NULL OR length(language) BETWEEN 1 AND 20",
            name="ck_transcript_runs_language_length",
        ),
        CheckConstraint(
            "language IS NULL OR language = trim(language)",
            name="ck_transcript_runs_language_trimmed",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name="ck_transcript_runs_completed_at_requires_started_at",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="ck_transcript_runs_completed_at_order",
        ),
        CheckConstraint(
            "status != 'completed' OR completed_at IS NOT NULL",
            name="ck_transcript_runs_completed_status_has_completed_at",
        ),
        CheckConstraint(
            "status != 'failed' OR "
            "(error_message IS NOT NULL AND length(trim(error_message)) >= 1)",
            name="ck_transcript_runs_failed_status_has_error_message",
        ),
        Index("ix_transcript_runs_meeting_id", "meeting_id"),
        Index("ix_transcript_runs_status", "status"),
        Index("ix_transcript_runs_created_by_user_id", "created_by_user_id"),
        Index("ix_transcript_runs_created_at", "created_at"),
        Index("ix_transcript_runs_meeting_id_created_at", "meeting_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )

    meeting: Mapped[Meeting] = relationship(
        back_populates="transcript_runs", foreign_keys=[meeting_id]
    )
    created_by: Mapped[User] = relationship(
        back_populates="created_transcript_runs", foreign_keys=[created_by_user_id]
    )
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript_run",
        foreign_keys="TranscriptSegment.transcript_run_id",
        passive_deletes="all",
        cascade="save-update, merge",
    )

    @validates("status")
    def validate_status(self, _key: str, value: TranscriptRunStatus | str) -> str:
        return TranscriptRunStatus(value).value

    @validates("source_type")
    def validate_source_type(self, _key: str, value: TranscriptSourceType | str) -> str:
        return TranscriptSourceType(value).value

    @validates("provider", "model_name", "language")
    def validate_optional_label(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{key}には文字列を指定してください。")  # noqa: TRY004
        normalized = value.strip()
        if not normalized:
            return None
        maximum_lengths = {"provider": 50, "model_name": 100, "language": 20}
        if len(normalized) > maximum_lengths[key]:
            raise ValueError(f"{key}が最大文字数を超えています。")
        return normalized

    @validates("error_message")
    def validate_error_message(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("error_messageには文字列を指定してください。")  # noqa: TRY004
        normalized = value.strip()
        return normalized or None
