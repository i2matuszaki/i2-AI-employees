from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Meeting, TranscriptRun, TranscriptSegment, User

NOW_TEXT = "2026-08-10T00:00:00.000000+00:00"


def make_user(email: str) -> User:
    return User(
        email=email,
        display_name="テスト利用者",
        role="user",
        password_hash="stored-password-hash",
    )


def make_meeting(organizer: User, creator: User) -> Meeting:
    return Meeting(
        title="文字起こしテスト会議",
        status="scheduled",
        scheduled_start_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
        scheduled_end_at=datetime(2026, 8, 10, 2, tzinfo=UTC),
        organizer=organizer,
        created_by=creator,
    )


def make_run(meeting: Meeting, creator: User, **overrides: object) -> TranscriptRun:
    values: dict[str, object] = {
        "meeting": meeting,
        "created_by": creator,
        "status": "pending",
        "source_type": "manual",
    }
    values.update(overrides)
    return TranscriptRun(**values)


def make_segment(run: TranscriptRun, **overrides: object) -> TranscriptSegment:
    values: dict[str, object] = {
        "transcript_run": run,
        "sequence_number": 1,
        "text": "発言本文",
    }
    values.update(overrides)
    return TranscriptSegment(**values)


def persist_context(db_session: Session) -> tuple[User, User, User, User, Meeting]:
    organizer = make_user("organizer-transcript@example.test")
    creator = make_user("creator-transcript@example.test")
    speaker = make_user("speaker-transcript@example.test")
    editor = make_user("editor-transcript@example.test")
    meeting = make_meeting(organizer, creator)
    db_session.add_all([organizer, creator, speaker, editor, meeting])
    db_session.flush()
    return organizer, creator, speaker, editor, meeting


