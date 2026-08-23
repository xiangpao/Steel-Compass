from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.design_profiles import (
    CustomSectionCreate,
    calculate_custom_section,
    GroundwaterDesignProfile,
    ProjectGeotechnicalProfile,
    SurfaceExposureProfile,
    foundation_system_catalog,
    geotechnical_hint_catalog,
    recommend_spread_foundation,
    recommend_spread_foundation_from_reaction,
    steel_section_catalog,
)


def test_custom_rhs_properties_are_derived_from_dimensions() -> None:
    section = calculate_custom_section(
        CustomSectionCreate(
            name="RHS 200x100x6",
            family="RHS",
            dimensions={"h_mm": 200, "b_mm": 100, "t_mm": 6},
        ),
        section_id="project-rhs-200x100x6",
    )
    assert section.area_mm2 == pytest.approx(3456)
    assert section.iy_mm4 > section.iz_mm4 > 0
    assert section.self_weight_kn_m == pytest.approx(0.266, rel=0.03)


def test_custom_section_rejects_impossible_wall_thickness() -> None:
    with pytest.raises(ValueError, match="壁厚"):
        calculate_custom_section(
            CustomSectionCreate(
                name="invalid",
                family="SHS",
                dimensions={"h_mm": 100, "b_mm": 100, "t_mm": 60},
            ),
            section_id="invalid",
        )


def test_design_catalogs_are_versioned_and_do_not_publish_piles_as_automatic() -> None:
    sections = steel_section_catalog()
    assert {item["family"] for item in sections["items"]} == {"SHS", "RHS", "CHS", "H", "I"}
    assert all(item["verification_status"] == "unverified" for item in sections["items"])
    hints = geotechnical_hint_catalog()
    assert len(hints["items"]) == 3
    assert "不是项目勘察值" in hints["notice"]
    piles = next(item for item in foundation_system_catalog()["items"] if item["id"] == "pile-cap")
    assert piles["availability"] == "planned"
    assert any("不得由城市土质" in item for item in piles["boundaries"])


def test_scheme_geotechnical_profile_requires_confirmed_hint_and_source() -> None:
    with pytest.raises(ValidationError):
        ProjectGeotechnicalProfile(
            stage="scheme_estimate",
            confirmed_soil_class="软黏土",
            bearing_capacity_kpa=60,
            bearing_capacity_source="区域参考",
            groundwater=GroundwaterDesignProfile(condition="unknown", source="待核实"),
        )


def test_project_check_requires_report_settlement_parameter_and_known_water() -> None:
    with pytest.raises(ValidationError):
        ProjectGeotechnicalProfile(
            stage="project_check",
            confirmed_soil_class="可塑黏土",
            bearing_capacity_kpa=150,
            bearing_capacity_source="勘察报告",
            report_name="勘察报告",
            report_date="2026-08-11",
            groundwater=GroundwaterDesignProfile(condition="unknown", source="勘察报告"),
        )


def test_surface_exposure_separates_vertical_enclosure_and_top_cover() -> None:
    profile = SurfaceExposureProfile(
        vertical_enclosure="open_members",
        vertical_open_ratio=0.7,
        top_cover="none",
        source="场景几何",
    )
    assert profile.top_cover == "none"
    with pytest.raises(ValidationError):
        SurfaceExposureProfile(
            vertical_enclosure="none",
            top_cover="none",
            roof_form="flat",
            source="错误组合",
        )


def test_foundation_candidate_uses_saved_biaxial_reaction_and_reports_pending_checks() -> None:
    candidate = recommend_spread_foundation_from_reaction(
        foundation_instance_id="FI1",
        reaction={
            "fx_kn": 12,
            "fy_kn": 5,
            "fz_kn": 280,
            "mx_kn_m": 18,
            "my_kn_m": 32,
            "mz_kn_m": 2,
        },
        bearing_capacity_kpa=120,
        initial_length_m=1.5,
        initial_width_m=1.2,
        initial_thickness_mm=400,
    )
    assert candidate.converged
    assert candidate.target_node_id == "FI1"
    assert candidate.recommended is not None
    assert candidate.recommended["column_reaction_n_kn"] == pytest.approx(280)
    assert candidate.recommended["column_reaction_v_kn"] == pytest.approx(13)
    assert candidate.recommended["qmax_kpa"] <= 120
    assert candidate.recommended["qmin_kpa"] >= 0
    assert candidate.recommended["sliding_ratio"] >= 1.3
    assert "冲切" in candidate.recommended["pending_checks"]


def test_foundation_candidate_does_not_treat_uplift_as_bearing_case() -> None:
    candidate = recommend_spread_foundation_from_reaction(
        foundation_instance_id="FI-up",
        reaction={"fz_kn": -20},
        bearing_capacity_kpa=120,
        initial_length_m=1.5,
        initial_width_m=1.5,
        initial_thickness_mm=400,
    )
    assert not candidate.converged
    assert candidate.recommended is None
    assert "上拔" in candidate.failure_reason


def test_foundation_recommendation_is_discrete_monotonic_and_never_switches_to_piles() -> None:
    light = recommend_spread_foundation(node_id="f", vertical_kn=200, moment_kn_m=20, bearing_capacity_kpa=100)
    heavy = recommend_spread_foundation(node_id="f", vertical_kn=400, moment_kn_m=40, bearing_capacity_kpa=100)
    assert light.converged and heavy.converged
    assert heavy.recommended["width_m"] >= light.recommended["width_m"]
    assert all(round(float(item["width_m"]) * 10) == float(item["width_m"]) * 10 for item in heavy.iterations)
    failed = recommend_spread_foundation(node_id="f", vertical_kn=10000, moment_kn_m=10000, bearing_capacity_kpa=20, max_plan_m=1)
    assert not failed.converged
    assert "未自动切换桩基" in failed.failure_reason
