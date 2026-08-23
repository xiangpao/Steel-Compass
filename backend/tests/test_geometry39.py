import pytest
from pydantic import ValidationError

from app.core.design_profiles import (
    ColumnBaseAssembly,
    ConnectionInstanceAssignment,
    ConnectionTypeDefinition,
    FoundationInstanceAssignment,
    FoundationTypeDefinition,
    MemberInstanceAssignment,
    MemberTypeDefinition,
    PedestalProfile,
    SceneGeometryProfile,
    StructuralMember,
    StructuralNode,
    SupportAssignment,
)


def geometry_22() -> SceneGeometryProfile:
    return SceneGeometryProfile(
        profile_version="2.2",
        layout_mode="free_plan",
        nodes=[
            StructuralNode(id="B1", x_m=0, y_m=0, z_m=0),
            StructuralNode(id="T1", x_m=0, y_m=0, z_m=3),
        ],
        members=[StructuralMember(id="C1", start_node_id="B1", end_node_id="T1", role="column", group_id="column")],
        member_types=[MemberTypeDefinition(id="column", mark_prefix="C", title="柱", role="column", material_grade="Q355B", section_id="shs-200x8")],
        member_instances=[MemberInstanceAssignment(member_id="C1", member_type_id="column", mark="C01")],
        supports=[SupportAssignment(id="S1", node_id="B1", restraint="fixed", foundation_id="FI1")],
        foundation_types=[FoundationTypeDefinition(id="fa", mark="F-A", title="阶形基础", form_id="spread-stepped", length_m=1.8, width_m=1.5, thickness_mm=450, embedment_m=1.1, concrete_grade="C30", rebar_grade="HRB400", bottom_x="Phi14@150", bottom_y="Phi12@150", pedestal=PedestalProfile(enabled=True, length_mm=500, width_mm=500, clear_height_mm=600, top_elevation_m=0, bottom_elevation_m=-0.6, concrete_grade="C30", cover_mm=40, longitudinal_bar_count_x=2, longitudinal_bar_count_y=2, longitudinal_bar_diameter_mm=16, stirrup_diameter_mm=8, stirrup_spacing_mm=150, dowel_anchorage_mm=600))],
        foundation_instances=[FoundationInstanceAssignment(id="FI1", support_id="S1", foundation_type_id="fa", mark="F-A-01", column_member_id="C1")],
        connection_types=[ConnectionTypeDefinition(id="j-base", mark="J-A", title="柱脚", family="column_base", behavior="rigid")],
        connection_instances=[ConnectionInstanceAssignment(id="JI1", mark="J-A-01", connection_type_id="j-base", node_id="B1", member_ids=["C1"], status="defined")],
        column_bases=[ColumnBaseAssembly(id="CB1", column_member_id="C1", support_id="S1", connection_instance_id="JI1", base_plate_length_mm=360, base_plate_width_mm=360, base_plate_thickness_mm=24, anchor_grade="Q355B", anchor_diameter_mm=24, anchor_count=4, anchor_embedment_mm=600)],
    )


def test_geometry_22_keeps_pedestal_connection_and_column_base_trace() -> None:
    geometry = geometry_22()
    assert geometry.foundation_types[0].pedestal is not None
    assert geometry.foundation_types[0].pedestal.enabled is True
    assert geometry.connection_instances[0].member_ids == ["C1"]
    assert geometry.column_bases[0].support_id == "S1"


def test_enabled_pedestal_requires_geometry_reinforcement_and_anchorage() -> None:
    with pytest.raises(ValidationError, match="启用短柱"):
        PedestalProfile(enabled=True)


def test_geometry_22_rejects_dangling_connection() -> None:
    payload = geometry_22().model_dump(mode="python")
    payload["connection_instances"][0]["member_ids"] = ["missing"]
    with pytest.raises(ValidationError, match="连接实例"):
        SceneGeometryProfile.model_validate(payload)


def test_spring_support_requires_stiffness() -> None:
    with pytest.raises(ValidationError, match="弹簧支承"):
        SupportAssignment(id="S1", node_id="B1", restraint="spring")
