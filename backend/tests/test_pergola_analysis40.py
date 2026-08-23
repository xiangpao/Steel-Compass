from app.core.design_profiles import (
    MemberGroupSpecification,
    MemberInstanceAssignment,
    MemberTypeDefinition,
    RoofLoadSelectionProfile,
    RoofLoadZone,
    RoofOpening,
    RoofSurface,
    SceneGeometryProfile,
    SceneStructuralProfile,
    StructuralMember,
    StructuralNode,
    SupportAssignment,
)
from app.core.pergola_analysis import analyze_pergola_package
from app.core.pergola_loads import build_pergola_load_package
from app.core.site_profile import ProjectSiteProfile


def geometry_23() -> SceneGeometryProfile:
    nodes = []
    members = []
    supports = []
    member_instances = []
    for index, (x, y) in enumerate(((0, 0), (4, 0), (4, 3), (0, 3)), 1):
        nodes.extend([
            StructuralNode(id=f"B{index}", x_m=x, y_m=y, z_m=0),
            StructuralNode(id=f"T{index}", x_m=x, y_m=y, z_m=3),
        ])
        members.append(StructuralMember(id=f"C{index}", start_node_id=f"B{index}", end_node_id=f"T{index}", role="column", group_id="columns"))
        supports.append(SupportAssignment(id=f"S{index}", node_id=f"B{index}", restraint="fixed"))
        member_instances.append(MemberInstanceAssignment(member_id=f"C{index}", member_type_id="columns", mark=f"C{index:02d}"))
    for index, (start, end) in enumerate(((1, 2), (2, 3), (3, 4), (4, 1)), 1):
        members.append(StructuralMember(id=f"M{index}", start_node_id=f"T{start}", end_node_id=f"T{end}", role="beam", group_id="beams"))
        member_instances.append(MemberInstanceAssignment(member_id=f"M{index}", member_type_id="beams", mark=f"M{index:02d}"))
    surface = RoofSurface(id="R1", node_ids=["T1", "T2", "T3", "T4"], form="flat", load_path_group_ids=["beams"])
    return SceneGeometryProfile(
        profile_version="2.3",
        layout_mode="free_plan",
        nodes=nodes,
        members=members,
        supports=supports,
        member_types=[
            MemberTypeDefinition(id="columns", mark_prefix="C", title="柱", role="column", material_grade="Q355B", section_id="shs-150x6"),
            MemberTypeDefinition(id="beams", mark_prefix="M", title="梁", role="beam", material_grade="Q355B", section_id="rhs-200x100x6"),
        ],
        member_instances=member_instances,
        roof_surfaces=[surface],
        roof_load_zones=[RoofLoadZone(id="Z1", surface_id="R1", boundary_node_ids=surface.node_ids, roof_assembly_id="steel-panel", load_path_group_ids=["beams"])],
    )


def site_profile() -> ProjectSiteProfile:
    return ProjectSiteProfile(
        completed_conditions=["wind", "snow", "seismic"],
        region_preset="zhejiang_inland",
        basic_wind_pressure_kpa=0.45,
        basic_snow_pressure_kpa=0.55,
        climate_source_reference="GB 50009-2012 表E.5测试档",
        seismic_level="7_010g",
    )


def roof_selection() -> RoofLoadSelectionProfile:
    return RoofLoadSelectionProfile(roof_assembly_id="steel-panel", maintenance_category="maintenance")


def test_pergola_load_package_is_generated_from_saved_conditions() -> None:
    package = build_pergola_load_package(geometry_23(), site_profile(), roof_selection())
    ids = {item.id for item in package.cases}
    assert {"SELF-WEIGHT", "ROOF-DEAD", "ROOF-LIVE", "ROOF-SNOW", "WIND-X+", "WIND-X-", "WIND-Y+", "WIND-Y-", "WIND-DOWN", "WIND-UP"} <= ids
    assert len([item for item in package.cases if item.kind == "seismic"]) == 4
    assert any(item.design_situation == "seismic" for item in package.combinations)
    assert not package.missing_inputs


