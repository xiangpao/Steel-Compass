from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import os

from .design_profiles import (
    CustomSectionDefinition,
    DesignLoadCombination,
    MemberDesignParameters,
    SceneStructuralProfile,
)
from .pergola_loads import PergolaLoadPackage, design_load_combinations, scene_area_cases
from .scene_member_checks import calculate_scene_member_checks
from .scene_schemas import SceneLoadItem
from .scene_space_frame import analyze_scene_space_frame, section_catalog


def _member_properties(
    profile: SceneStructuralProfile,
    custom_sections: list[CustomSectionDefinition],
) -> tuple[dict[str, CustomSectionDefinition], dict[str, str]]:
    geometry = profile.geometry
    if geometry is None:
        return {}, {}
    catalog = section_catalog(custom_sections)
    groups = {item.group_id: item for item in profile.member_groups}
    overrides = {item.member_id: item for item in profile.member_overrides}
    sections: dict[str, CustomSectionDefinition] = {}
    grades: dict[str, str] = {}
    for member in geometry.members:
        override = overrides.get(member.id)
        group = groups.get(member.group_id)
        section_id = override.section_id if override else (group.custom_section_id or group.section_catalog_id) if group else None
        grade = override.material_grade if override else group.material_grade if group else None
        if section_id in catalog and grade:
            sections[member.id] = catalog[section_id]
            grades[member.id] = grade
    return sections, grades


def _run_combination(
    profile: SceneStructuralProfile,
    cases_by_id: dict[str, object],
    combination: DesignLoadCombination,
    custom_sections: list[CustomSectionDefinition],
) -> dict[str, object]:
    factored = []
    for case_id, factor in combination.factors.items():
        if case_id == "SELF-WEIGHT" or not factor:
            continue
        case = cases_by_id.get(case_id)
        if case is not None:
            factored.append(case.model_copy(update={"adopted_value": float(case.adopted_value or 0.0) * factor}))
    return analyze_scene_space_frame(
        profile,
        factored,
        custom_sections,
        include_self_weight="SELF-WEIGHT" in combination.factors,
        self_weight_factor=float(combination.factors.get("SELF-WEIGHT", 0.0)),
    )


def _run_case(
    profile: SceneStructuralProfile,
    case: object,
    custom_sections: list[CustomSectionDefinition],
) -> dict[str, object]:
    self_weight = getattr(case, "id") == "SELF-WEIGHT"
    return analyze_scene_space_frame(
        profile,
        [] if self_weight else [case],
        custom_sections,
        include_self_weight=self_weight,
    )


def _analysis_workers() -> int:
    from ..config import get_settings

    return min(get_settings().analysis_workers, os.cpu_count() or 1)


@lru_cache(maxsize=1)
def _pool(workers: int) -> ProcessPoolExecutor:
    # Reused across requests; each analysis is independent and deterministic,
    # so results are identical to the serial loop.
    return ProcessPoolExecutor(max_workers=workers)


def _map_analyses(tasks: dict[tuple[str, str], tuple]) -> dict[tuple[str, str], dict[str, object]]:
    """Run independent analyses serially or in the shared process pool."""
    workers = _analysis_workers()
    if workers > 1:
        pool = _pool(workers)
        futures = {key: pool.submit(*task) for key, task in tasks.items()}
        return {key: future.result() for key, future in futures.items()}
    return {key: task[0](*task[1:]) for key, task in tasks.items()}


def analyze_pergola_package(
    profile: SceneStructuralProfile,
    load_package: PergolaLoadPackage,
    custom_sections: list[CustomSectionDefinition],
) -> dict[str, object]:
    cases_by_id = {case.id: case for case in load_package.cases}
    results = _map_analyses({
        **{
            ("case", case.id): (_run_case, profile, case, custom_sections)
            for case in load_package.cases
        },
        **{
            ("combination", combination.id): (
                _run_combination, profile, cases_by_id, combination, custom_sections
            )
            for combination in load_package.combinations
        },
    })
    case_results = {key: value for (kind, key), value in results.items() if kind == "case"}
    combination_results = {
        key: value for (kind, key), value in results.items() if kind == "combination"
    }
    check_basis = combination_results or case_results
    sections, grades = _member_properties(profile, custom_sections)
    geometry_for_checks = profile.geometry
    if geometry_for_checks is not None:
        groups = {item.group_id: item for item in profile.member_groups}
        geometry_for_checks = geometry_for_checks.model_copy(update={
            "members": [
                member if member.design_parameters is not None or member.group_id not in groups
                else member.model_copy(update={
                    "design_parameters": MemberDesignParameters(
                        effective_length_factor_y=groups[member.group_id].effective_length_factor_y,
                        effective_length_factor_z=groups[member.group_id].effective_length_factor_z,
                        unbraced_length_y_m=groups[member.group_id].strong_axis_unbraced_length_m,
                        unbraced_length_z_m=groups[member.group_id].weak_axis_unbraced_length_m,
                    )
                })
                for member in geometry_for_checks.members
            ]
        })
    member_checks = calculate_scene_member_checks(geometry_for_checks, check_basis, sections, grades)  # type: ignore[arg-type]
    maximum_translation = max(
        (float(result.get("maximum_translation_mm", 0.0)) for result in check_basis.values()),
        default=0.0,
    )
    maximum_balance = max(
        (
            max(abs(float(value)) for value in result.get("load_balance_kn", [0.0, 0.0, 0.0]))
            for result in check_basis.values()
        ),
        default=0.0,
    )
    return {
        "solver": "steel-compass-pergola-analysis-2.1",
        "stability_scope": _stability_summary(check_basis),
        "verification_status": "unverified",
        "case_results": case_results,
        "combination_results": combination_results,
        "member_checks": member_checks,
        "maximum_translation_mm": round(maximum_translation, 6),
        "maximum_balance_residual_kn": round(maximum_balance, 8),
        "balanced": maximum_balance < 1e-6,
    }


