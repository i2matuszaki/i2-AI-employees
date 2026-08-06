from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base
from app.utilities.datetime import UTCDateTime, utc_now
from app.utilities.email import normalize_email
from app.utilities.identifiers import generate_uuid

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.meeting_participant import MeetingParticipant
    from app.models.transcript_run import TranscriptRun
    from app.models.transcript_segment import TranscriptSegment
    from app.models.user_session import UserSession


class UserRole(str, Enum):
    USER = "user"
    APPROVER = "approver"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_users_id_length"),
        CheckConstraint("email = lower(trim(email))", name="ck_users_email_normalized"),
        CheckConstraint(
            "length(email) BETWEEN 1 AND 254",
            name="ck_users_email_length",
        ),
        CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 100",
            name="ck_users_display_name_length",
        ),
        CheckConstraint(
            "role IN ('user', 'approver', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
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

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    organizing_meetings: Mapped[list[Meeting]] = relationship(
        back_populates="organizer",
        foreign_keys="Meeting.organizer_user_id",
        passive_deletes="all",
    )
    created_meetings: Mapped[list[Meeting]] = relationship(
        back_populates="created_by",
        foreign_keys="Meeting.created_by_user_id",
        passive_deletes="all",
    )
    meeting_participations: Mapped[list[MeetingParticipant]] = relationship(
        back_populates="user",
        foreign_keys="MeetingParticipant.user_id",
        passive_deletes="all",
    )
    created_transcript_runs: Mapped[list[TranscriptRun]] = relationship(
        back_populates="created_by",
        foreign_keys="TranscriptRun.created_by_user_id",
        passive_deletes="all",
        cascade="save-update, merge",
    )
    spoken_transcript_segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="speaker_user",
        foreign_keys="TranscriptSegment.speaker_user_id",
        passive_deletes="all",
        cascade="save-update, merge",
    )
    edited_transcript_segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="edited_by",
        foreign_keys="TranscriptSegment.edited_by_user_id",
        passive_deletes="all",
        cascade="save-update, merge",
    )

    @validates("email")
    def validate_email(self, _key: str, value: str) -> str:
        return normalize_email(value)

    @validates("role")
    def validate_role(self, _key: str, value: UserRole | str) -> str:
        return UserRole(value).value
