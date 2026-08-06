from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import Meeting, MeetingParticipant, User
from app.security.password import hash_password


def make_user(email: str) -> User:
    return User(
        email=email,
        display_name="テスト利用者",
        role="user",
        password_hash=hash_password("fictional-password"),
    )


def make_meeting(organizer: User, created_by: User, **overrides: object) -> Meeting:
    values: dict[str, object] = {
        "title": "定例会議",
        "description": "進捗を確認する会議",
        "status": "scheduled",
        "scheduled_start_at": datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
        "scheduled_end_at": datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        "organizer": organizer,
        "created_by": created_by,
    }
    values.update(overrides)
    return Meeting(**values)


def make_participant(
    meeting: Meeting,
    user: User,
    **overrides: object,
) -> MeetingParticipant:
    values: dict[str, object] = {
        "meeting": meeting,
        "user": user,
        "participant_role": "participant",
        "attendance_status": "invited",
    }
    values.update(overrides)
    return MeetingParticipant(**values)


def persist_users(db_session: Session) -> tuple[User, User, User]:
    organizer = make_user("organizer@example.test")
    creator = make_user("creator@example.test")
    participant = make_user("participant@example.test")
    db_session.add_all([organizer, creator, participant])
    db_session.flush()
    return organizer, creator, participant


def assert_commit_fails(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def insert_meeting_directly(db_session: Session, **overrides: object) -> None:
    now = "2026-08-10T00:00:00.000000+00:00"
    values: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000010",
        "title": "直接登録会議",
        "description": None,
        "status": "scheduled",
        "scheduled_start_at": "2026-08-10T01:00:00.000000+00:00",
        "scheduled_end_at": "2026-08-10T02:00:00.000000+00:00",
        "actual_start_at": None,
        "actual_end_at": None,
        "organizer_user_id": "",
        "created_by_user_id": "",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    db_session.execute(
        text(
            """
            INSERT INTO meetings (
                id, title, description, status,
                scheduled_start_at, scheduled_end_at,
                actual_start_at, actual_end_at,
                organizer_user_id, created_by_user_id,
                created_at, updated_at
            ) VALUES (
                :id, :title, :description, :status,
                :scheduled_start_at, :scheduled_end_at,
                :actual_start_at, :actual_end_at,
                :organizer_user_id, :created_by_user_id,
                :created_at, :updated_at
            )
            """
        ),
        values,
    )


def insert_participant_directly(db_session: Session, **overrides: object) -> None:
    now = "2026-08-10T00:00:00.000000+00:00"
    values: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000020",
        "meeting_id": "",
        "user_id": "",
        "participant_role": "participant",
        "attendance_status": "invited",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    db_session.execute(
        text(
            """
            INSERT INTO meeting_participants (
                id, meeting_id, user_id, participant_role,
                attendance_status, created_at, updated_at
            ) VALUES (
                :id, :meeting_id, :user_id, :participant_role,
                :attendance_status, :created_at, :updated_at
            )
            """
        ),
        values,
    )


def test_meeting_can_be_registered_with_uuid_trimmed_title_and_relationships(
    db_session: Session,
) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator, title="  定例会議  ")
    participation = make_participant(meeting, participant_user)
    db_session.add(meeting)
    db_session.commit()

    parsed_id = UUID(meeting.id)
    assert len(meeting.id) == 36
    assert parsed_id.version == 4
    assert meeting.title == "定例会議"
    assert meeting.organizer == organizer
    assert meeting.created_by == creator
    assert meeting.participants == [participation]
    assert participation.meeting == meeting
    assert participation.user == participant_user
    assert organizer.organizing_meetings == [meeting]
    assert creator.created_meetings == [meeting]
    assert participant_user.meeting_participations == [participation]


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, 123])
def test_invalid_title_is_rejected_by_orm(title: object) -> None:
    organizer = make_user("organizer@example.test")
    creator = make_user("creator@example.test")
    with pytest.raises(ValueError):
        make_meeting(organizer, creator, title=title)


@pytest.mark.parametrize("title", ["   ", "x" * 201])
def test_invalid_title_is_rejected_by_database(db_session: Session, title: str) -> None:
    organizer, creator, _ = persist_users(db_session)
    with pytest.raises(IntegrityError):
        insert_meeting_directly(
            db_session,
            title=title,
            organizer_user_id=organizer.id,
            created_by_user_id=creator.id,
        )
    db_session.rollback()


@pytest.mark.parametrize("status", ["scheduled", "in_progress", "completed", "cancelled"])
def test_all_meeting_statuses_can_be_registered(db_session: Session, status: str) -> None:
    organizer, creator, _ = persist_users(db_session)
    db_session.add(make_meeting(organizer, creator, status=status))
    db_session.commit()


def test_undefined_meeting_status_is_rejected_by_orm() -> None:
    with pytest.raises(ValueError):
        make_meeting(
            make_user("organizer@example.test"),
            make_user("creator@example.test"),
            status="draft",
        )


