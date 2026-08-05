from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


JobCategory = Literal[
    "TECH_ENGINEERING",
    "AI_AGENT",
    "PRODUCT",
    "DESIGN",
    "SALES_BD",
    "MARKETING",
    "OPERATIONS",
    "CUSTOMER_SUCCESS",
    "HR",
    "FINANCE",
    "LEGAL_COMPLIANCE",
    "SUPPLY_CHAIN",
    "MANAGEMENT",
    "GENERAL",
]


class JobCreate(BaseModel):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    job_category: JobCategory = "GENERAL"
    jd_content: str = Field(min_length=10)


class JobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    job_category: JobCategory | None = None
    jd_content: str | None = Field(default=None, min_length=10)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    department: str | None
    job_category: JobCategory
    jd_content: str
    status: str
    active_requirement_version_id: int | None
    owner_name: str | None = None
    created_at: datetime
    updated_at: datetime


class RequirementItemCreate(BaseModel):
    dimension_code: str = Field(max_length=50)
    item_code: str = Field(max_length=100)
    name: str = Field(max_length=200)
    description: str | None = None
    requirement_type: str
    max_score: Decimal = Field(ge=0, le=100)
    is_gate: bool = False
    acceptable_alternatives: list[str] | None = None
    evidence_rule: str | None = None
    sort_order: int = 0


class RequirementVersionCreate(BaseModel):
    summary: str | None = None
    rubric_version: str = "1.0.0"
    weight_config: dict[str, Decimal]
    items: list[RequirementItemCreate]

    @model_validator(mode="after")
    def validate_score(self):
        total = sum((item.max_score for item in self.items), Decimal(0))
        if total != Decimal(100):
            raise ValueError(f"能力项总分必须为100，当前为{total}")
        return self


class RequirementVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    version_no: int
    summary: str | None
    rubric_version: str
    weight_config: dict
    status: str
    created_at: datetime
    published_at: datetime | None


class RequirementItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dimension_code: str
    item_code: str
    name: str
    description: str | None
    requirement_type: str
    max_score: Decimal
    is_gate: bool
    acceptable_alternatives: list[str] | None
    evidence_rule: str | None
    sort_order: int


class RequirementVersionDetail(RequirementVersionRead):
    items: list[RequirementItemRead]


class RequirementScoreUpdate(BaseModel):
    item_id: int
    max_score: Decimal = Field(ge=0, le=100)


class RequirementScoresUpdate(BaseModel):
    items: list[RequirementScoreUpdate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_total(self):
        total = sum((item.max_score for item in self.items), Decimal(0))
        if total != Decimal(100):
            raise ValueError(f"评分总分必须为100，当前为{total}")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("能力项不能重复")
        return self
