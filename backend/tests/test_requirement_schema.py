from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.jobs import RequirementItemCreate, RequirementVersionCreate


def item(score: str) -> RequirementItemCreate:
    return RequirementItemCreate(
        dimension_code="agent",
        item_code="agent_delivery",
        name="Agent 项目",
        requirement_type="MUST_HAVE",
        max_score=Decimal(score),
    )


def test_requirement_version_requires_exactly_one_hundred_points() -> None:
    with pytest.raises(ValidationError):
        RequirementVersionCreate(weight_config={"agent": Decimal(99)}, items=[item("99")])


def test_requirement_version_accepts_one_hundred_points() -> None:
    version = RequirementVersionCreate(weight_config={"agent": Decimal(100)}, items=[item("100")])
    assert version.items[0].max_score == Decimal(100)
