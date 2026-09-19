"""Auditable import gate for external YJK/PKPM comparison results.

The gate deliberately cannot manufacture commercial-software evidence.  It
accepts a user-exported JSON record with provenance and compares named metrics
against the immutable Steel-Compass snapshot values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import isfinite
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
    absolute_error: float
    tolerance_mode: str


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(
        marker in value.upper() for marker in ("REPLACE_WITH", "TODO", "TBD")
    ):
        raise ValueError(f"invalid evidence provenance: {field}")
    return value.strip()


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("metric must be a finite number, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("metric must be a finite number") from exc
    if not isfinite(number):
        raise ValueError("metric must be a finite number")
    return number


def _checked_file(record: Any, base_dir: Path, key: str) -> bytes:
    if not isinstance(record, dict):
        raise ValueError("source provenance requires file path and sha256")
    path = base_dir / _text(record.get(key), key)
    digest = _text(record.get("sha256"), "sha256")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"evidence file unavailable: {path.name}") from exc
    if sha256(data).hexdigest() != digest.lower():
        raise ValueError(f"evidence file hash mismatch: {path.name}")
    return data


def compare_record(payload: dict[str, Any], *, base_dir: str | Path = ".") -> dict[str, Any]:
    required = ("product", "product_version", "model_id", "export_date", "reviewer", "metrics")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"missing external evidence provenance: {', '.join(missing)}")
    for key in required[:-1]:
        _text(payload[key], key)
    date.fromisoformat(str(payload["export_date"]))
    kind = payload.get("evidence_kind", "external_commercial_software_export")
    if kind not in {"external_commercial_software_export", "public_reference", "independent_calculation", "test_fixture"}:
        raise ValueError("unsupported evidence_kind")
    sources = payload.get("source_files")
    if not isinstance(sources, list) or not sources:
        raise ValueError("missing source_files provenance")
    root = Path(base_dir)
    for source in sources:
        _checked_file(source, root, "path")
    reference = payload.get("snapshot_reference")
    try:
        snapshot = json.loads(_checked_file(reference, root, "file"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid snapshot JSON") from exc
    if not isinstance(snapshot, dict) or not reference.get("id") or snapshot.get("id") != reference["id"]:
        raise ValueError("snapshot id mismatch")
    metrics = payload["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("metrics must be a non-empty list")
    comparisons: list[MetricComparison] = []
    names: set[str] = set()
    for item in metrics:
        if not isinstance(item, dict):
            raise ValueError("each metric must be an object")
        for key in ("name", "steel_compass", "external", "tolerance"):
            if key not in item:
                raise ValueError(f"metric missing {key}")
        name = _text(item["name"], "metric name")
        if name in names:
            raise ValueError("duplicate metric name")
        names.add(name)
        _text(item.get("unit"), "metric unit")
        path = item.get("snapshot_path")
        if not isinstance(path, list) or not path:
            raise ValueError("missing snapshot metric path")
        value = snapshot
        try:
            for key in path:
                value = value[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("snapshot metric path does not exist") from exc
        internal = _number(value)
        if _number(item["steel_compass"]) != internal:
            raise ValueError("internal metric does not match immutable snapshot")
        external = _number(item["external"])
        tolerance = _number(item["tolerance"])
        mode = item.get("tolerance_mode", "relative")
        category = item.get("quantity_kind", "force")
        if mode not in {"relative", "absolute"} or tolerance <= 0:
            raise ValueError("invalid tolerance policy")
        caps = {"force":0.01,"moment":0.01,"pressure":0.01,"capacity":0.02,"utilization":0.02}
        if mode == "relative":
            if category not in caps or tolerance > caps[category]:
                raise ValueError("relative tolerance exceeds predeclared category limit")
            if abs(external) < 1e-9:
                raise ValueError("near-zero reference requires a predeclared dimensional tolerance")
        else:
            _text(item.get("tolerance_basis"), "dimensional tolerance basis")
        absolute_error = abs(internal - external)
        error = absolute_error / max(abs(external), 1e-9)
        comparisons.append(MetricComparison(
            metric=str(item["name"]),
            steel_compass=internal,
            external=external,
            relative_error=error,
            tolerance=tolerance,
            passed=(error if mode == "relative" else absolute_error) <= tolerance,
            absolute_error=absolute_error,
            tolerance_mode=mode,
        ))
    return {
        "evidence_kind": kind,
        "evidence_status": "unreviewed",
        "verification_status": "unverified",
        "snapshot_reference": reference,
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
    record = Path(path)
    return compare_record(json.loads(record.read_text(encoding="utf-8")), base_dir=record.resolve().parent)