def test_undefined_meeting_status_is_rejected_by_database(db_session: Session) -> None:
    organizer, creator, _ = persist_users(db_session)
    with pytest.raises(IntegrityError):
        insert_meeting_directly(
            db_session,
            status="draft",
            organizer_user_id=organizer.id,
            created_by_user_id=creator.id,
        )
    db_session.rollback()


@pytest.mark.parametrize(
    "scheduled_end_at",
    [
        datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
        datetime(2026, 8, 10, 0, 59, tzinfo=UTC),
    ],
)
def test_invalid_scheduled_time_order_is_rejected(
    db_session: Session,
    scheduled_end_at: datetime,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    db_session.add(make_meeting(organizer, creator, scheduled_end_at=scheduled_end_at))
    assert_commit_fails(db_session)


def test_actual_end_without_start_is_rejected(db_session: Session) -> None:
    organizer, creator, _ = persist_users(db_session)
    db_session.add(
        make_meeting(
            organizer,
            creator,
            actual_end_at=datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        )
    )
    assert_commit_fails(db_session)


def test_actual_start_without_end_is_allowed(db_session: Session) -> None:
    organizer, creator, _ = persist_users(db_session)
    meeting = make_meeting(
        organizer,
        creator,
        actual_start_at=datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
    )
    db_session.add(meeting)
    db_session.commit()
    assert meeting.actual_end_at is None


@pytest.mark.parametrize(
    "scheduled_end_at",
    [
        "2026-08-06T09:00:00.000000+00:00",
        "2026-08-06T08:59:59.999999+00:00",
    ],
)
def test_invalid_scheduled_time_order_is_rejected_by_direct_sql(
    db_session: Session,
    scheduled_end_at: str,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    with pytest.raises(IntegrityError):
        insert_meeting_directly(
            db_session,
            scheduled_start_at="2026-08-06T09:00:00.000000+00:00",
            scheduled_end_at=scheduled_end_at,
            organizer_user_id=organizer.id,
            created_by_user_id=creator.id,
        )
    db_session.rollback()


@pytest.mark.parametrize(
    ("actual_start_at", "actual_end_at"),
    [
        (None, "2026-08-06T10:00:00.000000+00:00"),
        (
            "2026-08-06T10:00:00.000000+00:00",
            "2026-08-06T09:59:59.999999+00:00",
        ),
    ],
)
def test_invalid_actual_times_are_rejected_by_direct_sql(
    db_session: Session,
    actual_start_at: str | None,
    actual_end_at: str,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    with pytest.raises(IntegrityError):
        insert_meeting_directly(
            db_session,
            actual_start_at=actual_start_at,
            actual_end_at=actual_end_at,
            organizer_user_id=organizer.id,
            created_by_user_id=creator.id,
        )
    db_session.rollback()


@pytest.mark.parametrize(
    ("actual_start_at", "actual_end_at"),
    [
        ("2026-08-06T09:00:00.000000+00:00", None),
        (
            "2026-08-06T09:00:00.000000+00:00",
            "2026-08-06T09:00:00.000000+00:00",
        ),
    ],
)
def test_valid_actual_times_are_allowed_by_direct_sql(
    db_session: Session,
    actual_start_at: str,
    actual_end_at: str | None,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    insert_meeting_directly(
        db_session,
        actual_start_at=actual_start_at,
        actual_end_at=actual_end_at,
        organizer_user_id=organizer.id,
        created_by_user_id=creator.id,
    )
    db_session.commit()


@pytest.mark.parametrize("is_valid", [False, True])
def test_actual_time_order_constraints(db_session: Session, is_valid: bool) -> None:
    organizer, creator, _ = persist_users(db_session)
    actual_start = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
    actual_end = actual_start if is_valid else actual_start - timedelta(minutes=1)
    meeting = make_meeting(
        organizer,
        creator,
        actual_start_at=actual_start,
        actual_end_at=actual_end,
    )
    db_session.add(meeting)
    if is_valid:
        db_session.commit()
        assert meeting.actual_end_at == meeting.actual_start_at
    else:
        assert_commit_fails(db_session)


@pytest.mark.parametrize("foreign_key", ["organizer_user_id", "created_by_user_id"])
def test_nonexistent_meeting_user_is_rejected(
    db_session: Session,
    foreign_key: str,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    meeting = Meeting(
        title="外部キー検証会議",
        status="scheduled",
        scheduled_start_at=datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
        scheduled_end_at=datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        organizer_user_id=organizer.id,
        created_by_user_id=creator.id,
    )
    setattr(meeting, foreign_key, "00000000-0000-4000-8000-000000000099")
    db_session.add(meeting)
    assert_commit_fails(db_session)


@pytest.mark.parametrize("relation", ["organizer", "creator"])
def test_user_delete_is_restricted_when_meeting_exists(
    db_session: Session,
    relation: str,
) -> None:
    organizer, creator, _ = persist_users(db_session)
    db_session.add(make_meeting(organizer, creator))
    db_session.commit()
    target = organizer if relation == "organizer" else creator
    db_session.delete(target)
    assert_commit_fails(db_session)


def test_meeting_utc_datetime_storage_and_naive_rejection(db_session: Session) -> None:
    organizer, creator, _ = persist_users(db_session)
    source_timezone = timezone(timedelta(hours=9))
    meeting = make_meeting(
        organizer,
        creator,
        scheduled_start_at=datetime(2026, 8, 10, 10, 0, 0, 123456, tzinfo=source_timezone),
        scheduled_end_at=datetime(2026, 8, 10, 11, 0, 0, 123456, tzinfo=source_timezone),
    )
    db_session.add(meeting)
    db_session.commit()

    stored = db_session.execute(
        text("SELECT scheduled_start_at FROM meetings WHERE id = :id"),
        {"id": meeting.id},
    ).scalar_one()
    assert stored == "2026-08-10T01:00:00.123456+00:00"
    assert meeting.scheduled_start_at == datetime(2026, 8, 10, 1, 0, 0, 123456, tzinfo=UTC)

    meeting.scheduled_start_at = datetime(2026, 8, 11, 1, 0)  # noqa: DTZ001
    with pytest.raises(StatementError):
        db_session.commit()
    db_session.rollback()


def test_meeting_updated_at_changes_on_orm_update(db_session: Session) -> None:
    organizer, creator, _ = persist_users(db_session)
    old_value = datetime(2020, 1, 1, tzinfo=UTC)
    meeting = make_meeting(organizer, creator, updated_at=old_value)
    db_session.add(meeting)
    db_session.commit()
    meeting.title = "更新後の会議"
    db_session.commit()
    assert meeting.updated_at > old_value
    assert meeting.updated_at.tzinfo is UTC


def test_participant_gets_uuid_and_all_enum_values_can_be_registered(
    db_session: Session,
) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator)
    participant = make_participant(meeting, participant_user)
    db_session.add(participant)
    db_session.commit()
    assert len(participant.id) == 36
    assert UUID(participant.id).version == 4

    roles = ["organizer", "facilitator", "participant", "observer"]
    statuses = ["invited", "accepted", "declined", "attended", "absent"]
    for index, role in enumerate(roles):
        participant.participant_role = role
        participant.attendance_status = statuses[index]
        db_session.flush()
    participant.attendance_status = statuses[-1]
    db_session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [("participant_role", "speaker"), ("attendance_status", "unknown")],
)
def test_undefined_participant_enum_is_rejected_by_orm(field: str, value: str) -> None:
    participant = MeetingParticipant()
    with pytest.raises(ValueError):
        setattr(participant, field, value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("participant_role", "speaker"), ("attendance_status", "unknown")],
)
def test_undefined_participant_enum_is_rejected_by_database(
    db_session: Session,
    field: str,
    value: str,
) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator)
    db_session.add(meeting)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_participant_directly(
            db_session,
            meeting_id=meeting.id,
            user_id=participant_user.id,
            **{field: value},
        )
    db_session.rollback()


def test_duplicate_meeting_participant_is_rejected(db_session: Session) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator)
    db_session.add_all(
        [
            make_participant(meeting, participant_user),
            make_participant(meeting, participant_user, participant_role="observer"),
        ]
    )
    assert_commit_fails(db_session)


