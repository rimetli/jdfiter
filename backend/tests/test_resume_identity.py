from app.api.resumes import _normalize_phone


def test_phone_identity_is_normalized_before_deduplication() -> None:
    assert _normalize_phone("+86 138-1234-5678") == "13812345678"
    assert _normalize_phone(" 138 1234 5678 ") == "13812345678"
    assert _normalize_phone("123") is None
