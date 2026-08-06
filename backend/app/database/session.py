from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import engine


def create_session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=database_engine, autoflush=False, expire_on_commit=False)


SessionLocal = create_session_factory(engine)


def get_db_session() -> Iterator[Session]:
    """APIリクエスト単位のDB Sessionを提供する。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
