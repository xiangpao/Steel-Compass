from __future__ import annotations

from math import atan2, cos, degrees, radians, sin, sqrt

import numpy as np
from shapely.geometry import Point, Polygon

from .design_profiles import (
    CustomSectionCreate,
    CustomSectionDefinition,
    STEEL_SECTIONS,
    SceneStructuralProfile,
    calculate_custom_section,
)
from .errors import CalculationInputError
from .analysis_engine_adapter import compare_with_pynite
from .scene_schemas import SceneLoadItem
from .space_frame import (
    SpaceFrameModel,
    SpaceMember,
    SpaceMemberUniformLoad,
    SpaceNodalLoad,
    SpaceNode,
    SpaceRestraint,
    analyze_space_frame,
    analyze_space_frame_stability,
)


def _catalog_properties() -> dict[str, CustomSectionDefinition]:
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
    return result


def _surface_area(profile: SceneStructuralProfile) -> float:
    if profile.geometry is None:
        return 0.0
    nodes = {
        item.id: np.array([item.x_m, item.y_m, item.z_m], dtype=float)
        for item in profile.geometry.nodes
    }
    area = 0.0
    for surface in profile.geometry.roof_surfaces:
        points = [nodes[item] for item in surface.node_ids]
        origin = points[0]
        for index in range(1, len(points) - 1):
            area += float(
                np.linalg.norm(
                    np.cross(points[index] - origin, points[index + 1] - origin)
                )
            ) / 2
    return area


def _point_in_plan_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= crossing_x:
                inside = not inside
        previous = current
    return inside