@pytest.mark.parametrize("foreign_key", ["meeting_id", "user_id"])
def test_nonexistent_participant_foreign_key_is_rejected(
    db_session: Session,
    foreign_key: str,
) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator)
    db_session.add(meeting)
    db_session.flush()
    values = {"meeting_id": meeting.id, "user_id": participant_user.id}
    values[foreign_key] = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(IntegrityError):
        insert_participant_directly(db_session, **values)
    db_session.rollback()


def test_meeting_delete_uses_database_cascade_without_participant_mutation(
    db_session: Session,
    test_engine: Engine,
) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    meeting = make_meeting(organizer, creator)
    participant = make_participant(meeting, participant_user)
    db_session.add(participant)
    db_session.commit()
    meeting_id = meeting.id
    assert meeting.participants == [participant]

    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", record_statement)
    try:
        db_session.delete(meeting)
        db_session.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", record_statement)

    assert db_session.scalar(
        select(func.count()).select_from(MeetingParticipant).where(
            MeetingParticipant.meeting_id == meeting_id
        )
    ) == 0
    participant_mutations = [
        statement
        for statement in statements
        if statement.startswith(("update", "delete"))
        and "meeting_participants" in statement
    ]
    assert participant_mutations == []


def test_user_delete_is_restricted_when_participation_exists(db_session: Session) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    db_session.add(make_participant(make_meeting(organizer, creator), participant_user))
    db_session.commit()
    db_session.delete(participant_user)
    assert_commit_fails(db_session)


def test_participant_updated_at_changes_on_orm_update(db_session: Session) -> None:
    organizer, creator, participant_user = persist_users(db_session)
    old_value = datetime(2020, 1, 1, tzinfo=UTC)
    participant = make_participant(
        make_meeting(organizer, creator),
        participant_user,
        updated_at=old_value,
    )
    db_session.add(participant)
    db_session.commit()
    participant.attendance_status = "accepted"
    db_session.commit()
    assert participant.updated_at > old_value
    assert participant.updated_at.tzinfo is UTC
