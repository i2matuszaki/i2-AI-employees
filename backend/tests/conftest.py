from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database.base import Base
from app.database.engine import create_database_engine
from app.database.session import create_session_factory


@pytest.fixture
def test_engine(tmp_path) -> Iterator[Engine]:
    database_path = tmp_path / "database" / "test.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    session_factory = create_session_factory(test_engine)
    with session_factory() as session:
        yield session
