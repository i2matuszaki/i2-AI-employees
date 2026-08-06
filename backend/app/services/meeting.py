from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from app.models import Meeting, MeetingParticipant, User
from app.schemas.meeting import (
    MeetingCreate,
    MeetingDetailResponse,
    MeetingListItem,
    MeetingListResponse,
    MeetingUpdate,
    ParticipantInput,
    ParticipantResponse,
    UserResponse,
)

DATABASE_CONFLICT_MESSAGE = "データベースの整合性競合が発生しました。"


def _not_found_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="会議が存在しません。",
    )


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _database_conflict_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DATABASE_CONFLICT_MESSAGE)


def _uuid_string(value: UUID) -> str:
    return str(value)


def validate_meeting_times(
    scheduled_start_at: datetime,
    scheduled_end_at: datetime,
    actual_start_at: datetime | None,
    actual_end_at: datetime | None,
) -> None:
    if scheduled_end_at <= scheduled_start_at:
        raise _validation_error("終了予定日時は開始予定日時より後にしてください。")
    if actual_end_at is not None and actual_start_at is None:
        raise _validation_error("実終了日時を指定する場合は実開始日時も必要です。")
    if (
        actual_start_at is not None
        and actual_end_at is not None
        and actual_end_at < actual_start_at
    ):
        raise _validation_error("実終了日時は実開始日時以降にしてください。")


def validate_participant_duplicates(participants: list[ParticipantInput]) -> None:
    normalized_ids = [_uuid_string(participant.user_id) for participant in participants]
    if len(normalized_ids) != len(set(normalized_ids)):
        raise _validation_error("同じ利用者を参加者へ複数指定できません。")


def ensure_user_ids_exist(db_session: Session, user_ids: set[str]) -> None:
    if not user_ids:
        return
    existing_ids = set(db_session.scalars(select(User.id).where(User.id.in_(user_ids))).all())
    if existing_ids != user_ids:
        raise _validation_error("指定された利用者が存在しません。")


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _meeting_response_values(meeting: Meeting, organizer: User, created_by: User) -> dict[str, Any]:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "status": meeting.status,
        "scheduled_start_at": meeting.scheduled_start_at,
        "scheduled_end_at": meeting.scheduled_end_at,
        "actual_start_at": meeting.actual_start_at,
        "actual_end_at": meeting.actual_end_at,
        "organizer": _user_response(organizer),
        "created_by": _user_response(created_by),
        "created_at": meeting.created_at,
        "updated_at": meeting.updated_at,
    }


def get_meeting_detail(db_session: Session, meeting_id: str) -> MeetingDetailResponse:
    organizer_alias = aliased(User)
    creator_alias = aliased(User)
    row = db_session.execute(
        select(Meeting, organizer_alias, creator_alias)
        .join(organizer_alias, organizer_alias.id == Meeting.organizer_user_id)
        .join(creator_alias, creator_alias.id == Meeting.created_by_user_id)
        .where(Meeting.id == meeting_id)
    ).one_or_none()
    if row is None:
        raise _not_found_error()

    meeting, organizer, created_by = row
    role_order = case(
        (MeetingParticipant.participant_role == "organizer", 0),
        (MeetingParticipant.participant_role == "facilitator", 1),
        (MeetingParticipant.participant_role == "participant", 2),
        (MeetingParticipant.participant_role == "observer", 3),
        else_=4,
    )
    participant_rows = db_session.execute(
        select(MeetingParticipant, User)
        .join(User, User.id == MeetingParticipant.user_id)
        .where(MeetingParticipant.meeting_id == meeting_id)
        .order_by(role_order, User.display_name.asc(), MeetingParticipant.id.asc())
    ).all()
    participants = [
        ParticipantResponse(
            id=participant.id,
            user=_user_response(user),
            participant_role=participant.participant_role,
            attendance_status=participant.attendance_status,
            created_at=participant.created_at,
            updated_at=participant.updated_at,
        )
        for participant, user in participant_rows
    ]
    return MeetingDetailResponse(
        **_meeting_response_values(meeting, organizer, created_by),
        participants=participants,
    )


def create_meeting(
    db_session: Session,
    request: MeetingCreate,
    created_by_user_id: str,
) -> MeetingDetailResponse:
    validate_participant_duplicates(request.participants)
    validate_meeting_times(
        request.scheduled_start_at,
        request.scheduled_end_at,
        request.actual_start_at,
        request.actual_end_at,
    )
    organizer_user_id = _uuid_string(request.organizer_user_id)
    participant_user_ids = {_uuid_string(item.user_id) for item in request.participants}
    ensure_user_ids_exist(db_session, {organizer_user_id, *participant_user_ids})

    meeting = Meeting(
        title=request.title,
        description=request.description,
        status=request.status,
        scheduled_start_at=request.scheduled_start_at,
        scheduled_end_at=request.scheduled_end_at,
        actual_start_at=request.actual_start_at,
        actual_end_at=request.actual_end_at,
        organizer_user_id=organizer_user_id,
        created_by_user_id=created_by_user_id,
    )
    db_session.add(meeting)
    db_session.add_all(
        [
            MeetingParticipant(
                meeting=meeting,
                user_id=_uuid_string(participant.user_id),
                participant_role=participant.participant_role,
                attendance_status=participant.attendance_status,
            )
            for participant in request.participants
        ]
    )
    try:
        db_session.flush()
        meeting_id = meeting.id
        db_session.commit()
    except IntegrityError as error:
        db_session.rollback()
        raise _database_conflict_error() from error
    except SQLAlchemyError:
        db_session.rollback()
        raise
    return get_meeting_detail(db_session, meeting_id)


