"""Independent closed-form references for geotechnical infrastructure modules.

This file intentionally imports no production package.  The equations are
duplicated from first principles so a regression in the production code can be
detected instead of being repeated by a shared helper.
"""

from __future__ import annotations

from math import hypot, radians, tan


def threshold_passes(demand: float, capacity: float) -> bool:
    """Return the exact screening decision used by the evidence cases."""

    if demand < 0.0 or capacity <= 0.0:
        raise ValueError("demand must be non-negative and capacity positive")
    return demand <= capacity


def gravity_wall_reference(
    *,
    height_m: float,
    base_width_m: float,
    base_thickness_m: float,
    wall_bottom_m: float,
    wall_top_m: float,
    toe_m: float,
    wall_gamma: float,
    soil_gamma: float,
    phi_deg: float,
    surcharge_kpa: float,
    water_depth_m: float,
    water_gamma: float,
    uplift_toe_m: float,
    uplift_heel_m: float,
) -> dict[str, float]:
    """Integrate soil/water actions and base equilibrium per metre of wall."""

    ka = tan(radians(45.0 - phi_deg / 2.0)) ** 2
    dry_height = height_m - water_depth_m
    dry_wedge = 0.5 * ka * soil_gamma * dry_height**2
    saturated_rectangle = ka * soil_gamma * dry_height * water_depth_m
    submerged_wedge = 0.5 * ka * (soil_gamma - water_gamma) * water_depth_m**2
    soil = dry_wedge + saturated_rectangle + submerged_wedge
    surcharge = ka * surcharge_kpa * height_m
    water = 0.5 * water_gamma * water_depth_m**2
    horizontal = soil + surcharge + water
    lateral_moment = (
        dry_wedge * (water_depth_m + dry_height / 3.0)
        + saturated_rectangle * water_depth_m / 2.0
        + submerged_wedge * water_depth_m / 3.0
        + surcharge * height_m / 2.0
        + water * water_depth_m / 3.0
    )

    wall_area = (wall_bottom_m + wall_top_m) * height_m / 2.0
    wall_weight = wall_area * wall_gamma
    wall_centroid_local = (
        wall_bottom_m**2 + wall_bottom_m * wall_top_m + wall_top_m**2
    ) / (3.0 * (wall_bottom_m + wall_top_m))
    base_weight = base_width_m * base_thickness_m * wall_gamma
    toe_pressure = water_gamma * uplift_toe_m
    heel_pressure = water_gamma * uplift_heel_m
    uplift = (toe_pressure + heel_pressure) * base_width_m / 2.0
    if uplift > 0.0:
        uplift_centroid = base_width_m * (
            toe_pressure + 2.0 * heel_pressure
        ) / (3.0 * (toe_pressure + heel_pressure))
    else:
        uplift_centroid = base_width_m / 2.0

    vertical = wall_weight + base_weight - uplift
    stabilizing = (
        wall_weight * (toe_m + wall_centroid_local)
        + base_weight * base_width_m / 2.0
    )
    resultant = (
        stabilizing - lateral_moment - uplift * uplift_centroid
    ) / vertical
    eccentricity = base_width_m / 2.0 - resultant
    average = vertical / base_width_m
    if abs(eccentricity) <= base_width_m / 6.0:
        q_max = average * (1.0 + 6.0 * abs(eccentricity) / base_width_m)
        q_min = average * (1.0 - 6.0 * abs(eccentricity) / base_width_m)
        contact = base_width_m
    else:
        compression_edge = min(resultant, base_width_m - resultant)
        contact = max(3.0 * compression_edge, 0.0)
        q_max = 2.0 * vertical / contact if contact > 0.0 else float("inf")
        q_min = 0.0
    material_stress = wall_weight / wall_bottom_m + 6.0 * lateral_moment / wall_bottom_m**2
    return {
        "ka": ka,
        "soil": soil,
        "surcharge": surcharge,
        "water": water,
        "horizontal": horizontal,
        "lateral_moment": lateral_moment,
        "wall_weight": wall_weight,
        "base_weight": base_weight,
        "uplift": uplift,
        "vertical": vertical,
        "resultant": resultant,
        "eccentricity": eccentricity,
        "contact": contact,
        "q_max": q_max,
        "q_min": q_min,
        "material_stress": material_stress,
    }


