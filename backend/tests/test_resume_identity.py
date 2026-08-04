from app.api.resumes import _extract_identity


def test_extract_identity_accepts_spaced_phone_number() -> None:
    name, email, phone = _extract_identity(
        "姓名：李小明\n电话：1 3 8 1 2 3 4 5 6 7 8\n邮箱：li@example.com",
        "李小明-简历.pdf",
    )

    assert name == "李小明"
    assert email == "li@example.com"
    assert phone == "13812345678"


def test_extract_identity_accepts_email_with_ocr_spaces() -> None:
    _, email, phone = _extract_identity("姓名：张三\nzhang san @ example.com", "张三-简历.pdf")

    assert email == "zhangsan@example.com"
    assert phone is None
