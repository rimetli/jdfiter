from hashlib import sha256
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.api.resumes import _stream_pdf_to_storage
from app.schemas.resumes import ResumeUploadRead


@pytest.mark.asyncio
async def test_upload_streams_pdf_to_pending_storage(tmp_path) -> None:
    content = b"%PDF-1.7\nexample resume"
    upload = UploadFile(filename="candidate.pdf", file=BytesIO(content))
    target = tmp_path / "pending" / "candidate.pdf"

    size, digest = await _stream_pdf_to_storage(upload, target)

    assert size == len(content)
    assert digest == sha256(content).hexdigest()
    assert target.read_bytes() == content


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf_and_removes_partial_file(tmp_path) -> None:
    upload = UploadFile(filename="candidate.pdf", file=BytesIO(b"not a pdf"))
    target = tmp_path / "pending" / "candidate.pdf"

    with pytest.raises(HTTPException) as error:
        await _stream_pdf_to_storage(upload, target)

    assert error.value.status_code == 415
    assert not target.exists()


def test_async_upload_response_allows_pending_identity() -> None:
    response = ResumeUploadRead(task_id=1, filename="candidate.pdf", status="PENDING")
    assert response.candidate_id is None
    assert response.match_rule == "pending"
