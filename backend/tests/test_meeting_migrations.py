import os
import subprocess
from pathlib import Path

from sqlalchemy import String, create_engine
from sqlalchemy import inspect as inspect_database

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
ALEMBIC_EXECUTABLE = BACKEND_DIRECTORY / ".venv" / "bin" / "alembic"


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


def test_meeting_migration_upgrade_downgrade_and_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "alembic" / "migration.db"
    database_path.parent.mkdir(parents=True)
    database_url = f"sqlite:///{database_path}"

    run_alembic(database_url, "upgrade", "head")
    current = run_alembic(database_url, "current")
    assert "0003 (head)" in current.stdout

    engine = create_engine(database_url)
    try:
        inspector = inspect_database(engine)
        assert {
            "users",
            "user_sessions",
            "meetings",
            "meeting_participants",
            "alembic_version",
        }.issubset(inspector.get_table_names())

        meeting_columns = {column["name"]: column for column in inspector.get_columns("meetings")}
        assert set(meeting_columns) == {
            "id",
            "title",
            "description",
            "status",
            "scheduled_start_at",
            "scheduled_end_at",
            "actual_start_at",
            "actual_end_at",
            "organizer_user_id",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        meeting_primary_key = inspector.get_pk_constraint("meetings")
        assert meeting_primary_key["constrained_columns"] == ["id"]
        meeting_column_definitions = {
            "id": (36, False),
            "title": (200, False),
            "description": (None, True),
            "status": (20, False),
            "scheduled_start_at": (32, False),
            "scheduled_end_at": (32, False),
            "actual_start_at": (32, True),
            "actual_end_at": (32, True),
            "organizer_user_id": (36, False),
            "created_by_user_id": (36, False),
            "created_at": (32, False),
            "updated_at": (32, False),
        }
        for column_name, (length, nullable) in meeting_column_definitions.items():
            column = meeting_columns[column_name]
            if length is not None:
                assert isinstance(column["type"], String)
                assert column["type"].length == length
            assert column["nullable"] is nullable
        assert meeting_columns["description"]["nullable"] is True
        assert meeting_columns["actual_start_at"]["nullable"] is True
        assert meeting_columns["actual_end_at"]["nullable"] is True

        participant_columns = {
            column["name"]: column
            for column in inspector.get_columns("meeting_participants")
        }
        assert set(participant_columns) == {
            "id",
            "meeting_id",
            "user_id",
            "participant_role",
            "attendance_status",
            "created_at",
            "updated_at",
        }
        participant_primary_key = inspector.get_pk_constraint("meeting_participants")
        assert participant_primary_key["constrained_columns"] == ["id"]
        participant_column_definitions = {
            "id": 36,
            "meeting_id": 36,
            "user_id": 36,
            "participant_role": 20,
            "attendance_status": 20,
            "created_at": 32,
            "updated_at": 32,
        }
        for column_name, length in participant_column_definitions.items():
            column = participant_columns[column_name]
            assert isinstance(column["type"], String)
            assert column["type"].length == length
            assert column["nullable"] is False

        meeting_checks = {check["name"] for check in inspector.get_check_constraints("meetings")}
        assert meeting_checks == {
            "ck_meetings_id_length",
            "ck_meetings_title_length",
            "ck_meetings_status",
            "ck_meetings_scheduled_time_order",
            "ck_meetings_actual_end_requires_start",
            "ck_meetings_actual_time_order",
        }
        participant_checks = {
            check["name"]
            for check in inspector.get_check_constraints("meeting_participants")
        }
        assert participant_checks == {
            "ck_meeting_participants_id_length",
            "ck_meeting_participants_participant_role",
            "ck_meeting_participants_attendance_status",
        }

        meeting_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys("meetings")
        }
        assert meeting_foreign_keys[("organizer_user_id",)]["referred_table"] == "users"
        assert meeting_foreign_keys[("organizer_user_id",)]["referred_columns"] == ["id"]
        assert meeting_foreign_keys[("organizer_user_id",)]["options"]["ondelete"] == "RESTRICT"
        assert meeting_foreign_keys[("created_by_user_id",)]["referred_table"] == "users"
        assert meeting_foreign_keys[("created_by_user_id",)]["referred_columns"] == ["id"]
        assert meeting_foreign_keys[("created_by_user_id",)]["options"]["ondelete"] == "RESTRICT"
        participant_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys("meeting_participants")
        }
        assert participant_foreign_keys[("meeting_id",)]["referred_table"] == "meetings"
        assert participant_foreign_keys[("meeting_id",)]["referred_columns"] == ["id"]
        assert participant_foreign_keys[("meeting_id",)]["options"]["ondelete"] == "CASCADE"
        assert participant_foreign_keys[("user_id",)]["referred_table"] == "users"
        assert participant_foreign_keys[("user_id",)]["referred_columns"] == ["id"]
        assert participant_foreign_keys[("user_id",)]["options"]["ondelete"] == "RESTRICT"

        meeting_indexes = {index["name"] for index in inspector.get_indexes("meetings")}
        assert meeting_indexes == {
            "ix_meetings_status",
            "ix_meetings_scheduled_start_at",
            "ix_meetings_organizer_user_id",
            "ix_meetings_created_by_user_id",
            "ix_meetings_status_scheduled_start_at",
        }
        participant_indexes = {
            index["name"] for index in inspector.get_indexes("meeting_participants")
        }
        assert participant_indexes == {
            "ix_meeting_participants_meeting_id",
            "ix_meeting_participants_user_id",
            "ix_meeting_participants_attendance_status",
        }
        unique_constraints = inspector.get_unique_constraints("meeting_participants")
        assert unique_constraints == [
            {
                "name": "uq_meeting_participants_meeting_id_user_id",
                "column_names": ["meeting_id", "user_id"],
            }
        ]
    finally:
        engine.dispose()

    run_alembic(database_url, "downgrade", "0002")
    downgraded_engine = create_engine(database_url)
    try:
        downgraded_tables = set(inspect_database(downgraded_engine).get_table_names())
        assert {"users", "user_sessions"}.issubset(downgraded_tables)
        assert "meetings" not in downgraded_tables
        assert "meeting_participants" not in downgraded_tables
    finally:
        downgraded_engine.dispose()

    run_alembic(database_url, "upgrade", "head")
    reapplied = run_alembic(database_url, "current")
    assert "0003 (head)" in reapplied.stdout
    check = run_alembic(database_url, "check")
    assert "No new upgrade operations detected" in check.stdout
