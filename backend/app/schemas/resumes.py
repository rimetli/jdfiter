from pydantic import BaseModel


class ResumeUploadRead(BaseModel):
    candidate_id: int
    resume_file_id: int
    application_id: int
    task_id: int
    filename: str
    status: str
    duplicate: bool = False
    match_rule: str
