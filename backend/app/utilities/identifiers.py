from uuid import uuid4


def generate_uuid() -> str:
    """標準形式のUUID v4文字列を生成する。"""
    return str(uuid4())
