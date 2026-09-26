import pytest

from app.core.design_profiles import DesignLoadCombination
from app.core.pergola_analysis import analyze_pergola_package
from app.core.pergola_loads import PergolaLoadPackage
from app.core.scene_space_frame import analyze_scene_space_frame
from app.core.scene_member_checks import calculate_scene_member_checks
from app.core.hydrostatics import hydrostatic_lateral_action, buoyancy_force
from verification.landscape_safety_cases import analytical_sweep, landscape_frame, pressure


@pytest.mark.parametrize("row", analytical_sweep()["cases"], ids=lambda row: row["case"])
def test_landscape_column_and_span_match_closed_form(row):
    assert row["relative_error"] <= row["tolerance_relative"]


@pytest.mark.parametrize("span,side,wall", [(3,150,6),(4,150,6),(5,150,6),(4,100,4),(4,200,8)])
def test_scene_spacing_and_section_preserve_roof_load_and_support_equilibrium(span, side, wall):
    profile, sections = landscape_frame(span=span, side=side, thickness=wall)
    result = analyze_scene_space_frame(profile, [pressure(value=1)], sections, include_self_weight=False)
    assert result["net_loaded_roof_area_m2"] == pytest.approx(span*3)
    assert sum(r["fz_kn"] for r in result["support_reactions"].values()) == pytest.approx(span*3)
    assert max(abs(v) for v in result["load_balance_kn"]) < 1e-7
    assert result["verification_status"] == "unverified"


def test_scene_member_checks_and_foundations_use_second_order_demand():
    profile, sections = landscape_frame()
    loads = (pressure(value=10), pressure("W",1,"wind","x_positive"))
    package = PergolaLoadPackage(loads, (DesignLoadCombination(id="GW",title="explicit G+W test",design_situation="persistent",source_reference="test only",factors={"G":1,"W":1}),), (), ())
    result = analyze_pergola_package(profile, package, sections)
    combination = result["combination_results"]["GW"]
    assert combination["second_order_amplification_ratio"] > 1.01
    assert combination["analysis_basis"] == "second_order"
    assert combination["maximum_translation_mm"] == combination["second_order_maximum_translation_mm"]
    assert result["maximum_translation_mm"] == combination["second_order_maximum_translation_mm"]
    assert combination["first_order_results"]["support_reactions"] != combination["support_reactions"]
    assert result["member_checks"]["status"] == "complete"
    for member in result["member_checks"]["items"]:
        if member["member_id"].startswith("C"):
            assert member["status"] == "pass"
            envelope = combination["member_end_forces"][member["member_id"]]["along_member"]
            assert envelope["status"] == "complete"
            assert envelope["mesh_convergence_relative"] <= .005
            assert member["verification_status"] == "unverified"


def test_water_depth_has_quadratic_thrust_cubic_moment_and_linear_buoyancy():
    shallow, deep = (hydrostatic_lateral_action(depth_m=h) for h in (1,2))
    assert deep.resultant_kn_per_m / shallow.resultant_kn_per_m == pytest.approx(4)
    assert deep.resultant_kn_per_m*deep.resultant_height_from_base_m / (shallow.resultant_kn_per_m*shallow.resultant_height_from_base_m) == pytest.approx(8)
    assert buoyancy_force(plan_area_m2=12,submerged_depth_m=2) == 2*buoyancy_force(plan_area_m2=12,submerged_depth_m=1)


def test_missing_member_force_case_cannot_pass_as_zero_demand():
    profile, sections = landscape_frame()
    geometry = profile.geometry.model_copy(update={"members": profile.geometry.members[:1]})
    checks = calculate_scene_member_checks(geometry, {"G": {"member_end_forces": {}}},
        {"C1": sections[0]}, {"C1": "Q355B"})
    assert checks["status"] == "incomplete"
    assert checks["items"][0]["status"] == "not_calculated"


@pytest.mark.parametrize("grade", ["Q235B","Q355B"])
def test_scene_thick_plate_strength_cannot_use_conflicting_unverified_table(grade):
    from app.core.scene_member_checks import _design_strength
    assert _design_strength(grade, 90) is None


@pytest.mark.parametrize("reverse", [False,True])
def test_known_failure_cannot_be_hidden_by_incomplete_member_order(reverse):
    profile, sections = landscape_frame()
    members = profile.geometry.members[:2]
    if reverse:
        members = members[::-1]
    geometry = profile.geometry.model_copy(update={"members": members})
    ends = {"n_kn":0,"vy_kn":0,"vz_kn":0,"my_kn_m":1000,"mz_kn_m":0,"t_kn_m":0}
    axial = {**ends,"n_kn":1,"my_kn_m":0}
    checks = calculate_scene_member_checks(geometry, {"ULS": {"analysis_basis":"second_order", "member_end_forces":{
        "C1":{"start":ends,"end":ends},"C2":{"start":axial,"end":axial}}}},
        {"C1":sections[0],"C2":sections[0]}, {"C1":"Q355B","C2":"Q355B"})
    assert checks["status"] == "failed"


@pytest.mark.parametrize("factor,expected", [(0.99,"pass"),(1.01,"failed")])
def test_column_serviceability_boundary_flips_with_actual_displacement(factor, expected):
    from app.core.space_frame import SpaceFrameModel, SpaceNode, SpaceMember, SpaceRestraint, SpaceNodalLoad, analyze_space_frame
    profile, sections = landscape_frame()
    section = sections[0]
    geometry = profile.geometry.model_copy(update={"members": profile.geometry.members[:1]})
    # Vertical 3 m fixed-free column, 150x150x6 sharp-corner SHS. Pure lateral
    # load, no axial action: analytical service displacement limit H/250=12 mm.
    inertia = (150**4-138**4)/12
    force_kn = factor*12*3*206000*inertia/3000**3/1000
    solved = analyze_space_frame(SpaceFrameModel((SpaceNode("B1",0,0,0),SpaceNode("T1",0,0,3)),
        (SpaceMember("C1","B1","T1",section.area_mm2,section.iy_mm4,section.iz_mm4,section.torsion_mm4),),
        (SpaceRestraint("B1",True,True,True,True,True,True),), (SpaceNodalLoad("T1",fx_kn=force_kn),)))
    vector = solved.members["C1"].local_end_forces
    ends = {end: dict(zip(("n_kn","vy_kn","vz_kn","t_kn_m","my_kn_m","mz_kn_m"),
        [value/(1000 if i<3 else 1e6) for i,value in enumerate(vector[offset:offset+6])], strict=True))
        for end,offset in (("start",0),("end",6))}
    displacements = {node:{"ux_mm":r.ux_mm,"uy_mm":r.uy_mm,"uz_mm":r.uz_mm} for node,r in solved.displacements.items()}
    result = calculate_scene_member_checks(geometry, {"SLS": {"member_end_forces":{"C1": ends}, "node_displacements":displacements}},
        {"C1":section},{"C1":"Q355B"})
    assert result["items"][0]["deflection_mm"] == pytest.approx(12*factor)
    assert result["items"][0]["status"] == expected
    assert result["items"][0]["verification_status"] == "unverified"
