import pytest
from pydantic import ValidationError

from app.api.candidates import BatchAnalyzeRequest


def test_batch_analysis_allows_at_most_five_resumes() -> None:
    payload = BatchAnalyzeRequest(application_ids=[1, 2, 3, 4, 5])
    assert payload.application_ids == [1, 2, 3, 4, 5]


def test_batch_analysis_rejects_more_than_five_resumes() -> None:
    with pytest.raises(ValidationError):
        BatchAnalyzeRequest(application_ids=[1, 2, 3, 4, 5, 6])
