from decimal import Decimal

from app.core.task_policy import retry_delay_seconds
from app.worker import credibility_adjustment, gate_score_cap, score_factor


def test_exponential_retry_delay_is_bounded() -> None:
    assert retry_delay_seconds(1, 15, 300) == 15
    assert retry_delay_seconds(2, 15, 300) == 30
    assert retry_delay_seconds(5, 15, 300) == 240
    assert retry_delay_seconds(8, 15, 300) == 300


def test_score_factor_uses_depth_and_role() -> None:
    assert score_factor("MET", "DEEP", "LEAD") == Decimal("0.90")
    assert score_factor("MET", "SHALLOW", "EXPOSURE") == Decimal("0.15")
    assert score_factor("PARTIAL", "DEEP", "LEAD") == Decimal("0.45")
    assert score_factor("PARTIAL", "DEEP", "CONTRIBUTOR") == Decimal("0.35")
    assert score_factor("PARTIAL", "SHALLOW", "LEAD") == Decimal("0.30")
    assert score_factor("PARTIAL", "SHALLOW", "CONTRIBUTOR") == Decimal("0.20")
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


def test_hard_gate_caps_total_score() -> None:
    assert gate_score_cap(Decimal("82"), ["NOT_MET"])[0] == Decimal("59")
    assert gate_score_cap(Decimal("82"), ["UNKNOWN"])[0] == Decimal("69")
    assert gate_score_cap(Decimal("82"), ["PARTIAL"])[0] == Decimal("69")
    assert gate_score_cap(Decimal("82"), ["MET"])[0] == Decimal("82")
