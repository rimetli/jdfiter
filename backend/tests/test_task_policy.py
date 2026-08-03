from decimal import Decimal

from app.core.task_policy import retry_delay_seconds
from app.worker import credibility_adjustment, score_factor


def test_exponential_retry_delay_is_bounded() -> None:
    assert retry_delay_seconds(1, 15, 300) == 15
    assert retry_delay_seconds(2, 15, 300) == 30
    assert retry_delay_seconds(5, 15, 300) == 240
    assert retry_delay_seconds(8, 15, 300) == 300


def test_score_factor_uses_depth_and_role() -> None:
    assert score_factor("MET", "DEEP", "LEAD") == Decimal(1)
    assert score_factor("MET", "SHALLOW", "EXPOSURE") == Decimal("0.3")
    assert score_factor("PARTIAL", "DEEP", "LEAD") == Decimal("0.3")
    assert score_factor("UNKNOWN", "NONE", "EXPOSURE") == Decimal(0)


def test_credibility_adjustment_reduces_all_high_confidence_claims() -> None:
    class Item:
        dimension_code = "agent"

    class Match:
        status = "MET"
        depth = "DEEP"
        role = "LEAD"

    total, warnings = credibility_adjustment([Item()], {"agent": Match()}, 100)
    assert total == 70
    assert warnings