def pool_combination_reference(
    *,
    inside_length_m: float,
    inside_width_m: float,
    wall_height_m: float,
    wall_thickness_mm: float,
    base_thickness_mm: float,
    base_projection_m: float,
    retained_soil_height_m: float,
    internal_depth_m: float,
    external_head_m: float,
    concrete_gamma: float,
    water_gamma: float,
    soil_gamma: float,
    phi_deg: float,
    surcharge_kpa: float,
    ballast_kn: float,
    external_lateral_factor: float,
    internal_water_factor: float,
    permanent_factor: float,
    uplift_factor: float,
) -> dict[str, float]:
    """Recompute one rectangular-pool action combination."""

    ka = tan(radians(45.0 - phi_deg / 2.0)) ** 2
    external_wall_depth = max(external_head_m - base_thickness_mm / 1000.0, 0.0)
    soil = 0.5 * ka * soil_gamma * retained_soil_height_m**2 * external_lateral_factor
    surcharge = ka * surcharge_kpa * retained_soil_height_m * external_lateral_factor
    external_water = 0.5 * water_gamma * external_wall_depth**2 * external_lateral_factor
    internal_water = 0.5 * water_gamma * internal_depth_m**2 * internal_water_factor
    net_force = soil + surcharge + external_water - internal_water
    net_moment = (
        soil * retained_soil_height_m / 3.0
        + surcharge * retained_soil_height_m / 2.0
        + external_water * external_wall_depth / 3.0
        - internal_water * internal_depth_m / 3.0
    )
    net_base_pressure = (
        ka * (soil_gamma * retained_soil_height_m + surcharge_kpa) * external_lateral_factor
        + water_gamma * external_wall_depth * external_lateral_factor
        - water_gamma * internal_depth_m * internal_water_factor
    )

    wall_t = wall_thickness_mm / 1000.0
    base_t = base_thickness_mm / 1000.0
    outer_l = inside_length_m + 2.0 * wall_t + 2.0 * base_projection_m
    outer_w = inside_width_m + 2.0 * wall_t + 2.0 * base_projection_m
    area = outer_l * outer_w
    base_weight = area * base_t * concrete_gamma
    wall_volume = 2.0 * (inside_length_m + inside_width_m + 2.0 * wall_t) * wall_t * wall_height_m
    wall_weight = wall_volume * concrete_gamma
    water_weight = inside_length_m * inside_width_m * internal_depth_m * water_gamma
    downward = (base_weight + wall_weight + ballast_kn) * permanent_factor + water_weight * internal_water_factor
    uplift = area * external_head_m * water_gamma * uplift_factor
    net_vertical = downward - uplift
    soil_reaction = max(net_vertical, 0.0) / area
    net_pressure = (
        external_head_m * water_gamma * uplift_factor
        + soil_reaction
        - base_t * concrete_gamma * permanent_factor
        - ballast_kn * permanent_factor / area
        - internal_depth_m * water_gamma * internal_water_factor
    )
    lx, ly = sorted((inside_length_m, inside_width_m))
    denominator = lx**4 + ly**4
    qx = abs(net_pressure) * ly**4 / denominator
    qy = abs(net_pressure) * lx**4 / denominator
    return {
        "ka": ka,
        "net_force": net_force,
        "net_moment": net_moment,
        "net_base_pressure": net_base_pressure,
        "area": area,
        "downward": downward,
        "uplift": uplift,
        "net_vertical": net_vertical,
        "soil_reaction": soil_reaction,
        "net_pressure": net_pressure,
        "x_moment": qx * lx**2 / 8.0,
        "y_moment": qy * ly**2 / 8.0,
        "x_shear": qx * lx / 2.0,
        "y_shear": qy * ly / 2.0,
    }


def rc_strip_reference(
    *,
    thickness_mm: float,
    cover_mm: float,
    bar_diameter_mm: float,
    steel_area_mm2: float,
    concrete_fc_mpa: float,
    concrete_ft_mpa: float,
    rebar_fy_mpa: float,
) -> dict[str, float]:
    """Independent one-metre RC strip flexure/shear screening capacity."""

    depth = thickness_mm - cover_mm - bar_diameter_mm / 2.0
    x = rebar_fy_mpa * steel_area_mm2 / (concrete_fc_mpa * 1000.0)
    x_effective = min(x, 0.45 * depth)
    return {
        "effective_depth": depth,
        "moment_capacity": rebar_fy_mpa * steel_area_mm2 * (depth - x_effective / 2.0) / 1.0e6,
        "shear_capacity": 0.7 * concrete_ft_mpa * 1000.0 * depth / 1000.0,
        "reinforcement_ratio": steel_area_mm2 / (1000.0 * depth),
    }


