from __future__ import annotations

import re
from typing import Any

from .design_profiles import (
    FoundationTypeDefinition,
    ProjectGeotechnicalProfile,
    SceneGeometryProfile,
)
from .engine import calculate
from .schemas import CalculationMode, CalculationModule, CalculationRequest


_REBAR_PATTERN = re.compile(
    r"^(?:Φ|φ|Ø|Phi)?\s*(?P<diameter>\d+(?:\.\d+)?)\s*@\s*(?P<spacing>\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def _parse_rebar(value: str) -> tuple[float, float] | None:
    match = _REBAR_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    return float(match.group("diameter")), float(match.group("spacing"))


def scene_reaction_envelopes(reaction: dict[str, float]) -> list[dict[str, Any]]:
    """Adapt an already-factored saved combination envelope for legacy cores.

    Geometry 2.3 analysis applies the versioned combination factors before
    reactions reach this adapter. Both compatibility entries therefore carry
    the saved envelope unchanged; applying another blanket factor here would
    double-factor the same action effect.
    """
    def adapted(source: dict[str, float], combination_id: str, limit_state: str) -> dict[str, Any]:
        components = {
            "N": {"value": float(source.get("fz_kn", 0.0)), "unit": "kN"},
            "Vx": {"value": float(source.get("fx_kn", 0.0)), "unit": "kN"},
            "Vy": {"value": float(source.get("fy_kn", 0.0)), "unit": "kN"},
            "Mx": {"value": float(source.get("mx_kn_m", 0.0)), "unit": "kN·m"},
            "My": {"value": float(source.get("my_kn_m", 0.0)), "unit": "kN·m"},
            "T": {"value": float(source.get("mz_kn_m", 0.0)), "unit": "kN·m"},
        }
        item: dict[str, Any] = {
            "name": combination_id,
            "limit_state": limit_state,
            "combination_id": combination_id,
            "combination_name": combination_id,
            "direction": "gravity" if components["N"]["value"] >= 0 else "uplift",
            "components": components,
        }
        if limit_state == "SLS":
            item["sls_type"] = "frequent" if combination_id.startswith("SLS-FREQUENT") else "quasi_permanent" if combination_id.startswith("SLS-QUASI") else "standard"
        return item

    cases = reaction.get("_cases")
    if isinstance(cases, list) and cases:
        return [
            adapted(item["reaction"], str(item["combination_id"]), str(item["limit_state"]))
            for item in cases
        ]
    return [
        adapted(reaction, "SCENE-SLS-SCREEN", "SLS"),
        adapted(reaction, "SCENE-ULS-SCREEN", "ULS"),
    ]


def _groundwater_inputs(profile: ProjectGeotechnicalProfile) -> dict[str, Any]:
    groundwater = profile.groundwater
    if groundwater.condition == "no_influence":
        return {
            "groundwater_condition": "no_influence",
            "groundwater_source": groundwater.source,
        }
    if groundwater.condition == "known_levels":
        assert groundwater.service_level_m is not None
        return {
            "groundwater_condition": "known_water_table",
            "water_table_depth_m": max(-groundwater.service_level_m, 0.0),
            "groundwater_source": groundwater.source,
        }
    return {
        "groundwater_condition": "unknown",
        "groundwater_source": groundwater.source,
    }


def _missing_item(foundation_id: str, mark: str, support_id: str, *missing: str) -> dict[str, Any]:
    return {
        "foundation_id": foundation_id,
        "mark": mark,
        "support_id": support_id,
        "status": "not_calculated",
        "verification_status": "unverified",
        "missing_inputs": list(missing),
    }


def _shape_geometry(foundation: FoundationTypeDefinition) -> dict[str, float] | None:
    base_height_m = foundation.thickness_mm / 1000
    base_area = foundation.length_m * foundation.width_m
    upper_volume = 0.0
    upper_height = 0.0
    if foundation.form_id == "spread-stepped":
        if not foundation.steps:
            return None
        upper_volume = sum(
            item.length_m * item.width_m * item.height_mm / 1000
            for item in foundation.steps
        )
        upper_height = sum(item.height_mm for item in foundation.steps) / 1000
    elif foundation.form_id == "spread-tapered":
        if (
            foundation.tapered_top_length_m is None
            or foundation.tapered_top_width_m is None
            or foundation.tapered_height_mm is None
        ):
            return None
        top_area = foundation.tapered_top_length_m * foundation.tapered_top_width_m
        upper_height = foundation.tapered_height_mm / 1000
        upper_volume = upper_height / 3 * (
            base_area + top_area + (base_area * top_area) ** 0.5
        )
    elif foundation.form_id != "spread-prismatic":
        return None
    return {
        "concrete_volume_m3": base_area * base_height_m + upper_volume,
        "total_height_m": base_height_m + upper_height,
        "upper_volume_m3": upper_volume,
    }


def calculate_scene_foundations(
    geometry: SceneGeometryProfile,
    support_reactions: dict[str, dict[str, float]],
    geotechnical: ProjectGeotechnicalProfile | None,
    *,
    project_name: str,
) -> list[dict[str, Any]]:
    """Run the existing spread-footing core from saved model reactions.

    Step and taper geometry contributes its real concrete volume and height.
    The current component core still checks the bottom slab section and records
    the upper-shape punching/anchorage scope as pending. All results remain
    unverified scheme checks.
    """

    foundation_types = {item.id: item for item in geometry.foundation_types}
    supports = {item.id: item for item in geometry.supports}
    bases_by_support = {item.support_id: item for item in geometry.column_bases}
    items: list[dict[str, Any]] = []
    for foundation in geometry.foundation_instances:
        foundation_type = foundation_types[foundation.foundation_type_id]
        support = supports[foundation.support_id]
        if geotechnical is None:
            items.append(_missing_item(foundation.id, foundation.mark, support.id, "project_geotechnical_profile"))
            continue
        reaction = support_reactions.get(support.node_id)
        if reaction is None:
            items.append(_missing_item(foundation.id, foundation.mark, support.id, "support_reaction"))
            continue
        shape = _shape_geometry(foundation_type)
        if shape is None:
            items.append(_missing_item(
                foundation.id,
                foundation.mark,
                support.id,
                "complete_step_or_taper_geometry",
            ))
            continue
        if foundation_type.cover_mm is None:
            items.append(_missing_item(foundation.id, foundation.mark, support.id, "foundation_cover_mm"))
            continue
        rebar_x = _parse_rebar(foundation_type.bottom_x)
        rebar_y = _parse_rebar(foundation_type.bottom_y)
        if rebar_x is None or rebar_y is None:
            items.append(_missing_item(foundation.id, foundation.mark, support.id, "parseable_bottom_x_y_rebar"))
            continue
        column_base = bases_by_support.get(support.id)
        pedestal = foundation_type.pedestal
        if not (pedestal and pedestal.enabled) and column_base is None:
            items.append(_missing_item(foundation.id, foundation.mark, support.id, "column_base_or_pedestal_geometry"))
            continue
        loaded_length = (
            float(pedestal.length_mm)
            if pedestal and pedestal.enabled
            else float(column_base.base_plate_length_mm)  # type: ignore[union-attr]
        )
        loaded_width = (
            float(pedestal.width_mm)
            if pedestal and pedestal.enabled
            else float(column_base.base_plate_width_mm)  # type: ignore[union-attr]
        )
        base_height_m = foundation_type.thickness_mm / 1000
        soil_cover_depth = max(foundation_type.embedment_m - base_height_m, 0.0)
        soil_above_upper_shape_depth = max(
            foundation_type.embedment_m - shape["total_height_m"],
            0.0,
        )
        pedestal_volume_in_cover = 0.0
        if pedestal and pedestal.enabled:
            pedestal_volume_in_cover = (
                float(pedestal.length_mm) / 1000
                * float(pedestal.width_mm) / 1000
                * min(float(pedestal.clear_height_mm) / 1000, soil_above_upper_shape_depth)
            )
        soil_cover_volume = max(
            foundation_type.length_m * foundation_type.width_m * soil_cover_depth
            - shape["upper_volume_m3"]
            - pedestal_volume_in_cover,
            0.0,
        )
        inputs: dict[str, Any] = {
            "explicit_design_profile": True,
            "length_m": foundation_type.length_m,
            "width_m": foundation_type.width_m,
            "thickness_mm": foundation_type.thickness_mm,
            "column_x_mm": loaded_length,
            "column_y_mm": loaded_width,
            "embedment_m": foundation_type.embedment_m,
            "soil_cover_m": soil_cover_depth,
            "footing_concrete_volume_m3": shape["concrete_volume_m3"],
            "soil_cover_volume_m3": soil_cover_volume,
            "total_foundation_height_m": shape["total_height_m"],
            "concrete_grade": foundation_type.concrete_grade,
            "rebar_grade": foundation_type.rebar_grade,
            "cover_mm": foundation_type.cover_mm,
            "bar_dia_x_mm": rebar_x[0],
            "bar_spacing_x_mm": rebar_x[1],
            "bar_dia_y_mm": rebar_y[0],
            "bar_spacing_y_mm": rebar_y[1],
            "soil_capacity_kpa": geotechnical.bearing_capacity_kpa,
            "soil_source": geotechnical.bearing_capacity_source,
            "base_friction_coefficient": 0.30,
            "upstream_reaction_envelopes": scene_reaction_envelopes(reaction),
            **_groundwater_inputs(geotechnical),
        }
        if pedestal and pedestal.enabled:
            inputs.update({
                "pedestal_enabled": True,
                "pedestal_length_mm": pedestal.length_mm,
                "pedestal_width_mm": pedestal.width_mm,
                "pedestal_height_mm": pedestal.clear_height_mm,
            })
        result = calculate(CalculationRequest(
            mode=CalculationMode.QUICK,
            module=CalculationModule.SPREAD_FOOTING,
            project_name=f"{project_name} · {foundation.mark}",
            standard_profile="CN-2026.7",
            inputs=inputs,
            loads=[],
        ))
        failed_checks = [item.name for item in result.checks if not item.passed]
        items.append({
            "foundation_id": foundation.id,
            "mark": foundation.mark,
            "support_id": support.id,
            "support_node_id": support.node_id,
            "status": "failed" if failed_checks else "incomplete",
            "verification_status": "unverified",
            "calculation_trace_id": result.trace_id,
            "checks": [item.model_dump(mode="json") for item in result.checks],
            "steps": [item.model_dump(mode="json") for item in result.steps],
            "reactions": {key: value.model_dump(mode="json") for key, value in result.reactions.items()},
            "warnings": [item.model_dump(mode="json") for item in result.warnings],
            "failed_checks": failed_checks,
            "shape_geometry": {
                "form_id": foundation_type.form_id,
                **shape,
                "soil_cover_volume_m3": soil_cover_volume,
            },
            "pending_checks": [
                "沉降计算",
                "基础构造锚固",
                *(
                    ["阶形/锥形上部截面冲切与局部构造"]
                    if foundation_type.form_id != "spread-prismatic"
                    else []
                ),
            ],
            "analysis_assumption": "采用已保存的设计组合包络；基础适配器不再二次统一放大反力。",
        })
    return items