def _limit_state(combination_id: str) -> str:
    return "SLS" if combination_id.startswith("SLS-") else "ULS"


def _stability_summary(results: dict[str, dict[str, object]]) -> dict[str, object]:
    scopes = {key: (value.get("stability_scope") or {}) for key, value in results.items()}
    incomplete = [key for key, scope in scopes.items() if scope.get("status") == "incomplete"]
    return {
        "status": "incomplete" if incomplete else "complete",
        "incomplete_cases": incomplete,
        "excluded_truss_member_ids": sorted({
            member_id
            for scope in scopes.values()
            for member_id in scope.get("excluded_truss_member_ids", [])
        }),
    }


def analyze_scene_load_combinations(
    profile: SceneStructuralProfile,
    load_cases: list[SceneLoadItem],
    custom_sections: list[CustomSectionDefinition] | None = None,
) -> dict[str, object]:
    """Analyse a guided-grid scene once per real design combination.

    Scene load items are characteristic values. They are combined with the
    same versioned generator as the Geometry 2.3 analysis package, so
    alternative wind directions are separate combinations and are never netted
    against each other, and self-weight is factored with each combination.
    """
    custom_sections = list(custom_sections or [])
    cases, unsupported = scene_area_cases(load_cases)
    cases_by_id = {case.id: case for case in cases}
    combinations = design_load_combinations(cases)
    solved = _map_analyses({
        ("combination", combination.id): (
            _run_combination, profile, cases_by_id, combination, custom_sections
        )
        for combination in combinations
    })
    results = {key: value for (_, key), value in solved.items()}
    summaries = {}
    for combination in combinations:
        result = results[combination.id]
        summaries[combination.id] = {
            "limit_state": _limit_state(combination.id),
            "factors": dict(combination.factors),
            "maximum_translation_mm": result["maximum_translation_mm"],
            "second_order_amplification_ratio": result["second_order_amplification_ratio"],
            "first_elastic_buckling_factor": next(iter(result["elastic_buckling_factors"]), None),
            "load_balance_kn": result["load_balance_kn"],
            "support_reactions": result["support_reactions"],
            "stability_scope_status": (result.get("stability_scope") or {}).get("status"),
        }
    serviceability = {key: value for key, value in summaries.items() if value["limit_state"] == "SLS"} or summaries
    governing_id = max(serviceability, key=lambda key: serviceability[key]["maximum_translation_mm"])
    governing = results[governing_id]
    # One real combination vector per support: the combination with the
    # largest compression at that node. Components are never mixed.
    support_reactions: dict[str, dict[str, object]] = {}
    for key, summary in summaries.items():
        if summary["limit_state"] != "ULS":
            continue
        for node_id, reaction in summary["support_reactions"].items():
            current = support_reactions.get(node_id)
            if current is None or reaction["fz_kn"] > current["fz_kn"]:
                support_reactions[node_id] = {**reaction, "combination_id": key}
    maximum_balance = max(
        (max(abs(float(value)) for value in summary["load_balance_kn"]) for summary in summaries.values()),
        default=0.0,
    )
    return {
        "solver": governing["solver"],
        "analysis_basis": governing["analysis_basis"],
        "verification_status": "unverified",
        "node_count": governing["node_count"],
        "member_count": governing["member_count"],
        "roof_area_m2": governing["roof_area_m2"],
        "net_loaded_roof_area_m2": governing["net_loaded_roof_area_m2"],
        "maximum_translation_mm": governing["maximum_translation_mm"],
        "maximum_translation_combination_id": governing_id,
        "maximum_translation_basis": "SLS" if serviceability is not summaries else "ULS",
        "node_displacements": governing["node_displacements"],
        "load_balance_kn": governing["load_balance_kn"],
        "maximum_balance_residual_kn": round(maximum_balance, 8),
        "balanced": maximum_balance < 1e-6,
        "support_reactions": support_reactions,
        "support_reaction_basis": "每个支座取 ULS 组合中竖向压力最大的同一组合六分量",
        "stability_scope": _stability_summary(results),
        "load_cases": [case.id for case in cases],
        "unsupported_load_case_ids": unsupported,
        "combination_results": summaries,
        "parallel_analysis": governing["parallel_analysis"],
        "parallel_second_order_analysis": governing["parallel_second_order_analysis"],
        "load_scope": (
            "按版本化组合逐个求解：杆件自重与屋面恒载/活载/雪荷载按组合系数参与；"
            "±X、±Y 风和向下风/风吸力为互斥方向，各自形成独立组合，不相互抵消。"
            f"共 {len(summaries)} 个 ULS/SLS 组合；最大位移取 SLS 组合包络。"
        ),
    }