def list_meetings(
    db_session: Session,
    *,
    meeting_status: str | None,
    organizer_user_id: str | None,
    created_by_user_id: str | None,
    scheduled_from: datetime | None,
    scheduled_to: datetime | None,
    limit: int,
    offset: int,
) -> MeetingListResponse:
    if scheduled_from is not None and (
        scheduled_from.tzinfo is None or scheduled_from.utcoffset() is None
    ):
        raise _validation_error("scheduled_fromにはタイムゾーンが必要です。")
    if scheduled_to is not None and (
        scheduled_to.tzinfo is None or scheduled_to.utcoffset() is None
    ):
        raise _validation_error("scheduled_toにはタイムゾーンが必要です。")
    if scheduled_from is not None and scheduled_to is not None and scheduled_from >= scheduled_to:
        raise _validation_error("scheduled_fromはscheduled_toより前にしてください。")

    filters = []
    if meeting_status is not None:
        filters.append(Meeting.status == meeting_status)
    if organizer_user_id is not None:
        filters.append(Meeting.organizer_user_id == organizer_user_id)
    if created_by_user_id is not None:
        filters.append(Meeting.created_by_user_id == created_by_user_id)
    if scheduled_from is not None:
        filters.append(Meeting.scheduled_start_at >= scheduled_from)
    if scheduled_to is not None:
        filters.append(Meeting.scheduled_start_at < scheduled_to)

    total = db_session.scalar(select(func.count()).select_from(Meeting).where(*filters)) or 0
    participant_counts = (
        select(
            MeetingParticipant.meeting_id.label("meeting_id"),
            func.count(MeetingParticipant.id).label("participant_count"),
        )
        .group_by(MeetingParticipant.meeting_id)
        .subquery()
    )
    organizer_alias = aliased(User)
    creator_alias = aliased(User)
    rows = db_session.execute(
        select(
            Meeting,
            organizer_alias,
            creator_alias,
            func.coalesce(participant_counts.c.participant_count, 0),
        )
        .join(organizer_alias, organizer_alias.id == Meeting.organizer_user_id)
        .join(creator_alias, creator_alias.id == Meeting.created_by_user_id)
        .outerjoin(participant_counts, participant_counts.c.meeting_id == Meeting.id)
        .where(*filters)
        .order_by(Meeting.scheduled_start_at.asc(), Meeting.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return MeetingListResponse(
        items=[
            MeetingListItem(
                **_meeting_response_values(meeting, organizer, created_by),
                participant_count=participant_count,
            )
            for meeting, organizer, created_by, participant_count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def replace_participants(
    db_session: Session,
    meeting: Meeting,
    participants: list[ParticipantInput],
) -> None:
    db_session.execute(
        delete(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting.id)
    )
    db_session.flush()
    db_session.add_all(
        [
            MeetingParticipant(
                meeting_id=meeting.id,
                user_id=_uuid_string(participant.user_id),
                participant_role=participant.participant_role,
                attendance_status=participant.attendance_status,
            )
            for participant in participants
        ]
    )


def update_meeting(
    db_session: Session,
    meeting_id: str,
    request: MeetingUpdate,
) -> MeetingDetailResponse:
    meeting = db_session.get(Meeting, meeting_id)
    if meeting is None:
        raise _not_found_error()

    specified = request.model_fields_set
    participants = request.participants if "participants" in specified else None
    if participants is not None:
        validate_participant_duplicates(participants)

    organizer_user_id = (
        _uuid_string(request.organizer_user_id)
        if "organizer_user_id" in specified and request.organizer_user_id is not None
        else meeting.organizer_user_id
    )
    requested_user_ids = {organizer_user_id}
    if participants is not None:
        requested_user_ids.update(_uuid_string(item.user_id) for item in participants)
    ensure_user_ids_exist(db_session, requested_user_ids)

    scheduled_start_at = (
        request.scheduled_start_at
        if "scheduled_start_at" in specified
        else meeting.scheduled_start_at
    )
    scheduled_end_at = (
        request.scheduled_end_at if "scheduled_end_at" in specified else meeting.scheduled_end_at
    )
    actual_start_at = (
        request.actual_start_at if "actual_start_at" in specified else meeting.actual_start_at
    )
    actual_end_at = request.actual_end_at if "actual_end_at" in specified else meeting.actual_end_at
    assert scheduled_start_at is not None
    assert scheduled_end_at is not None
    validate_meeting_times(scheduled_start_at, scheduled_end_at, actual_start_at, actual_end_at)

    scalar_fields = {
        "title",
        "description",
        "status",
        "scheduled_start_at",
        "scheduled_end_at",
        "actual_start_at",
        "actual_end_at",
    }
    for field_name in specified & scalar_fields:
        setattr(meeting, field_name, getattr(request, field_name))
    if "organizer_user_id" in specified:
        meeting.organizer_user_id = organizer_user_id

    try:
        if participants is not None:
            replace_participants(db_session, meeting, participants)
        db_session.flush()
        db_session.commit()
    except IntegrityError as error:
        db_session.rollback()
        raise _database_conflict_error() from error
    except SQLAlchemyError:
        db_session.rollback()
        raise
    return get_meeting_detail(db_session, meeting_id)


def delete_meeting(db_session: Session, meeting_id: str) -> None:
    meeting = db_session.get(Meeting, meeting_id)
    if meeting is None:
        raise _not_found_error()
    try:
        db_session.delete(meeting)
        db_session.commit()
    except IntegrityError as error:
        db_session.rollback()
        raise _database_conflict_error() from error
    except SQLAlchemyError:
        db_session.rollback()
        raise
