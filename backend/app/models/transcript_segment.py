from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base
from app.utilities.datetime import UTCDateTime, utc_now
from app.utilities.identifiers import generate_uuid

if TYPE_CHECKING:
    from app.models.transcript_run import TranscriptRun
    from app.models.user import User


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_transcript_segments_id_length"),
        CheckConstraint(
            "sequence_number >= 1", name="ck_transcript_segments_sequence_number"
        ),
        CheckConstraint(
            "length(trim(text)) >= 1", name="ck_transcript_segments_text_not_blank"
        ),
        CheckConstraint(
            "speaker_label IS NULL OR "
            "(length(speaker_label) BETWEEN 1 AND 100 "
            "AND speaker_label = trim(speaker_label))",
            name="ck_transcript_segments_speaker_label",
        ),
        CheckConstraint(
            "start_offset_ms IS NULL OR start_offset_ms >= 0",
            name="ck_transcript_segments_start_offset_nonnegative",
        ),
        CheckConstraint(
            "end_offset_ms IS NULL OR end_offset_ms >= 0",
            name="ck_transcript_segments_end_offset_nonnegative",
        ),
        CheckConstraint(
            "start_offset_ms IS NULL OR end_offset_ms IS NULL "
            "OR end_offset_ms >= start_offset_ms",
            name="ck_transcript_segments_offset_order",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_transcript_segments_confidence_range",
        ),
        CheckConstraint("is_edited IN (0, 1)", name="ck_transcript_segments_is_edited"),
        CheckConstraint(
            "is_edited = 1 OR (edited_by_user_id IS NULL AND edited_at IS NULL)",
            name="ck_transcript_segments_unedited_has_no_editor",
        ),
        CheckConstraint(
            "is_edited = 0 OR (edited_by_user_id IS NOT NULL AND edited_at IS NOT NULL)",
            name="ck_transcript_segments_edited_has_editor",
        ),
        UniqueConstraint(
            "transcript_run_id",
            "sequence_number",
            name="uq_transcript_segments_transcript_run_id_sequence_number",
        ),
        Index("ix_transcript_segments_transcript_run_id", "transcript_run_id"),
        Index("ix_transcript_segments_speaker_user_id", "speaker_user_id"),
        Index("ix_transcript_segments_edited_by_user_id", "edited_by_user_id"),
        Index(
            "ix_transcript_segments_transcript_run_id_sequence_number",
            "transcript_run_id",
            "sequence_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    transcript_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcript_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    speaker_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edited_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )

    transcript_run: Mapped[TranscriptRun] = relationship(
        back_populates="segments", foreign_keys=[transcript_run_id]
    )
    speaker_user: Mapped[User | None] = relationship(
        back_populates="spoken_transcript_segments", foreign_keys=[speaker_user_id]
    )
    edited_by: Mapped[User | None] = relationship(
        back_populates="edited_transcript_segments", foreign_keys=[edited_by_user_id]
    )

    @validates("text")
    def validate_text(self, _key: str, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("textには文字列を指定してください。")  # noqa: TRY004
        normalized = value.strip()
        if not normalized:
            raise ValueError("textには空白以外の文字が必要です。")
        return normalized

    @validates("speaker_label")
    def validate_speaker_label(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("speaker_labelには文字列を指定してください。")  # noqa: TRY004
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 100:
            raise ValueError("speaker_labelは100文字以下です。")
        return normalized

    @validates("sequence_number")
    def validate_sequence_number(self, _key: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("sequence_numberには1以上の整数を指定してください。")
        return value

    @validates("start_offset_ms", "end_offset_ms")
    def validate_offset(self, key: str, value: int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key}には0以上の整数を指定してください。")
        return value

    @validates("confidence")
    def validate_confidence(self, _key: str, value: object | None) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(  # noqa: TRY004
                "confidenceには0以上1以下の数値を指定してください。"
            )
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("confidenceには0以上1以下の数値を指定してください。") from None
        if not normalized.is_finite() or not Decimal(0) <= normalized <= Decimal(1):
            raise ValueError("confidenceには0以上1以下の数値を指定してください。")
        return normalized

    @validates("is_edited")
    def validate_is_edited(self, _key: str, value: bool) -> bool:
        if not isinstance(value, bool):
            raise ValueError("is_editedにはboolを指定してください。")  # noqa: TRY004
        return value
