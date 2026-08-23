from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.seismic import build_screening_seismic_package, calculate_seismic_influence_alpha
from app.core.site_profile import (
    CLIMATE_REGION_PRESETS,
    ProjectSiteProfile,
    SEISMIC_DESIGN_PROFILES,
)


def _profile(level: str) -> ProjectSiteProfile:
    return ProjectSiteProfile(
        region_preset="zhejiang_inland",
        recurrence_period_years=50,
        basic_wind_pressure_kpa=0.45,
        basic_snow_pressure_kpa=0.55,
        climate_source_reference="GB 50009-2012 表 E.5",
        seismic_level=level,
    )


def test_zhejiang_presets_are_versioned_and_recurrence_values_are_monotonic() -> None:
    presets = {item.id: item for item in CLIMATE_REGION_PRESETS}
    assert set(presets) == {"zhejiang_coastal", "zhejiang_inland", "zhejiang_mountain", "manual"}
    for preset in (presets["zhejiang_coastal"], presets["zhejiang_inland"], presets["zhejiang_mountain"]):
        assert preset.station_scope
        assert [preset.wind_kpa[key] for key in ("10", "50", "100")] == sorted(preset.wind_kpa.values())
        assert [preset.snow_kpa[key] for key in ("10", "50", "100")] == sorted(preset.snow_kpa.values())
        assert preset.verification_status == "unverified"


def test_manual_region_and_advanced_overrides_require_traceable_sources() -> None:
    with pytest.raises(ValidationError):
        ProjectSiteProfile(
            region_preset="manual",
            basic_wind_pressure_kpa=0.5,
            basic_snow_pressure_kpa=0.2,
            climate_source_reference="x",
            seismic_level="6_005g",
        )
    with pytest.raises(ValidationError):
        ProjectSiteProfile(
            region_preset="zhejiang_inland",
            basic_wind_pressure_kpa=0.45,
            basic_snow_pressure_kpa=0.55,
            climate_source_reference="GB 50009-2012 表 E.5",
            seismic_level="6_005g",
            wind_shape_factor_override=1.5,
        )


def test_seismic_action_increases_by_level_and_balances_directions() -> None:
    packages = [build_screening_seismic_package(_profile(level), 100.0) for level in SEISMIC_DESIGN_PROFILES]
    assert [item.f_ek_kn for item in packages] == sorted(item.f_ek_kn for item in packages)
    assert len({item.f_ek_kn for item in packages}) == 6
    for package in packages:
        signed = {item.direction: item.signed_force_kn for item in package.actions}
        assert signed["x_positive"] == -signed["x_negative"]
        assert signed["y_positive"] == -signed["y_negative"]
        assert package.base_reactions_kn == signed
        assert all(item.combination_factor == 1.0 for item in package.actions)


def test_invalid_seismic_value_never_falls_back_silently() -> None:
    with pytest.raises(ValidationError):
        _profile("7_999g")
    with pytest.raises(ValueError):
        calculate_seismic_influence_alpha(7.2, "II", 0.2)


def test_profile_11_allows_staged_conditions_without_marking_them_complete() -> None:
    partial = ProjectSiteProfile(
        profile_version="1.1",
        completed_conditions=["wind"],
        region_preset="zhejiang_inland",
        basic_wind_pressure_kpa=0.45,
        climate_source_reference="GB 50009-2012 表 E.5",
    )
    assert partial.is_condition_complete("wind")
    assert not partial.is_condition_complete("snow")
    assert not partial.is_condition_complete("seismic")
    with pytest.raises(ValueError, match="snow"):
        partial.require_conditions(["wind", "snow"])


def test_legacy_full_profile_is_read_as_completed_conditions() -> None:
    profile = _profile("7_010g")
    assert profile.profile_version == "1.0"
    assert set(profile.completed_conditions) == {"wind", "snow", "seismic"}
