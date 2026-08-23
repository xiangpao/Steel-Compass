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
