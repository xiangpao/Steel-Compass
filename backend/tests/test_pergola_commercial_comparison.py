from __future__ import annotations

import pytest

from verification.pergola_commercial_comparison import compare_record


def test_comparison_gate_requires_real_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        compare_record({"metrics": [{"name": "x", "steel_compass": 1, "external": 1, "tolerance": 0.1}]})


def test_comparison_gate_reports_numeric_difference_without_claiming_source() -> None:
    result = compare_record({
        "product": "synthetic-test-only",
        "product_version": "fixture",
        "model_id": "unit-test",
        "export_date": "2026-08-24",
        "reviewer": "automated-test",
        "metrics": [
            {"name": "reaction", "steel_compass": 100, "external": 104, "tolerance": 0.05},
            {"name": "settlement", "steel_compass": 12, "external": 15, "tolerance": 0.10},
        ],
    })
    assert result["status"] == "failed"
    assert result["comparisons"][0]["passed"] is True
    assert result["comparisons"][1]["passed"] is False
