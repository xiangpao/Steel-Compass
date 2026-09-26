from __future__ import annotations

from math import pi, sqrt

from .design_profiles import CustomSectionDefinition, SceneGeometryProfile


STEEL_MEMBER_CHECK_VERSION = "GB50017-member-checks-2026.2-unverified"


def _design_strength(grade: str, thickness_mm: float) -> float | None:
    # The scene and standalone registries disagree above 40 mm. Do not choose
    # either table until the grade/edition mapping has independent evidence.
    if thickness_mm <= 0 or thickness_mm > 40:
        return None
    mapping = {
        "Q235B": ((16, 215.0), (40, 205.0), (100, 195.0)),
        "Q355B": ((16, 305.0), (40, 295.0), (100, 285.0)),
        "Q390": ((16, 335.0), (40, 325.0), (100, 315.0)),
        "Q420": ((16, 355.0), (40, 345.0), (100, 335.0)),
        "Q460": ((16, 390.0), (40, 380.0), (100, 370.0)),
    }
    for limit, value in mapping.get(grade, ()):
        if thickness_mm <= limit:
            return value
    return None


def _thickness(section: CustomSectionDefinition) -> float:
    values = section.dimensions
    return max(float(values.get("t_mm", 0)), float(values.get("tw_mm", 0)), float(values.get("tf_mm", 0)))


def _depths(section: CustomSectionDefinition) -> tuple[float, float]:
    dimensions = section.dimensions
    if section.family == "CHS":
        diameter = float(dimensions["diameter_mm"])
        return diameter, diameter
    return float(dimensions.get("h_mm", dimensions.get("b_mm", 0))), float(dimensions.get("b_mm", dimensions.get("h_mm", 0)))


def _local_slenderness_utilization(section: CustomSectionDefinition, strength: float) -> tuple[float, str]:
    dimensions = section.dimensions
    epsilon = sqrt(235.0 / strength)
    if section.family in {"SHS", "RHS"}:
        thickness = float(dimensions["t_mm"])
        flat = max(
            float(dimensions.get("h_mm", dimensions.get("b_mm", 0))) - 3 * thickness,
            float(dimensions.get("b_mm", dimensions.get("h_mm", 0))) - 3 * thickness,
        )
        ratio = flat / thickness
        return ratio / max(40 * epsilon, 1e-9), "空心截面受压板件宽厚比"
    if section.family in {"H", "I"}:
        height = float(dimensions["h_mm"])
        width = float(dimensions["b_mm"])
        web = float(dimensions["tw_mm"])
        flange = float(dimensions["tf_mm"])
        flange_ratio = (width - web) / (2 * flange) / max(13 * epsilon, 1e-9)
        web_ratio = (height - 2 * flange) / web / max(33 * epsilon, 1e-9)
        return max(flange_ratio, web_ratio), "H/I截面翼缘及腹板宽厚比"
    if section.family == "CHS":
        ratio = float(dimensions["diameter_mm"]) / float(dimensions["t_mm"])
        return ratio / max(100 * epsilon**2, 1e-9), "圆管径厚比"
    return float("inf"), "未支持的截面局部稳定"


