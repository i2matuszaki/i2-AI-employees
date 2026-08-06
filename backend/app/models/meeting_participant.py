from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base
from app.utilities.datetime import UTCDateTime, utc_now
from app.utilities.identifiers import generate_uuid

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User


class ParticipantRole(str, Enum):
    ORGANIZER = "organizer"
    FACILITATOR = "facilitator"
    PARTICIPANT = "participant"
    OBSERVER = "observer"


class AttendanceStatus(str, Enum):
    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ATTENDED = "attended"
    ABSENT = "absent"


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 36",
            name="ck_meeting_participants_id_length",
        ),
        CheckConstraint(
            "participant_role IN ('organizer', 'facilitator', 'participant', 'observer')",
            name="ck_meeting_participants_participant_role",
        ),
        CheckConstraint(
            "attendance_status IN ('invited', 'accepted', 'declined', 'attended', 'absent')",
            name="ck_meeting_participants_attendance_status",
        ),
        UniqueConstraint(
            "meeting_id",
            "user_id",
            name="uq_meeting_participants_meeting_id_user_id",
        ),
        Index("ix_meeting_participants_meeting_id", "meeting_id"),
        Index("ix_meeting_participants_user_id", "user_id"),
        Index("ix_meeting_participants_attendance_status", "attendance_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    participant_role: Mapped[str] = mapped_column(String(20), nullable=False)
    attendance_status: Mapped[str] = mapped_column(String(20), nullable=False)
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

    meeting: Mapped[Meeting] = relationship(
        back_populates="participants",
        foreign_keys=[meeting_id],
    )
    user: Mapped[User] = relationship(
        back_populates="meeting_participations",
        foreign_keys=[user_id],
    )

    @validates("participant_role")
    def validate_participant_role(
        self,
        _key: str,
        value: ParticipantRole | str,
    ) -> str:
        return ParticipantRole(value).value

    @validates("attendance_status")
    def validate_attendance_status(
        self,
        _key: str,
        value: AttendanceStatus | str,
    ) -> str:
        return AttendanceStatus(value).value
