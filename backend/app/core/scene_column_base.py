from __future__ import annotations

import re
from typing import Any

from .design_profiles import CustomSectionDefinition, SceneGeometryProfile, STEEL_SECTIONS
from .engine import calculate
from .errors import CalculationInputError
from .scene_foundation import scene_reaction_envelopes
from .schemas import CalculationMode, CalculationModule, CalculationRequest


_ANCHOR_GRADES = {"4.8", "5.8", "8.8"}


def _not_calculated(base_id: str, connection_id: str | None, support_id: str, code: str, missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "column_base_id": base_id,
        "connection_id": connection_id,
        "support_id": support_id,
        "status": "not_calculated",
        "verification_status": "unverified",
        "issue_code": code,
        "missing_inputs": missing or [],
    }


def _section_geometry(section: Any) -> tuple[float, float] | None:
    dimensions = section.dimensions
    if section.family == "SHS":
        side = float(dimensions.get("b_mm") or dimensions.get("h_mm") or 0)
        return (side, side) if side > 0 else None
    if section.family in {"RHS", "H", "I"}:
        depth = float(dimensions.get("h_mm") or 0)
        width = float(dimensions.get("b_mm") or 0)
        return (depth, width) if depth > 0 and width > 0 else None
    return None


def _concrete_strength(grade: str) -> float | None:
    match = re.fullmatch(r"C(?P<value>\d+(?:\.\d+)?)", grade.strip().upper())
    return float(match.group("value")) if match else None


def calculate_scene_column_bases(
    geometry: SceneGeometryProfile,
    support_reactions: dict[str, dict[str, float]],
    custom_sections: list[CustomSectionDefinition],
    *,
    project_name: str,
) -> list[dict[str, Any]]:
    """Check saved steel column bases from their real support reactions.

    The adapter refuses missing geometry and unsupported section/anchor families.
    It never substitutes the single-calculation module's quick defaults.
    """

    supports = {item.id: item for item in geometry.supports}
    assignments = {item.member_id: item for item in geometry.member_instances}
    member_types = {item.id: item for item in geometry.member_types}
    standard_sections = {item.id: item for item in STEEL_SECTIONS}
    project_sections = {item.id: item for item in custom_sections}
    foundations = {item.support_id: item for item in geometry.foundation_instances}
    foundation_types = {item.id: item for item in geometry.foundation_types}
    results: list[dict[str, Any]] = []

    for base in geometry.column_bases:
        support = supports.get(base.support_id)
        if support is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, base.support_id, "unknown_support"))
            continue
        reaction = support_reactions.get(support.node_id)
        if reaction is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "missing_support_reaction", ["support_reaction"]))
            continue
        assignment = assignments.get(base.column_member_id)
        member_type = member_types.get(assignment.member_type_id) if assignment else None
        if assignment is None or member_type is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "missing_column_assignment", ["column_member_type"] ))
            continue
        section_id = assignment.override_section_id or member_type.section_id
        section = standard_sections.get(section_id) or project_sections.get(section_id)
        if section is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "unknown_section", ["saved_column_section"] ))
            continue
        section_geometry = _section_geometry(section)
        if section_geometry is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "unsupported_section_family"))
            continue
        if member_type.material_grade not in {"Q235B", "Q355B"}:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "unsupported_steel_grade"))
            continue
        if base.anchor_grade not in _ANCHOR_GRADES:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "unsupported_anchor_property_class", ["anchor_grade_4.8_5.8_or_8.8"]))
            continue
        required = {
            "anchor_spacing_mm": base.anchor_spacing_mm,
            "anchor_edge_mm": base.anchor_edge_mm,
            "weld_throat_mm": base.weld_throat_mm,
            "concrete_bearing_capacity_mpa": base.concrete_bearing_capacity_mpa,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "missing_column_base_inputs", missing))
            continue
        foundation = foundations.get(support.id)
        foundation_type = foundation_types.get(foundation.foundation_type_id) if foundation else None
        concrete_fcu = _concrete_strength(foundation_type.concrete_grade) if foundation_type else None
        if concrete_fcu is None:
            results.append(_not_calculated(base.id, base.connection_instance_id, support.id, "missing_supported_foundation_concrete_grade", ["foundation_concrete_grade"] ))
            continue

        depth, width = section_geometry
        request = CalculationRequest(
            mode=CalculationMode.QUICK,
            module=CalculationModule.STEEL_BASEPLATE_ANCHOR,
            project_name=project_name,
            inputs={
                "plate_length_mm": base.base_plate_length_mm,
                "plate_width_mm": base.base_plate_width_mm,
                "plate_thickness_mm": base.base_plate_thickness_mm,
                "column_depth_mm": depth,
                "column_width_mm": width,
                "steel_grade": member_type.material_grade,
                "concrete_bearing_capacity_mpa": base.concrete_bearing_capacity_mpa,
                "anchor_count": base.anchor_count,
                "anchor_diameter_mm": base.anchor_diameter_mm,
                "anchor_grade": base.anchor_grade,
                "anchor_spacing_mm": base.anchor_spacing_mm,
                "anchor_edge_mm": base.anchor_edge_mm,
                "weld_throat_mm": base.weld_throat_mm,
                "embedment_depth_mm": base.anchor_embedment_mm,
                "concrete_fcu_mpa": concrete_fcu,
                "upstream_reaction_envelopes": scene_reaction_envelopes(reaction),
            },
            loads=[],
        )
        try:
            calculation = calculate(request)
        except CalculationInputError as exc:
            item = _not_calculated(base.id, base.connection_instance_id, support.id, exc.code)
            item["error"] = exc.as_dict()
            results.append(item)
            continue

        failed = [check.name for check in calculation.checks if not check.passed]
        results.append({
            "column_base_id": base.id,
            "connection_id": base.connection_instance_id,
            "support_id": support.id,
            "support_node_id": support.node_id,
            "column_member_id": base.column_member_id,
            "status": "failed" if failed else "incomplete",
            "verification_status": "unverified",
            "section_id": section_id,
            "section_source": "project_custom" if section_id in project_sections else "standard_catalog",
            "checks": [item.model_dump(mode="json") for item in calculation.checks],
            "failed_checks": failed,
            "steps": [item.model_dump(mode="json") for item in calculation.steps],
            "warnings": [item.model_dump(mode="json") for item in calculation.warnings],
            "reaction_envelopes": [item.model_dump(mode="json") for item in calculation.reaction_envelopes],
            "pending_checks": ["锚栓深层拔出与劈裂", "锚栓和短柱配筋耦合", "节点族独立基准验证"],
        })
    return results
