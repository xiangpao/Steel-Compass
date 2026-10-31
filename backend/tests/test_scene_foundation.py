from __future__ import annotations

from app.core.design_profiles import (
    ColumnBaseAssembly,
    FoundationInstanceAssignment,
    FoundationStep,
    FoundationTypeDefinition,
    GroundwaterDesignProfile,
    PedestalProfile,
    ProjectGeotechnicalProfile,
    SceneGeometryProfile,
    StructuralMember,
    StructuralNode,
    SupportAssignment,
)
from app.core.scene_foundation import calculate_scene_foundations


def _geometry(
    *,
    form_id: str = "spread-prismatic",
    cover_mm: float | None = 50,
    pedestal: PedestalProfile | None = None,
    steps: list[FoundationStep] | None = None,
    tapered_top_length_m: float | None = None,
    tapered_top_width_m: float | None = None,
    tapered_height_mm: float | None = None,
) -> SceneGeometryProfile:
    return SceneGeometryProfile(
        profile_version="2.2",
        layout_mode="custom_grid",
        nodes=[
            StructuralNode(id="B1", x_m=0, y_m=0, z_m=0),
            StructuralNode(id="T1", x_m=0, y_m=0, z_m=3),
        ],
        members=[StructuralMember(id="C1", start_node_id="B1", end_node_id="T1", role="column", group_id="columns")],
        supports=[SupportAssignment(id="S1", node_id="B1", restraint="fixed", foundation_id="FI1")],
        foundation_types=[FoundationTypeDefinition(
            id="fa",
            mark="F-A",
            title="基础 A",
            form_id=form_id,
            length_m=2.0,
            width_m=1.8,
            thickness_mm=500,
            embedment_m=1.1,
            concrete_grade="C30",
            rebar_grade="HRB400",
            bottom_x="Φ14@150",
            bottom_y="Φ12@150",
            cover_mm=cover_mm,
            steps=steps or [],
            tapered_top_length_m=tapered_top_length_m,
            tapered_top_width_m=tapered_top_width_m,
            tapered_height_mm=tapered_height_mm,
            pedestal=pedestal,
        )],
        foundation_instances=[FoundationInstanceAssignment(
            id="FI1",
            support_id="S1",
            foundation_type_id="fa",
            mark="F-A-01",
            column_member_id="C1",
        )],
        column_bases=[ColumnBaseAssembly(
            id="CB1",
            column_member_id="C1",
            support_id="S1",
            base_plate_length_mm=360,
            base_plate_width_mm=320,
            base_plate_thickness_mm=24,
            anchor_grade="Q355B",
            anchor_diameter_mm=24,
            anchor_count=4,
            anchor_embedment_mm=600,
        )],
    )


def _geotechnical() -> ProjectGeotechnicalProfile:
    return ProjectGeotechnicalProfile(
        stage="scheme_estimate",
        regional_hint_id="zhejiang-inland-reference",
        confirmed_soil_class="可塑黏土",
        bearing_capacity_kpa=120,
        bearing_capacity_source="方案土质档测试值",
        groundwater=GroundwaterDesignProfile(condition="no_influence", source="方案假定"),
    )


REACTIONS = {
    "B1": {
        "fx_kn": 10.0,
        "fy_kn": 5.0,
        "fz_kn": 220.0,
        "mx_kn_m": 12.0,
        "my_kn_m": 20.0,
        "mz_kn_m": 0.0,
    }
}


def test_prismatic_scene_foundation_runs_existing_component_checks() -> None:
    item = calculate_scene_foundations(
        _geometry(),
        REACTIONS,
        _geotechnical(),
        project_name="亭廊",
    )[0]
    assert item["status"] in {"incomplete", "failed"}
    assert item["verification_status"] == "unverified"
    assert len(item["checks"]) >= 10
    assert item["support_node_id"] == "B1"
    assert any("沉降计算" in value for value in item["pending_checks"])


def test_missing_cover_and_nonprismatic_geometry_are_not_silently_defaulted() -> None:
    missing_cover = calculate_scene_foundations(
        _geometry(cover_mm=None), REACTIONS, _geotechnical(), project_name="亭廊"
    )[0]
    assert missing_cover["status"] == "not_calculated"
    assert missing_cover["missing_inputs"] == ["foundation_cover_mm"]

    stepped = calculate_scene_foundations(
        _geometry(form_id="spread-stepped"), REACTIONS, _geotechnical(), project_name="亭廊"
    )[0]
    assert stepped["status"] == "not_calculated"
    assert stepped["missing_inputs"] == ["complete_step_or_taper_geometry"]