def test_no_cover_removes_roof_dead_live_and_snow() -> None:
    selection = RoofLoadSelectionProfile(roof_assembly_id="none", maintenance_category="not_applicable")
    package = build_pergola_load_package(geometry_23(), site_profile(), selection)
    assert not {"ROOF-DEAD", "ROOF-LIVE", "ROOF-SNOW"} & {item.id for item in package.cases}


def test_pergola_analysis_runs_each_case_and_combination_with_member_checks() -> None:
    geometry = geometry_23()
    profile = SceneStructuralProfile(
        profile_version="3.0",
        stage="scheme_estimate",
        member_groups=[
            MemberGroupSpecification(group_id="columns", role="column", material_grade="Q355B", section_catalog_id="shs-150x6", strong_axis_unbraced_length_m=3, weak_axis_unbraced_length_m=3),
            MemberGroupSpecification(group_id="beams", role="beam", material_grade="Q355B", section_catalog_id="rhs-200x100x6", strong_axis_unbraced_length_m=4, weak_axis_unbraced_length_m=4),
        ],
        geometry=geometry,
    )
    package = build_pergola_load_package(geometry, site_profile(), roof_selection())
    result = analyze_pergola_package(profile, package, [])
    assert result["case_results"]
    assert result["combination_results"]
    assert result["balanced"] is True
    assert result["member_checks"]["items"]
    first_case = next(iter(result["case_results"].values()))
    assert first_case["net_loaded_roof_area_m2"] == 12.0
    assert sum(item["tributary_area_m2"] for item in first_case["member_load_assignments"]) == 12.0
    roof_dead = result["case_results"]["ROOF-DEAD"]
    assert roof_dead["member_uniform_loads"]
    assert any(abs(item["qz_kn_m"]) > 0 for item in roof_dead["member_uniform_loads"])
    beam_check = next(item for item in result["member_checks"]["items"] if item["member_id"].startswith("M"))
    assert any(
        max(case["maximum_moment_y_kn_m"], case["maximum_moment_z_kn_m"]) > 0
        for case in beam_check["case_checks"]
    )


def test_roof_opening_is_subtracted_from_tributary_area() -> None:
    geometry = geometry_23()
    opening_nodes = [
        StructuralNode(id="O1", x_m=1, y_m=1, z_m=3),
        StructuralNode(id="O2", x_m=3, y_m=1, z_m=3),
        StructuralNode(id="O3", x_m=3, y_m=2, z_m=3),
        StructuralNode(id="O4", x_m=1, y_m=2, z_m=3),
    ]
    geometry = geometry.model_copy(update={
        "nodes": [*geometry.nodes, *opening_nodes],
        "roof_openings": [RoofOpening(id="OPEN-1", surface_id="R1", node_ids=["O1", "O2", "O3", "O4"])],
        "roof_surfaces": [geometry.roof_surfaces[0].model_copy(update={"opening_ids": ["OPEN-1"]})],
    })
    profile = SceneStructuralProfile(
        profile_version="3.0",
        stage="scheme_estimate",
        member_groups=[
            MemberGroupSpecification(group_id="columns", role="column", material_grade="Q355B", section_catalog_id="shs-150x6", strong_axis_unbraced_length_m=3, weak_axis_unbraced_length_m=3),
            MemberGroupSpecification(group_id="beams", role="beam", material_grade="Q355B", section_catalog_id="rhs-200x100x6", strong_axis_unbraced_length_m=4, weak_axis_unbraced_length_m=4),
        ],
        geometry=geometry,
    )
    package = build_pergola_load_package(geometry, site_profile(), roof_selection())
    result = analyze_pergola_package(profile, package, [])
    first_case = next(iter(result["case_results"].values()))
    assert first_case["net_loaded_roof_area_m2"] == 10.0
    assert sum(item["tributary_area_m2"] for item in first_case["member_load_assignments"]) == 10.0
