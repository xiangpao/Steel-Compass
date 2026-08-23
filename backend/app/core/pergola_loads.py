from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .design_profiles import (
    DesignLoadCombination,
    ROOF_ASSEMBLIES,
    RoofLoadSelectionProfile,
    SceneGeometryProfile,
)
from .errors import CalculationInputError
from .load_environment import LoadCase, generate_action_combinations
from .scene_schemas import SceneLoadItem
from .seismic import build_screening_seismic_package
from .site_profile import ProjectSiteProfile


LOAD_CATALOG_VERSION = "pergola-loads-CN-2026.7-unverified"


@dataclass(frozen=True)
class PergolaLoadPackage:
    cases: tuple[SceneLoadItem, ...]
    combinations: tuple[DesignLoadCombination, ...]
    assumptions: tuple[str, ...]
    missing_inputs: tuple[str, ...]


def _height_factor(profile: ProjectSiteProfile, geometry: SceneGeometryProfile) -> float:
    if profile.height_factor_override is not None:
        return profile.height_factor_override
    height = max(node.z_m for node in geometry.nodes)
    terrain_base = {"A": 1.28, "B": 1.00, "C": 0.74, "D": 0.62}[profile.terrain_category]
    height_adjustment = max(0.8, min(1.55, 0.8 + 0.04 * max(height, 0.0)))
    return round(terrain_base * height_adjustment, 4)


def _scene_item(
    *,
    case_id: str,
    label: str,
    kind: str,
    value: float,
    direction: str,
    source: str,
) -> SceneLoadItem:
    return SceneLoadItem(
        id=case_id,
        label=label,
        kind=kind,
        value_type="calculated",
        adopted_value=round(max(value, 0.0), 6),
        unit="kPa",
        source_reference=source,
        applicable_when="亭廊 Geometry 2.3 屋面分区",
        distribution="pressure",
        direction=direction,
        application_target="roof_load_zones",
        notes=f"目录版本 {LOAD_CATALOG_VERSION}",
    )


def _combination_cases(cases: list[SceneLoadItem]) -> list[LoadCase]:
    result: list[LoadCase] = []
    for case in cases:
        category = {
            "self_weight": "permanent",
            "dead": "permanent",
            "live": "live",
            "wind": "wind",
            "snow": "snow",
            "seismic": "seismic",
        }.get(case.kind)
        if category is None:
            continue
        direction = case.direction
        if direction in {"down", "gravity"}:
            direction = "gravity"
        elif direction in {"up", "uplift"}:
            direction = "uplift"
        result.append(
            LoadCase(
                id=case.id,
                label=case.label,
                category=category,  # type: ignore[arg-type]
                characteristic_value=float(case.adopted_value or 0.0),
                unit="kPa",
                direction=direction,  # type: ignore[arg-type]
                target="roof_load_zones",
                source_reference=case.source_reference,
                exclusive_group=(
                    "wind-x" if direction in {"x_positive", "x_negative"}
                    else "wind-y" if direction in {"y_positive", "y_negative"}
                    else "wind-vertical" if case.kind == "wind" and direction in {"gravity", "uplift"}
                    else "seismic-x" if case.kind == "seismic" and direction in {"x_positive", "x_negative"}
                    else "seismic-y" if case.kind == "seismic" and direction in {"y_positive", "y_negative"}
                    else None
                ),
            )
        )
    return result


