from __future__ import annotations

import re
from typing import Any

from .concrete import CONCRETE
from .contact import solve_rectangular_contact
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


def _case_component(case: dict[str, Any], name: str) -> float:
    return float(case["components"].get(name, {}).get("value", 0.0))


def _settlement_check(
    foundation: FoundationTypeDefinition,
    geotechnical: ProjectGeotechnicalProfile,
    reaction: dict[str, float],
) -> dict[str, Any] | None:
    """Layered 2:1 stress-spread estimate using explicit investigation data.

    This is intentionally traceable and conservative for the scheme workflow;
    it is not presented as an independently verified code implementation.
    """
    if not geotechnical.settlement_layers:
        return None
    factor = geotechnical.settlement_correction_factor
    limit = geotechnical.settlement_limit_mm
    if factor is None or limit is None:
        return None
    sls = [item for item in scene_reaction_envelopes(reaction) if item["limit_state"] == "SLS"]
    if not sls:
        return None
    area = foundation.length_m * foundation.width_m
    controlling = max(sls, key=lambda item: max(_case_component(item, "N"), 0.0))
    base_pressure = max(_case_component(controlling, "N"), 0.0) / area
    first_gamma = geotechnical.settlement_layers[0].unit_weight_kn_m3
    net_pressure = max(base_pressure - first_gamma * foundation.embedment_m, 0.0)
    depth = 0.0
    increments: list[dict[str, Any]] = []
    total = 0.0
    for layer in geotechnical.settlement_layers:
        midpoint = depth + layer.thickness_m / 2
        influence = (
            foundation.length_m * foundation.width_m
            / ((foundation.length_m + midpoint) * (foundation.width_m + midpoint))
        )
        stress = net_pressure * influence
        increment = stress * layer.thickness_m / (layer.compression_modulus_mpa * 1000) * 1000
        total += increment
        increments.append({
            "layer_id": layer.id,
            "layer_name": layer.name,
            "mid_depth_m": midpoint,
            "influence_factor": influence,
            "additional_stress_kpa": stress,
            "compression_modulus_mpa": layer.compression_modulus_mpa,
            "increment_mm": increment,
            "source": layer.source,
        })
        depth += layer.thickness_m
    corrected = total * factor
    return {
        "name": "地基沉降分层总和法（2:1应力扩散）",
        "status": "passed" if corrected <= limit else "failed",
        "demand": {"value": corrected, "unit": "mm"},
        "capacity": {"value": limit, "unit": "mm"},
        "utilization": corrected / limit,
        "passed": corrected <= limit,
        "reference": "GB 50007-2011 分层总和法工作流；2:1应力扩散为当前透明方案模型",
        "note": "采用勘察录入土层逐层积分；邻基影响、应力历史及复杂地层有限元尚未计入。",
        "combination_id": controlling["combination_id"],
        "base_pressure_kpa": base_pressure,
        "net_pressure_kpa": net_pressure,
        "correction_factor": factor,
        "layers": increments,
        "verification_status": "unverified",
    }


