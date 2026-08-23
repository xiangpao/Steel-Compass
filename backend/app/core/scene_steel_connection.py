from __future__ import annotations

from math import hypot, pi
from typing import Any

from .design_profiles import CustomSectionDefinition, SceneGeometryProfile, STEEL_SECTIONS
from .schemas import CheckResult, Quantity
from .steel import steel_design_strength


def _not_calculated(connection: Any, code: str, missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "connection_id": connection.id,
        "mark": connection.mark,
        "node_id": connection.node_id,
        "status": "not_calculated",
        "verification_status": "unverified",
        "issue_code": code,
        "missing_inputs": missing or [],
    }


def _check(name: str, demand: float, capacity: float, unit: str, reference: str, note: str | None = None) -> CheckResult:
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


def _section_geometry(section: Any) -> tuple[float, float, float] | None:
    dimensions = section.dimensions
    if section.family == "SHS":
        side = float(dimensions.get("b_mm") or dimensions.get("h_mm") or 0)
        thickness = float(dimensions.get("t_mm") or 0)
        return (side, side, thickness) if min(side, thickness) > 0 else None
    if section.family == "RHS":
        height = float(dimensions.get("h_mm") or 0)
        width = float(dimensions.get("b_mm") or 0)
        thickness = float(dimensions.get("t_mm") or 0)
        return (height, width, thickness) if min(height, width, thickness) > 0 else None
    return None


def _force_score(forces: dict[str, Any]) -> float:
    return (
        abs(float(forces.get("n_kn", 0)))
        + hypot(float(forces.get("vy_kn", 0)), float(forces.get("vz_kn", 0)))
        + 10.0 * hypot(float(forces.get("my_kn_m", 0)), float(forces.get("mz_kn_m", 0)))
        + 10.0 * abs(float(forces.get("t_kn_m", 0)))
    )


def _forces_at_node(connection: Any, member: Any, force_package: dict[str, Any]) -> tuple[dict[str, float], str, str | None] | None:
    if connection.node_id == force_package.get("start_node_id"):
        end_name = "start"
    elif connection.node_id == force_package.get("end_node_id"):
        end_name = "end"
    else:
        return None
    cases = [item for item in force_package.get("cases", []) if item.get("limit_state") == "ULS"]
    if cases:
        controlling = max(cases, key=lambda item: _force_score(item.get(end_name, {})))
        return controlling.get(end_name, {}), end_name, str(controlling.get("combination_id"))
    return force_package.get(end_name, {}), end_name, None


def _bolt_capacity(parameters: dict[str, Any]) -> tuple[float, float, list[str]]:
    required = [name for name in ("bolt_count", "bolt_diameter_mm", "bolt_fu_mpa") if parameters.get(name) is None]
    if required:
        return 0.0, 0.0, required
    count = float(parameters["bolt_count"])
    diameter = float(parameters["bolt_diameter_mm"])
    fu = float(parameters["bolt_fu_mpa"])
    area = pi * diameter**2 / 4
    shear = count * 0.6 * fu * area / 1.25 / 1000
    tension = count * 0.8 * fu * area / 1.25 / 1000
    return shear, tension, []


