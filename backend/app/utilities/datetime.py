from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    """現在UTC日時をtimezone-awareな値で返す。"""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """UTC日時を固定長ISO 8601文字列として保存する型。"""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("日時にはdatetimeを指定してください。")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("日時にはタイムゾーンが必要です。")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