def build_pergola_load_package(
    geometry: SceneGeometryProfile,
    site_profile: ProjectSiteProfile | None,
    roof_selection: RoofLoadSelectionProfile | None,
) -> PergolaLoadPackage:
    missing: list[str] = []
    assumptions: list[str] = []
    if geometry.profile_version != "2.3":
        missing.append("请先将亭廊模型另存为 Geometry 2.3")
    if site_profile is None:
        missing.append("项目条件")
    if roof_selection is None:
        missing.append("屋面构造与使用类别")
    if missing:
        return PergolaLoadPackage((), (), (), tuple(missing))

    roof = next((item for item in ROOF_ASSEMBLIES if item.id == roof_selection.roof_assembly_id), None)
    if roof is None:
        raise CalculationInputError("unknown_roof_assembly", "屋面构造目录中不存在所选项目", field="roof_load_selection")

    assert site_profile is not None
    assert roof_selection is not None
    required = ["wind", "seismic"]
    if roof.cover_type != "none":
        required.append("snow")
    missing_conditions = [item for item in required if not site_profile.is_condition_complete(item)]
    if missing_conditions:
        return PergolaLoadPackage((), (), (), tuple(f"项目条件未完成：{item}" for item in missing_conditions))

    cases: list[SceneLoadItem] = [
        _scene_item(
            case_id="SELF-WEIGHT",
            label="钢构件自重",
            kind="self_weight",
            value=0.0,
            direction="gravity",
            source="由各杆件最终截面面积、材料密度和实际长度自动计算",
        )
    ]
    if roof.cover_type != "none":
        cases.append(_scene_item(
            case_id="ROOF-DEAD",
            label="屋面构造恒载",
            kind="dead",
            value=roof.total_dead_load_kn_m2,
            direction="gravity",
            source=roof.source_reference,
        ))
        maintenance = (
            0.5
            if roof_selection.maintenance_category == "maintenance"
            and roof_selection.maintenance_load_kn_m2 is None
            else float(roof_selection.maintenance_load_kn_m2 or 0.0)
        )
        if roof_selection.maintenance_category != "not_applicable":
            cases.append(_scene_item(
                case_id="ROOF-LIVE",
                label="屋面检修或使用荷载",
                kind="live",
                value=maintenance,
                direction="gravity",
                source="GB 50009-2012；使用类别由项目选择",
            ))
        snow_shape = site_profile.snow_shape_factor_override or 1.0
        cases.append(_scene_item(
            case_id="ROOF-SNOW",
            label="屋面雪荷载",
            kind="snow",
            value=float(site_profile.basic_snow_pressure_kpa or 0.0) * snow_shape,
            direction="gravity",
            source=site_profile.climate_source_reference or "项目条件",
        ))
    else:
        assumptions.append("无顶部覆盖：不生成屋面构造恒载、检修荷载和屋面雪荷载")

    height_factor = _height_factor(site_profile, geometry)
    pressure_shape = site_profile.wind_shape_factor_override or 0.8
    suction_shape = site_profile.wind_shape_factor_override or 1.0
    base_wind = float(site_profile.basic_wind_pressure_kpa or 0.0) * height_factor
    for case_id, label, direction, factor in (
        ("WIND-X+", "+X向风", "x_positive", pressure_shape),
        ("WIND-X-", "-X向风", "x_negative", pressure_shape),
        ("WIND-Y+", "+Y向风", "y_positive", pressure_shape),
        ("WIND-Y-", "-Y向风", "y_negative", pressure_shape),
        ("WIND-DOWN", "屋面向下风压力", "gravity", pressure_shape),
        ("WIND-UP", "屋面风吸力/上拔", "uplift", suction_shape),
    ):
        cases.append(_scene_item(
            case_id=case_id,
            label=label,
            kind="wind",
            value=base_wind * factor,
            direction=direction,
            source=site_profile.climate_source_reference or "项目条件",
        ))

    area = 0.0
    node_by_id = {node.id: node for node in geometry.nodes}
    for surface in geometry.roof_surfaces:
        points = [node_by_id[node_id] for node_id in surface.node_ids]
        for index in range(1, len(points) - 1):
            a, b, c = points[0], points[index], points[index + 1]
            ab = (b.x_m - a.x_m, b.y_m - a.y_m, b.z_m - a.z_m)
            ac = (c.x_m - a.x_m, c.y_m - a.y_m, c.z_m - a.z_m)
            cross = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            area += sqrt(sum(value * value for value in cross)) / 2
    gravity_pressure = sum(float(case.adopted_value or 0) for case in cases if case.kind in {"dead", "live", "snow"})
    seismic = build_screening_seismic_package(site_profile, gravity_pressure * area)
    equivalent_pressure = seismic.f_ek_kn / area if area > 0 else 0.0
    for action in seismic.actions:
        cases.append(_scene_item(
            case_id=action.id,
            label=f"{action.direction}等效地震作用",
            kind="seismic",
            value=equivalent_pressure,
            direction=action.direction,
            source=seismic.source_reference,
        ))

    generated = generate_action_combinations(_combination_cases(cases))
    combinations = tuple(
        DesignLoadCombination(
            id=item.id,
            title=item.id,
            design_situation=item.design_situation,
            factors={action.case_id: action.factor for action in item.actions},
            source_reference="GB 50009-2012；GB 55002-2021；GB/T 50011-2010（2024年版）",
        )
        for item in generated.combinations
    )
    assumptions.append(
        f"风荷载：基本风压×高度系数{height_factor:g}×体型系数；高级覆盖必须记录原因"
    )
    return PergolaLoadPackage(tuple(cases), combinations, tuple(assumptions), ())
