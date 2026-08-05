from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url

from app.config import settings


def create_sqlite_parent_directory(database_url: str) -> None:
    """ファイルを使用するSQLite URLの場合だけ親ディレクトリを作成する。"""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if (
        database is None
        or database == ""
        or database == ":memory:"
        or database.startswith("file:")
    ):
        return

    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    create_sqlite_parent_directory(database_url)
    is_sqlite = make_url(database_url).get_backend_name() == "sqlite"
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    database_engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)

    return database_engine


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """SQLiteのDBAPI接続ごとに外部キー制約を有効化する。"""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


engine = create_database_engine(settings.database_url)
