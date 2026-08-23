import pytest

from app.core.design_profiles import (
    BoundaryPoint,
    BoundarySegment,
    CustomSectionCreate,
    DoubleSlopeRoofRule,
    FoundationInstanceAssignment,
    FoundationTypeDefinition,
    MemberInstanceAssignment,
    MemberTypeDefinition,
    PlanBoundaryProfile,
    RoofElevationRule,
    SceneGeometryProfile,
    StructuralMember,
    StructuralNode,
    SupportAssignment,
    calculate_custom_section,
)
from app.core.geometry_topology import discretize_boundary_segment, discretize_plan_boundary, find_member_topology_conflicts, validate_plan_boundary


def rectangle_boundary() -> PlanBoundaryProfile:
    return PlanBoundaryProfile(
        outer_points=[
            BoundaryPoint(id="P1", x_m=0, y_m=0),
            BoundaryPoint(id="P2", x_m=4, y_m=0),
            BoundaryPoint(id="P3", x_m=4, y_m=3),
            BoundaryPoint(id="P4", x_m=0, y_m=3),
        ],
        outer_segments=[
            BoundarySegment(id="S1", start_point_id="P1", end_point_id="P2"),
            BoundarySegment(id="S2", start_point_id="P2", end_point_id="P3"),
            BoundarySegment(id="S3", start_point_id="P3", end_point_id="P4"),
            BoundarySegment(id="S4", start_point_id="P4", end_point_id="P1"),
        ],
    )


def test_rhs_200_100_6_has_traceable_theoretical_weight():
    section = calculate_custom_section(
        CustomSectionCreate(
            name="RHS 200x100x6",
            family="RHS",
            dimensions={"h_mm": 200, "b_mm": 100, "t_mm": 6},
        ),
        section_id="rhs-test",
    )
    assert section.area_mm2 == pytest.approx(3456)
    assert section.self_weight_kn_m == pytest.approx(0.26605, abs=1e-5)
    assert section.theoretical_mass_kg_m == pytest.approx(27.1296)
    assert any("0.26605" in line for line in section.property_trace)
    assert section.assumptions == ["未计圆角和制造公差，按锐角理论截面计算"]


def test_arc_boundary_is_discretized_with_bounded_chords():
    boundary = rectangle_boundary().model_copy(deep=True)
    boundary.outer_segments[0] = BoundarySegment(
        id="S1",
        start_point_id="P1",
        end_point_id="P2",
        kind="arc",
        arc_mid_x_m=2,
        arc_mid_y_m=-1,
    )
    points = discretize_boundary_segment(
        boundary.outer_segments[0],
        {point.id: point for point in boundary.outer_points},
    )
    assert len(points) > 4
    assert max(
            ((points[index + 1][0] - point[0]) ** 2 + (points[index + 1][1] - point[1]) ** 2) ** 0.5
            for index, point in enumerate(points[:-1])
    ) <= 0.501


def test_self_intersecting_boundary_is_rejected():
    boundary = PlanBoundaryProfile(
        outer_points=[
            BoundaryPoint(id="P1", x_m=0, y_m=0),
            BoundaryPoint(id="P2", x_m=2, y_m=2),
            BoundaryPoint(id="P3", x_m=0, y_m=2),
            BoundaryPoint(id="P4", x_m=2, y_m=0),
        ],
        outer_segments=[
            BoundarySegment(id="S1", start_point_id="P1", end_point_id="P2"),
            BoundarySegment(id="S2", start_point_id="P2", end_point_id="P3"),
            BoundarySegment(id="S3", start_point_id="P3", end_point_id="P4"),
            BoundarySegment(id="S4", start_point_id="P4", end_point_id="P1"),
        ],
    )
    with pytest.raises(ValueError, match="自交"):
        validate_plan_boundary(boundary)


def test_removing_column_does_not_remove_roof_nodes_or_beam():
    nodes = [
        StructuralNode(id="B1", x_m=0, y_m=0, z_m=0),
        StructuralNode(id="T1", x_m=0, y_m=0, z_m=3),
        StructuralNode(id="B2", x_m=4, y_m=0, z_m=0),
        StructuralNode(id="T2", x_m=4, y_m=0, z_m=3),
    ]
    geometry = SceneGeometryProfile(
        profile_version="2.0",
        nodes=nodes,
        members=[
            StructuralMember(id="C1", start_node_id="B1", end_node_id="T1", role="column", group_id="columns"),
            StructuralMember(id="B1-2", start_node_id="T1", end_node_id="T2", role="beam", group_id="beams"),
        ],
        supports=[SupportAssignment(id="SUP1", node_id="B1", restraint="fixed")],
    )
    without_column = geometry.model_copy(update={"members": [geometry.members[1]], "supports": []})
    assert {node.id for node in without_column.nodes} == {"B1", "T1", "B2", "T2"}
    assert [member.id for member in without_column.members] == ["B1-2"]