def test_complete_step_and_taper_geometry_affect_volume_and_weight() -> None:
    prismatic = calculate_scene_foundations(
        _geometry(), REACTIONS, _geotechnical(), project_name="亭廊"
    )[0]
    stepped = calculate_scene_foundations(
        _geometry(
            form_id="spread-stepped",
            steps=[FoundationStep(length_m=1.4, width_m=1.2, height_mm=250)],
        ),
        REACTIONS,
        _geotechnical(),
        project_name="亭廊",
    )[0]
    tapered = calculate_scene_foundations(
        _geometry(
            form_id="spread-tapered",
            tapered_top_length_m=0.7,
            tapered_top_width_m=0.6,
            tapered_height_mm=300,
        ),
        REACTIONS,
        _geotechnical(),
        project_name="亭廊",
    )[0]
    assert stepped["shape_geometry"]["concrete_volume_m3"] > prismatic["shape_geometry"]["concrete_volume_m3"]
    assert tapered["shape_geometry"]["concrete_volume_m3"] > prismatic["shape_geometry"]["concrete_volume_m3"]
    assert stepped["reactions"]["N_service"]["value"] > prismatic["reactions"]["N_service"]["value"]
    assert tapered["detailed_shape_checks"]
    assert all(level["checks"] for level in tapered["detailed_shape_checks"])


def test_explicit_layers_produce_traceable_settlement_and_softer_soil_increases_it() -> None:
    def profile(modulus: float) -> ProjectGeotechnicalProfile:
        return ProjectGeotechnicalProfile.model_validate({
            "profile_version": "1.1",
            "stage": "project_check",
            "confirmed_soil_class": "可塑黏土",
            "bearing_capacity_kpa": 120,
            "bearing_capacity_source": "勘察报告",
            "settlement_layers": [{"id": "L1", "name": "压缩层", "thickness_m": 6, "compression_modulus_mpa": modulus, "unit_weight_kn_m3": 18, "source": "勘察报告第3层"}],
            "settlement_correction_factor": 1.0,
            "settlement_limit_mm": 30,
            "groundwater": {"condition": "known_levels", "construction_level_m": -2.5, "service_level_m": -2, "antifloat_level_m": -1.5, "source": "勘察报告"},
            "report_name": "测试勘察报告",
            "report_date": "2026-08-24",
        })
    stiff = calculate_scene_foundations(_geometry(), REACTIONS, profile(16), project_name="亭廊")[0]
    soft = calculate_scene_foundations(_geometry(), REACTIONS, profile(8), project_name="亭廊")[0]
    assert stiff["settlement_check"]["layers"]
    assert soft["settlement_check"]["demand"]["value"] > stiff["settlement_check"]["demand"]["value"]
    assert not any("沉降计算" in value for value in soft["pending_checks"])


def test_pedestal_changes_foundation_reaction_chain() -> None:
    pedestal = PedestalProfile(
        enabled=True,
        length_mm=600,
        width_mm=500,
        clear_height_mm=800,
        concrete_grade="C30",
        cover_mm=40,
        longitudinal_bar_count_x=2,
        longitudinal_bar_count_y=2,
        longitudinal_bar_diameter_mm=16,
        stirrup_diameter_mm=8,
        stirrup_spacing_mm=150,
        dowel_anchorage_mm=600,
    )
    plain = calculate_scene_foundations(_geometry(), REACTIONS, _geotechnical(), project_name="亭廊")[0]
    with_pedestal = calculate_scene_foundations(
        _geometry(pedestal=pedestal), REACTIONS, _geotechnical(), project_name="亭廊"
    )[0]
    assert with_pedestal["reactions"]["N_service"]["value"] > plain["reactions"]["N_service"]["value"]
    assert with_pedestal["reactions"]["My"]["value"] > plain["reactions"]["My"]["value"]


def _windy_pedestal_case() -> tuple[SceneGeometryProfile, dict[str, dict]]:
    pedestal = PedestalProfile(
        enabled=True, length_mm=500, width_mm=500, clear_height_mm=900, concrete_grade="C30",
        cover_mm=40, longitudinal_bar_count_x=2, longitudinal_bar_count_y=2,
        longitudinal_bar_diameter_mm=16, stirrup_diameter_mm=8, stirrup_spacing_mm=150,
        dowel_anchorage_mm=600,
    )
    geometry = _geometry(pedestal=pedestal)
    start = geometry.foundation_types[0].model_copy(update={
        "length_m": 1.0, "width_m": 1.0, "thickness_mm": 300, "embedment_m": 1.4})
    uls = {"fx_kn": 7.0, "fy_kn": 0.0, "fz_kn": 78.0, "mx_kn_m": 0.0, "my_kn_m": 4.0, "mz_kn_m": 0.0}
    sls = {"fx_kn": 5.0, "fy_kn": 0.0, "fz_kn": 60.0, "mx_kn_m": 0.0, "my_kn_m": 3.0, "mz_kn_m": 0.0}
    cases = [
        {"combination_id": "ULS-W", "limit_state": "ULS", "reaction": uls},
        {"combination_id": "SLS-STANDARD-W", "limit_state": "SLS", "reaction": sls},
    ]
    return geometry.model_copy(update={"foundation_types": [start]}), {"B1": {**sls, "_cases": cases}}