def calculate_scene_member_checks(
    geometry: SceneGeometryProfile,
    case_results: dict[str, dict[str, object]],
    section_by_member: dict[str, CustomSectionDefinition],
    grade_by_member: dict[str, str],
) -> dict[str, object]:
    node_by_id = {node.id: node for node in geometry.nodes}
    items: list[dict[str, object]] = []
    controlling: list[str] = []
    package_status = "complete"

    for member in geometry.members:
        missing_cases = [case_id for case_id, result in case_results.items()
                         if not (result.get("member_end_forces") or {}).get(member.id)]
        if not case_results or missing_cases:
            package_status = "incomplete"
            items.append({"member_id": member.id, "status": "not_calculated",
                          "reason": "缺少完整的构件组合内力，不能按零需求判定通过",
                          "missing_case_ids": missing_cases,
                          "verification_status": "unverified"})
            continue
        second_order_axial_cases = [
            case_id for case_id, result in case_results.items()
            if result.get("analysis_basis") == "second_order" and any(
                abs(float(result["member_end_forces"][member.id][end]["n_kn"])) > 1e-8
                for end in ("start", "end")
            )
        ]
        if second_order_axial_cases:
            # M0 - V*x - q*x²/2 below is a first-order diagram. It omits the
            # axial-force x transverse-displacement term and cannot certify
            # an interior maximum from second-order end actions alone.
            package_status = "incomplete"
        section = section_by_member.get(member.id)
        grade = grade_by_member.get(member.id)
        if section is None or grade is None:
            package_status = "incomplete"
            items.append({"member_id": member.id, "status": "not_calculated", "reason": "缺少最终截面或材料牌号"})
            continue
        strength = _design_strength(grade, _thickness(section))
        if strength is None:
            package_status = "incomplete"
            items.append({"member_id": member.id, "status": "not_calculated", "reason": "材料牌号或厚度超出强度映射范围"})
            continue

        start = node_by_id[member.start_node_id]
        end = node_by_id[member.end_node_id]
        length_mm = 1000 * sqrt((end.x_m - start.x_m) ** 2 + (end.y_m - start.y_m) ** 2 + (end.z_m - start.z_m) ** 2)
        design = member.design_parameters
        ky = design.effective_length_factor_y if design else 1.0
        kz = design.effective_length_factor_z if design else 1.0
        ly = 1000 * (design.unbraced_length_y_m if design and design.unbraced_length_y_m else length_mm / 1000)
        lz = 1000 * (design.unbraced_length_z_m if design and design.unbraced_length_z_m else length_mm / 1000)
        ry = float(section.radius_y_mm or sqrt(section.iy_mm4 / section.area_mm2))
        rz = float(section.radius_z_mm or sqrt(section.iz_mm4 / section.area_mm2))
        slender_y = ky * ly / ry
        slender_z = kz * lz / rz
        slenderness = max(slender_y, slender_z)
        slender_limit = 150.0 if member.role in {"column", "brace", "truss_chord", "truss_web"} else 200.0
        h, b = _depths(section)
        wy = section.iy_mm4 / max(h / 2, 1e-9)
        wz = section.iz_mm4 / max(b / 2, 1e-9)
        axial_capacity = section.area_mm2 * strength / 1000
        moment_y_capacity = wy * strength / 1e6
        moment_z_capacity = wz * strength / 1e6
        shear_capacity = 0.58 * strength * 0.6 * section.area_mm2 / 1000
        local_stability, local_stability_name = _local_slenderness_utilization(section, strength)
        lateral_unbraced_length = max(ly, lz)
        if section.family in {"H", "I"}:
            mcr_kn_m = (
                pi / max(lateral_unbraced_length, 1e-9)
                * sqrt(206000.0 * min(section.iy_mm4, section.iz_mm4) * 79000.0 * section.torsion_mm4)
                / 1e6
            )
            lateral_torsional_reduction = min(1.0, sqrt(mcr_kn_m / max(moment_y_capacity, moment_z_capacity, 1e-9)))
        else:
            mcr_kn_m = None
            lateral_torsional_reduction = 1.0

        lambda_bar = slenderness / pi * sqrt(strength / 206000.0)
        phi = max(0.1, 1.0 / (1.0 + lambda_bar**2))
        buckling_capacity = phi * axial_capacity
        case_checks: list[dict[str, object]] = []
        maximum = 0.0
        controlling_case = None
        for case_id, result in case_results.items():
            member_forces = (result.get("member_end_forces") or {}).get(member.id)  # type: ignore[union-attr]
            if not member_forces:
                continue
            ends = [member_forces["start"], member_forces["end"]]
            n = max(abs(float(item["n_kn"])) for item in ends)
            vy = max(abs(float(item["vy_kn"])) for item in ends)
            vz = max(abs(float(item["vz_kn"])) for item in ends)
            my = max(abs(float(item["my_kn_m"])) for item in ends)
            mz = max(abs(float(item["mz_kn_m"])) for item in ends)
            uniform = member_forces.get("uniform_load_local", {})
            qy = float(uniform.get("qy_kn_m", 0.0))
            qz = float(uniform.get("qz_kn_m", 0.0))
            start_forces = member_forces["start"]
            length_m = length_mm / 1000
            for station in range(1, 20):
                x = length_m * station / 20
                internal_my = (
                    float(start_forces["my_kn_m"])
                    + float(start_forces["vz_kn"]) * x
                    + qz * x**2 / 2
                )
                internal_mz = (
                    float(start_forces["mz_kn_m"])
                    - float(start_forces["vy_kn"]) * x
                    - qy * x**2 / 2
                )
                my = max(my, abs(internal_my))
                mz = max(mz, abs(internal_mz))
            compression = max(-float(item["n_kn"]) for item in ends) > 0
            axial_denominator = buckling_capacity if compression else axial_capacity
            interaction = (
                n / max(axial_denominator, 1e-9)
                + my / max(moment_y_capacity * lateral_torsional_reduction, 1e-9)
                + mz / max(moment_z_capacity * lateral_torsional_reduction, 1e-9)
            )
            shear = sqrt(vy**2 + vz**2) / max(shear_capacity, 1e-9)
            utilization = max(interaction, shear, slenderness / slender_limit, local_stability)
            if utilization > maximum:
                maximum = utilization
                controlling_case = case_id
            case_checks.append({
                "case_id": case_id,
                "maximum_moment_y_kn_m": round(my, 5),
                "maximum_moment_z_kn_m": round(mz, 5),
                "axial_biaxial_utilization": round(interaction, 5),
                "shear_utilization": round(shear, 5),
                "local_stability_utilization": round(local_stability, 5),
                "utilization": round(utilization, 5),
            })

        node_displacements = [
            result.get("node_displacements", {})
            for result in case_results.values()
            if result.get("node_displacements")
        ]
        maximum_relative_mm = 0.0
        for displacements in node_displacements:
            first = displacements.get(member.start_node_id)
            second = displacements.get(member.end_node_id)
            if first and second:
                displacement_delta = [float(second[key]) - float(first[key]) for key in ("ux_mm", "uy_mm", "uz_mm")]
                member_axis = [
                    (end.x_m - start.x_m) * 1000 / length_mm,
                    (end.y_m - start.y_m) * 1000 / length_mm,
                    (end.z_m - start.z_m) * 1000 / length_mm,
                ]
                axial_delta = sum(value * axis for value, axis in zip(displacement_delta, member_axis, strict=True))
                delta = sqrt(sum((value - axial_delta * axis) ** 2 for value, axis in zip(displacement_delta, member_axis, strict=True)))
                maximum_relative_mm = max(maximum_relative_mm, delta)
        for result in case_results.values():
            member_forces = (result.get("member_end_forces") or {}).get(member.id)  # type: ignore[union-attr]
            if not member_forces:
                continue
            uniform = member_forces.get("uniform_load_local", {})
            qy = abs(float(uniform.get("qy_kn_m", 0.0)))
            qz = abs(float(uniform.get("qz_kn_m", 0.0)))
            uniform_deflection_y = 5 * qy * length_mm**4 / (384 * 206000.0 * section.iz_mm4)
            uniform_deflection_z = 5 * qz * length_mm**4 / (384 * 206000.0 * section.iy_mm4)
            maximum_relative_mm = max(maximum_relative_mm, sqrt(uniform_deflection_y**2 + uniform_deflection_z**2))
        deflection_limit = length_mm / (design.deflection_limit_ratio if design else 250.0)
        deflection_utilization = maximum_relative_mm / max(deflection_limit, 1e-9)
        maximum = max(maximum, deflection_utilization)
        status = "pass" if maximum <= 1.0 else "failed"
        if second_order_axial_cases:
            status = "not_calculated"
        if status == "failed":
            package_status = "failed"
            controlling.append(member.id)
        items.append({
            "member_id": member.id,
            "status": status,
            "material_grade": grade,
            "section_id": section.id,
            "design_strength_mpa": strength,
            "slenderness_y": round(slender_y, 3),
            "slenderness_z": round(slender_z, 3),
            "slenderness_limit": slender_limit,
            "buckling_reduction": round(phi, 5),
            "local_stability_check": local_stability_name,
            "local_stability_utilization": round(local_stability, 5),
            "lateral_torsional_buckling_reduction": round(lateral_torsional_reduction, 5),
            "elastic_lateral_torsional_moment_kn_m": round(mcr_kn_m, 5) if mcr_kn_m is not None else None,
            "deflection_mm": round(maximum_relative_mm, 5),
            "deflection_limit_mm": round(deflection_limit, 5),
            "utilization": None if second_order_axial_cases else round(maximum, 5),
            "controlling_case": controlling_case,
            "case_checks": case_checks,
            **({"reason": "二阶杆端力已计算；含轴力杆件的沿杆弯矩及变形包络尚未完成独立验证",
                "blocked_case_ids": second_order_axial_cases,
                "case_checks_basis": "end-actions-and-first-order-interpolation-diagnostic-only"}
               if second_order_axial_cases else {}),
            "formula_source": "GB 55006-2021；GB 50017-2017（强度、稳定、长细比和变形）",
            "catalog_version": STEEL_MEMBER_CHECK_VERSION,
            "verification_status": "unverified",
        })
    # A known failed member always controls the package, independent of member
    # ordering. Missing evidence must not erase an already demonstrated failure.
    package_status = ("failed" if any(item["status"] == "failed" for item in items)
                      else "incomplete" if not items or any(item["status"] == "not_calculated" for item in items)
                      else "complete")
    return {"status": package_status, "items": items, "controlling_member_ids": controlling}
