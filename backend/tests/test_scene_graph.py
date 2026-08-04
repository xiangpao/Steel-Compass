from __future__ import annotations

import pytest

from app.core.errors import CalculationInputError
from app.core.scene_catalog import (
    SCENE_FAMILIES,
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from app.core.scene_graph import (
    downstream_node_ids,
    execute_scene,
    validate_scene_graph,
)
from app.core.scene_schemas import (
    SceneConnection,
    SceneNodeCalculation,
    SceneRevisionResult,
)
from app.core.scenarios import SCENARIOS
from app.core.schemas import (
    CalculationModule,
    CalculationRequest,
    LoadItem,
    LoadKind,
)


def test_scene_catalog_has_five_public_families_and_valid_variant_dags() -> None:
    assert len(SCENE_FAMILIES) == 10
    assert {family.id for family in SCENE_FAMILIES} == {
        "pergola-pavilion",
        "canopy",
        "signage-billboard",
        "landscape-wall-fence",
        "boardwalk-platform",
        "bench-planter",
        "water-feature-pool",
        "landscape-bridge",
        "entrance-frame",
        "retaining-facility",
    }
    assert {family.id for family in SCENE_FAMILIES if family.availability == "public"} == {
        "pergola-pavilion",
        "canopy",
        "signage-billboard",
        "landscape-wall-fence",
        "entrance-frame",
    }
    for family in SCENE_FAMILIES:
        for variant in family.variants:
            order = validate_scene_graph(family, variant.id)
            graph = instantiate_scene_graph(family, variant.id)
            assert "load" in {node.role for node in graph.nodes}
            assert len(order) == len(graph.nodes)


def test_wall_canopy_has_no_foundation_and_column_canopy_has_full_support_chain() -> None:
    family = get_scene_family("canopy")
    assert family is not None
    wall_graph = instantiate_scene_graph(family, "wall-cantilever")
    assert "foundation" not in {node.role for node in wall_graph.nodes}
    assert [node.id for node in wall_graph.nodes] == [
        "environment",
        "secondary_beam",
        "wall_substrate",
        "wall_anchor",
    ]
    column_graph = instantiate_scene_graph(family, "single-row")
    assert {"column", "base_connection", "foundation"} <= {
        node.id for node in column_graph.nodes
    }


def test_landscape_wall_defaults_to_constrained_masonry_complete_chain() -> None:
    family = get_scene_family("landscape-wall-fence")
    assert family is not None
    assert family.default_variant_id == "constrained-masonry"
    graph = instantiate_scene_graph(family, family.default_variant_id)
    assert [node.id for node in graph.nodes] == [
        "wall_loads",
        "masonry_infill",
        "construction_columns",
        "cap_beam",
        "ground_beam",
        "wall_foundation",
    ]


def test_upstream_change_marks_all_downstream_nodes_stale() -> None:
    family = get_scene_family("signage-billboard")
    assert family is not None
    assert downstream_node_ids(family, ["wind_panel"], "single-post") == [
        "post",
        "base_plate",
        "foundation",
    ]


def test_cycle_is_rejected_before_scene_execution() -> None:
    family = get_scene_family("signage-billboard")
    assert family is not None
    cyclic = family.model_copy(deep=True)
    cyclic.graph_template.connections.append(
        SceneConnection(
            id="cycle",
            source_node_id="foundation",
            target_node_id="wind_panel",
            transfer="manual",
        )
    )
    with pytest.raises(CalculationInputError) as caught:
        validate_scene_graph(cyclic)
    assert caught.value.code == "cyclic_scene_graph"


def test_scene_load_packages_are_scenario_specific_and_traceable() -> None:
    package_ids = set()
    for family_id in (
        "pergola-pavilion",
        "canopy",
        "signage-billboard",
        "landscape-wall-fence",
        "entrance-frame",
    ):
        family = get_scene_family(family_id)
        assert family is not None
        variant = get_scene_variant(family, family.default_variant_id)
        assert variant is not None and variant.load_package is not None
        package_ids.add(variant.load_package.id)
        graph_node_ids = {
            node.id for node in instantiate_scene_graph(family, variant.id).nodes
        }
        for item in variant.load_package.items:
            assert item.unit
            assert item.source_reference
            assert item.applicable_when
            assert item.application_target in graph_node_ids
            if item.value_type == "reference_range":
                assert item.recommended_min is not None
                assert item.recommended_max is not None
    assert len(package_ids) == 5


def _confirmed_canopy_loads():
    family = get_scene_family("canopy")
    assert family is not None
    variant = get_scene_variant(family, "wall-cantilever")
    assert variant is not None and variant.load_package is not None
    return [
        item.model_copy(
            update={
                "adopted_value": (
                    item.adopted_value
                    if item.adopted_value is not None
                    else 0.35
                ),
                "confirmed": True,
                "override_reason": (
                    "风雪向导计算值"
                    if item.value_type == "calculated"
                    else item.override_reason
                ),
            },
            deep=True,
        )
        for item in variant.load_package.items
    ]


def _canopy_calculation(mode: str) -> SceneNodeCalculation:
    scenario = next(item for item in SCENARIOS if item.id == "cantilever-canopy")
    return SceneNodeCalculation(
        node_id="secondary_beam",
        calculation=CalculationRequest(
            mode=mode,
            module=scenario.module,
            project_name=scenario.title,
            confirmed_assumptions=True,
            inputs=scenario.inputs,
            loads=[
                item.model_copy(update={"confirmed": True}, deep=True)
                for item in scenario.loads
            ],
        ),
    )


def test_wall_canopy_quick_estimate_closes_but_professional_is_gated() -> None:
    family = get_scene_family("canopy")
    assert family is not None
    confirmed_nodes = ["environment", "wall_substrate", "wall_anchor"]
    quick = execute_scene(
        family,
        "wall-cantilever",
        "quick",
        [_canopy_calculation("quick")],
        confirmed_nodes,
        load_cases=_confirmed_canopy_loads(),
    )
    assert quick.workflow_status == "ready"
    assert quick.engineering_status == "passed"
    assert quick.result_class == "quick_estimate"
    assert quick.completed_nodes == quick.total_required_nodes == 4

    professional = execute_scene(
        family,
        "wall-cantilever",
        "professional",
        [_canopy_calculation("professional")],
        confirmed_nodes,
        load_cases=_confirmed_canopy_loads(),
    )
    assert professional.engineering_status == "incomplete"
    assert professional.workflow_status == "capability_unavailable"
    assert professional.result_class == "professional_check"


def test_all_five_public_default_scenes_close_as_quick_estimates() -> None:
    for family in SCENE_FAMILIES:
        if family.availability != "public":
            continue
        variant = get_scene_variant(family, family.default_variant_id)
        assert variant is not None and variant.load_package is not None
        graph = instantiate_scene_graph(family, variant.id)
        load_cases = [
            item.model_copy(
                update={
                    "adopted_value": (
                        item.adopted_value
                        if item.adopted_value is not None
                        else 0.5
                    ),
                    "confirmed": True,
                    "override_reason": (
                        "风雪向导计算值"
                        if item.value_type == "calculated"
                        else item.override_reason
                    ),
                },
                deep=True,
            )
            for item in variant.load_package.items
        ]
        node_calculations: list[SceneNodeCalculation] = []
        for node in graph.nodes:
            if not node.calculation_module:
                continue
            module = CalculationModule(node.calculation_module)
            scenario = next(item for item in SCENARIOS if item.module == module)
            calculation_loads = [
                item.model_copy(update={"confirmed": True}, deep=True)
                for item in scenario.loads
            ]
            direct_units = {
                CalculationModule.SPREAD_FOOTING: {"kN"},
                CalculationModule.STRIP_FOOTING: {"kN/m"},
                CalculationModule.STEEL_COLUMN: {"kN"},
                CalculationModule.CONCRETE_COLUMN: {"kN"},
                CalculationModule.TIMBER_COLUMN: {"kN"},
            }.get(module, {"kN/m", "kN/m2"})
            for scene_load in load_cases:
                if (
                    scene_load.application_target != node.id
                    or scene_load.unit in direct_units
                ):
                    continue
                calculation_loads.append(
                    LoadItem(
                        kind=LoadKind.DEAD,
                        value=0,
                        unit=(
                            "kN/m"
                            if module is CalculationModule.STRIP_FOOTING
                            else "kN"
                        ),
                        source=scene_load.label,
                        preset_id=scene_load.id,
                        source_reference=f"scene-load:{scene_load.id}",
                        confirmed=True,
                    )
                )
            node_calculations.append(
                SceneNodeCalculation(
                    node_id=node.id,
                    calculation=CalculationRequest(
                        mode="quick",
                        module=module,
                        project_name=family.title,
                        confirmed_assumptions=True,
                        inputs=scenario.inputs,
                        loads=calculation_loads,
                    ),
                )
            )
        result = execute_scene(
            family,
            variant.id,
            "quick",
            node_calculations,
            [node.id for node in graph.nodes if not node.calculation_module],
            load_cases=load_cases,
        )
        assert result.engineering_status == "passed", family.id
        assert result.workflow_status == "ready", family.id
        assert result.completed_nodes == result.total_required_nodes, family.id


def test_legacy_scene_result_remains_readable_without_recalculation() -> None:
    legacy = SceneRevisionResult.model_validate(
        {
            "scene_family_id": "canopy",
            "scene_variant_id": "wall-cantilever",
            "mode": "quick",
            "status": "incomplete",
            "completed_nodes": 0,
            "total_required_nodes": 1,
            "node_results": {},
            "missing_nodes": ["旧节点"],
            "stale_node_ids": [],
            "control_path": ["旧节点"],
            "warnings": ["旧快照"],
            "catalog_versions": {"scenes": "CN-SCENE-2026.1"},
        }
    )
    assert legacy.engineering_status == "incomplete"
    assert legacy.workflow_status == "missing_inputs"
    assert legacy.result_class == "quick_estimate"
    assert legacy.load_cases == []
