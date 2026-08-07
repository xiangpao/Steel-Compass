from __future__ import annotations

import pytest

from app.core.scene_catalog import (
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from app.core.scene_graph import _apply_reaction, downstream_node_ids, validate_scene_graph
from app.core.scene_schemas import SceneConnection
from app.core.schemas import (
    CalculationRequest,
    CalculationResult,
    LoadDirection,
    Quantity,
    ReactionEnvelope,
)


POOL_VARIANTS = (
    "rect-above",
    "rect-semi-buried",
    "rect-buried",
    "rect-above-pile",
    "rect-semi-buried-pile",
    "rect-buried-pile",
)

BRIDGE_VARIANTS = (
    "single-straight",
    "single-steel-timber-pile",
    "multi-span",
    "multi-steel-timber-pile",
    "single-rc-shallow",
    "single-rc-pile",
    "multi-rc-shallow",
    "multi-rc-pile",
)


@pytest.mark.parametrize("variant_id", POOL_VARIANTS)
def test_pool_variants_are_public_real_dags(variant_id: str) -> None:
    family = get_scene_family("water-feature-pool")
    assert family is not None
    variant = get_scene_variant(family, variant_id)
    assert variant is not None
    assert variant.availability == "public"
    assert variant.missing_capabilities == []
    graph = instantiate_scene_graph(family, variant_id)
    assert len(validate_scene_graph(family, variant_id)) == len(graph.nodes)
    assert [node.id for node in graph.nodes[:3]] == [
        "pool_loads",
        "pool_structure",
        "antifloat_support",
    ]
    assert graph.nodes[1].calculation_module == "pool_structure"
    assert all(node.maturity != "planned" for node in graph.nodes)
    assert all(
        item.application_target in {node.id for node in graph.nodes}
        for item in variant.load_package.items
    )
    stale = downstream_node_ids(family, ["pool_loads"], variant_id)
    assert stale[:2] == ["pool_structure", "antifloat_support"]
    if variant_id.endswith("-pile"):
        assert graph.nodes[-1].calculation_module == "pile_group_cap"
        assert stale[-1] == "pile_cap"
    else:
        assert graph.nodes[-1].id == "antifloat_support"
        assert graph.nodes[-1].role == "foundation"


@pytest.mark.parametrize("variant_id", BRIDGE_VARIANTS)
def test_bridge_material_support_variants_are_explicit_and_public(
    variant_id: str,
) -> None:
    family = get_scene_family("landscape-bridge")
    assert family is not None
    variant = get_scene_variant(family, variant_id)
    assert variant is not None
    assert variant.availability == "public"
    assert variant.missing_capabilities == []
    graph = instantiate_scene_graph(family, variant_id)
    assert len(validate_scene_graph(family, variant_id)) == len(graph.nodes)
    superstructure = next(
        node for node in graph.nodes if node.id == "bridge_superstructure"
    )
    assert superstructure.calculation_module == (
        "bridge_rc" if "rc" in variant_id else "bridge_steel_timber"
    )
    expected_support_count = 3 if variant_id.startswith("multi") else 2
    supports = [node for node in graph.nodes if node.role == "foundation"]
    assert len(supports) == expected_support_count
    expected_module = "pile_group_cap" if variant_id.endswith("pile") else "spread_footing"
    assert {node.calculation_module for node in supports} == {expected_module}
    stale = downstream_node_ids(family, ["bridge_loads"], variant_id)
    assert stale[0] == "bridge_superstructure"
    assert set(stale[1:]) == {node.id for node in supports}
    assert all(
        item.requires_source_trace
        for item in graph.connections
        if item.transfer != "manual"
    )


def _q(value: float, unit: str) -> dict[str, float | str]:
    return {"value": value, "unit": unit}


def _pile_request() -> CalculationRequest:
    positions = (
        ("p1", -800, -800, "bored"),
        ("p2", 800, -800, "precast_pipe"),
        ("p3", 800, 800, "precast_square"),
        ("p4", -800, 800, "bored"),
    )
    return CalculationRequest.model_validate(
        {
            "mode": "quick",
            "module": "pile_group_cap",
            "typed_inputs": {
                "module": "pile_group_cap",
                "combination_id": "ULS-1",
                "combination_name": "placeholder",
                "limit_state": "ULS",
                "piles": [
                    {
                        "id": name,
                        "x": _q(x, "mm"),
                        "y": _q(y, "mm"),
                        "diameter_or_side": _q(400, "mm"),
                        "pile_type": pile_type,
                    }
                    for name, x, y, pile_type in positions
                ],
                "capacities": {
                    "compression": _q(500, "kN"),
                    "uplift": _q(200, "kN"),
                    "horizontal": _q(100, "kN"),
                    "source": "investigation report table 8",
                },
                "cap": {
                    "length_x": _q(3000, "mm"),
                    "width_y": _q(3000, "mm"),
                    "thickness": _q(500, "mm"),
                    "column_x": _q(500, "mm"),
                    "column_y": _q(500, "mm"),
                    "cover": _q(70, "mm"),
                    "bar_diameter": _q(20, "mm"),
                },
                "material": {
                    "concrete_ft": _q(1.43, "MPa"),
                    "rebar_fy": _q(360, "MPa"),
                    "provided_rebar_x": _q(2500, "mm2/m"),
                    "provided_rebar_y": _q(2500, "mm2/m"),
                    "minimum_reinforcement_ratio": _q(0.0015, "1"),
                },
                "effects": {
                    "axial": _q(0, "kN"),
                    "shear_x": _q(0, "kN"),
                    "shear_y": _q(0, "kN"),
                    "moment_x": _q(0, "kN*m"),
                    "moment_y": _q(0, "kN*m"),
                    "torsion": _q(0, "kN*m"),
                },
            },
        }
    )


def _support_envelope(name: str, axial: float, shear: float) -> ReactionEnvelope:
    return ReactionEnvelope(
        name=name,
        limit_state="ULS",
        combination_id="ULS-1",
        combination_name="ULS crowd leading",
        direction=LoadDirection.GRAVITY,
        components={
            "N": Quantity(value=axial, unit="kN"),
            "Vx": Quantity(value=shear, unit="kN"),
            "My": Quantity(value=axial * 0.1, unit="kN*m"),
        },
    )


def test_middle_bridge_support_transfers_same_combination_to_pile_cap() -> None:
    source = CalculationResult(
        trace_id="bridge-trace",
        project_name="bridge transfer",
        module="bridge_rc",
        mode="quick",
        status="passed",
        workflow_status="ready",
        quick_outcome="screening_passed",
        result_class="quick_estimate",
        standards=[],
        input_summary={},
        combinations=[],
        reaction_envelopes=[
            _support_envelope("A", 100, 5),
            _support_envelope("B", 180, 8),
            _support_envelope("C", 120, 6),
        ],
    )
    connection = SceneConnection(
        id="bridge-middle-pile",
        source_node_id="bridge_superstructure",
        target_node_id="support_middle",
        transfer="combination_package",
        support="base",
        requires_source_trace=True,
    )
    updated = _apply_reaction(_pile_request(), connection, source)
    assert updated.typed_inputs is not None
    assert updated.typed_inputs.combination_id == "ULS-1"
    assert updated.typed_inputs.effects.axial.value == pytest.approx(180)
    assert updated.typed_inputs.effects.shear_x.value == pytest.approx(8)
    assert updated.typed_inputs.effects.moment_y.value == pytest.approx(18)
    assert updated.inputs["reaction_source_trace_id"] == "bridge-trace"
