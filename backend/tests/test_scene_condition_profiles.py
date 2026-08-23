from __future__ import annotations

import pytest

from app.core.errors import CalculationInputError
from app.core.scene_catalog import get_scene_family, get_scene_variant
from app.core.scene_graph import required_scene_conditions, validate_scene_site_profile
from app.core.site_profile import ProjectSiteProfile


def _wind_only_profile() -> ProjectSiteProfile:
    return ProjectSiteProfile(
        profile_version="1.1",
        completed_conditions=["wind"],
        region_preset="zhejiang_inland",
        recurrence_period_years=50,
        basic_wind_pressure_kpa=0.45,
        climate_source_reference="GB 50009-2012 表 E.5",
    )


@pytest.mark.parametrize(
    ("family_id", "variant_id", "wind", "snow", "seismic"),
    [
        ("pergola-pavilion", "flat-single", "required", "required", "required"),
        ("canopy", "single-row", "required", "required", "required"),
        ("signage-billboard", "single-post", "required", "not_applicable", "required"),
        ("landscape-wall-fence", "constrained-masonry", "required", "not_applicable", "required"),
        ("entrance-frame", "single-span", "required", "not_applicable", "required"),
        ("boardwalk-platform", "straight", "not_applicable", "required", "required"),
        ("bench-planter", "bench", "not_applicable", "not_applicable", "not_applicable"),
        ("bench-planter", "planter", "optional", "not_applicable", "not_supported"),
        ("water-feature-pool", "rect-above", "not_applicable", "not_applicable", "not_supported"),
        ("landscape-bridge", "single-straight", "required", "not_applicable", "not_supported"),
        ("retaining-facility", "cantilever-rc", "not_applicable", "not_applicable", "not_supported"),
    ],
)
def test_public_variants_declare_scene_specific_conditions(
    family_id: str,
    variant_id: str,
    wind: str,
    snow: str,
    seismic: str,
) -> None:
    family = get_scene_family(family_id)
    assert family is not None
    variant = get_scene_variant(family, variant_id)
    assert variant is not None and variant.condition_profile is not None
    assert variant.condition_profile.wind == wind
    assert variant.condition_profile.snow == snow
    assert variant.condition_profile.seismic == seismic


def test_calculated_wind_and_snow_loads_have_matching_condition_contracts() -> None:
    for family_id in (
        "pergola-pavilion",
        "canopy",
        "signage-billboard",
        "landscape-wall-fence",
        "entrance-frame",
        "boardwalk-platform",
        "bench-planter",
        "water-feature-pool",
        "landscape-bridge",
        "retaining-facility",
    ):
        family = get_scene_family(family_id)
        assert family is not None
        for variant in family.variants:
            if variant.availability != "public" or variant.load_package is None:
                continue
            profile = variant.condition_profile
            assert profile is not None
            kinds = {
                item.kind
                for item in variant.load_package.items
                if item.value_type == "calculated"
            }
            if "wind" in kinds:
                assert profile.wind in {"required", "optional"}
            if "snow" in kinds:
                assert profile.snow in {"required", "optional"}


def test_required_conditions_are_revalidated_for_scene_revisions() -> None:
    family = get_scene_family("pergola-pavilion")
    assert family is not None
    variant = get_scene_variant(family, "flat-single")
    assert variant is not None
    assert required_scene_conditions(variant) == ["wind", "snow", "seismic"]
    with pytest.raises(CalculationInputError, match="项目条件向导"):
        validate_scene_site_profile(variant, None)
    with pytest.raises(CalculationInputError, match="项目条件"):
        validate_scene_site_profile(variant, _wind_only_profile())
