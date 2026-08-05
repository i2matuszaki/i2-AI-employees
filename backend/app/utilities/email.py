def normalize_email(email: str) -> str:
    """メールアドレスの前後空白を除き、小文字へ正規化する。"""
    return email.strip().lower()
