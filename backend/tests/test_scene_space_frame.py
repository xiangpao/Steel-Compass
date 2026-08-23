from __future__ import annotations

from app.core.design_profiles import (
    GridAxisDefinition,
    MemberSpecification,
    SceneGeometryProfile,
    SceneStructuralProfile,
    StructuralMember,
    StructuralNode,
)
from app.core.scene_schemas import SceneLoadItem
from app.core.scene_space_frame import analyze_scene_space_frame


def _profile(beam_section: str) -> SceneStructuralProfile:
    geometry = SceneGeometryProfile(
        layout_mode="custom_grid",
        axes=[
            GridAxisDefinition(id="X", direction="x", positions_m=[0, 4]),
            GridAxisDefinition(id="Y", direction="y", positions_m=[0]),
        ],
        nodes=[
            StructuralNode(id="B-1", x_m=0, y_m=0, z_m=0, support="fixed"),
            StructuralNode(id="T-1", x_m=0, y_m=0, z_m=3, column_top=True),
            StructuralNode(id="B-2", x_m=4, y_m=0, z_m=0, support="fixed"),
            StructuralNode(id="T-2", x_m=4, y_m=0, z_m=3, column_top=True),
        ],
        members=[
            StructuralMember(id="C-1", start_node_id="B-1", end_node_id="T-1", role="column", group_id="columns"),
            StructuralMember(id="C-2", start_node_id="B-2", end_node_id="T-2", role="column", group_id="columns"),
            StructuralMember(id="B-1", start_node_id="T-1", end_node_id="T-2", role="beam", group_id="beams"),
        ],
        roof_surfaces=[],
    )
    return SceneStructuralProfile(
        stage="scheme_estimate",
        members=[
            MemberSpecification(node_id="frame", member_role="column", material_grade="Q355B", section_catalog_id="shs-150x6", section_type="SHS", section_name="方管", effective_length_m=3, unbraced_length_m=3, selection_source="recommended"),
            MemberSpecification(node_id="frame", member_role="beam", material_grade="Q355B", section_catalog_id=beam_section, section_type="RHS", section_name="矩形管", effective_length_m=4, unbraced_length_m=4, selection_source="recommended"),
        ],
        foundations=[],
        geometry=geometry,
        catalog_versions={},
    )


def test_parametric_space_frame_uses_real_geometry_and_sections() -> None:
    loads = [
        SceneLoadItem(
            id="roof-dead",
            label="屋面恒载",
            kind="dead",
            value_type="calculated",
            adopted_value=0.5,
            unit="kN/m2",
            source_reference="test",
            applicable_when="test",
            distribution="area",
            direction="gravity",
            application_target="frame",
        )
    ]
    result = analyze_scene_space_frame(_profile("rhs-200x100x6"), loads)
    assert result["node_count"] == 4
    assert result["member_count"] == 3
    assert max(abs(value) for value in result["load_balance_kn"]) < 1e-8
    assert result["maximum_translation_mm"] > 0
    assert len(result["support_reactions"]) == 2
    assert result["member_end_forces"]
    first_force = next(iter(result["member_end_forces"].values()))
    assert set(first_force["start"]) == {"n_kn", "vy_kn", "vz_kn", "t_kn_m", "my_kn_m", "mz_kn_m"}
    assert first_force["force_basis"] == "member-local-axis"
    assert result["parallel_analysis"]["solver"] == "PyNiteFEA-3.0.0"
    assert result["parallel_analysis"]["verification_status"] == "unverified"
    assert result["parallel_analysis"]["within_tolerance"] is True