def _nonprismatic_checks(
    foundation: FoundationTypeDefinition,
    loaded_length_mm: float,
    loaded_width_mm: float,
    reaction: dict[str, float],
    contact_solutions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check every step/taper transition instead of replacing it by one slab."""
    if foundation.form_id == "spread-prismatic":
        return []
    concrete = CONCRETE.get(foundation.concrete_grade)
    if concrete is None or foundation.cover_mm is None:
        return []
    uls = [item for item in contact_solutions if item["limit_state"] == "ULS"]
    if not uls or any(item["status"] != "solved" for item in uls):
        return []
    area = foundation.length_m * foundation.width_m
    ft = concrete["ft"]
    levels: list[tuple[str, float, float, float]] = []
    if foundation.form_id == "spread-stepped":
        cumulative_height = foundation.thickness_mm
        for index, step in enumerate(foundation.steps, start=1):
            cumulative_height += step.height_mm
            levels.append((f"第{index}阶根部", step.length_m, step.width_m, cumulative_height))
    elif (
        foundation.tapered_top_length_m is not None
        and foundation.tapered_top_width_m is not None
        and foundation.tapered_height_mm is not None
    ):
        levels.extend([
            ("锥台顶根部", foundation.tapered_top_length_m, foundation.tapered_top_width_m, foundation.thickness_mm + foundation.tapered_height_mm),
            ("锥面与底板交界", max(foundation.tapered_top_length_m, loaded_length_mm / 1000), max(foundation.tapered_top_width_m, loaded_width_mm / 1000), foundation.thickness_mm),
        ])
    results: list[dict[str, Any]] = []
    for label, upper_l, upper_b, total_depth_mm in levels:
        d_mm = total_depth_mm - foundation.cover_mm - 8.0
        if d_mm <= 0:
            continue
        governing: dict[str, Any] | None = None
        for case in uls:
            n, mx, my = case["resultants_n_mx_my"]
            solution = solve_rectangular_contact(foundation.length_m, foundation.width_m, n, mx, my)
            q = solution.qmax_kpa
            px, py = (upper_l+d_mm/1000)/2, (upper_b+d_mm/1000)/2
            punching = max(n-solution.integrate((-px,px,-py,py))[0], 0.0)
            perimeter_mm = 2 * ((upper_l + d_mm / 1000) + (upper_b + d_mm / 1000)) * 1000
            punch_capacity = 0.7 * ft * perimeter_mm * d_mm / 1000
            xlo,xhi,ylo,yhi = -foundation.length_m/2, foundation.length_m/2, -foundation.width_m/2, foundation.width_m/2
            sx,sy = upper_l/2+d_mm/1000, upper_b/2+d_mm/1000
            shear_x = max(solution.integrate((sx,xhi,ylo,yhi))[0],solution.integrate((xlo,-sx,ylo,yhi))[0])
            shear_y = max(solution.integrate((xlo,xhi,sy,yhi))[0],solution.integrate((xlo,xhi,ylo,-sy))[0])
            cap_x = 0.7 * ft * foundation.width_m * 1000 * d_mm / 1000
            cap_y = 0.7 * ft * foundation.length_m * 1000 * d_mm / 1000
            utilization = max(punching / max(punch_capacity, 1e-9), shear_x / max(cap_x, 1e-9), shear_y / max(cap_y, 1e-9))
            if governing is None or utilization > governing["utilization"]:
                governing = {"combination_id": case["combination_name"], "pressure_kpa": q, "punching_kn": punching, "punch_capacity_kn": punch_capacity, "shear_x_kn": shear_x, "shear_x_capacity_kn": cap_x, "shear_y_kn": shear_y, "shear_y_capacity_kn": cap_y, "utilization": utilization}
        assert governing is not None
        results.append({
            "level": label,
            "upper_plan_m": {"length": upper_l, "width": upper_b},
            "effective_depth_mm": d_mm,
            "controlling_combination": governing["combination_id"],
            "checks": [
                {"name": f"{label}冲切", "demand": {"value": governing["punching_kn"], "unit": "kN"}, "capacity": {"value": governing["punch_capacity_kn"], "unit": "kN"}, "utilization": governing["punching_kn"] / max(governing["punch_capacity_kn"], 1e-9), "passed": governing["punching_kn"] <= governing["punch_capacity_kn"], "reference": "GB/T 50010-2010 冲切承载力；非棱柱基础转换截面方案映射"},
                {"name": f"{label}X向受剪", "demand": {"value": governing["shear_x_kn"], "unit": "kN"}, "capacity": {"value": governing["shear_x_capacity_kn"], "unit": "kN"}, "utilization": governing["shear_x_kn"] / max(governing["shear_x_capacity_kn"], 1e-9), "passed": governing["shear_x_kn"] <= governing["shear_x_capacity_kn"], "reference": "GB/T 50010-2010 斜截面受剪；非棱柱基础转换截面方案映射"},
                {"name": f"{label}Y向受剪", "demand": {"value": governing["shear_y_kn"], "unit": "kN"}, "capacity": {"value": governing["shear_y_capacity_kn"], "unit": "kN"}, "utilization": governing["shear_y_kn"] / max(governing["shear_y_capacity_kn"], 1e-9), "passed": governing["shear_y_kn"] <= governing["shear_y_capacity_kn"], "reference": "GB/T 50010-2010 斜截面受剪；非棱柱基础转换截面方案映射"},
            ],
            "verification_status": "unverified",
        })
    return results


def calculate_scene_foundations(
    geometry: SceneGeometryProfile,
    support_reactions: dict[str, dict[str, float]],
    geotechnical: ProjectGeotechnicalProfile | None,
    *,
    project_name: str,
) -> list[dict[str, Any]]:
    """Run bottom-slab, non-prismatic section and explicit settlement checks."""

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
        for axis in ("x", "y"):
            top_text = getattr(foundation_type, f"top_{axis}", None)
            if top_text:
                parsed_top = _parse_rebar(top_text)
                if parsed_top is not None:
                    inputs[f"top_bar_dia_{axis}_mm"] = parsed_top[0]
                    inputs[f"top_bar_spacing_{axis}_mm"] = parsed_top[1]
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
        settlement = _settlement_check(foundation_type, geotechnical, reaction)
        detailed_shape_checks = _nonprismatic_checks(
            foundation_type, loaded_length, loaded_width, reaction, result.contact_solutions
        )
        for level in detailed_shape_checks:
            failed_checks.extend(
                check["name"] for check in level["checks"] if not check["passed"]
            )
        if settlement is not None and not settlement["passed"]:
            failed_checks.append(settlement["name"])
        pending_checks = ["基础构造锚固"]
        if any(item.get("contact_area_m2", 0) < foundation_type.length_m * foundation_type.width_m * (1-1e-9)
               for item in result.contact_solutions):
            pending_checks.append("非均匀接触沉降")
            if any(requirement.get("missing_inputs") for record in result.contact_solutions
                   for requirement in record.get("top_reinforcement_requirements",{}).values()):
                pending_checks.append("脱开区向下荷载产生反向弯矩，需要明确顶筋")
        if settlement is None:
            pending_checks.append("沉降计算（需录入分层压缩参数与允许值）")
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
            "contact_solutions": result.contact_solutions,
            "reactions": {key: value.model_dump(mode="json") for key, value in result.reactions.items()},
            "warnings": [item.model_dump(mode="json") for item in result.warnings],
            "failed_checks": failed_checks,
            "shape_geometry": {
                "form_id": foundation_type.form_id,
                **shape,
                "soil_cover_volume_m3": soil_cover_volume,
            },
            "settlement_check": settlement,
            "detailed_shape_checks": detailed_shape_checks,
            "pending_checks": pending_checks,
            "analysis_assumption": "采用已保存的设计组合包络；基础适配器不再二次统一放大反力。",
        })
    return items
