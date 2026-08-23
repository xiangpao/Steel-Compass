from __future__ import annotations

from copy import deepcopy

from app.core.design_profiles import SceneGeometryProfile
from app.core.scene_steel_connection import calculate_scene_steel_connections


def _geometry(
    *,
    form: str = "rhs_full_perimeter_weld",
    beam_section: str = "rhs-200x100x6",
    family: str = "beam_column",
) -> SceneGeometryProfile:
    return SceneGeometryProfile.model_validate({
        "profile_version": "2.2",
        "layout_mode": "custom_grid",
        "nodes": [
            {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0},
            {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
            {"id": "T2", "x_m": 4, "y_m": 0, "z_m": 3},
        ],
        "members": [
            {"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"},
            {"id": "M1", "start_node_id": "T1", "end_node_id": "T2", "role": "beam", "group_id": "beams"},
        ],
        "member_types": [
            {"id": "columns", "mark_prefix": "C", "title": "柱", "role": "column", "material_grade": "Q355B", "section_id": "shs-200x8"},
            {"id": "beams", "mark_prefix": "M", "title": "梁", "role": "beam", "material_grade": "Q355B", "section_id": beam_section},
        ],
        "member_instances": [
            {"member_id": "C1", "member_type_id": "columns", "mark": "C01"},
            {"member_id": "M1", "member_type_id": "beams", "mark": "M01"},
        ],
        "supports": [{"id": "S1", "node_id": "B1", "restraint": "fixed"}],
        "connection_types": [{
            "id": "frame", "mark": "J-B", "title": "矩形管梁柱全周焊接节点",
            "family": family, "behavior": "rigid",
            "supported_section_families": ["SHS", "RHS", "H", "I"],
            "parameters": {
                "connection_form": form,
                "weld_throat_mm": 8,
                "stiffener_thickness_mm": 8,
                "plate_thickness_mm": 12,
                "plate_depth_mm": 240,
                "bolt_count": 4,
                "bolt_diameter_mm": 20,
                "bolt_fu_mpa": 400,
            },
        }],
        "connection_instances": [{
            "id": "J1", "mark": "J-B-01", "connection_type_id": "frame", "node_id": "T1",
            "member_ids": ["C1", "M1"], "status": "defined",
        }],
    })


FORCES = {
    "M1": {
        "start_node_id": "T1", "end_node_id": "T2", "force_basis": "member-local-axis",
        "start": {"n_kn": 4, "vy_kn": 12, "vz_kn": 6, "t_kn_m": 1, "my_kn_m": 5, "mz_kn_m": 8},
        "end": {"n_kn": -4, "vy_kn": -12, "vz_kn": -6, "t_kn_m": -1, "my_kn_m": 5, "mz_kn_m": 8},
    }
}


def _max_utilization(item: dict) -> float:
    return max(float(check["utilization"]) for check in item["checks"])


def test_rhs_welded_beam_column_connection_uses_saved_member_end_force() -> None:
    item = calculate_scene_steel_connections(_geometry(), FORCES, [])[0]
    assert item["status"] in {"complete", "failed"}
    assert item["verification_status"] == "unverified"
    assert item["beam_member_id"] == "M1"
    assert item["beam_end"] == "start"
    assert len(item["checks"]) == 4
    assert item["force_source"]["basis"] == "member-local-axis"


def test_connection_utilization_increases_with_end_force() -> None:
    baseline = calculate_scene_steel_connections(_geometry(), FORCES, [])[0]
    increased_forces = deepcopy(FORCES)
    increased_forces["M1"]["start"]["my_kn_m"] = 15
    increased_forces["M1"]["start"]["mz_kn_m"] = 24
    increased = calculate_scene_steel_connections(_geometry(), increased_forces, [])[0]
    assert _max_utilization(increased) > _max_utilization(baseline)


def test_unsupported_connection_form_and_section_are_explicit() -> None:
    unsupported_form = calculate_scene_steel_connections(_geometry(form="end_plate"), FORCES, [])[0]
    assert unsupported_form["issue_code"] == "unsupported_connection_form"
    unsupported_section = calculate_scene_steel_connections(_geometry(beam_section="h-200x200x8x12"), FORCES, [])[0]
    assert unsupported_section["issue_code"] == "unsupported_section_family"


def test_supported_connection_families_return_a_real_check_package() -> None:
    cases = (
        ("h_end_plate", "beam_column"),
        ("h_welded_flange_web", "beam_column"),
        ("shear_tab", "secondary_beam"),
        ("bolted_splice", "beam_splice"),
        ("gusset_plate", "brace"),
    )
    for form, family in cases:
        item = calculate_scene_steel_connections(
            _geometry(form=form, family=family, beam_section="h-200x200x8x12"),
            FORCES,
            [],
        )[0]
        assert item["connection_form"] == form
        assert item["status"] in {"complete", "failed"}
        assert item["checks"]


def test_missing_connection_parameters_never_pass_silently() -> None:
    geometry = _geometry(form="shear_tab", family="secondary_beam", beam_section="h-200x200x8x12")
    connection_type = geometry.connection_types[0].model_copy(update={"parameters": {"connection_form": "shear_tab"}})
    geometry = geometry.model_copy(update={"connection_types": [connection_type]})
    item = calculate_scene_steel_connections(geometry, FORCES, [])[0]
    assert item["status"] == "not_calculated"
    assert item["issue_code"] == "missing_connection_parameters"


def test_connection_uses_one_concurrent_uls_force_vector() -> None:
    forces = deepcopy(FORCES)
    forces["M1"]["cases"] = [
        {
            "combination_id": "ULS-A",
            "limit_state": "ULS",
            "start": {"n_kn": 120, "vy_kn": 1, "vz_kn": 0, "t_kn_m": 0, "my_kn_m": 0, "mz_kn_m": 0},
            "end": {},
        },
        {
            "combination_id": "ULS-B",
            "limit_state": "ULS",
            "start": {"n_kn": 1, "vy_kn": 2, "vz_kn": 0, "t_kn_m": 0, "my_kn_m": 30, "mz_kn_m": 0},
            "end": {},
        },
    ]
    item = calculate_scene_steel_connections(_geometry(), forces, [])[0]
    assert item["force_source"]["controlling_combination_id"] == "ULS-B"
    assert item["force_source"]["axial_kn"] == 1
    assert item["force_source"]["moment_kn_m"] == 30