def assert_commit_fails(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def insert_run_directly(db_session: Session, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000041",
        "meeting_id": "",
        "status": "pending",
        "source_type": "manual",
        "provider": None,
        "model_name": None,
        "language": None,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "raw_response": None,
        "created_by_user_id": "",
        "created_at": NOW_TEXT,
        "updated_at": NOW_TEXT,
    }
    values.update(overrides)
    db_session.execute(
        text(
            """
            INSERT INTO transcript_runs (
                id, meeting_id, status, source_type, provider, model_name, language,
                started_at, completed_at, error_message, raw_response,
                created_by_user_id, created_at, updated_at
            ) VALUES (
                :id, :meeting_id, :status, :source_type, :provider, :model_name, :language,
                :started_at, :completed_at, :error_message, :raw_response,
                :created_by_user_id, :created_at, :updated_at
            )
            """
        ),
        values,
    )


def insert_segment_directly(db_session: Session, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000000042",
        "transcript_run_id": "",
        "sequence_number": 1,
        "speaker_label": None,
        "speaker_user_id": None,
        "text": "発言本文",
        "start_offset_ms": None,
        "end_offset_ms": None,
        "confidence": None,
        "is_edited": 0,
        "edited_by_user_id": None,
        "edited_at": None,
        "created_at": NOW_TEXT,
        "updated_at": NOW_TEXT,
    }
    values.update(overrides)
    db_session.execute(
        text(
            """
            INSERT INTO transcript_segments (
                id, transcript_run_id, sequence_number, speaker_label, speaker_user_id,
                text, start_offset_ms, end_offset_ms, confidence, is_edited,
                edited_by_user_id, edited_at, created_at, updated_at
            ) VALUES (
                :id, :transcript_run_id, :sequence_number, :speaker_label, :speaker_user_id,
                :text, :start_offset_ms, :end_offset_ms, :confidence, :is_edited,
                :edited_by_user_id, :edited_at, :created_at, :updated_at
            )
            """
        ),
        values,
    )


def test_run_registration_uuid_normalization_and_relationships(db_session: Session) -> None:
    _, creator, speaker, _, meeting = persist_context(db_session)
    run = make_run(
        meeting,
        creator,
        provider="  provider  ",
        model_name="  model  ",
        language="  ja  ",
    )
    segment = make_segment(run, speaker_user=speaker)
    db_session.add(run)
    db_session.commit()

    assert len(run.id) == 36
    assert UUID(run.id).version == 4
    assert (run.provider, run.model_name, run.language) == ("provider", "model", "ja")
    assert run.meeting == meeting
    assert run.created_by == creator
    assert run.segments == [segment]
    assert segment.is_edited is False
    assert meeting.transcript_runs == [run]
    assert creator.created_transcript_runs == [run]


@pytest.mark.parametrize("status", ["pending", "processing", "completed", "failed", "cancelled"])
def test_all_run_statuses_can_be_registered(db_session: Session, status: str) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    started = datetime(2026, 8, 10, 1, tzinfo=UTC)
    values: dict[str, object] = {"status": status}
    if status == "completed":
        values.update(started_at=started, completed_at=started)
    if status == "failed":
        values["error_message"] = "失敗"
    db_session.add(make_run(meeting, creator, **values))
    db_session.commit()


@pytest.mark.parametrize("source_type", ["manual", "file", "realtime", "external"])
def test_all_source_types_can_be_registered(db_session: Session, source_type: str) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    db_session.add(make_run(meeting, creator, source_type=source_type))
    db_session.commit()


@pytest.mark.parametrize(("field", "value"), [("status", "unknown"), ("source_type", "unknown")])
def test_undefined_run_enum_is_rejected_by_orm(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        setattr(TranscriptRun(), field, value)


@pytest.mark.parametrize(("field", "value"), [("status", "unknown"), ("source_type", "unknown")])
def test_undefined_run_enum_is_rejected_by_database(
    db_session: Session, field: str, value: str
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    with pytest.raises(IntegrityError):
        insert_run_directly(
            db_session, meeting_id=meeting.id, created_by_user_id=creator.id, **{field: value}
        )
    db_session.rollback()


@pytest.mark.parametrize("field", ["provider", "model_name", "language"])
def test_optional_run_labels_normalize_blank_to_none(field: str) -> None:
    run = TranscriptRun()
    setattr(run, field, "   ")
    assert getattr(run, field) is None


@pytest.mark.parametrize(("field", "length"), [("provider", 51), ("model_name", 101), ("language", 21)])
def test_optional_run_label_maximum_is_rejected_by_orm(field: str, length: int) -> None:
    with pytest.raises(ValueError):
        setattr(TranscriptRun(), field, "x" * length)


@pytest.mark.parametrize(("field", "length"), [("provider", 51), ("model_name", 101), ("language", 21)])
def test_optional_run_label_maximum_is_rejected_by_database(
    db_session: Session, field: str, length: int
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    with pytest.raises(IntegrityError):
        insert_run_directly(
            db_session,
            meeting_id=meeting.id,
            created_by_user_id=creator.id,
            **{field: "x" * length},
        )
    db_session.rollback()


@pytest.mark.parametrize(
    "overrides",
    [
        {"completed_at": datetime(2026, 8, 10, 2, tzinfo=UTC)},
        {
            "started_at": datetime(2026, 8, 10, 2, tzinfo=UTC),
            "completed_at": datetime(2026, 8, 10, 1, tzinfo=UTC),
        },
        {"status": "completed"},
        {"status": "failed"},
        {"status": "failed", "error_message": "   "},
    ],
)
def test_invalid_run_cross_field_state_is_rejected_by_orm(
    db_session: Session, overrides: dict[str, object]
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    db_session.add(make_run(meeting, creator, **overrides))
    assert_commit_fails(db_session)


@pytest.mark.parametrize(
    "overrides",
    [
        {"completed_at": "2026-08-10T02:00:00.000000+00:00"},
        {
            "started_at": "2026-08-10T02:00:00.000000+00:00",
            "completed_at": "2026-08-10T01:00:00.000000+00:00",
        },
        {"status": "completed"},
        {"status": "failed", "error_message": None},
        {"status": "failed", "error_message": ""},
        {"status": "failed", "error_message": "   "},
    ],
)
def test_invalid_run_cross_field_state_is_rejected_by_database(
    db_session: Session, overrides: dict[str, object]
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    with pytest.raises(IntegrityError):
        insert_run_directly(
            db_session,
            meeting_id=meeting.id,
            created_by_user_id=creator.id,
            **overrides,
        )
    db_session.rollback()


def test_non_failed_error_and_non_completed_completion_are_allowed(db_session: Session) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    started = datetime(2026, 8, 10, 1, tzinfo=UTC)
    run = make_run(
        meeting,
        creator,
        status="cancelled",
        error_message="  中止理由  ",
        started_at=started,
        completed_at=started,
    )
    db_session.add(run)
    db_session.commit()
    assert run.error_message == "中止理由"


def test_run_utc_datetime_naive_rejection_and_raw_response_round_trip(
    db_session: Session,
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    raw_response = ' {\n  "z": "日本語",\n  "a": 1\n} \n'
    source_timezone = timezone(timedelta(hours=9))
    run = make_run(
        meeting,
        creator,
        started_at=datetime(2026, 8, 10, 10, 0, 0, 123456, tzinfo=source_timezone),
        raw_response=raw_response,
    )
    db_session.add(run)
    db_session.commit()
    stored = db_session.execute(
        text("SELECT started_at, raw_response FROM transcript_runs WHERE id = :id"),
        {"id": run.id},
    ).one()
    assert stored.started_at == "2026-08-10T01:00:00.123456+00:00"
    assert stored.raw_response == raw_response
    assert run.raw_response == raw_response

    run.started_at = datetime(2026, 8, 11, 1)  # noqa: DTZ001
    with pytest.raises(StatementError):
        db_session.commit()
    db_session.rollback()


def test_run_updated_at_changes_and_creator_delete_is_restricted(db_session: Session) -> None:
    _, meeting_creator, _, _, meeting = persist_context(db_session)
    run_creator = make_user("run-creator-transcript@example.test")
    db_session.add(run_creator)
    old_value = datetime(2020, 1, 1, tzinfo=UTC)
    run = make_run(meeting, run_creator, updated_at=old_value)
    db_session.add(run)
    db_session.commit()
    run.provider = "provider"
    db_session.commit()
    assert run.updated_at > old_value
    assert meeting.created_by == meeting_creator
    db_session.delete(run_creator)
    assert_commit_fails(db_session)


def test_segment_registration_normalization_decimal_and_relationships(db_session: Session) -> None:
    _, creator, speaker, editor, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    edited_at = datetime(2026, 8, 10, 2, tzinfo=UTC)
    segment = make_segment(
        run,
        text="  発言本文  ",
        speaker_label="  話者  ",
        speaker_user=speaker,
        confidence="0.875",
        is_edited=True,
        edited_by=editor,
        edited_at=edited_at,
    )
    db_session.add(segment)
    db_session.commit()
    assert len(segment.id) == 36
    assert UUID(segment.id).version == 4
    assert segment.text == "発言本文"
    assert segment.speaker_label == "話者"
    assert segment.confidence == Decimal("0.8750")
    assert isinstance(segment.confidence, Decimal)
    assert segment.transcript_run == run
    assert segment.speaker_user == speaker
    assert segment.edited_by == editor
    assert speaker.spoken_transcript_segments == [segment]
    assert editor.edited_transcript_segments == [segment]


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_segment_text_is_rejected_by_orm(value: str) -> None:
    with pytest.raises(ValueError):
        TranscriptSegment(text=value)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_segment_text_is_rejected_by_database(db_session: Session, value: str) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_segment_directly(db_session, transcript_run_id=run.id, text=value)
    db_session.rollback()


def test_speaker_label_boundaries_and_blank_normalization() -> None:
    segment = TranscriptSegment(speaker_label="   ")
    assert segment.speaker_label is None
    segment.speaker_label = "x" * 100
    assert len(segment.speaker_label) == 100
    with pytest.raises(ValueError):
        segment.speaker_label = "x" * 101


@pytest.mark.parametrize("value", ["", "   ", "x" * 101])
def test_invalid_speaker_label_is_rejected_by_database(
    db_session: Session, value: str
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_segment_directly(
            db_session, transcript_run_id=run.id, speaker_label=value
        )
    db_session.rollback()


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_invalid_sequence_number_is_rejected_by_orm(value: object) -> None:
    with pytest.raises(ValueError):
        TranscriptSegment(sequence_number=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_sequence_number_is_rejected_by_database(
    db_session: Session, value: int
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_segment_directly(
            db_session, transcript_run_id=run.id, sequence_number=value
        )
    db_session.rollback()


def test_sequence_number_is_unique_per_run(db_session: Session) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    first_run = make_run(meeting, creator)
    second_run = make_run(meeting, creator)
    db_session.add_all(
        [make_segment(first_run), make_segment(first_run), make_segment(second_run)]
    )
    assert_commit_fails(db_session)


def test_same_sequence_number_is_allowed_in_different_runs(db_session: Session) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    db_session.add_all(
        [make_segment(make_run(meeting, creator)), make_segment(make_run(meeting, creator))]
    )
    db_session.commit()


@pytest.mark.parametrize("field", ["start_offset_ms", "end_offset_ms"])
@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
def test_invalid_offset_is_rejected_by_orm(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        setattr(TranscriptSegment(), field, value)


@pytest.mark.parametrize("field", ["start_offset_ms", "end_offset_ms"])
def test_negative_offset_is_rejected_by_database(db_session: Session, field: str) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_segment_directly(
            db_session, transcript_run_id=run.id, **{field: -1}
        )
    db_session.rollback()


@pytest.mark.parametrize("direct", [False, True])
def test_invalid_offset_order_is_rejected(
    db_session: Session, direct: bool
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    if direct:
        with pytest.raises(IntegrityError):
            insert_segment_directly(
                db_session,
                transcript_run_id=run.id,
                start_offset_ms=2,
                end_offset_ms=1,
            )
        db_session.rollback()
    else:
        db_session.add(make_segment(run, start_offset_ms=2, end_offset_ms=1))
        assert_commit_fails(db_session)


@pytest.mark.parametrize("value", [Decimal(0), Decimal(1)])
def test_confidence_boundaries_are_allowed(db_session: Session, value: Decimal) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    segment = make_segment(make_run(meeting, creator), confidence=value)
    db_session.add(segment)
    db_session.commit()
    assert isinstance(segment.confidence, Decimal)


@pytest.mark.parametrize("value", [Decimal("-0.1"), Decimal("1.1"), True, "invalid"])
def test_invalid_confidence_is_rejected_by_orm(value: object) -> None:
    with pytest.raises(ValueError):
        TranscriptSegment(confidence=value)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_invalid_confidence_is_rejected_by_database(
    db_session: Session, value: float
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    with pytest.raises(IntegrityError):
        insert_segment_directly(
            db_session, transcript_run_id=run.id, confidence=value
        )
    db_session.rollback()


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_edited": False, "edited_by_user_id": "user", "edited_at": NOW_TEXT},
        {"is_edited": True, "edited_by_user_id": None, "edited_at": NOW_TEXT},
        {"is_edited": True, "edited_by_user_id": "user", "edited_at": None},
    ],
)
def test_invalid_edit_state_is_rejected_by_database(
    db_session: Session, overrides: dict[str, object]
) -> None:
    _, creator, _, editor, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(run)
    db_session.flush()
    if overrides.get("edited_by_user_id") == "user":
        overrides["edited_by_user_id"] = editor.id
    with pytest.raises(IntegrityError):
        insert_segment_directly(
            db_session, transcript_run_id=run.id, **overrides
        )
    db_session.rollback()


def test_invalid_edit_state_is_rejected_through_orm_and_valid_state_is_allowed(
    db_session: Session,
) -> None:
    _, creator, _, editor, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    db_session.add(make_segment(run, is_edited=True, edited_at=datetime.now(UTC)))
    assert_commit_fails(db_session)

    _, creator, _, editor, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    segment = make_segment(
        run,
        is_edited=True,
        edited_by=editor,
        edited_at=datetime(2026, 8, 10, 2, tzinfo=UTC),
    )
    db_session.add(segment)
    db_session.commit()


def test_non_bool_is_edited_is_rejected_by_orm() -> None:
    with pytest.raises(ValueError):
        TranscriptSegment(is_edited=1)  # type: ignore[arg-type]


def test_segment_updated_at_and_editor_delete_restriction(db_session: Session) -> None:
    _, creator, _, editor, meeting = persist_context(db_session)
    old_value = datetime(2020, 1, 1, tzinfo=UTC)
    segment = make_segment(
        make_run(meeting, creator),
        is_edited=True,
        edited_by=editor,
        edited_at=datetime(2026, 8, 10, 2, tzinfo=UTC),
        updated_at=old_value,
    )
    db_session.add(segment)
    db_session.commit()
    segment.text = "更新後"
    db_session.commit()
    assert segment.updated_at > old_value
    db_session.delete(editor)
    assert_commit_fails(db_session)


def collect_mutations(engine: Engine) -> tuple[list[str], object]:
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lower().strip())

    event.listen(engine, "before_cursor_execute", record)
    return statements, record


def transcript_mutations(statements: list[str], table_name: str) -> list[str]:
    return [
        statement
        for statement in statements
        if statement.startswith(("update", "delete")) and table_name in statement
    ]


def test_meeting_delete_uses_two_level_database_cascade(
    db_session: Session, test_engine: Engine
) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    segment = make_segment(run)
    db_session.add(segment)
    db_session.commit()
    assert meeting.transcript_runs == [run]
    assert run.segments == [segment]
    statements, listener = collect_mutations(test_engine)
    try:
        db_session.delete(meeting)
        db_session.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", listener)
    assert db_session.scalar(select(func.count()).select_from(TranscriptRun)) == 0
    assert db_session.scalar(select(func.count()).select_from(TranscriptSegment)) == 0
    assert transcript_mutations(statements, "transcript_runs") == []
    assert transcript_mutations(statements, "transcript_segments") == []


def test_run_delete_uses_database_cascade(db_session: Session, test_engine: Engine) -> None:
    _, creator, _, _, meeting = persist_context(db_session)
    run = make_run(meeting, creator)
    segment = make_segment(run)
    db_session.add(segment)
    db_session.commit()
    assert run.segments == [segment]
    statements, listener = collect_mutations(test_engine)
    try:
        db_session.delete(run)
        db_session.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", listener)
    assert db_session.scalar(select(func.count()).select_from(TranscriptSegment)) == 0
    assert transcript_mutations(statements, "transcript_segments") == []


def test_speaker_delete_uses_database_set_null_without_segment_mutation(
    db_session: Session, test_engine: Engine
) -> None:
    _, creator, speaker, _, meeting = persist_context(db_session)
    segment = make_segment(make_run(meeting, creator), speaker_user=speaker, text="保持する本文")
    db_session.add(segment)
    db_session.commit()
    segment_id = segment.id
    assert speaker.spoken_transcript_segments == [segment]
    statements, listener = collect_mutations(test_engine)
    try:
        db_session.delete(speaker)
        db_session.commit()
    finally:
        event.remove(test_engine, "before_cursor_execute", listener)
    db_session.close()

    check_session = sessionmaker(bind=test_engine)()
    try:
        stored = check_session.get(TranscriptSegment, segment_id)
        assert stored is not None
        assert stored.speaker_user_id is None
        assert stored.text == "保持する本文"
    finally:
        check_session.close()
    assert transcript_mutations(statements, "transcript_segments") == []
