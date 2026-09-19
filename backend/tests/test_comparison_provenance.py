import hashlib
import json
from pathlib import Path

import pytest

from verification.pergola_commercial_comparison import compare_file, compare_record


def evidence(tmp_path):
    source = tmp_path / "reference.txt"
    source.write_text("Synthetic regression fixture, NOT engineering evidence.\nN=100 kN", encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"id": 7, "snapshot": {"reaction_kn": 100.0}}), encoding="utf-8")
    return {
        "evidence_kind": "test_fixture",
        "product": "regression-fixture", "product_version": "1",
        "model_id": "fixture-1", "export_date": "2026-09-19",
        "reviewer": "automated-test",
        "source_files": [{"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        "snapshot_reference": {"file": snapshot.name, "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(), "id": 7},
        "metrics": [{"name": "reaction", "snapshot_path": ["snapshot", "reaction_kn"], "unit": "kN", "steel_compass": 100, "external": 100, "tolerance": 0.01}],
    }


def test_unfilled_template_cannot_pass():
    with pytest.raises(ValueError):
        compare_file(Path(__file__).parents[1] / "verification/PERGOLA_COMMERCIAL_COMPARISON_TEMPLATE.json")


def test_fixture_numeric_pass_is_not_review_approval(tmp_path):
    result = compare_record(evidence(tmp_path), base_dir=tmp_path)
    assert result["status"] == "passed"
    assert result["evidence_kind"] == "test_fixture"
    assert result["evidence_status"] == "unreviewed"
    assert result["verification_status"] == "unverified"


def test_cannot_relax_force_tolerance_or_use_relative_zero(tmp_path):
    payload=evidence(tmp_path)
    payload["metrics"][0]["tolerance"]=0.1
    with pytest.raises(ValueError):
        compare_record(payload,base_dir=tmp_path)
    payload["metrics"][0].update(tolerance=0.01,external=0)
    with pytest.raises(ValueError):
        compare_record(payload,base_dir=tmp_path)


@pytest.mark.parametrize("field", ["steel_compass", "external", "tolerance"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True])
def test_nonfinite_and_boolean_metrics_rejected(tmp_path, field, value):
    payload = evidence(tmp_path)
    payload["metrics"][0][field] = value
    with pytest.raises(ValueError):
        compare_record(payload, base_dir=tmp_path)


@pytest.mark.parametrize("mutation", ["missing_source", "tampered_source", "tampered_snapshot", "wrong_id", "wrong_value", "missing_path", "duplicate_metric", "placeholder"])
def test_unbound_evidence_rejected(tmp_path, mutation):
    payload = evidence(tmp_path)
    if mutation == "missing_source":
        payload["source_files"] = []
    elif mutation == "tampered_source":
        (tmp_path / "reference.txt").write_text("changed", encoding="utf-8")
    elif mutation == "tampered_snapshot":
        (tmp_path / "snapshot.json").write_text("{}", encoding="utf-8")
    elif mutation == "wrong_id":
        payload["snapshot_reference"]["id"] = 8
    elif mutation == "wrong_value":
        payload["metrics"][0]["steel_compass"] = 99
    elif mutation == "missing_path":
        payload["metrics"][0]["snapshot_path"] = ["missing"]
    elif mutation == "duplicate_metric":
        payload["metrics"].append(payload["metrics"][0].copy())
    else:
        payload["reviewer"] = "REPLACE_WITH_REVIEWER"
    with pytest.raises(ValueError):
        compare_record(payload, base_dir=tmp_path)


def test_file_paths_resolve_relative_to_record(tmp_path):
    payload = evidence(tmp_path)
    payload["metrics"][0]["external"] = 110
    record = tmp_path / "comparison.json"
    record.write_text(json.dumps(payload), encoding="utf-8")
    assert compare_file(record)["status"] == "failed"
