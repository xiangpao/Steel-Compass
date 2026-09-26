"""Saved support contracts must never silently change during analysis."""
import pytest

from app.core.design_profiles import (
    MemberGroupSpecification,
    SceneGeometryProfile,
    SceneStructuralProfile,
    StructuralMember,
    StructuralNode,
    SupportAssignment,
)
from app.core.errors import CalculationInputError
from app.core.scene_space_frame import analyze_scene_space_frame


def _profile(support: SupportAssignment) -> SceneStructuralProfile:
    return SceneStructuralProfile(
        profile_version="3.0", stage="scheme_estimate",
        geometry=SceneGeometryProfile(
            profile_version="2.3", layout_mode="free_plan",
            nodes=[StructuralNode(id="B", x_m=0, y_m=0, z_m=0),
                   StructuralNode(id="T", x_m=0, y_m=0, z_m=3)],
            members=[StructuralMember(id="C", start_node_id="B", end_node_id="T",
                                      role="column", group_id="columns")],
            supports=[support],
        ),
        member_groups=[MemberGroupSpecification(
            group_id="columns", role="column", material_grade="Q355B",
            section_catalog_id="shs-150x6",
            strong_axis_unbraced_length_m=3, weak_axis_unbraced_length_m=3,
        )],
    )


@pytest.mark.parametrize("restraint,dofs", [
    ("fixed", ["uz"]),
    ("fixed", ["ux", "uy", "uz"]),
    ("pinned", ["ux", "uy", "uz", "rx"]),
])
def test_noncanonical_support_dofs_are_rejected(restraint, dofs):
    support = SupportAssignment(id="S", node_id="B", restraint=restraint,
                                restrained_dofs=dofs)
    with pytest.raises(CalculationInputError) as caught:
        analyze_scene_space_frame(_profile(support), [])
    assert caught.value.code == "unsupported_support_dofs"


@pytest.mark.parametrize("dofs", [[], ["rz", "ry", "rx", "uz", "uy", "ux"]])
def test_fixed_support_accepts_implicit_or_explicit_canonical_dofs(dofs):
    support = SupportAssignment(id="S", node_id="B", restraint="fixed",
                                restrained_dofs=dofs)
    result = analyze_scene_space_frame(_profile(support), [])
    assert result["support_reactions"]["B"]["fz_kn"] > 0


def test_spring_stiffness_is_explicitly_blocked_until_solver_supports_it():
    support = SupportAssignment(id="S", node_id="B", restraint="spring",
                                spring_stiffness={"uz": 50000})
    with pytest.raises(CalculationInputError) as caught:
        analyze_scene_space_frame(_profile(support), [])
    assert caught.value.code == "unsupported_spring_support"
