from __future__ import annotations

from app.core.calculation_library import (
    CALCULATION_LIBRARY_VERSION,
    calculation_library,
)


def test_calculation_library_has_no_placeholder_entries() -> None:
    catalog = calculation_library()
    assert catalog["version"] == CALCULATION_LIBRARY_VERSION
    assert CALCULATION_LIBRARY_VERSION == "CN-CALC-LIB-2026.3"
    assert catalog["items"]
    assert all(item["availability"] == "public" for item in catalog["items"])
    assert all(item["maturity"] == "beta" for item in catalog["items"])
    assert all(item["module"] is not None for item in catalog["items"])
    assert all(item["verification_status"] == "unverified" for item in catalog["items"])


def test_load_environment_entries_bind_to_schema32_modules() -> None:
    items = calculation_library(task="loads_environment")["items"]
    assert {item["id"]: item["module"] for item in items} == {
        "load-combinations": "load_combinations",
        "wind-snow": "wind_snow_guide",
        "soil-water": "soil_water_actions",
    }
    assert {item["task_title"] for item in items} == {"荷载与环境"}


def test_calculation_library_search_still_matches_titles_descriptions_and_presets() -> None:
    assert [item["id"] for item in calculation_library(query="风雪荷载向导")["items"]] == [
        "wind-snow"
    ]
    assert [item["id"] for item in calculation_library(query="导视牌风荷载")["items"]] == [
        "wind-snow"
    ]
    assert [item["id"] for item in calculation_library(query="主动土压力")["items"]] == [
        "soil-water"
    ]


def test_material_and_task_filters_preserve_neutral_and_material_specific_items() -> None:
    steel = calculation_library(material="steel")["items"]
    assert any(item["module"] == "steel_beam" for item in steel)
    assert any(item["module"] == "load_combinations" for item in steel)
    assert not any(item["material"] in {"concrete", "timber", "masonry"} for item in steel)

    foundations = calculation_library(task="foundations_geotechnical")["items"]
    assert {item["id"] for item in foundations} == {
        "spread-footing",
        "strip-footing",
        "pile-foundation",
    }
