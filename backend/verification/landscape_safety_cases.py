"""Reproducible scheme sensitivity cases; analytical references are not approval.

Closed forms assume prismatic Euler-Bernoulli members, small displacement,
ideal restraints, no shear deformation or local buckling. Sections use sharp
corners (not manufacturer section tables). No production function generates
the reference values. Units: N, mm, MPa internally; kN and m for model loads.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.design_profiles import (
    CustomSectionCreate, MemberGroupSpecification, RoofSurface,
    SceneGeometryProfile, SceneStructuralProfile, StructuralMember,
    StructuralNode, SupportAssignment, calculate_custom_section,
)
from app.core.scene_schemas import SceneLoadItem
from app.core.space_frame import (
    SpaceFrameModel, SpaceMember, SpaceMemberUniformLoad, SpaceNodalLoad,
    SpaceNode, SpaceRestraint, analyze_space_frame,
)


def landscape_frame(span=4.0, width=3.0, height=3.0, side=150.0, thickness=6.0):
    """Explicit four-column geometry, all supports fixed, no hidden foundations."""
    section = calculate_custom_section(CustomSectionCreate(
        name=f"SHS {side}x{thickness}", family="SHS",
        dimensions={"b_mm": side, "h_mm": side, "t_mm": thickness},
        source_reference="analytical sharp-corner section test fixture",
    ), section_id="sweep-column")
    nodes, members, supports = [], [], []
    for i, (x, y) in enumerate(((0, 0), (span, 0), (span, width), (0, width)), 1):
        nodes.extend([StructuralNode(id=f"B{i}", x_m=x, y_m=y, z_m=0),
                      StructuralNode(id=f"T{i}", x_m=x, y_m=y, z_m=height)])
        members.append(StructuralMember(id=f"C{i}", start_node_id=f"B{i}", end_node_id=f"T{i}", role="column", group_id="columns"))
        supports.append(SupportAssignment(id=f"S{i}", node_id=f"B{i}", restraint="fixed"))
    for i, (a, b) in enumerate(((1, 2), (2, 3), (3, 4), (4, 1)), 1):
        members.append(StructuralMember(id=f"M{i}", start_node_id=f"T{a}", end_node_id=f"T{b}", role="beam", group_id="beams"))
    geometry = SceneGeometryProfile(profile_version="2.3", layout_mode="free_plan", nodes=nodes,
        members=members, supports=supports, roof_surfaces=[RoofSurface(id="R", form="flat", node_ids=["T1", "T2", "T3", "T4"], load_path_group_ids=["beams"])])
    profile = SceneStructuralProfile(stage="scheme_estimate", geometry=geometry, member_groups=[
        MemberGroupSpecification(group_id="columns", role="column", material_grade="Q355B", custom_section_id=section.id,
            strong_axis_unbraced_length_m=height, weak_axis_unbraced_length_m=height),
        MemberGroupSpecification(group_id="beams", role="beam", material_grade="Q355B", section_catalog_id="rhs-200x100x6",
            strong_axis_unbraced_length_m=span, weak_axis_unbraced_length_m=span),
    ])
    return profile, [section]


def pressure(case_id="G", value=1.0, kind="dead", direction="gravity"):
    return SceneLoadItem(id=case_id, label=case_id, kind=kind, value_type="calculated", adopted_value=value,
        unit="kPa", source_reference="explicit test action, not a site design value", applicable_when="analytical fixture",
        distribution="pressure", direction=direction, application_target="roof_load_zones")


def analytical_sweep():
    rows = []
    # Column under a fixed 1 kN horizontal tip action: isolates stiffness from wind area.
    for side, wall, length in ((100, 4, 3), (150, 4, 3), (150, 6, 3), (200, 6, 3), (150, 6, 4)):
        area = side**2 - (side - 2*wall)**2
        inertia = (side**4 - (side - 2*wall)**4) / 12
        section = calculate_custom_section(CustomSectionCreate(name="reference", family="SHS",
            dimensions={"b_mm": side, "h_mm": side, "t_mm": wall}, source_reference="analytical fixture"), section_id="reference")
        model = SpaceFrameModel((SpaceNode("A",0,0,0), SpaceNode("B",length,0,0)),
            (SpaceMember("C","A","B",section.area_mm2,section.iy_mm4,section.iz_mm4,section.torsion_mm4),),
            (SpaceRestraint("A",True,True,True,True,True,True),), (SpaceNodalLoad("B",fy_kn=1),))
        result = analyze_space_frame(model)
        expected = 1000*(length*1000)**3/(3*206000*inertia)
        actual = result.displacements["B"].uy_mm
        rows.append(dict(case=f"column-{side}x{wall}-H{length}", side_mm=side, wall_mm=wall, height_m=length,
            reference_area_mm2=area, reference_inertia_mm4=inertia, reference_displacement_mm=expected,
            actual_displacement_mm=actual, relative_error=abs(actual-expected)/expected,
            root_moment_kn_m=abs(result.reactions["A"].mz_kn_m), tolerance_relative=1e-9))
    # Beam between columns: fixed pressure 1 kPa, tributary width 2 m -> q=2 kN/m.
    for span in (2.0, 3.0, 4.0):
        for support in ("simple", "cantilever"):
            inertia = (100*200**3-88*188**3)/12
            restraints = ((SpaceRestraint("A",True,True,True,True,True,True),) if support == "cantilever" else
                (SpaceRestraint("A",ux=True,uy=True,uz=True,rx=True), SpaceRestraint("B",uy=True,uz=True)))
            model = SpaceFrameModel((SpaceNode("A",0,0,0), SpaceNode("B",span/2,0,0), SpaceNode("D",span,0,0)),
                (SpaceMember("m1","A","B",3456,inertia,inertia,1e6), SpaceMember("m2","B","D",3456,inertia,inertia,1e6)),
                tuple(SpaceRestraint("D",uy=True,uz=True) if r.node=="B" else r for r in restraints),
                member_uniform_loads=(SpaceMemberUniformLoad("m1",qy_kn_m=-2),SpaceMemberUniformLoad("m2",qy_kn_m=-2)))
            result = analyze_space_frame(model)
            expected = (5/384 if support=="simple" else 1/8)*2*(span*1000)**4/(206000*inertia)
            actual = abs(result.displacements["B" if support=="simple" else "D"].uy_mm)
            rows.append(dict(case=f"{support}-span-{span}", span_m=span, support=support, reference_displacement_mm=expected,
                actual_displacement_mm=actual, relative_error=abs(actual-expected)/expected, tolerance_relative=1e-9))
    return {"evidence_kind": "independent_calculation", "verification_status": "unverified",
            "formula_source": {"publisher": "American Wood Council", "title": "Design Aid 6, Beam Design Formulas, July 2010",
                "url": "https://web-media.awc.org/wp-content/uploads/2021/12/17210710/AWC-DA6-BeamFormulas-0710.pdf",
                "pages": "printed 4, 9, 10 (PDF 4, 9, 10)", "figures": [1, 12, 13],
                "use": "elastic formulas only, material E=206000 MPa explicitly assigned; no foreign code strength substitution"},
            "tolerance_basis": "1e-9 relative for linear closed forms, registered in regression before production execution",
            "scope": "linear elastic analytical sensitivities; not a complete scene or code capacity approval", "cases": rows}


if __name__ == "__main__":
    import sys
    report = analytical_sweep()
    Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if any(row["relative_error"] > row["tolerance_relative"] for row in report["cases"]):
        raise SystemExit("Analytical sensitivity mismatch")
