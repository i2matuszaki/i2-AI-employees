from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import AttendanceStatus, MeetingStatus, ParticipantRole, UserRole

AwareDateTime = Annotated[datetime, Field(description="タイムゾーン付き日時")]


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("日時にはタイムゾーンが必要です。")
    return value


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParticipantInput(StrictInputModel):
    user_id: UUID
    participant_role: ParticipantRole
    attendance_status: AttendanceStatus = AttendanceStatus.INVITED


class MeetingCreate(StrictInputModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: MeetingStatus = MeetingStatus.SCHEDULED
    scheduled_start_at: AwareDateTime
    scheduled_end_at: AwareDateTime
    actual_start_at: AwareDateTime | None = None
    actual_end_at: AwareDateTime | None = None
    organizer_user_id: UUID
    participants: list[ParticipantInput] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("会議名は空白以外の文字を指定してください。")
        return normalized

    @field_validator(
        "scheduled_start_at",
        "scheduled_end_at",
        "actual_start_at",
        "actual_end_at",
    )
    @classmethod
    def validate_aware_datetime(cls, value: datetime | None) -> datetime | None:
        return _validate_aware_datetime(value)


class MeetingUpdate(StrictInputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: MeetingStatus | None = None
    scheduled_start_at: AwareDateTime | None = None
    scheduled_end_at: AwareDateTime | None = None
    actual_start_at: AwareDateTime | None = None
    actual_end_at: AwareDateTime | None = None
    organizer_user_id: UUID | None = None
    participants: list[ParticipantInput] | None = None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self) -> Self:
        nullable_fields = {"description", "actual_start_at", "actual_end_at"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name}にnullは指定できません。")
        return self

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("会議名は空白以外の文字を指定してください。")
        return normalized

    @field_validator(
        "scheduled_start_at",
        "scheduled_end_at",
        "actual_start_at",
        "actual_end_at",
    )
    @classmethod
    def validate_aware_datetime(cls, value: datetime | None) -> datetime | None:
        return _validate_aware_datetime(value)


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole


class ParticipantResponse(BaseModel):
    id: UUID
    user: UserResponse
    participant_role: ParticipantRole
    attendance_status: AttendanceStatus
    created_at: datetime
    updated_at: datetime


class MeetingBaseResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    status: MeetingStatus
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    organizer: UserResponse
    created_by: UserResponse
    created_at: datetime
    updated_at: datetime


class MeetingListItem(MeetingBaseResponse):
    participant_count: int


class MeetingListResponse(BaseModel):
    items: list[MeetingListItem]
    total: int
    limit: int
    offset: int


class MeetingDetailResponse(MeetingBaseResponse):
    participants: list[ParticipantResponse]
