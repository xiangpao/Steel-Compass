"""Auditable import gate for external YJK/PKPM comparison results.

The gate deliberately cannot manufacture commercial-software evidence.  It
accepts a user-exported JSON record with provenance and compares named metrics
against the immutable Steel-Compass snapshot values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricComparison:
    metric: str
    steel_compass: float
    external: float
    relative_error: float
    tolerance: float
    passed: bool


def compare_record(payload: dict[str, Any]) -> dict[str, Any]:
    required = ("product", "product_version", "model_id", "export_date", "reviewer", "metrics")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"missing external evidence provenance: {', '.join(missing)}")
    date.fromisoformat(str(payload["export_date"]))
    metrics = payload["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("metrics must be a non-empty list")
    comparisons: list[MetricComparison] = []
    for item in metrics:
        if not isinstance(item, dict):
            raise ValueError("each metric must be an object")
        for key in ("name", "steel_compass", "external", "tolerance"):
            if key not in item:
                raise ValueError(f"metric missing {key}")
        internal = float(item["steel_compass"])
        external = float(item["external"])
        tolerance = float(item["tolerance"])
        if tolerance <= 0 or tolerance > 1:
            raise ValueError("tolerance must be within (0, 1]")
        denominator = max(abs(external), abs(internal), 1e-9)
        error = abs(internal - external) / denominator
        comparisons.append(MetricComparison(
            metric=str(item["name"]),
            steel_compass=internal,
            external=external,
            relative_error=error,
            tolerance=tolerance,
            passed=error <= tolerance,
        ))
    return {
        "evidence_kind": "external_commercial_software_export",
        "product": payload["product"],
        "product_version": payload["product_version"],
        "model_id": payload["model_id"],
        "export_date": payload["export_date"],
        "reviewer": payload["reviewer"],
        "source_files": payload.get("source_files", []),
        "status": "passed" if all(item.passed for item in comparisons) else "failed",
        "comparisons": [item.__dict__ for item in comparisons],
    }


def compare_file(path: str | Path) -> dict[str, Any]:
    return compare_record(json.loads(Path(path).read_text(encoding="utf-8")))
