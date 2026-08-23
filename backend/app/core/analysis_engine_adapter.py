from __future__ import annotations

from math import sqrt

from Pynite import FEModel3D

from .space_frame import SpaceFrameModel, SpaceFrameResult


PARALLEL_TOLERANCE = 0.05


def compare_with_pynite(
    model: SpaceFrameModel,
    primary: SpaceFrameResult,
    *,
    second_order: bool = False,
) -> dict[str, object]:
    """Run an independent PyNite model without changing the primary result path.

    Units are kN and m. This adapter remains unverified until the published
    benchmark set has been completed, so it is evidence rather than an approval.
    """
    pynite = FEModel3D()
    pynite.add_material("steel", 2.06e8, 7.9e7, 0.30, 78.5)
    for node in model.nodes:
        pynite.add_node(node.id, node.x_m, node.y_m, node.z_m)
    for member in model.members:
        section_name = f"section-{member.id}"
        pynite.add_section(
            section_name,
            member.area_mm2 * 1e-6,
            member.iy_mm4 * 1e-12,
            member.iz_mm4 * 1e-12,
            member.torsion_mm4 * 1e-12,
        )
        pynite.add_member(member.id, member.start, member.end, "steel", section_name)
        pynite.def_releases(member.id, *member.start_releases, *member.end_releases)
    for restraint in model.restraints:
        pynite.def_support(
            restraint.node,
            restraint.ux,
            restraint.uy,
            restraint.uz,
            restraint.rx,
            restraint.ry,
            restraint.rz,
        )
    for load in model.nodal_loads:
        for direction, value in (
            ("FX", load.fx_kn), ("FY", load.fy_kn), ("FZ", load.fz_kn),
            ("MX", load.mx_kn_m), ("MY", load.my_kn_m), ("MZ", load.mz_kn_m),
        ):
            if value:
                pynite.add_node_load(load.node, direction, value)
    for load in model.member_uniform_loads:
        for direction, value in (
            ("FX", load.qx_kn_m),
            ("FY", load.qy_kn_m),
            ("FZ", load.qz_kn_m),
        ):
            if value:
                pynite.add_member_dist_load(load.member, direction, value, value)
    if second_order:
        pynite.analyze_PDelta(log=False, check_stability=True)
    else:
        pynite.analyze_linear(log=False, check_stability=True, check_statics=False)

    combo = "Combo 1"
    pynite_max_mm = max(
        sqrt(float(node.DX[combo]) ** 2 + float(node.DY[combo]) ** 2 + float(node.DZ[combo]) ** 2) * 1000
        for node in pynite.nodes.values()
    )
    primary_max_mm = max(
        sqrt(value.ux_mm**2 + value.uy_mm**2 + value.uz_mm**2)
        for value in primary.displacements.values()
    )
    displacement_scale = max(abs(primary_max_mm), abs(pynite_max_mm), 1e-9)
    displacement_difference = abs(primary_max_mm - pynite_max_mm) / displacement_scale

    pynite_vertical_reaction = sum(float(node.RxnFZ.get(combo, 0.0)) for node in pynite.nodes.values())
    primary_vertical_reaction = sum(value.fz_kn for value in primary.reactions.values())
    reaction_scale = max(abs(primary_vertical_reaction), abs(pynite_vertical_reaction), 1e-9)
    reaction_difference = abs(primary_vertical_reaction - pynite_vertical_reaction) / reaction_scale
    within_tolerance = max(displacement_difference, reaction_difference) <= PARALLEL_TOLERANCE

    return {
        "solver": "PyNiteFEA-3.0.0",
        "analysis_type": "P-Delta" if second_order else "linear_static",
        "verification_status": "unverified",
        "tolerance": PARALLEL_TOLERANCE,
        "primary_maximum_translation_mm": round(primary_max_mm, 8),
        "parallel_maximum_translation_mm": round(pynite_max_mm, 8),
        "translation_relative_difference": round(displacement_difference, 8),
        "primary_vertical_reaction_kn": round(primary_vertical_reaction, 8),
        "parallel_vertical_reaction_kn": round(pynite_vertical_reaction, 8),
        "reaction_relative_difference": round(reaction_difference, 8),
        "within_tolerance": within_tolerance,
        "engineering_check_blocked": not within_tolerance,
    }
