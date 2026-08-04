from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """すべてのORMモデルが継承する基底クラス。"""