def test_geometry_21_keeps_member_and_foundation_type_assignments_traceable():
    geometry = SceneGeometryProfile(
        profile_version="2.1",
        nodes=[
            StructuralNode(id="B1", x_m=0, y_m=0, z_m=0),
            StructuralNode(id="T1", x_m=0, y_m=0, z_m=3),
            StructuralNode(id="T2", x_m=4, y_m=0, z_m=3),
        ],
        members=[
            StructuralMember(id="C1", start_node_id="B1", end_node_id="T1", role="column", group_id="column"),
            StructuralMember(id="M1", start_node_id="T1", end_node_id="T2", role="beam", group_id="x-main"),
        ],
        supports=[SupportAssignment(id="SUP1", node_id="B1", restraint="fixed")],
        member_types=[
            MemberTypeDefinition(id="column", mark_prefix="C", title="柱", role="column", material_grade="Q355B", section_id="SHS-200x8"),
            MemberTypeDefinition(id="x-main", mark_prefix="X-M", title="X向主梁", role="beam", material_grade="Q355B", section_id="RHS-250x150x8"),
        ],
        member_instances=[
            MemberInstanceAssignment(member_id="C1", member_type_id="column", mark="C01"),
            MemberInstanceAssignment(member_id="M1", member_type_id="x-main", mark="X-M01"),
        ],
        foundation_types=[
            FoundationTypeDefinition(id="foundation-a", mark="F-A", title="阶形基础", form_id="spread-stepped", length_m=1.8, width_m=1.5, thickness_mm=450, embedment_m=1.1, concrete_grade="C30", rebar_grade="HRB400", bottom_x="Φ14@150", bottom_y="Φ12@150")
        ],
        foundation_instances=[FoundationInstanceAssignment(id="FI1", support_id="SUP1", foundation_type_id="foundation-a", mark="F-A-01", column_member_id="C1")],
        roof_elevation=RoofElevationRule(kind="double_slope", datum_height_m=3, slope_deg=8, opposite_slope_deg=8, ridge_start=(0, 0), ridge_end=(4, 0)),
        double_slope_rule=DoubleSlopeRoofRule(ridge_direction_deg=0, ridge_offset_ratio=0.5, left_slope_deg=8, right_slope_deg=8),
    )
    assert geometry.member_instances[1].mark == "X-M01"
    assert geometry.foundation_instances[0].mark == "F-A-01"


def test_geometry_21_double_slope_requires_independent_ridge_rule():
    with pytest.raises(ValueError, match="屋脊方向规则"):
        SceneGeometryProfile(
            profile_version="2.1",
            nodes=[StructuralNode(id="T1", x_m=0, y_m=0, z_m=3), StructuralNode(id="T2", x_m=4, y_m=0, z_m=3)],
            members=[StructuralMember(id="M1", start_node_id="T1", end_node_id="T2", role="beam", group_id="x-main")],
            roof_elevation=RoofElevationRule(kind="double_slope", datum_height_m=3, slope_deg=8, opposite_slope_deg=8, ridge_start=(0, 0), ridge_end=(4, 0)),
        )


def test_unconnected_crossing_members_are_located() -> None:
    nodes = [
        StructuralNode(id="A", x_m=0, y_m=0, z_m=3),
        StructuralNode(id="B", x_m=4, y_m=4, z_m=3),
        StructuralNode(id="C", x_m=0, y_m=4, z_m=3),
        StructuralNode(id="D", x_m=4, y_m=0, z_m=3),
    ]
    members = [
        StructuralMember(id="M1", start_node_id="A", end_node_id="B", role="beam", group_id="beam"),
        StructuralMember(id="M2", start_node_id="C", end_node_id="D", role="beam", group_id="beam"),
    ]
    conflicts = find_member_topology_conflicts(nodes, members)
    assert conflicts == [{"code": "unconnected_member_crossing", "member_ids": ("M1", "M2"), "location": (2.0, 2.0, 3.0)}]


def test_crossing_at_different_elevations_is_not_a_topology_conflict() -> None:
    nodes = [
        StructuralNode(id="A", x_m=0, y_m=0, z_m=3),
        StructuralNode(id="B", x_m=4, y_m=4, z_m=3),
        StructuralNode(id="C", x_m=0, y_m=4, z_m=2),
        StructuralNode(id="D", x_m=4, y_m=0, z_m=2),
    ]
    members = [
        StructuralMember(id="M1", start_node_id="A", end_node_id="B", role="beam", group_id="beam"),
        StructuralMember(id="M2", start_node_id="C", end_node_id="D", role="beam", group_id="beam"),
    ]
    assert find_member_topology_conflicts(nodes, members) == []
