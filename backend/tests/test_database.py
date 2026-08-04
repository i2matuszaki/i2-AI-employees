from sqlalchemy import text

from app.database.engine import create_database_engine
from app.database.session import create_session_factory


def test_sqlite_connection_uses_temporary_database(tmp_path) -> None:
    database_path = tmp_path / "database" / "test.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    test_session_factory = create_session_factory(database_engine)

    try:
        with test_session_factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database_engine.dispose()

    assert database_path.is_file()


def test_memory_sqlite_does_not_create_a_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    database_engine = create_database_engine("sqlite:///:memory:")
    try:
        with database_engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database_engine.dispose()

    assert list(tmp_path.iterdir()) == []


def test_non_sqlite_url_does_not_create_a_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    from app.database.engine import create_sqlite_parent_directory

    create_sqlite_parent_directory("postgresql://user:password@localhost/example")

    assert list(tmp_path.iterdir()) == []
