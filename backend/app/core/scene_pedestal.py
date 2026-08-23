from __future__ import annotations

from math import hypot, pi, sqrt
from typing import Any

from .concrete import CONCRETE, REBAR
from .design_profiles import FoundationTypeDefinition, SceneGeometryProfile
from .scene_foundation import scene_reaction_envelopes
from .schemas import CalculationStep, CheckResult, Quantity


def _missing(
    foundation_id: str,
    mark: str,
    support_id: str,
    code: str,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "foundation_id": foundation_id,
        "mark": mark,
        "support_id": support_id,
        "status": "not_calculated",
        "verification_status": "unverified",
        "issue_code": code,
        "missing_inputs": missing or [],
    }


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    reference: str,
    note: str | None = None,
) -> CheckResult:
    utilization = demand / max(capacity, 1e-9)
    return CheckResult(
        name=name,
        demand=Quantity(value=max(demand, 0.0), unit=unit),
        capacity=Quantity(value=max(capacity, 0.0), unit=unit),
        utilization=max(utilization, 0.0),
        passed=demand <= capacity,
        reference=reference,
        note=note,
    )


def _pedestal_check(
    foundation_id: str,
    mark: str,
    support_id: str,
    support_node_id: str,
    foundation_type: FoundationTypeDefinition,
    reaction: dict[str, float],
) -> dict[str, Any]:
    pedestal = foundation_type.pedestal
    assert pedestal is not None and pedestal.enabled
    concrete = CONCRETE.get(str(pedestal.concrete_grade))
    rebar = REBAR.get(foundation_type.rebar_grade)
    if concrete is None:
        return _missing(foundation_id, mark, support_id, "unsupported_pedestal_concrete_grade")
    if rebar is None:
        return _missing(foundation_id, mark, support_id, "unsupported_pedestal_rebar_grade")

    required = {
        "length_mm": pedestal.length_mm,
        "width_mm": pedestal.width_mm,
        "clear_height_mm": pedestal.clear_height_mm,
        "cover_mm": pedestal.cover_mm,
        "longitudinal_bar_count_x": pedestal.longitudinal_bar_count_x,
        "longitudinal_bar_count_y": pedestal.longitudinal_bar_count_y,
        "longitudinal_bar_diameter_mm": pedestal.longitudinal_bar_diameter_mm,
        "stirrup_diameter_mm": pedestal.stirrup_diameter_mm,
        "stirrup_spacing_mm": pedestal.stirrup_spacing_mm,
        "dowel_anchorage_mm": pedestal.dowel_anchorage_mm,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        return _missing(foundation_id, mark, support_id, "incomplete_pedestal_profile", missing)

    length = float(pedestal.length_mm)
    width = float(pedestal.width_mm)
    height_m = float(pedestal.clear_height_mm) / 1000
    cover = float(pedestal.cover_mm)
    long_diameter = float(pedestal.longitudinal_bar_diameter_mm)
    stirrup_diameter = float(pedestal.stirrup_diameter_mm)
    stirrup_spacing = float(pedestal.stirrup_spacing_mm)
    bar_count = 2 * (
        int(pedestal.longitudinal_bar_count_x)
        + int(pedestal.longitudinal_bar_count_y)
    )
    longitudinal_area = bar_count * pi * long_diameter**2 / 4
    gross_area = length * width
    reinforcement_ratio = longitudinal_area / gross_area
    radius = min(length, width) / sqrt(12)
    slenderness = height_m * 1000 / radius
    stability_factor = max(0.65, min(1.0, 1.0 - max(slenderness - 20, 0) / 300))
    compression_capacity = 0.9 * stability_factor * (
        concrete["fc"] * max(gross_area - longitudinal_area, 0)
        + rebar["fy"] * longitudinal_area
    ) / 1000
    tension_capacity = 0.8 * rebar["fy"] * longitudinal_area / 1000
    moment_capacity_x = 0.8 * rebar["fy"] * longitudinal_area * 0.4 * width / 1e6
    moment_capacity_y = 0.8 * rebar["fy"] * longitudinal_area * 0.4 * length / 1e6
    effective_depth_x = length - cover - stirrup_diameter - long_diameter / 2
    effective_depth_y = width - cover - stirrup_diameter - long_diameter / 2
    if min(effective_depth_x, effective_depth_y) <= 0:
        return _missing(foundation_id, mark, support_id, "invalid_pedestal_effective_depth")
    stirrup_area_two_legs = 2 * pi * stirrup_diameter**2 / 4
    shear_capacity_x = (
        0.7 * concrete["ft"] * width * effective_depth_x
        + rebar["fyv"] * stirrup_area_two_legs * effective_depth_x / stirrup_spacing
    ) / 1000
    shear_capacity_y = (
        0.7 * concrete["ft"] * length * effective_depth_y
        + rebar["fyv"] * stirrup_area_two_legs * effective_depth_y / stirrup_spacing
    ) / 1000
    self_weight_sls = length / 1000 * width / 1000 * height_m * 25.0

    envelopes = scene_reaction_envelopes(reaction)
    uls_envelopes = [item for item in envelopes if item["limit_state"] == "ULS"]
    demands: list[dict[str, float | str]] = []
    for envelope in uls_envelopes:
        components = envelope["components"]
        axial = float(components["N"]["value"])
        shear_x_case = abs(float(components["Vx"]["value"]))
        shear_y_case = abs(float(components["Vy"]["value"]))
        moment_x_case = abs(float(components["Mx"]["value"]) + float(components["Vy"]["value"]) * height_m)
        moment_y_case = abs(float(components["My"]["value"]) + float(components["Vx"]["value"]) * height_m)
        compression_case = max(axial + 1.3 * self_weight_sls, 0.0)
        tension_case = max(-axial - 0.9 * self_weight_sls, 0.0)
        demands.append({
            "combination_id": str(envelope["combination_id"]),
            "compression": compression_case,
            "tension": tension_case,
            "shear_x": shear_x_case,
            "shear_y": shear_y_case,
            "moment_x": moment_x_case,
            "moment_y": moment_y_case,
            "interaction": compression_case / max(compression_capacity, 1e-9)
            + hypot(moment_x_case / max(moment_capacity_x, 1e-9), moment_y_case / max(moment_capacity_y, 1e-9)),
        })
    if not demands:
        return _missing(foundation_id, mark, support_id, "missing_uls_reaction_combination")
    compression = max(float(item["compression"]) for item in demands)
    tension = max(float(item["tension"]) for item in demands)
    shear_x = max(float(item["shear_x"]) for item in demands)
    shear_y = max(float(item["shear_y"]) for item in demands)
    controlling = max(demands, key=lambda item: float(item["interaction"]))
    moment_x = float(controlling["moment_x"])
    moment_y = float(controlling["moment_y"])
    biaxial_interaction = float(controlling["interaction"])
    maximum_stirrup_spacing = min(400.0, 15 * long_diameter, min(length, width))
    minimum_anchorage = 35 * long_diameter

    checks = [
        _check("短柱轴压承载力", compression, compression_capacity, "kN", "GB/T 50010-2010 轴心受压构件（方案级Beta映射）"),
        _check("短柱上拔纵筋承载力", tension, tension_capacity, "kN", "GB/T 50010-2010 钢筋受拉承载力（方案级Beta映射）"),
        _check("短柱双向偏压相互作用", biaxial_interaction, 1.0, "1", "GB/T 50010-2010 偏心受压构件（保守简化Beta相互作用）", "同时计入 Mx、My 及水平力经短柱净高形成的附加弯矩。"),
        _check("短柱X向受剪", shear_x, shear_capacity_x, "kN", "GB/T 50010-2010 斜截面受剪（方案级Beta映射）"),
        _check("短柱Y向受剪", shear_y, shear_capacity_y, "kN", "GB/T 50010-2010 斜截面受剪（方案级Beta映射）"),
        _check("短柱最小纵筋率", 0.005, reinforcement_ratio, "1", "GB/T 50010-2010 柱纵向钢筋构造", "同时要求总配筋率不大于5%。"),
        _check("短柱最大纵筋率", reinforcement_ratio, 0.05, "1", "GB/T 50010-2010 柱纵向钢筋构造"),
        _check("短柱箍筋间距", stirrup_spacing, maximum_stirrup_spacing, "mm", "GB/T 50010-2010 柱箍筋构造（方案级筛查）"),
        _check("短柱插筋锚固长度", minimum_anchorage, float(pedestal.dowel_anchorage_mm), "mm", "GB/T 50010-2010 受拉钢筋锚固（35d方案筛查）", "工程校核须按混凝土、钢筋、受力状态和抗震等级计算实际锚固长度。"),
    ]
    failed_checks = [item.name for item in checks if not item.passed]
    return {
        "foundation_id": foundation_id,
        "mark": mark,
        "support_id": support_id,
        "support_node_id": support_node_id,
        "status": "failed" if failed_checks else "incomplete",
        "verification_status": "unverified",
        "checks": [item.model_dump(mode="json") for item in checks],
        "failed_checks": failed_checks,
        "steps": [
            CalculationStep(
                name="短柱根部双向弯矩",
                equation="Mx,root=Mx+Vy·h; My,root=My+Vx·h",
                substitution=f"h={height_m:.3f}m, Mx={moment_x:.3f}kN·m, My={moment_y:.3f}kN·m",
                result=Quantity(value=hypot(moment_x, moment_y), unit="kN·m"),
                reference="柱脚至基础顶传力平衡",
            ).model_dump(mode="json"),
            CalculationStep(
                name="短柱自重",
                equation="G=b·h·L·25",
                substitution=f"{length/1000:.3f}×{width/1000:.3f}×{height_m:.3f}×25",
                result=Quantity(value=self_weight_sls, unit="kN"),
                reference="钢筋混凝土方案容重 25kN/m³",
            ).model_dump(mode="json"),
        ],
        "reaction_envelopes": envelopes,
        "controlling_combinations": {
            "biaxial_interaction": controlling["combination_id"],
            "compression": max(demands, key=lambda item: float(item["compression"]))["combination_id"],
            "uplift": max(demands, key=lambda item: float(item["tension"]))["combination_id"],
            "shear_x": max(demands, key=lambda item: float(item["shear_x"]))["combination_id"],
            "shear_y": max(demands, key=lambda item: float(item["shear_y"]))["combination_id"],
        },
        "input_summary": {
            "section_mm": f"{length:g}×{width:g}",
            "clear_height_mm": height_m * 1000,
            "concrete_grade": pedestal.concrete_grade,
            "rebar_grade": foundation_type.rebar_grade,
            "longitudinal_bars": f"{bar_count}Φ{long_diameter:g}",
            "stirrups": f"Φ{stirrup_diameter:g}@{stirrup_spacing:g}",
            "self_weight_kn": self_weight_sls,
        },
        "pending_checks": ["短柱裂缝控制", "柱脚局部承压区配筋", "抗震节点区与锚固构造", "独立基准验证"],
        "analysis_assumption": "采用已保存的设计组合包络；短柱自重按持久作用另计，反力不再二次统一放大。",
    }


def calculate_scene_pedestals(
    geometry: SceneGeometryProfile,
    support_reactions: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    foundation_types = {item.id: item for item in geometry.foundation_types}
    supports = {item.id: item for item in geometry.supports}
    items: list[dict[str, Any]] = []
    for foundation in geometry.foundation_instances:
        foundation_type = foundation_types[foundation.foundation_type_id]
        pedestal = foundation_type.pedestal
        if pedestal is None or not pedestal.enabled:
            continue
        support = supports[foundation.support_id]
        reaction = support_reactions.get(support.node_id)
        if reaction is None:
            items.append(_missing(foundation.id, foundation.mark, support.id, "missing_support_reaction", ["support_reaction"]))
            continue
        items.append(_pedestal_check(
            foundation.id,
            foundation.mark,
            support.id,
            support.node_id,
            foundation_type,
            reaction,
        ))
    return items
