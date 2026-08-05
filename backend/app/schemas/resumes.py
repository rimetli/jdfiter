from pydantic import BaseModel


class ResumeUploadRead(BaseModel):
    candidate_id: int | None = None
    resume_file_id: int | None = None
    application_id: int | None = None
    task_id: int
    filename: str
    status: str
    duplicate: bool | None = None
    match_rule: str = "pending"
