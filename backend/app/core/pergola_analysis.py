from __future__ import annotations

from .design_profiles import (
    CustomSectionCreate,
    CustomSectionDefinition,
    DesignLoadCombination,
    MemberDesignParameters,
    STEEL_SECTIONS,
    SceneStructuralProfile,
    calculate_custom_section,
)
from .pergola_loads import PergolaLoadPackage
from .scene_member_checks import calculate_scene_member_checks
from .scene_space_frame import analyze_scene_space_frame


def _section_catalog(custom_sections: list[CustomSectionDefinition]) -> dict[str, CustomSectionDefinition]:
    result: dict[str, CustomSectionDefinition] = {}
    for entry in STEEL_SECTIONS:
        dimensions = dict(entry.dimensions)
        if entry.family == "SHS":
            dimensions["h_mm"] = dimensions["b_mm"]
        result[entry.id] = calculate_custom_section(
            CustomSectionCreate(
                name=entry.designation,
                family=entry.family,
                dimensions=dimensions,
                source_reference=entry.source_reference,
            ),
            section_id=entry.id,
        )
    result.update({item.id: item for item in custom_sections})
    return result


def _member_properties(
    profile: SceneStructuralProfile,
    custom_sections: list[CustomSectionDefinition],
) -> tuple[dict[str, CustomSectionDefinition], dict[str, str]]:
    geometry = profile.geometry
    if geometry is None:
        return {}, {}
    catalog = _section_catalog(custom_sections)
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


def analyze_pergola_package(
    profile: SceneStructuralProfile,
    load_package: PergolaLoadPackage,
    custom_sections: list[CustomSectionDefinition],
) -> dict[str, object]:
    cases_by_id = {case.id: case for case in load_package.cases}
    case_results: dict[str, dict[str, object]] = {}
    for case in load_package.cases:
        case_results[case.id] = analyze_scene_space_frame(
            profile,
            [] if case.id == "SELF-WEIGHT" else [case],
            custom_sections,
            include_self_weight=case.id == "SELF-WEIGHT",
        )
    combination_results = {
        combination.id: _run_combination(profile, cases_by_id, combination, custom_sections)
        for combination in load_package.combinations
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
        "solver": "steel-compass-pergola-analysis-2.0",
        "verification_status": "unverified",
        "case_results": case_results,
        "combination_results": combination_results,
        "member_checks": member_checks,
        "maximum_translation_mm": round(maximum_translation, 6),
        "maximum_balance_residual_kn": round(maximum_balance, 8),
        "balanced": maximum_balance < 1e-6,
    }
