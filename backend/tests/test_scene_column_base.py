from __future__ import annotations

from copy import deepcopy

from app.core.design_profiles import SceneGeometryProfile
from app.core.scene_column_base import calculate_scene_column_bases


REACTIONS = {
    "B1": {
        "fx_kn": 8.0,
        "fy_kn": 4.0,
        "fz_kn": 120.0,
        "mx_kn_m": 8.0,
        "my_kn_m": 12.0,
        "mz_kn_m": 1.0,
    }
}


def _payload() -> dict:
    return {
        "profile_version": "2.2",
        "layout_mode": "custom_grid",
        "nodes": [
            {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0},
            {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
        ],
        "members": [
            {"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"},
        ],
        "member_types": [
            {"id": "columns", "mark_prefix": "C", "title": "柱", "role": "column", "material_grade": "Q355B", "section_id": "shs-200x8"},
        ],
        "member_instances": [
            {"member_id": "C1", "member_type_id": "columns", "mark": "C01"},
        ],
        "supports": [
            {"id": "S1", "node_id": "B1", "restraint": "fixed", "foundation_id": "FI1"},
        ],
        "foundation_types": [
            {"id": "fa", "mark": "F-A", "title": "基础", "form_id": "spread-prismatic", "length_m": 2, "width_m": 2, "thickness_mm": 500, "embedment_m": 1.2, "concrete_grade": "C30", "rebar_grade": "HRB400", "bottom_x": "Phi14@150", "bottom_y": "Phi14@150", "cover_mm": 50},
        ],
        "foundation_instances": [
            {"id": "FI1", "support_id": "S1", "foundation_type_id": "fa", "mark": "F-A-01", "column_member_id": "C1"},
        ],
        "connection_types": [
            {"id": "base", "mark": "J-A", "title": "柱脚", "family": "column_base", "behavior": "rigid"},
        ],
        "connection_instances": [
            {"id": "J1", "mark": "J-A-01", "connection_type_id": "base", "node_id": "B1", "member_ids": ["C1"], "status": "defined"},
        ],
        "column_bases": [{
            "id": "CB1", "column_member_id": "C1", "support_id": "S1", "connection_instance_id": "J1",
            "base_plate_length_mm": 420, "base_plate_width_mm": 420, "base_plate_thickness_mm": 28,
            "anchor_grade": "5.8", "anchor_diameter_mm": 24, "anchor_count": 4, "anchor_embedment_mm": 600,
            "anchor_spacing_mm": 280, "anchor_edge_mm": 60, "weld_throat_mm": 8,
            "anchor_head_diameter_mm": 60, "anchor_supplementary_reinforcement_area_mm2": 0,
            "anchor_cracked_concrete": True,
            "concrete_bearing_capacity_mpa": 10,
        }],
    }


def test_saved_column_base_runs_real_component_checks() -> None:
    item = calculate_scene_column_bases(
        SceneGeometryProfile.model_validate(_payload()),
        REACTIONS,
        [],
        project_name="亭廊柱脚",
    )[0]
    assert item["status"] in {"incomplete", "failed"}
    assert item["verification_status"] == "unverified"
    assert item["support_node_id"] == "B1"
    assert len(item["checks"]) >= 8
    assert item["section_id"] == "shs-200x8"
    assert item["reaction_envelopes"]
    assert any(check["name"] == "锚栓头部拔出破坏验算" for check in item["checks"])
    assert any(check["name"] == "锚栓劈裂破坏验算" for check in item["checks"])


def test_missing_geometry_and_legacy_anchor_grade_never_use_quick_defaults() -> None:
    missing_payload = _payload()
    missing_payload["column_bases"][0].pop("anchor_spacing_mm")
    missing = calculate_scene_column_bases(
        SceneGeometryProfile.model_validate(missing_payload), REACTIONS, [], project_name="缺参数"
    )[0]
    assert missing["status"] == "not_calculated"
    assert missing["missing_inputs"] == ["anchor_spacing_mm"]

    legacy_payload = deepcopy(_payload())
    legacy_payload["column_bases"][0]["anchor_grade"] = "Q355B"
    legacy = calculate_scene_column_bases(
        SceneGeometryProfile.model_validate(legacy_payload), REACTIONS, [], project_name="旧草稿"
    )[0]
    assert legacy["issue_code"] == "unsupported_anchor_property_class"


def test_circular_column_is_explicitly_outside_rectangular_baseplate_model() -> None:
    payload = _payload()
    payload["member_types"][0]["section_id"] = "chs-168x6"
    item = calculate_scene_column_bases(
        SceneGeometryProfile.model_validate(payload), REACTIONS, [], project_name="圆管柱"
    )[0]
    assert item["status"] == "not_calculated"
    assert item["issue_code"] == "unsupported_section_family"