def _surface_tributary_areas(
    profile: SceneStructuralProfile,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], list[dict[str, object]], float]:
    """Clip roof zones into tributary strips and return member/node areas.

    A zone's transfer direction is treated as the supporting-member axis. The
    strip boundaries lie halfway between adjacent member centrelines and are
    clipped against the real zone polygon after subtracting roof openings.
    This preserves L/concave outlines and holes without averaging the whole
    surface merely by member length.
    """
    geometry = profile.geometry
    if geometry is None:
        return {}, {}, {}, [], 0.0
    node_by_id = {item.id: item for item in geometry.nodes}
    member_by_id = {item.id: item for item in geometry.members}
    openings_by_surface: dict[str, list[Polygon]] = {}
    for opening in geometry.roof_openings:
        polygon = Polygon(
            [(node_by_id[node_id].x_m, node_by_id[node_id].y_m) for node_id in opening.node_ids]
        )
        if not polygon.is_valid or polygon.area <= 1e-9:
            raise CalculationInputError(
                "invalid_roof_opening",
                f"屋面开洞 {opening.id} 未闭合、自交或面积为零",
                field="roof_openings",
            )
        openings_by_surface.setdefault(opening.surface_id, []).append(polygon)

    zones = list(geometry.roof_load_zones)
    if not zones:
        zones = [
            type("DerivedRoofZone", (), {
                "id": f"derived-{surface.id}",
                "surface_id": surface.id,
                "boundary_node_ids": surface.node_ids,
                "load_path_group_ids": surface.load_path_group_ids,
                "load_direction_deg": surface.load_direction_deg,
            })()
            for surface in geometry.roof_surfaces
        ]
    surfaces = {item.id: item for item in geometry.roof_surfaces}
    member_area: dict[str, float] = {}
    assignments: list[dict[str, object]] = []
    total_net_area = 0.0
    for zone in zones:
        boundary = [
            (node_by_id[node_id].x_m, node_by_id[node_id].y_m)
            for node_id in zone.boundary_node_ids
        ]
        zone_polygon = Polygon(boundary)
        if not zone_polygon.is_valid or zone_polygon.area <= 1e-9:
            raise CalculationInputError(
                "invalid_roof_load_zone",
                f"屋面荷载区 {zone.id} 未闭合、自交或面积为零",
                field="roof_load_zones",
            )
        for opening_polygon in openings_by_surface.get(zone.surface_id, []):
            zone_polygon = zone_polygon.difference(opening_polygon)
        if zone_polygon.is_empty:
            continue

        surface = surfaces[zone.surface_id]
        surface_points = [
            np.array([node_by_id[node_id].x_m, node_by_id[node_id].y_m, node_by_id[node_id].z_m])
            for node_id in surface.node_ids
        ]
        surface_area = sum(
            float(np.linalg.norm(np.cross(surface_points[index] - surface_points[0], surface_points[index + 1] - surface_points[0]))) / 2
            for index in range(1, len(surface_points) - 1)
        )
        surface_plan_area = max(Polygon(
            [(point[0], point[1]) for point in surface_points]
        ).area, 1e-9)
        slope_factor = surface_area / surface_plan_area
        total_net_area += zone_polygon.area * slope_factor

        candidates = []
        target_angle = float(zone.load_direction_deg if zone.load_direction_deg is not None else surface.load_direction_deg or 0.0)
        for member in geometry.members:
            if member.role == "column" or member.group_id not in zone.load_path_group_ids:
                continue
            start = node_by_id[member.start_node_id]
            end = node_by_id[member.end_node_id]
            member_angle = degrees(atan2(end.y_m - start.y_m, end.x_m - start.x_m)) % 180
            target_axis = target_angle % 180
            angle_delta = abs(member_angle - target_axis)
            angle_delta = min(angle_delta, 180 - angle_delta)
            if angle_delta > 20:
                continue
            midpoint = ((start.x_m + end.x_m) / 2, (start.y_m + end.y_m) / 2)
            if not zone_polygon.buffer(1e-8).covers(Point(midpoint)):
                # Boundary members are retained below by endpoint membership.
                if member.start_node_id not in zone.boundary_node_ids or member.end_node_id not in zone.boundary_node_ids:
                    continue
            candidates.append(member)
        if not candidates:
            share = zone_polygon.area * slope_factor / len(zone.boundary_node_ids)
            for node_id in zone.boundary_node_ids:
                member_area[f"__node__{node_id}"] = member_area.get(f"__node__{node_id}", 0.0) + share
            continue

        angle = radians(target_angle)
        axis = np.array([cos(angle), sin(angle)])
        normal = np.array([-sin(angle), cos(angle)])
        coordinates: dict[float, list[object]] = {}
        for member in candidates:
            start = node_by_id[member.start_node_id]
            end = node_by_id[member.end_node_id]
            midpoint = np.array([(start.x_m + end.x_m) / 2, (start.y_m + end.y_m) / 2])
            coordinate = round(float(midpoint @ normal), 9)
            coordinates.setdefault(coordinate, []).append(member)
        ordered = sorted(coordinates)
        minx, miny, maxx, maxy = zone_polygon.bounds
        extent = max(maxx - minx, maxy - miny, 1.0) * 10
        for index, coordinate in enumerate(ordered):
            lower = (ordered[index - 1] + coordinate) / 2 if index else coordinate - extent
            upper = (coordinate + ordered[index + 1]) / 2 if index + 1 < len(ordered) else coordinate + extent
            center = axis * ((minx + maxx) * axis[0] / 2 + (miny + maxy) * axis[1] / 2)
            strip = Polygon([
                tuple(center - axis * extent + normal * lower),
                tuple(center + axis * extent + normal * lower),
                tuple(center + axis * extent + normal * upper),
                tuple(center - axis * extent + normal * upper),
            ])
            clipped_area = zone_polygon.intersection(strip).area * slope_factor
            same_line_members = coordinates[coordinate]
            line_total_length = sum(
                sqrt(
                    (node_by_id[item.start_node_id].x_m - node_by_id[item.end_node_id].x_m) ** 2
                    + (node_by_id[item.start_node_id].y_m - node_by_id[item.end_node_id].y_m) ** 2
                    + (node_by_id[item.start_node_id].z_m - node_by_id[item.end_node_id].z_m) ** 2
                )
                for item in same_line_members
            )
            for member in same_line_members:
                start = node_by_id[member.start_node_id]
                end = node_by_id[member.end_node_id]
                length = sqrt((start.x_m - end.x_m) ** 2 + (start.y_m - end.y_m) ** 2 + (start.z_m - end.z_m) ** 2)
                area = clipped_area * length / max(line_total_length, 1e-9)
                member_area[member.id] = member_area.get(member.id, 0.0) + area
                assignments.append({
                    "zone_id": zone.id,
                    "member_id": member.id,
                    "tributary_area_m2": round(area, 8),
                    "tributary_width_m": round(area / max(length, 1e-9), 8),
                    "transfer_direction_deg": target_angle,
                    "method": "midline tributary strips clipped by roof polygon and openings",
                })

    node_area = {item.id: 0.0 for item in geometry.nodes}
    direct_node_area = {item.id: 0.0 for item in geometry.nodes}
    distributed_member_area: dict[str, float] = {}
    for key, area in member_area.items():
        if key.startswith("__node__"):
            node_id = key.removeprefix("__node__")
            node_area[node_id] += area
            direct_node_area[node_id] += area
            continue
        member = member_by_id[key]
        distributed_member_area[key] = area
        node_area[member.start_node_id] += area / 2
        node_area[member.end_node_id] += area / 2
    return node_area, direct_node_area, distributed_member_area, assignments, total_net_area


