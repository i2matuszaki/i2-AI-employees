import os
import subprocess
from pathlib import Path

from sqlalchemy import Boolean, Numeric, String, create_engine, inspect, text

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
ALEMBIC_EXECUTABLE = BACKEND_DIRECTORY / ".venv" / "bin" / "alembic"
EXISTING_MIGRATIONS = [
    BACKEND_DIRECTORY / "migrations" / "versions" / "0001_initialize_database.py",
    BACKEND_DIRECTORY / "migrations" / "versions" / "0002_create_users_and_sessions.py",
    BACKEND_DIRECTORY / "migrations" / "versions" / "0003_create_meetings_and_participants.py",
]


def run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [str(ALEMBIC_EXECUTABLE), *arguments],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_transcript_migration_upgrade_downgrade_and_schema(tmp_path: Path) -> None:
    original_migrations = {path: path.read_bytes() for path in EXISTING_MIGRATIONS}
    database_path = tmp_path / "alembic" / "transcripts.db"
    database_path.parent.mkdir(parents=True)
    database_url = f"sqlite:///{database_path}"

    run_alembic(database_url, "upgrade", "head")
    current = run_alembic(database_url, "current")
    assert "0004 (head)" in current.stdout

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {"transcript_runs", "transcript_segments"}.issubset(
            inspector.get_table_names()
        )

        run_columns = {
            column["name"]: column for column in inspector.get_columns("transcript_runs")
        }
        assert set(run_columns) == {
            "id",
            "meeting_id",
            "status",
            "source_type",
            "provider",
            "model_name",
            "language",
            "started_at",
            "completed_at",
            "error_message",
            "raw_response",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        run_string_lengths = {
            "id": 36,
            "meeting_id": 36,
            "status": 20,
            "source_type": 20,
            "provider": 50,
            "model_name": 100,
            "language": 20,
            "started_at": 32,
            "completed_at": 32,
            "created_by_user_id": 36,
            "created_at": 32,
            "updated_at": 32,
        }
        for name, length in run_string_lengths.items():
            assert isinstance(run_columns[name]["type"], String)
            assert run_columns[name]["type"].length == length
        assert {name for name, column in run_columns.items() if column["nullable"]} == {
            "provider",
            "model_name",
            "language",
            "started_at",
            "completed_at",
            "error_message",
            "raw_response",
        }
        assert inspector.get_pk_constraint("transcript_runs")["constrained_columns"] == [
            "id"
        ]
        assert {check["name"] for check in inspector.get_check_constraints("transcript_runs")} == {
            "ck_transcript_runs_id_length",
            "ck_transcript_runs_status",
            "ck_transcript_runs_source_type",
            "ck_transcript_runs_provider_length",
            "ck_transcript_runs_provider_trimmed",
            "ck_transcript_runs_model_name_length",
            "ck_transcript_runs_model_name_trimmed",
            "ck_transcript_runs_language_length",
            "ck_transcript_runs_language_trimmed",
            "ck_transcript_runs_completed_at_requires_started_at",
            "ck_transcript_runs_completed_at_order",
            "ck_transcript_runs_completed_status_has_completed_at",
            "ck_transcript_runs_failed_status_has_error_message",
        }
        run_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys("transcript_runs")
        }
        assert run_foreign_keys[("meeting_id",)]["referred_table"] == "meetings"
        assert run_foreign_keys[("meeting_id",)]["referred_columns"] == ["id"]
        assert run_foreign_keys[("meeting_id",)]["options"]["ondelete"] == "CASCADE"
        assert run_foreign_keys[("created_by_user_id",)]["referred_table"] == "users"
        assert run_foreign_keys[("created_by_user_id",)]["referred_columns"] == ["id"]
        assert run_foreign_keys[("created_by_user_id",)]["options"]["ondelete"] == "RESTRICT"
        run_indexes = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes("transcript_runs")
        }
        assert run_indexes == {
            "ix_transcript_runs_created_at": ["created_at"],
            "ix_transcript_runs_created_by_user_id": ["created_by_user_id"],
            "ix_transcript_runs_meeting_id": ["meeting_id"],
            "ix_transcript_runs_meeting_id_created_at": ["meeting_id", "created_at"],
            "ix_transcript_runs_status": ["status"],
        }

        segment_columns = {
            column["name"]: column
            for column in inspector.get_columns("transcript_segments")
        }
        assert set(segment_columns) == {
            "id",
            "transcript_run_id",
            "sequence_number",
            "speaker_label",
            "speaker_user_id",
            "text",
            "start_offset_ms",
            "end_offset_ms",
            "confidence",
            "is_edited",
            "edited_by_user_id",
            "edited_at",
            "created_at",
            "updated_at",
        }
        for name, length in {
            "id": 36,
            "transcript_run_id": 36,
            "speaker_label": 100,
            "speaker_user_id": 36,
            "edited_by_user_id": 36,
            "edited_at": 32,
            "created_at": 32,
            "updated_at": 32,
        }.items():
            assert isinstance(segment_columns[name]["type"], String)
            assert segment_columns[name]["type"].length == length
        confidence_type = segment_columns["confidence"]["type"]
        assert isinstance(confidence_type, Numeric)
        assert confidence_type.precision == 5
        assert confidence_type.scale == 4
        assert isinstance(segment_columns["is_edited"]["type"], Boolean)
        assert segment_columns["is_edited"]["nullable"] is False
        assert str(segment_columns["is_edited"]["default"]) in {"0", "false", "(0)"}
        assert inspector.get_pk_constraint("transcript_segments")["constrained_columns"] == [
            "id"
        ]
        assert {
            check["name"] for check in inspector.get_check_constraints("transcript_segments")
        } == {
            "ck_transcript_segments_id_length",
            "ck_transcript_segments_sequence_number",
            "ck_transcript_segments_text_not_blank",
            "ck_transcript_segments_speaker_label",
            "ck_transcript_segments_start_offset_nonnegative",
            "ck_transcript_segments_end_offset_nonnegative",
            "ck_transcript_segments_offset_order",
            "ck_transcript_segments_confidence_range",
            "ck_transcript_segments_is_edited",
            "ck_transcript_segments_unedited_has_no_editor",
            "ck_transcript_segments_edited_has_editor",
        }
        assert inspector.get_unique_constraints("transcript_segments") == [
            {
                "name": "uq_transcript_segments_transcript_run_id_sequence_number",
                "column_names": ["transcript_run_id", "sequence_number"],
            }
        ]
        segment_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys("transcript_segments")
        }
        expected_foreign_keys = {
            ("transcript_run_id",): ("transcript_runs", "CASCADE"),
            ("speaker_user_id",): ("users", "SET NULL"),
            ("edited_by_user_id",): ("users", "RESTRICT"),
        }
        for columns, (table, ondelete) in expected_foreign_keys.items():
            assert segment_foreign_keys[columns]["referred_table"] == table
            assert segment_foreign_keys[columns]["referred_columns"] == ["id"]
            assert segment_foreign_keys[columns]["options"]["ondelete"] == ondelete
        segment_indexes = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes("transcript_segments")
        }
        assert segment_indexes == {
            "ix_transcript_segments_edited_by_user_id": ["edited_by_user_id"],
            "ix_transcript_segments_speaker_user_id": ["speaker_user_id"],
            "ix_transcript_segments_transcript_run_id": ["transcript_run_id"],
            "ix_transcript_segments_transcript_run_id_sequence_number": [
                "transcript_run_id",
                "sequence_number",
            ],
        }
        table_sql = engine.connect().scalar(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'transcript_segments'"
            )
        )
        assert table_sql is not None
        assert "NUMERIC(5, 4)" in table_sql
        assert "DEFAULT 0" in table_sql
    finally:
        engine.dispose()

    run_alembic(database_url, "downgrade", "0003")
    downgraded_engine = create_engine(database_url)
    try:
        tables = set(inspect(downgraded_engine).get_table_names())
        assert {"users", "user_sessions", "meetings", "meeting_participants"}.issubset(
            tables
        )
        assert "transcript_runs" not in tables
        assert "transcript_segments" not in tables
    finally:
        downgraded_engine.dispose()

    run_alembic(database_url, "upgrade", "head")
    assert "0004 (head)" in run_alembic(database_url, "current").stdout
    assert "No new upgrade operations detected" in run_alembic(
        database_url, "check"
    ).stdout
    assert {path: path.read_bytes() for path in EXISTING_MIGRATIONS} == original_migrations
