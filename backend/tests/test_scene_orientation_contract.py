import pytest

from app.core.design_profiles import (
    MemberDesignParameters, MemberInstanceAssignment, MemberSectionOverride,
    MemberTypeDefinition, SceneGeometryProfile, StructuralMember, StructuralNode,
    SupportAssignment,
)
from app.core.scene_space_frame import analyze_scene_space_frame
from app.routers.scene_routes import _structural_profile_from_saved_geometry


def _cantilever():
    return SceneGeometryProfile(
        profile_version="2.3", layout_mode="free_plan",
        nodes=[StructuralNode(id="B", x_m=0, y_m=0, z_m=0),
               StructuralNode(id="T", x_m=4, y_m=0, z_m=0)],
        members=[StructuralMember(id="M", start_node_id="B", end_node_id="T",
                                  role="beam", group_id="beams")],
        supports=[SupportAssignment(id="S", node_id="B", restraint="fixed")],
        member_types=[MemberTypeDefinition(id="beams", mark_prefix="M", title="beam",
            role="beam", material_grade="Q355B", section_id="rhs-200x100x6")],
        member_instances=[MemberInstanceAssignment(member_id="M", member_type_id="beams", mark="M1")],
    )


def _analyze(geometry):
    # Round-trip the exact persisted geometry contract before the API adapter.
    saved = SceneGeometryProfile.model_validate(geometry.model_dump(mode="json"))
    profile = _structural_profile_from_saved_geometry(saved, "scheme_estimate", [])
    return analyze_scene_space_frame(profile, [])


def test_saved_type_orientation_changes_rectangular_member_response():
    geometry = _cantilever()
    strong = _analyze(geometry)
    for member_type in geometry.member_types:
        member_type.orientation = "weak_axis"
    weak = _analyze(geometry)
    assert weak["maximum_translation_mm"] > strong["maximum_translation_mm"] * 2
    assert weak["member_end_forces"] != strong["member_end_forces"]
    for member in geometry.members:
        member.design_parameters = MemberDesignParameters(local_axis_rotation_deg=90)
    assert _analyze(geometry) == weak


@pytest.mark.parametrize("angle", [0, 30, 90])
def test_explicit_member_angle_has_precedence_and_is_not_applied_twice(angle):
    geometry = _cantilever()
    for member in geometry.members:
        member.design_parameters = MemberDesignParameters(local_axis_rotation_deg=angle)
    explicit = _analyze(geometry)
    for member_type in geometry.member_types:
        member_type.orientation = "weak_axis"
    weak_type_with_explicit_angle = _analyze(geometry)
    assert weak_type_with_explicit_angle == explicit


def test_member_override_orientation_is_used_without_explicit_member_angle():
    geometry = _cantilever()
    strong_profile = _structural_profile_from_saved_geometry(geometry, "scheme_estimate", [])
    strong = analyze_scene_space_frame(strong_profile, [])
    weak_profile = strong_profile.model_copy(deep=True)
    weak_profile.member_overrides = [MemberSectionOverride(
        member_id=member.id, material_grade="Q355B", section_id="rhs-200x100x6",
        orientation="weak_axis", source="user_locked",
    ) for member in geometry.members if member.role == "beam"]
    weak = analyze_scene_space_frame(weak_profile, [])
    assert weak["maximum_translation_mm"] > strong["maximum_translation_mm"] * 2
