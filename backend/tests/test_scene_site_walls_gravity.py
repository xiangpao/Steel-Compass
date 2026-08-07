from __future__ import annotations

import pytest

from app.core.calculation_library import calculation_library
from app.core.scene_catalog import (
    SCENE_FAMILIES,
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from app.core.scene_graph import downstream_node_ids, execute_scene
from app.core.scene_schemas import SceneNodeCalculation
from app.core.schemas import CalculationRequest


def q(value: float, unit: str) -> dict[str, float | str]:
    return {"value": value, "unit": unit}


def wall_cases() -> list[dict]:
    return [
        {"combination_id": "W+", "combination_name": "positive", "limit_state": "ULS", "wind_pressure": q(0.1, "kPa"), "additional_dead_load": q(0.0, "kPa")},
        {"combination_id": "W-", "combination_name": "negative", "limit_state": "ULS", "wind_pressure": q(-0.1, "kPa"), "additional_dead_load": q(0.0, "kPa")},
    ]


def wall_typed(module: str) -> dict:
    common = {
        "module": module,
        "height": q(1.8 if module == "site_rc_wall" else 2.0 if module == "steel_infill_wall" else 1.0, "m"),
        "length": q(8 if module == "steel_infill_wall" else 6, "m"),
        "support_spacing": q(2 if module == "steel_infill_wall" else 3, "m"),
        "opening_ratio": q(0.1, "1"),
        "load_cases": wall_cases(),
    }
    if module == "site_rc_wall":
        return {
            **common, "thickness": q(180, "mm"), "concrete_unit_weight": q(25, "kN/m3"),
            "concrete_fc": q(14.3, "MPa"), "concrete_ft": q(1.43, "MPa"),
            "rebar_fy": q(360, "MPa"), "vertical_rebar": q(1200, "mm2/m"),
            "horizontal_rebar": q(1200, "mm2/m"), "cover": q(30, "mm"),
            "bar_diameter": q(12, "mm"), "minimum_reinforcement_ratio": q(0.0015, "1"),
            "slenderness_limit": q(25, "1"),
        }
    if module == "steel_infill_wall":
        return {
            **common, "infill_dead_load": q(0.5, "kPa"), "post_self_weight": q(0.12, "kN/m"),
            "post_area": q(3000, "mm2"), "post_inertia": q(8e6, "mm4"),
            "post_section_modulus": q(8e4, "mm3"), "steel_elastic_modulus": q(206, "GPa"),
            "steel_yield_strength": q(235, "MPa"), "effective_length_factor": q(1, "1"),
            "slenderness_limit": q(150, "1"), "maximum_post_spacing": q(3, "m"),
        }
    return {
        **common, "thickness": q(240, "mm"), "masonry_unit_weight": q(19, "kN/m3"),
        "masonry_bending_strength": q(0.4, "MPa"), "masonry_shear_strength": q(0.15, "MPa"),
        "masonry_compression_strength": q(2, "MPa"), "slenderness_limit": q(15, "1"),
        "minimum_thickness": q(120, "mm"), "maximum_height": q(1.5, "m"),
    }


def request(module: str, typed: dict, *, mode: str = "quick") -> CalculationRequest:
    return CalculationRequest.model_validate(
        {
            "schema_version": "3.2", "mode": mode, "module": module,
            "project_name": f"scene-{module}", "standard_profile": "CN-2026.1",
            "typed_inputs": typed, "loads": [],
        }
    )


def gravity_typed() -> dict:
    return {
        "module": "gravity_retaining_wall", "combination_id": "ULS-G", "combination_name": "soil water", "limit_state": "ULS",
        "retained_height": q(2, "m"), "base_width": q(2.4, "m"), "base_slab_thickness": q(0.3, "m"),
        "wall_bottom_thickness": q(1.2, "m"), "wall_top_thickness": q(0.5, "m"), "toe_projection": q(0.7, "m"),
        "wall_unit_weight": q(24, "kN/m3"), "soil_unit_weight": q(18, "kN/m3"), "soil_friction_angle": q(30, "deg"),
        "surcharge": q(5, "kPa"), "base_friction_coefficient": q(0.6, "1"), "soil_bearing_capacity": q(300, "kPa"),
        "material_compressive_design": q(1000, "kPa"), "water_depth_behind": q(0.8, "m"), "water_unit_weight": q(10, "kN/m3"),
        "uplift_head_toe": q(0, "m"), "uplift_head_heel": q(0.5, "m"), "sliding_safety_factor": q(1, "1"),
        "overturning_safety_factor": q(1, "1"),
    }


def test_all_scene_variants_are_public_and_dags_are_valid() -> None:
    assert all(
        variant.availability == "public"
        for family in SCENE_FAMILIES
        for variant in family.variants
    )
    wall = get_scene_family("landscape-wall-fence")
    retaining = get_scene_family("retaining-facility")
    assert wall is not None and retaining is not None
    expected = {
        "concrete-straight": "site_rc_wall",
        "steel-infill": "steel_infill_wall",
        "plain-masonry": "plain_masonry_wall",
    }
    for variant_id, module in expected.items():
        graph = instantiate_scene_graph(wall, variant_id)
        assert [node.id for node in graph.nodes] == ["wall_loads", "wall_system", "foundation_interface"]
        assert graph.nodes[1].calculation_module == module
        assert graph.connections[1].requires_source_trace
    gravity = instantiate_scene_graph(retaining, "gravity")
    assert [node.id for node in gravity.nodes] == ["soil_water_inputs", "gravity_wall", "soil_contact"]
    assert gravity.nodes[1].calculation_module == "gravity_retaining_wall"


def test_wall_load_packages_are_distinct_and_map_into_typed_combinations() -> None:
    family = get_scene_family("landscape-wall-fence")
    assert family is not None
    defaults: dict[str, tuple[float, ...]] = {}
    modules = {
        "concrete-straight": "site_rc_wall",
        "steel-infill": "steel_infill_wall",
        "plain-masonry": "plain_masonry_wall",
    }
    for variant_id, module in modules.items():
        variant = get_scene_variant(family, variant_id)
        assert variant is not None and variant.load_package is not None
        defaults[variant_id] = tuple(item.adopted_value or 0.0 for item in variant.load_package.items)
        result = execute_scene(
            family, variant_id, "quick",
            [SceneNodeCalculation(node_id="wall_system", calculation=request(module, wall_typed(module)))],
        )
        assert result.workflow_status == "ready", result.model_dump_json(indent=2)
        wall_result = result.node_results["wall_system"].calculation_result
        assert wall_result is not None
        positive = next(item for item in wall_result.combinations if item.combination_id == "W+")
        expected_pressure = next(
            item.adopted_value for item in variant.load_package.items
            if item.direction == "x_positive"
        )
        height = wall_typed(module)["height"]["value"]
        spacing = wall_typed(module)["support_spacing"]["value"]
        assert positive.effect_components["Vx"].value == pytest.approx(expected_pressure * height * 0.9 * spacing)
        assert result.node_results["foundation_interface"].workflow_status == "ready"
    assert len(set(defaults.values())) == 3


def test_wall_stale_propagation_and_professional_gate() -> None:
    family = get_scene_family("landscape-wall-fence")
    assert family is not None
    assert downstream_node_ids(family, ["wall_loads"], "concrete-straight") == [
        "wall_system", "foundation_interface"
    ]
    result = execute_scene(
        family, "concrete-straight", "professional",
        [SceneNodeCalculation(node_id="wall_system", calculation=request("site_rc_wall", wall_typed("site_rc_wall"), mode="professional"))],
    )
    assert result.workflow_status == "capability_unavailable"
    assert result.engineering_status == "incomplete"
    assert result.verification_status == "unverified"
    assert result.node_results["wall_system"].engineering_status == "incomplete"


def test_gravity_wall_scene_executes_real_core_and_is_professionally_gated() -> None:
    family = get_scene_family("retaining-facility")
    assert family is not None
    quick = execute_scene(
        family, "gravity", "quick",
        [SceneNodeCalculation(node_id="gravity_wall", calculation=request("gravity_retaining_wall", gravity_typed()))],
    )
    assert quick.workflow_status == "ready", quick.model_dump_json(indent=2)
    calculated = quick.node_results["gravity_wall"].calculation_result
    assert calculated is not None and calculated.reaction_envelopes
    assert calculated.module.value == "gravity_retaining_wall"
    professional = execute_scene(
        family, "gravity", "professional",
        [SceneNodeCalculation(node_id="gravity_wall", calculation=request("gravity_retaining_wall", gravity_typed(), mode="professional"))],
    )
    assert professional.workflow_status == "capability_unavailable"
    assert professional.engineering_status == "incomplete"


def test_calculation_library_exposes_real_modules_only() -> None:
    items = calculation_library()["items"]
    mapping = {item["id"]: item for item in items}
    expected = {
        "continuous-beam": "continuous_beam",
        "planar-truss": "planar_truss",
        "two-way-slab": "two_way_slab",
        "timber-base": "timber_connection",
        "pile-foundation": "pile_group_cap",
        "pool-structure": "pool_structure",
        "gravity-retaining-wall": "gravity_retaining_wall",
        "site-rc-wall": "site_rc_wall",
        "steel-infill-wall": "steel_infill_wall",
        "plain-masonry-wall": "plain_masonry_wall",
        "load-combinations": "load_combinations",
        "wind-snow": "wind_snow_guide",
        "soil-water": "soil_water_actions",
    }
    for item_id, module in expected.items():
        assert mapping[item_id]["module"] == module
        assert mapping[item_id]["availability"] == "public"
    assert all(item["availability"] == "public" for item in items)
    assert all(item["module"] is not None for item in items)
