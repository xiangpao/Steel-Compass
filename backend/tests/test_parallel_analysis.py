import pickle
from dataclasses import replace

from app.core import pergola_analysis
from app.core.errors import CalculationInputError
from test_pergola_analysis40 import (
    MemberGroupSpecification,
    SceneStructuralProfile,
    build_pergola_load_package,
    geometry_23,
    roof_selection,
    site_profile,
)


def test_calculation_input_error_survives_worker_pickling() -> None:
    error = CalculationInputError("second_order_instability", "失稳", field="geometry", details={"a": 1})
    restored = pickle.loads(pickle.dumps(error))
    assert (restored.code, restored.message, restored.field, restored.details) == (
        "second_order_instability", "失稳", "geometry", {"a": 1})


def test_parallel_pergola_analysis_matches_serial(monkeypatch) -> None:
    geometry = geometry_23()
    profile = SceneStructuralProfile(
        profile_version="3.0",
        stage="scheme_estimate",
        member_groups=[
            MemberGroupSpecification(group_id="columns", role="column", material_grade="Q355B", section_catalog_id="shs-150x6", strong_axis_unbraced_length_m=3, weak_axis_unbraced_length_m=3),
            MemberGroupSpecification(group_id="beams", role="beam", material_grade="Q355B", section_catalog_id="rhs-200x100x6", strong_axis_unbraced_length_m=4, weak_axis_unbraced_length_m=4),
        ],
        geometry=geometry,
    )
    package = build_pergola_load_package(geometry, site_profile(), roof_selection())
    package = replace(package, combinations=package.combinations[:6])
    monkeypatch.setattr(pergola_analysis, "_analysis_workers", lambda: 1)
    serial = pergola_analysis.analyze_pergola_package(profile, package, [])
    monkeypatch.setattr(pergola_analysis, "_analysis_workers", lambda: 2)
    parallel = pergola_analysis.analyze_pergola_package(profile, package, [])
    # Repeated serial runs already differ at ~1e-13 through multithreaded BLAS
    # summation order; parallel workers must stay within the same noise.
    assert _close(serial["combination_results"], parallel["combination_results"])
    assert _close(serial["case_results"], parallel["case_results"])
    assert _close(serial["member_checks"], parallel["member_checks"])


def _close(a, b, rel=1e-9, abs_tol=1e-9) -> bool:
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) <= max(rel * max(abs(a), abs(b)), abs_tol)
    return a == b