def test_candidate_sizing_cannot_be_rejected_by_the_final_foundation_check() -> None:
    # Regression: the trapezoid pre-sizer ignored soil cover above the footing
    # and recommended 1.0x1.0 m, which the final check failed on bearing.
    from app.core.design_profiles import recommend_spread_foundation_from_reaction
    from app.core.foundation_candidate_validation import size_scene_foundation_candidate

    geometry, reactions = _windy_pedestal_case()
    start = geometry.foundation_types[0]
    legacy = recommend_spread_foundation_from_reaction(
        foundation_instance_id="FI1", reaction=reactions["B1"]["_cases"][0]["reaction"],
        bearing_capacity_kpa=120, initial_length_m=start.length_m, initial_width_m=start.width_m,
        initial_thickness_mm=start.thickness_mm, pedestal=start.pedestal)
    assert legacy.converged and "与完整基础验算一致性" in legacy.recommended["pending_checks"]
    legacy_size = start.model_copy(update={key: legacy.recommended[key] for key in ("length_m", "width_m", "thickness_mm")})
    legacy_final = calculate_scene_foundations(
        geometry.model_copy(update={"foundation_types": [legacy_size]}), reactions, _geotechnical(), project_name="亭廊")[0]
    assert "地基承载力" in legacy_final["failed_checks"]

    candidate = size_scene_foundation_candidate(geometry, "FI1", reactions, _geotechnical(), project_name="亭廊")
    assert candidate.converged
    chosen = candidate.recommended
    sized = start.model_copy(update={key: chosen[key] for key in ("length_m", "width_m", "thickness_mm")})
    final = calculate_scene_foundations(
        geometry.model_copy(update={"foundation_types": [sized]}), reactions, _geotechnical(), project_name="亭廊")[0]
    assert final["failed_checks"] == []
    assert final["status"] == "incomplete"
    assert chosen["final_check_status"] == "incomplete"
    assert chosen["length_m"] * chosen["width_m"] > legacy.recommended["length_m"] * legacy.recommended["width_m"]
    assert set(chosen["validated_combination_ids"]) == {"ULS-W", "SLS-STANDARD-W"}


def test_candidate_sizing_stops_on_reinforcement_instead_of_growing_plan() -> None:
    from app.core.foundation_candidate_validation import size_scene_foundation_candidate

    geometry, reactions = _windy_pedestal_case()
    thin_bars = geometry.foundation_types[0].model_copy(update={
        "length_m": 2.0, "width_m": 2.0, "bottom_x": "Φ6@400", "bottom_y": "Φ6@400"})
    candidate = size_scene_foundation_candidate(
        geometry.model_copy(update={"foundation_types": [thin_bars]}), "FI1", reactions,
        _geotechnical(), project_name="亭廊")
    assert not candidate.converged
    assert "配筋" in candidate.failure_reason
    assert len(candidate.iterations) == 1


def test_stepped_transition_effective_depth_follows_bar_diameter() -> None:
    # Regression: the transition checks hard-coded d = h - cover - 8 mm while
    # the reference slab check uses h - cover - d_bar/2 per axis.
    geometry = _geometry(form_id="spread-stepped", steps=[FoundationStep(length_m=1.4, width_m=1.2, height_mm=250)])
    foundation_type = geometry.foundation_types[0].model_copy(update={"bottom_x": "Φ25@150", "bottom_y": "Φ20@150"})
    item = calculate_scene_foundations(
        geometry.model_copy(update={"foundation_types": [foundation_type]}), REACTIONS, _geotechnical(), project_name="亭廊")[0]
    level = item["detailed_shape_checks"][0]
    assert level["effective_depth_mm"] == 750 - 50 - 12.5
    assert level["effective_depth_x_mm"] == 750 - 50 - 12.5
    assert level["effective_depth_y_mm"] == 750 - 50 - 10
    assert level["verification_status"] == "unverified"