def _calculate_bolted_or_gusset_connection(
    connection: Any,
    connection_type: Any,
    resolved: list[tuple[Any, Any, Any]],
    member_end_forces: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    form = str(connection_type.parameters.get("connection_form", ""))
    supported = {
        "h_end_plate",
        "h_welded_flange_web",
        "shear_tab",
        "bolted_splice",
        "gusset_plate",
    }
    if form not in supported:
        return _not_calculated(connection, "unsupported_connection_form", sorted(supported))
    action_member, member_type, section = next(
        (item for item in resolved if item[0].role != "column"), resolved[0]
    )
    if form in {"h_end_plate", "h_welded_flange_web", "shear_tab", "bolted_splice"} and section.family not in {"H", "I"}:
        return _not_calculated(connection, "unsupported_section_family", ["H", "I"])
    force_package = member_end_forces.get(action_member.id)
    if force_package is None:
        return _not_calculated(connection, "missing_member_end_force", [action_member.id])
    force_at_node = _forces_at_node(connection, action_member, force_package)
    if force_at_node is None:
        return _not_calculated(connection, "connection_node_not_on_action_member")
    forces, end_name, controlling_combination = force_at_node
    axial = abs(float(forces.get("n_kn", 0)))
    shear = hypot(float(forces.get("vy_kn", 0)), float(forces.get("vz_kn", 0)))
    moment = hypot(float(forces.get("my_kn_m", 0)), float(forces.get("mz_kn_m", 0)))
    torsion = abs(float(forces.get("t_kn_m", 0)))
    plate_thickness = connection_type.parameters.get("plate_thickness_mm")
    plate_depth = connection_type.parameters.get("plate_depth_mm")
    weld_throat = connection_type.parameters.get("weld_throat_mm")
    missing = [name for name, value in {
        "plate_thickness_mm": plate_thickness,
        "plate_depth_mm": plate_depth,
        "weld_throat_mm": weld_throat,
    }.items() if value is None]
    bolt_shear, bolt_tension, bolt_missing = _bolt_capacity(connection_type.parameters)
    if form != "h_welded_flange_web":
        missing.extend(bolt_missing)
    if missing:
        return _not_calculated(connection, "missing_connection_parameters", sorted(set(missing)))
    try:
        plate_thickness = float(plate_thickness)
        plate_depth = float(plate_depth)
        weld_throat = float(weld_throat)
    except (TypeError, ValueError):
        return _not_calculated(connection, "invalid_connection_parameters")
    if min(plate_thickness, plate_depth, weld_throat) <= 0:
        return _not_calculated(connection, "invalid_connection_parameters")

    grade = member_type.material_grade
    steel = steel_design_strength(grade, max(float(section.dimensions.get("t_mm", 0)), float(section.dimensions.get("tf_mm", 0)), 6.0))
    plate_shear = 0.6 * steel["fd"] * plate_thickness * plate_depth / 1000
    plate_tension = steel["fd"] * plate_thickness * plate_depth / 1000
    weld_length = 2 * plate_depth
    weld_capacity = weld_length * weld_throat * steel["fv"] / 1000
    lever_arm = max(plate_depth / 1000 * 0.75, 0.05)
    checks: list[CheckResult]
    if form in {"h_end_plate", "h_welded_flange_web"}:
        tension_capacity = weld_capacity if form == "h_welded_flange_web" else min(bolt_tension, plate_tension)
        shear_capacity = weld_capacity if form == "h_welded_flange_web" else min(bolt_shear, plate_shear)
        checks = [
            _check("梁柱节点剪力传递", shear, shear_capacity, "kN", "GB 50017-2017 连接承载力"),
            _check("梁柱节点弯矩传递", moment, tension_capacity * lever_arm, "kN*m", "GB 50017-2017 端板/焊接梁柱连接"),
            _check("连接板轴力传递", axial, min(tension_capacity, plate_tension), "kN", "GB 50017-2017 连接板净截面"),
        ]
    elif form == "shear_tab":
        checks = [
            _check("主次梁剪切板螺栓", shear, bolt_shear, "kN", "GB 50017-2017 螺栓受剪"),
            _check("主次梁剪切板", shear, plate_shear, "kN", "GB 50017-2017 连接板抗剪"),
            _check("剪切板焊缝", shear, weld_capacity, "kN", "GB 50017-2017 角焊缝"),
        ]
    elif form == "bolted_splice":
        equivalent_tension = axial + moment / lever_arm
        checks = [
            _check("梁拼接螺栓受剪", shear, bolt_shear, "kN", "GB 50017-2017 螺栓受剪"),
            _check("梁拼接拉力与弯矩", equivalent_tension, min(bolt_tension, plate_tension), "kN", "GB 50017-2017 拼接连接"),
            _check("拼接板抗剪", shear, plate_shear, "kN", "GB 50017-2017 连接板抗剪"),
        ]
    else:
        equivalent = axial + shear + torsion / lever_arm
        checks = [
            _check("支撑节点板拉压", equivalent, plate_tension, "kN", "GB 50017-2017 支撑节点板"),
            _check("支撑节点螺栓", equivalent, hypot(bolt_shear, bolt_tension), "kN", "GB 50017-2017 螺栓拉剪组合（保守包络）"),
            _check("支撑节点焊缝", equivalent, weld_capacity, "kN", "GB 50017-2017 角焊缝"),
        ]
    failed = [item.name for item in checks if not item.passed]
    return {
        "connection_id": connection.id,
        "mark": connection.mark,
        "node_id": connection.node_id,
        "member_ids": connection.member_ids,
        "action_member_id": action_member.id,
        "member_end": end_name,
        "connection_form": form,
        "status": "failed" if failed else "complete",
        "verification_status": "unverified",
        "checks": [item.model_dump(mode="json") for item in checks],
        "failed_checks": failed,
        "force_source": {
            "analysis_member_id": action_member.id,
            "basis": force_package.get("force_basis", "member-local-axis"),
            "component_sources": force_package.get("component_sources", {}),
            "controlling_combination_id": controlling_combination,
            "axial_kn": axial,
            "shear_kn": shear,
            "moment_kn_m": moment,
            "torsion_kn_m": torsion,
        },
    }


def calculate_scene_steel_connections(
    geometry: SceneGeometryProfile,
    member_end_forces: dict[str, dict[str, Any]],
    custom_sections: list[CustomSectionDefinition],
) -> list[dict[str, Any]]:
    """Check explicitly defined, supported pergola steel connection families."""

    connection_types = {item.id: item for item in geometry.connection_types}
    members = {item.id: item for item in geometry.members}
    assignments = {item.member_id: item for item in geometry.member_instances}
    member_types = {item.id: item for item in geometry.member_types}
    standard_sections = {item.id: item for item in STEEL_SECTIONS}
    project_sections = {item.id: item for item in custom_sections}
    items: list[dict[str, Any]] = []

    def member_data(member_id: str) -> tuple[Any, Any, Any] | None:
        member = members.get(member_id)
        assignment = assignments.get(member_id)
        member_type = member_types.get(assignment.member_type_id) if assignment else None
        if member is None or assignment is None or member_type is None:
            return None
        section_id = assignment.override_section_id or member_type.section_id
        section = standard_sections.get(section_id) or project_sections.get(section_id)
        return (member, member_type, section) if section is not None else None

    for connection in geometry.connection_instances:
        connection_type = connection_types.get(connection.connection_type_id)
        if connection_type is None:
            items.append(_not_calculated(connection, "unknown_connection_type"))
            continue
        if connection_type.family not in {"beam_column", "secondary_beam", "beam_splice", "brace"}:
            continue
        connected = [member_data(member_id) for member_id in connection.member_ids]
        if any(item is None for item in connected):
            items.append(_not_calculated(connection, "incomplete_connection_member_assignment"))
            continue
        resolved = [item for item in connected if item is not None]
        supported_families = set(connection_type.supported_section_families)
        if supported_families and any(item[2].family not in supported_families for item in resolved):
            items.append(_not_calculated(connection, "unsupported_section_family"))
            continue
        if connection_type.parameters.get("connection_form") != "rhs_full_perimeter_weld":
            items.append(_calculate_bolted_or_gusset_connection(connection, connection_type, resolved, member_end_forces))
            continue
        column_candidates = [item for item in resolved if item[0].role == "column"]
        beam_candidates = [item for item in resolved if item[0].role != "column"]
        if len(column_candidates) != 1 or len(beam_candidates) != 1:
            items.append(_not_calculated(connection, "unsupported_connection_topology"))
            continue
        column_member, column_type, column_section = column_candidates[0]
        beam_member, beam_type, beam_section = beam_candidates[0]
        column_geometry = _section_geometry(column_section)
        beam_geometry = _section_geometry(beam_section)
        if column_geometry is None or beam_geometry is None:
            items.append(_not_calculated(connection, "unsupported_section_family"))
            continue
        if column_type.material_grade not in {"Q235B", "Q355B"} or beam_type.material_grade not in {"Q235B", "Q355B"}:
            items.append(_not_calculated(connection, "unsupported_steel_grade"))
            continue
        weld_throat = connection_type.parameters.get("weld_throat_mm")
        stiffener_thickness = connection_type.parameters.get("stiffener_thickness_mm", connection_type.parameters.get("stiffener_mm"))
        missing = [name for name, value in {"weld_throat_mm": weld_throat, "stiffener_thickness_mm": stiffener_thickness}.items() if value is None]
        if missing:
            items.append(_not_calculated(connection, "missing_connection_parameters", missing))
            continue
        try:
            weld_throat_value = float(weld_throat)
            stiffener_value = float(stiffener_thickness)
        except (TypeError, ValueError):
            items.append(_not_calculated(connection, "invalid_connection_parameters"))
            continue
        if weld_throat_value < 3 or stiffener_value <= 0:
            items.append(_not_calculated(connection, "invalid_connection_parameters"))
            continue
        force_package = member_end_forces.get(beam_member.id)
        if force_package is None:
            items.append(_not_calculated(connection, "missing_member_end_force", ["beam_member_end_force"]))
            continue
        force_at_node = _forces_at_node(connection, beam_member, force_package)
        if force_at_node is None:
            items.append(_not_calculated(connection, "connection_node_not_on_beam"))
            continue
        forces, end_name, controlling_combination = force_at_node
        if not isinstance(forces, dict):
            items.append(_not_calculated(connection, "missing_member_end_force"))
            continue

        beam_height, beam_width, beam_thickness = beam_geometry
        column_height, column_width, column_thickness = column_geometry
        beam_steel = steel_design_strength(beam_type.material_grade, beam_thickness)
        column_steel = steel_design_strength(column_type.material_grade, column_thickness)
        axial = abs(float(forces.get("n_kn", 0)))
        shear = hypot(float(forces.get("vy_kn", 0)), float(forces.get("vz_kn", 0)))
        moment = hypot(float(forces.get("my_kn_m", 0)), float(forces.get("mz_kn_m", 0)))
        torsion = abs(float(forces.get("t_kn_m", 0)))
        lever_arm = max(min(beam_height, beam_width) / 2000, 0.05)
        equivalent_force = axial + shear + moment / lever_arm + torsion / lever_arm
        weld_length = 2 * (beam_height + beam_width)
        weld_capacity = weld_length * weld_throat_value * min(beam_steel["fv"], column_steel["fv"]) / 1000
        beam_wall_capacity = 0.6 * beam_steel["fd"] * float(beam_section.area_mm2) / 1000
        column_face_width = min(beam_width + 2 * stiffener_value, column_width)
        column_face_capacity = 2 * column_face_width * column_thickness * column_steel["fd"] / 1000
        minimum_stiffener = max(beam_thickness, 6.0)
        checks = [
            _check("梁柱节点全周角焊缝", equivalent_force, weld_capacity, "kN", "GB 50017-2017 焊缝连接（方案级等效力Beta模型）", "弯矩和扭矩按保守力臂折算为等效力。"),
            _check("梁端管壁传力", equivalent_force, beam_wall_capacity, "kN", "GB 50017-2017 构件净截面与局部传力（方案级Beta模型）"),
            _check("柱壁局部承压/屈服", equivalent_force, column_face_capacity, "kN", "GB 50017-2017 箱形截面节点局部承压（方案级Beta模型）", "当前不替代屈服线或有限元节点分析。"),
            _check("节点加劲板厚度", minimum_stiffener, stiffener_value, "mm", "GB 50017-2017 节点加劲构造（方案筛查）"),
        ]
        failed = [item.name for item in checks if not item.passed]
        items.append({
            "connection_id": connection.id,
            "mark": connection.mark,
            "node_id": connection.node_id,
            "member_ids": connection.member_ids,
            "beam_member_id": beam_member.id,
            "column_member_id": column_member.id,
            "beam_end": end_name,
            "status": "failed" if failed else "complete",
            "verification_status": "unverified",
            "checks": [item.model_dump(mode="json") for item in checks],
            "failed_checks": failed,
            "force_source": {
                "analysis_member_id": beam_member.id,
                "basis": force_package.get("force_basis", "member-local-axis"),
                "uls_factor": 1.0,
                "controlling_combination_id": controlling_combination,
                "axial_kn": axial,
                "shear_kn": shear,
                "moment_kn_m": moment,
                "torsion_kn_m": torsion,
            },
            "pending_checks": ["柱壁屈服线/精细刚度属于专项节点分析，不在当前连接族范围"],
        })
    return items
