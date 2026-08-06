"""文字起こし実行履歴と発言データのテーブルを作成する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.Column("completed_at", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("length(id) = 36", name="ck_transcript_runs_id_length"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_transcript_runs_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'file', 'realtime', 'external')",
            name="ck_transcript_runs_source_type",
        ),
        sa.CheckConstraint(
            "provider IS NULL OR length(provider) BETWEEN 1 AND 50",
            name="ck_transcript_runs_provider_length",
        ),
        sa.CheckConstraint(
            "provider IS NULL OR provider = trim(provider)",
            name="ck_transcript_runs_provider_trimmed",
        ),
        sa.CheckConstraint(
            "model_name IS NULL OR length(model_name) BETWEEN 1 AND 100",
            name="ck_transcript_runs_model_name_length",
        ),
        sa.CheckConstraint(
            "model_name IS NULL OR model_name = trim(model_name)",
            name="ck_transcript_runs_model_name_trimmed",
        ),
        sa.CheckConstraint(
            "language IS NULL OR length(language) BETWEEN 1 AND 20",
            name="ck_transcript_runs_language_length",
        ),
        sa.CheckConstraint(
            "language IS NULL OR language = trim(language)",
            name="ck_transcript_runs_language_trimmed",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name="ck_transcript_runs_completed_at_requires_started_at",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="ck_transcript_runs_completed_at_order",
        ),
        sa.CheckConstraint(
            "status != 'completed' OR completed_at IS NOT NULL",
            name="ck_transcript_runs_completed_status_has_completed_at",
        ),
        sa.CheckConstraint(
            "status != 'failed' OR "
            "(error_message IS NOT NULL AND length(trim(error_message)) >= 1)",
            name="ck_transcript_runs_failed_status_has_error_message",
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name="fk_transcript_runs_meeting_id_meetings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_transcript_runs_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcript_runs_meeting_id", "transcript_runs", ["meeting_id"], unique=False
    )
    op.create_index("ix_transcript_runs_status", "transcript_runs", ["status"], unique=False)
    op.create_index(
        "ix_transcript_runs_created_by_user_id",
        "transcript_runs",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_runs_created_at", "transcript_runs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_transcript_runs_meeting_id_created_at",
        "transcript_runs",
        ["meeting_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(length=100), nullable=True),
        sa.Column("speaker_user_id", sa.String(length=36), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset_ms", sa.Integer(), nullable=True),
        sa.Column("end_offset_ms", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "is_edited", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("edited_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("edited_at", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint("length(id) = 36", name="ck_transcript_segments_id_length"),
        sa.CheckConstraint(
            "sequence_number >= 1", name="ck_transcript_segments_sequence_number"
        ),
        sa.CheckConstraint(
            "length(trim(text)) >= 1", name="ck_transcript_segments_text_not_blank"
        ),
        sa.CheckConstraint(
            "speaker_label IS NULL OR "
            "(length(speaker_label) BETWEEN 1 AND 100 "
            "AND speaker_label = trim(speaker_label))",
            name="ck_transcript_segments_speaker_label",
        ),
        sa.CheckConstraint(
            "start_offset_ms IS NULL OR start_offset_ms >= 0",
            name="ck_transcript_segments_start_offset_nonnegative",
        ),
        sa.CheckConstraint(
            "end_offset_ms IS NULL OR end_offset_ms >= 0",
            name="ck_transcript_segments_end_offset_nonnegative",
        ),
        sa.CheckConstraint(
            "start_offset_ms IS NULL OR end_offset_ms IS NULL "
            "OR end_offset_ms >= start_offset_ms",
            name="ck_transcript_segments_offset_order",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_transcript_segments_confidence_range",
        ),
        sa.CheckConstraint(
            "is_edited IN (0, 1)", name="ck_transcript_segments_is_edited"
        ),
        sa.CheckConstraint(
            "is_edited = 1 OR (edited_by_user_id IS NULL AND edited_at IS NULL)",
            name="ck_transcript_segments_unedited_has_no_editor",
        ),
        sa.CheckConstraint(
            "is_edited = 0 OR (edited_by_user_id IS NOT NULL AND edited_at IS NOT NULL)",
            name="ck_transcript_segments_edited_has_editor",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_run_id"],
            ["transcript_runs.id"],
            name="fk_transcript_segments_transcript_run_id_transcript_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["speaker_user_id"],
            ["users.id"],
            name="fk_transcript_segments_speaker_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["edited_by_user_id"],
            ["users.id"],
            name="fk_transcript_segments_edited_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transcript_run_id",
            "sequence_number",
            name="uq_transcript_segments_transcript_run_id_sequence_number",
        ),
    )
    op.create_index(
        "ix_transcript_segments_transcript_run_id",
        "transcript_segments",
        ["transcript_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_speaker_user_id",
        "transcript_segments",
        ["speaker_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_edited_by_user_id",
        "transcript_segments",
        ["edited_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segments_transcript_run_id_sequence_number",
        "transcript_segments",
        ["transcript_run_id", "sequence_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcript_segments_transcript_run_id_sequence_number",
        table_name="transcript_segments",
    )
    op.drop_index(
        "ix_transcript_segments_edited_by_user_id", table_name="transcript_segments"
    )
    op.drop_index(
        "ix_transcript_segments_speaker_user_id", table_name="transcript_segments"
    )
    op.drop_index(
        "ix_transcript_segments_transcript_run_id", table_name="transcript_segments"
    )
    op.drop_table("transcript_segments")

    op.drop_index(
        "ix_transcript_runs_meeting_id_created_at", table_name="transcript_runs"
    )
    op.drop_index("ix_transcript_runs_created_at", table_name="transcript_runs")
    op.drop_index(
        "ix_transcript_runs_created_by_user_id", table_name="transcript_runs"
    )
    op.drop_index("ix_transcript_runs_status", table_name="transcript_runs")
    op.drop_index("ix_transcript_runs_meeting_id", table_name="transcript_runs")
    op.drop_table("transcript_runs")
