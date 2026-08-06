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
    from app.models.meeting_participant import MeetingParticipant
    from app.models.transcript_run import TranscriptRun
    from app.models.user import User


class MeetingStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_meetings_id_length"),
        CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 200",
            name="ck_meetings_title_length",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
            name="ck_meetings_status",
        ),
        CheckConstraint(
            "scheduled_end_at > scheduled_start_at",
            name="ck_meetings_scheduled_time_order",
        ),
        CheckConstraint(
            "actual_end_at IS NULL OR actual_start_at IS NOT NULL",
            name="ck_meetings_actual_end_requires_start",
        ),
        CheckConstraint(
            "actual_start_at IS NULL OR actual_end_at IS NULL "
            "OR actual_end_at >= actual_start_at",
            name="ck_meetings_actual_time_order",
        ),
        Index("ix_meetings_status", "status"),
        Index("ix_meetings_scheduled_start_at", "scheduled_start_at"),
        Index("ix_meetings_organizer_user_id", "organizer_user_id"),
        Index("ix_meetings_created_by_user_id", "created_by_user_id"),
        Index(
            "ix_meetings_status_scheduled_start_at",
            "status",
            "scheduled_start_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    actual_start_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    organizer_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    organizer: Mapped[User] = relationship(
        back_populates="organizing_meetings",
        foreign_keys=[organizer_user_id],
    )
    created_by: Mapped[User] = relationship(
        back_populates="created_meetings",
        foreign_keys=[created_by_user_id],
    )
    participants: Mapped[list[MeetingParticipant]] = relationship(
        back_populates="meeting",
        passive_deletes="all",
        cascade="save-update, merge",
    )
    transcript_runs: Mapped[list[TranscriptRun]] = relationship(
        back_populates="meeting",
        foreign_keys="TranscriptRun.meeting_id",
        passive_deletes="all",
        cascade="save-update, merge",
    )

    @validates("title")
    def validate_title(self, _key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("会議名には文字列を指定してください。")  # noqa: TRY004
        normalized = value.strip()
        if not 1 <= len(normalized) <= 200:
            raise ValueError("会議名は前後の空白を除いて1文字以上200文字以下です。")
        return normalized

    @validates("status")
    def validate_status(self, _key: str, value: MeetingStatus | str) -> str:
        return MeetingStatus(value).value
