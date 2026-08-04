import json

from app.ai.jd_analyzer import _normalize_analysis_payload


def test_normalize_accepts_dimensions_object() -> None:
    payload = _normalize_analysis_payload(
        json.dumps(
            {
                "summary": "test",
                "dimensions": {
                    "agent": {
                        "description": "Agent 开发",
                        "is_gate": True,
                        "acceptable_alternatives": [],
                        "evidence_rule": "有项目证据",
                    }
                },
            }
        )
    )

    assert payload["dimensions"] == [
        {
            "code": "agent",
            "description": "Agent 开发",
            "is_gate": True,
            "acceptable_alternatives": [],
            "evidence_rule": "有项目证据",
        }
    ]


def test_normalize_uses_object_key_as_canonical_code() -> None:
    payload = _normalize_analysis_payload(
        json.dumps(
            {
                "dimensions": {
                    "engineering": {
                        "code": "software_engineering",
                        "description": "工程能力",
                        "is_gate": False,
                        "acceptable_alternatives": [],
                        "evidence_rule": "项目证据",
                    }
                }
            }
        )
    )

    assert payload["dimensions"][0]["code"] == "engineering"
