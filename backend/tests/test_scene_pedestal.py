from __future__ import annotations

from copy import deepcopy

from app.core.design_profiles import SceneGeometryProfile
from app.core.scene_pedestal import calculate_scene_pedestals


def _geometry(*, enabled: bool = True, concrete_grade: str = "C30") -> SceneGeometryProfile:
    return SceneGeometryProfile.model_validate({
        "profile_version": "2.2",
        "layout_mode": "custom_grid",
        "nodes": [
            {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0},
            {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
        ],
        "members": [
            {"id": "C1", "start_node_id": "B1", "end_node_id": "T1", "role": "column", "group_id": "columns"},
        ],
        "supports": [
            {"id": "S1", "node_id": "B1", "restraint": "fixed", "foundation_id": "FI1"},
        ],
        "foundation_types": [{
            "id": "fa", "mark": "F-A", "title": "带短柱基础", "form_id": "spread-prismatic",
            "length_m": 2, "width_m": 2, "thickness_mm": 500, "embedment_m": 1.2,
            "concrete_grade": "C30", "rebar_grade": "HRB400", "bottom_x": "Phi14@150",
            "bottom_y": "Phi14@150", "cover_mm": 50,
            "pedestal": {
                "enabled": enabled, "auto_enabled": True, "length_mm": 500, "width_mm": 450,
                "clear_height_mm": 700, "top_elevation_m": 0, "bottom_elevation_m": -0.7,
                "concrete_grade": concrete_grade, "cover_mm": 40,
                "longitudinal_bar_count_x": 2, "longitudinal_bar_count_y": 2,
                "longitudinal_bar_diameter_mm": 16, "stirrup_diameter_mm": 8,
                "stirrup_spacing_mm": 150, "confinement_spacing_mm": 100,
                "dowel_anchorage_mm": 600, "splice_type": "lap", "top_local_reinforcement": True,
            },
        }],
        "foundation_instances": [
            {"id": "FI1", "support_id": "S1", "foundation_type_id": "fa", "mark": "F-A-01", "column_member_id": "C1"},
        ],
    })


REACTION = {
    "B1": {"fx_kn": 12, "fy_kn": 8, "fz_kn": 180, "mx_kn_m": 10, "my_kn_m": 16, "mz_kn_m": 0}
}


def _maximum_utilization(item: dict) -> float:
    return max(float(check["utilization"]) for check in item["checks"])


def test_enabled_pedestal_checks_real_biaxial_reaction_and_reinforcement() -> None:
    item = calculate_scene_pedestals(_geometry(), REACTION)[0]
    assert item["status"] in {"incomplete", "failed"}
    assert item["verification_status"] == "unverified"
    assert item["support_node_id"] == "B1"
    assert len(item["checks"]) == 9
    assert item["input_summary"]["longitudinal_bars"] == "8Φ16"
    assert any(check["name"] == "短柱双向偏压相互作用" for check in item["checks"])
    assert item["steps"][0]["name"] == "短柱根部双向弯矩"


def test_pedestal_demand_increases_with_saved_reaction() -> None:
    baseline = calculate_scene_pedestals(_geometry(), REACTION)[0]
    increased_reaction = deepcopy(REACTION)
    increased_reaction["B1"].update({"fx_kn": 24, "fy_kn": 16, "mx_kn_m": 20, "my_kn_m": 32})
    increased = calculate_scene_pedestals(_geometry(), increased_reaction)[0]
    baseline_biaxial = next(item for item in baseline["checks"] if item["name"] == "短柱双向偏压相互作用")
    increased_biaxial = next(item for item in increased["checks"] if item["name"] == "短柱双向偏压相互作用")
    assert increased_biaxial["utilization"] > baseline_biaxial["utilization"]


def test_disabled_or_unsupported_pedestal_never_silently_calculates() -> None:
    assert calculate_scene_pedestals(_geometry(enabled=False), REACTION) == []
    unsupported = calculate_scene_pedestals(_geometry(concrete_grade="C50"), REACTION)[0]
    assert unsupported["status"] == "not_calculated"
    assert unsupported["issue_code"] == "unsupported_pedestal_concrete_grade"


def test_seismic_combination_triggers_pedestal_detailing_checks() -> None:
    seismic_reaction = {
        "B1": {
            **REACTION["B1"],
            "_cases": [{
                "combination_id": "ULS-SEISMIC-X+",
                "limit_state": "ULS",
                "reaction": REACTION["B1"],
            }],
        }
    }
    item = calculate_scene_pedestals(_geometry(), seismic_reaction)[0]
    assert item["seismic_detail"]["applicable"] is True
    assert any(check["name"] == "短柱抗震轴压比" for check in item["checks"])
    assert any(check["name"] == "短柱抗震加密区箍筋间距" for check in item["checks"])
    assert not any("抗震" in value for value in item["pending_checks"])
