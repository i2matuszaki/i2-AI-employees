"""会議テーブルと会議参加者テーブルを作成する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_start_at", sa.String(length=32), nullable=False),
        sa.Column("scheduled_end_at", sa.String(length=32), nullable=False),
        sa.Column("actual_start_at", sa.String(length=32), nullable=True),
        sa.Column("actual_end_at", sa.String(length=32), nullable=True),
        sa.Column("organizer_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("length(id) = 36", name="ck_meetings_id_length"),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 200",
            name="ck_meetings_title_length",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
            name="ck_meetings_status",
        ),
        sa.CheckConstraint(
            "scheduled_end_at > scheduled_start_at",
            name="ck_meetings_scheduled_time_order",
        ),
        sa.CheckConstraint(
            "actual_end_at IS NULL OR actual_start_at IS NOT NULL",
            name="ck_meetings_actual_end_requires_start",
        ),
        sa.CheckConstraint(
            "actual_start_at IS NULL OR actual_end_at IS NULL "
            "OR actual_end_at >= actual_start_at",
            name="ck_meetings_actual_time_order",
        ),
        sa.ForeignKeyConstraint(
            ["organizer_user_id"],
            ["users.id"],
            name="fk_meetings_organizer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_meetings_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_status", "meetings", ["status"], unique=False)
    op.create_index(
        "ix_meetings_scheduled_start_at",
        "meetings",
        ["scheduled_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_meetings_organizer_user_id",
        "meetings",
        ["organizer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_meetings_created_by_user_id",
        "meetings",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_meetings_status_scheduled_start_at",
        "meetings",
        ["status", "scheduled_start_at"],
        unique=False,
    )

    op.create_table(
        "meeting_participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("participant_role", sa.String(length=20), nullable=False),
        sa.Column("attendance_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "length(id) = 36",
            name="ck_meeting_participants_id_length",
        ),
        sa.CheckConstraint(
            "participant_role IN ('organizer', 'facilitator', 'participant', 'observer')",
            name="ck_meeting_participants_participant_role",
        ),
        sa.CheckConstraint(
            "attendance_status IN ('invited', 'accepted', 'declined', 'attended', 'absent')",
            name="ck_meeting_participants_attendance_status",
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name="fk_meeting_participants_meeting_id_meetings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_meeting_participants_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meeting_id",
            "user_id",
            name="uq_meeting_participants_meeting_id_user_id",
        ),
    )
    op.create_index(
        "ix_meeting_participants_meeting_id",
        "meeting_participants",
        ["meeting_id"],
        unique=False,
    )
    op.create_index(
        "ix_meeting_participants_user_id",
        "meeting_participants",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_meeting_participants_attendance_status",
        "meeting_participants",
        ["attendance_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meeting_participants_attendance_status",
        table_name="meeting_participants",
    )
    op.drop_index(
        "ix_meeting_participants_user_id",
        table_name="meeting_participants",
    )
    op.drop_index(
        "ix_meeting_participants_meeting_id",
        table_name="meeting_participants",
    )
    op.drop_table("meeting_participants")

    op.drop_index("ix_meetings_status_scheduled_start_at", table_name="meetings")
    op.drop_index("ix_meetings_created_by_user_id", table_name="meetings")
    op.drop_index("ix_meetings_organizer_user_id", table_name="meetings")
    op.drop_index("ix_meetings_scheduled_start_at", table_name="meetings")
    op.drop_index("ix_meetings_status", table_name="meetings")
    op.drop_table("meetings")