def pile_group_reference(
    *,
    coordinates_mm: tuple[tuple[float, float], ...],
    n_kn: float,
    vx_kn: float,
    vy_kn: float,
    mx_kn_m: float,
    my_kn_m: float,
    torsion_kn_m: float,
    cap_length_x_mm: float,
    cap_width_y_mm: float,
    cap_thickness_mm: float,
    column_x_mm: float,
    column_y_mm: float,
    cover_mm: float,
    bar_diameter_mm: float,
    concrete_ft_mpa: float,
    rebar_fy_mpa: float,
    rebar_x_mm2_per_m: float,
    rebar_y_mm2_per_m: float,
    minimum_ratio: float,
) -> dict[str, object]:
    """Closed-form rigid-cap reference for centred orthogonal pile layouts."""

    count = len(coordinates_mm)
    if abs(sum(x for x, _ in coordinates_mm)) > 1e-9 or abs(sum(y for _, y in coordinates_mm)) > 1e-9:
        raise ValueError("reference is limited to layouts centred on the cap origin")
    sum_x2 = sum(x * x for x, _ in coordinates_mm)
    sum_y2 = sum(y * y for _, y in coordinates_mm)
    sum_xy = sum(x * y for x, y in coordinates_mm)
    if abs(sum_xy) > 1e-9:
        raise ValueError("reference requires orthogonal principal layout axes")
    axial = tuple(
        n_kn / count + mx_kn_m * 1000.0 * y / sum_y2 + my_kn_m * 1000.0 * x / sum_x2
        for x, y in coordinates_mm
    )
    sum_r2 = sum(x * x + y * y for x, y in coordinates_mm)
    torsion_factor = torsion_kn_m * 1000.0 / sum_r2
    hx = tuple(vx_kn / count - torsion_factor * y for x, y in coordinates_mm)
    hy = tuple(vy_kn / count + torsion_factor * x for x, y in coordinates_mm)
    horizontal = tuple(hypot(x, y) for x, y in zip(hx, hy, strict=True))

    depth = cap_thickness_mm - cover_mm - bar_diameter_mm / 2.0
    critical_perimeter = 2.0 * (column_x_mm + column_y_mm + 2.0 * depth)
    inside = [
        i for i, (x, y) in enumerate(coordinates_mm)
        if abs(x) <= column_x_mm / 2.0 + depth / 2.0
        and abs(y) <= column_y_mm / 2.0 + depth / 2.0
    ]
    punching_demand = max(0.0, abs(n_kn) - sum(abs(axial[i]) for i in inside))
    punching_capacity = 0.7 * concrete_ft_mpa * critical_perimeter * depth / 1000.0
    x_limit = column_x_mm / 2.0 + depth
    y_limit = column_y_mm / 2.0 + depth
    shear_x = max(
        sum(abs(axial[i]) for i, (x, _) in enumerate(coordinates_mm) if x > x_limit),
        sum(abs(axial[i]) for i, (x, _) in enumerate(coordinates_mm) if x < -x_limit),
    )
    shear_y = max(
        sum(abs(axial[i]) for i, (_, y) in enumerate(coordinates_mm) if y > y_limit),
        sum(abs(axial[i]) for i, (_, y) in enumerate(coordinates_mm) if y < -y_limit),
    )
    moment_x = max(
        sum(abs(axial[i]) * (x - column_x_mm / 2.0) / 1000.0 for i, (x, _) in enumerate(coordinates_mm) if x > column_x_mm / 2.0),
        sum(abs(axial[i]) * (-x - column_x_mm / 2.0) / 1000.0 for i, (x, _) in enumerate(coordinates_mm) if x < -column_x_mm / 2.0),
    )
    moment_y = max(
        sum(abs(axial[i]) * (y - column_y_mm / 2.0) / 1000.0 for i, (_, y) in enumerate(coordinates_mm) if y > column_y_mm / 2.0),
        sum(abs(axial[i]) * (-y - column_y_mm / 2.0) / 1000.0 for i, (_, y) in enumerate(coordinates_mm) if y < -column_y_mm / 2.0),
    )
    rebar_x_total = rebar_x_mm2_per_m * cap_width_y_mm / 1000.0
    rebar_y_total = rebar_y_mm2_per_m * cap_length_x_mm / 1000.0
    return {
        "axial": axial,
        "horizontal_x": hx,
        "horizontal_y": hy,
        "horizontal": horizontal,
        "effective_depth": depth,
        "punching_demand": punching_demand,
        "punching_capacity": punching_capacity,
        "shear_x_demand": shear_x,
        "shear_y_demand": shear_y,
        "shear_x_capacity": 0.7 * concrete_ft_mpa * cap_width_y_mm * depth / 1000.0,
        "shear_y_capacity": 0.7 * concrete_ft_mpa * cap_length_x_mm * depth / 1000.0,
        "moment_x_demand": moment_x,
        "moment_y_demand": moment_y,
        "moment_x_capacity": rebar_x_total * rebar_fy_mpa * 0.9 * depth / 1.0e6,
        "moment_y_capacity": rebar_y_total * rebar_fy_mpa * 0.9 * depth / 1.0e6,
        "minimum_x": minimum_ratio * cap_width_y_mm * depth,
        "minimum_y": minimum_ratio * cap_length_x_mm * depth,
        "provided_x": rebar_x_total,
        "provided_y": rebar_y_total,
    }