def analyze_scene_space_frame(
    profile: SceneStructuralProfile,
    load_cases: list[SceneLoadItem],
    custom_sections: list[CustomSectionDefinition] | None = None,
    *,
    include_self_weight: bool = True,
    self_weight_factor: float = 1.0,
) -> dict[str, object]:
    geometry = profile.geometry
    if geometry is None:
        raise CalculationInputError(
            "missing_space_geometry", "参数化亭廊必须保存三维几何模型", field="geometry"
        )
    spring_supports = [item.id for item in geometry.supports if item.restraint == "spring"]
    if spring_supports:
        raise CalculationInputError(
            "unsupported_spring_support",
            f"弹簧支承尚未接入空间刚度矩阵：{', '.join(spring_supports)}",
            field="supports",
        )

    section_by_id = _catalog_properties()
    section_by_id.update({item.id: item for item in (custom_sections or [])})
    role_specs = {item.member_role: item for item in profile.members}
    group_specs = {item.group_id: item for item in profile.member_groups}
    member_overrides = {item.member_id: item for item in profile.member_overrides}
    members: list[SpaceMember] = []
    analysis_mapping: list[dict[str, str]] = []
    self_weights: dict[str, float] = {item.id: 0.0 for item in geometry.nodes}
    member_self_weights: dict[str, float] = {}
    wind_exposure_x: dict[str, float] = {item.id: 0.0 for item in geometry.nodes}
    wind_exposure_y: dict[str, float] = {item.id: 0.0 for item in geometry.nodes}
    node_by_id = {item.id: item for item in geometry.nodes}

    for member in geometry.members:
        role = "column" if member.role == "column" else "beam"
        specification = role_specs.get(role)
        override = member_overrides.get(member.id)
        group = group_specs.get(member.group_id)
        section_id = (
            override.section_id
            if override is not None
            else (group.custom_section_id or group.section_catalog_id)
            if group is not None
            else specification.section_catalog_id
            if specification is not None
            else None
        )
        if section_id is None:
            raise CalculationInputError(
                "missing_space_member_section",
                f"三维模型杆件 {member.id} 缺少构件组或单根截面",
                field="members",
            )
        section = section_by_id.get(section_id)
        if section is None:
            raise CalculationInputError(
                "unknown_section_catalog_entry",
                f"三维模型截面不存在：{section_id}",
                field="members",
            )
        analysis_mapping.append({
            "analysis_member_id": member.id,
            "source_member_id": member.id,
            "section_id": section_id,
            "assignment_scope": "member_override" if override is not None else "group",
        })
        members.append(
            SpaceMember(
                id=member.id,
                start=member.start_node_id,
                end=member.end_node_id,
                area_mm2=section.area_mm2,
                iy_mm4=section.iy_mm4,
                iz_mm4=section.iz_mm4,
                torsion_mm4=section.torsion_mm4,
                behavior=member.behavior,
                start_releases=(
                    tuple(bool(getattr(member.start_release, key)) for key in ("ux", "uy", "uz", "rx", "ry", "rz"))
                    if member.start_release is not None else (False,) * 6
                ),
                end_releases=(
                    tuple(bool(getattr(member.end_release_dofs, key)) for key in ("ux", "uy", "uz", "rx", "ry", "rz"))
                    if member.end_release_dofs is not None else (False,) * 6
                ),
                rigid_offset_start_m=member.rigid_offset.start_m if member.rigid_offset else 0.0,
                rigid_offset_end_m=member.rigid_offset.end_m if member.rigid_offset else 0.0,
                local_axis_rotation_deg=(
                    member.design_parameters.local_axis_rotation_deg
                    if member.design_parameters is not None else 0.0
                ),
            )
        )
        start = node_by_id[member.start_node_id]
        end = node_by_id[member.end_node_id]
        length = sqrt(
            (start.x_m - end.x_m) ** 2
            + (start.y_m - end.y_m) ** 2
            + (start.z_m - end.z_m) ** 2
        )
        half_weight = section.self_weight_kn_m * length / 2
        member_self_weights[member.id] = section.self_weight_kn_m
        self_weights[start.id] += half_weight
        self_weights[end.id] += half_weight
        dimensions = section.dimensions
        projected_width_m = max(
            float(dimensions.get("h_mm", 0.0)),
            float(dimensions.get("b_mm", 0.0)),
            float(dimensions.get("diameter_mm", 0.0)),
        ) / 1000
        if projected_width_m > 0:
            exposure_x = projected_width_m * sqrt(
                (start.y_m - end.y_m) ** 2 + (start.z_m - end.z_m) ** 2
            ) / 2
            exposure_y = projected_width_m * sqrt(
                (start.x_m - end.x_m) ** 2 + (start.z_m - end.z_m) ** 2
            ) / 2
            wind_exposure_x[start.id] += exposure_x
            wind_exposure_x[end.id] += exposure_x
            wind_exposure_y[start.id] += exposure_y
            wind_exposure_y[end.id] += exposure_y

    roof_nodes = sorted(
        {node_id for surface in geometry.roof_surfaces for node_id in surface.node_ids}
    )
    roof_area = _surface_area(profile)
    gravity_pressure = sum(
        item.adopted_value or 0
        for item in load_cases
        if item.unit in {"kN/m2", "kPa"}
        and item.kind in {"dead", "live", "snow"}
        and item.direction not in {"uplift", "up"}
    )
    uplift_pressure = max(
        [
            item.adopted_value or 0
            for item in load_cases
            if item.unit in {"kN/m2", "kPa"}
            and item.direction in {"uplift", "up"}
        ]
        or [0.0]
    )
    wind_pressure = {
        direction: sum(
            item.adopted_value or 0
            for item in load_cases
            if item.kind == "wind" and item.unit in {"kN/m2", "kPa"} and item.direction == direction
        )
        for direction in ("x_positive", "x_negative", "y_positive", "y_negative")
    }
    seismic_pressure = {
        direction: sum(
            item.adopted_value or 0
            for item in load_cases
            if item.kind == "seismic" and item.unit in {"kN/m2", "kPa"} and item.direction == direction
        )
        for direction in ("x_positive", "x_negative", "y_positive", "y_negative")
    }
    tributary_area, direct_node_area, member_tributary_area, load_assignments, net_roof_area = _surface_tributary_areas(profile)
    loads = [
        SpaceNodalLoad(
            node=node.id,
            fx_kn=(wind_pressure["x_positive"] - wind_pressure["x_negative"])
            * wind_exposure_x.get(node.id, 0.0)
            + (seismic_pressure["x_positive"] - seismic_pressure["x_negative"])
            * tributary_area.get(node.id, 0.0),
            fy_kn=(wind_pressure["y_positive"] - wind_pressure["y_negative"])
            * wind_exposure_y.get(node.id, 0.0)
            + (seismic_pressure["y_positive"] - seismic_pressure["y_negative"])
            * tributary_area.get(node.id, 0.0),
            fz_kn=(-gravity_pressure + uplift_pressure) * direct_node_area.get(node.id, 0.0),
        )
        for node in geometry.nodes
        if node.id in roof_nodes
        or (
            wind_exposure_x[node.id]
            and wind_pressure["x_positive"] != wind_pressure["x_negative"]
        )
        or (
            wind_exposure_y[node.id]
            and wind_pressure["y_positive"] != wind_pressure["y_negative"]
        )
    ]
    member_uniform_loads: list[SpaceMemberUniformLoad] = []
    for member in geometry.members:
        start = node_by_id[member.start_node_id]
        end = node_by_id[member.end_node_id]
        length = sqrt(
            (start.x_m - end.x_m) ** 2
            + (start.y_m - end.y_m) ** 2
            + (start.z_m - end.z_m) ** 2
        )
        qz = -(member_self_weights.get(member.id, 0.0) * self_weight_factor if include_self_weight else 0.0)
        qz += (-gravity_pressure + uplift_pressure) * member_tributary_area.get(member.id, 0.0) / max(length, 1e-9)
        if abs(qz) > 1e-12:
            member_uniform_loads.append(SpaceMemberUniformLoad(member=member.id, qz_kn_m=qz))
    support_by_node = (
        {item.node_id: item.restraint for item in geometry.supports}
        if geometry.profile_version in {"2.0", "2.1", "2.2", "2.3"}
        else {item.id: item.support for item in geometry.nodes if item.support != "none"}
    )
    restraints = [
        SpaceRestraint(
            node=node.id,
            ux=True,
            uy=True,
            uz=True,
            rx=support_by_node[node.id] == "fixed",
            ry=support_by_node[node.id] == "fixed",
            rz=support_by_node[node.id] == "fixed",
        )
        for node in geometry.nodes
        if node.id in support_by_node
    ]
    analysis_model = SpaceFrameModel(
            nodes=tuple(
                SpaceNode(item.id, item.x_m, item.y_m, item.z_m)
                for item in geometry.nodes
            ),
            members=tuple(members),
            restraints=tuple(restraints),
            nodal_loads=tuple(loads),
            member_uniform_loads=tuple(member_uniform_loads),
        )
    result = analyze_space_frame(analysis_model)
    stability = analyze_space_frame_stability(analysis_model, result)
    try:
        parallel_check = compare_with_pynite(analysis_model, result)
    except Exception as exc:  # PyNite remains an independent, unverified check path.
        parallel_check = {
            "solver": "PyNiteFEA-3.0.0",
            "verification_status": "unverified",
            "within_tolerance": False,
            "engineering_check_blocked": True,
            "error": str(exc),
        }
    try:
        parallel_second_order = compare_with_pynite(
            analysis_model, stability.second_order, second_order=True
        )
    except Exception as exc:
        parallel_second_order = {
            "solver": "PyNiteFEA-3.0.0",
            "analysis_type": "P-Delta",
            "verification_status": "unverified",
            "within_tolerance": False,
            "engineering_check_blocked": True,
            "error": str(exc),
        }
    if profile.stage == "project_check" and (
        parallel_check["engineering_check_blocked"]
        or parallel_second_order["engineering_check_blocked"]
    ):
        raise CalculationInputError(
            "analysis_engine_mismatch",
            "当前求解器与 PyNite 并行复核未通过，不能生成工程校核结论",
            field="geometry",
        )
    maximum_translation = max(
        sqrt(item.ux_mm**2 + item.uy_mm**2 + item.uz_mm**2)
        for item in result.displacements.values()
    )
    second_order_maximum = max(
        sqrt(item.ux_mm**2 + item.uy_mm**2 + item.uz_mm**2)
        for item in stability.second_order.displacements.values()
    )
    return {
        "solver": "steel-compass-space-frame-adapter-1.0",
        "verification_status": "unverified",
        "node_count": len(geometry.nodes),
        "member_count": len(geometry.members),
        "roof_area_m2": round(roof_area, 4),
        "net_loaded_roof_area_m2": round(net_roof_area, 4),
        "maximum_translation_mm": round(maximum_translation, 6),
        "second_order_maximum_translation_mm": round(second_order_maximum, 6),
        "second_order_amplification_ratio": round(stability.amplification_ratio, 6),
        "elastic_buckling_factors": [round(value, 6) for value in stability.buckling_factors],
        "stability_method": "first-order axial-force geometric stiffness / elastic eigen-buckling",
        "node_displacements": {
            node_id: {
                "ux_mm": item.ux_mm,
                "uy_mm": item.uy_mm,
                "uz_mm": item.uz_mm,
                "rx_rad": item.rx_rad,
                "ry_rad": item.ry_rad,
                "rz_rad": item.rz_rad,
            }
            for node_id, item in result.displacements.items()
        },
        "load_balance_kn": [round(value, 8) for value in result.load_balance_kn],
        "support_reactions": {
            node.id: {
                "fx_kn": result.reactions[node.id].fx_kn,
                "fy_kn": result.reactions[node.id].fy_kn,
                "fz_kn": result.reactions[node.id].fz_kn,
                "mx_kn_m": result.reactions[node.id].mx_kn_m,
                "my_kn_m": result.reactions[node.id].my_kn_m,
                "mz_kn_m": result.reactions[node.id].mz_kn_m,
            }
            for node in geometry.nodes
            if node.id in support_by_node
        },
        "member_end_forces": {
            member.id: {
                "start_node_id": member.start,
                "end_node_id": member.end,
                "start": {
                    "n_kn": result.members[member.id].local_end_forces[0] / 1000,
                    "vy_kn": result.members[member.id].local_end_forces[1] / 1000,
                    "vz_kn": result.members[member.id].local_end_forces[2] / 1000,
                    "t_kn_m": result.members[member.id].local_end_forces[3] / 1e6,
                    "my_kn_m": result.members[member.id].local_end_forces[4] / 1e6,
                    "mz_kn_m": result.members[member.id].local_end_forces[5] / 1e6,
                },
                "end": {
                    "n_kn": result.members[member.id].local_end_forces[6] / 1000,
                    "vy_kn": result.members[member.id].local_end_forces[7] / 1000,
                    "vz_kn": result.members[member.id].local_end_forces[8] / 1000,
                    "t_kn_m": result.members[member.id].local_end_forces[9] / 1e6,
                    "my_kn_m": result.members[member.id].local_end_forces[10] / 1e6,
                    "mz_kn_m": result.members[member.id].local_end_forces[11] / 1e6,
                },
                "force_basis": "member-local-axis",
                "uniform_load_local": {
                    "qx_kn_m": result.member_uniform_loads_local.get(member.id, (0.0, 0.0, 0.0))[0],
                    "qy_kn_m": result.member_uniform_loads_local.get(member.id, (0.0, 0.0, 0.0))[1],
                    "qz_kn_m": result.member_uniform_loads_local.get(member.id, (0.0, 0.0, 0.0))[2],
                },
                "verification_status": "unverified",
            }
            for member in members
        },
        "analysis_member_mapping": analysis_mapping,
        "parallel_analysis": parallel_check,
        "parallel_second_order_analysis": parallel_second_order,
        "member_load_assignments": load_assignments,
        "member_uniform_loads": [
            {"member_id": item.member, "qx_kn_m": item.qx_kn_m, "qy_kn_m": item.qy_kn_m, "qz_kn_m": item.qz_kn_m}
            for item in member_uniform_loads
        ],
        "wind_projected_area_by_node_m2": {
            node.id: {
                "for_global_x": round(wind_exposure_x[node.id], 6),
                "for_global_y": round(wind_exposure_y[node.id], 6),
            }
            for node in geometry.nodes
            if wind_exposure_x[node.id] or wind_exposure_y[node.id]
        },
        "load_distribution": "屋面荷载区按相邻构件中线形成分担条带，经真实屋面边界及开洞裁切后生成杆件均布荷载；无适用传力构件时才回退到分区节点。",
        "load_scope": "杆件自重＋屋面竖向恒载/活载/雪荷载＋控制风吸力；±X/±Y 风按杆件投影迎风面积分配，地震按重力代表值的屋面分担面积分配。",
        "self_weight_included": include_self_weight,
        "self_weight_factor": self_weight_factor,
    }
