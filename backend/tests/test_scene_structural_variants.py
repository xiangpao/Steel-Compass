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


PUBLIC_STRUCTURAL_VARIANTS = [
    ("pergola-pavilion", "mono-pitch"),
    ("pergola-pavilion", "dual-pitch"),
    ("pergola-pavilion", "multi-bay"),
    ("canopy", "wall-cantilever"),
    ("signage-billboard", "double-post"),
    ("signage-billboard", "ground-mounted"),
    ("signage-billboard", "eccentric-panel"),
    ("entrance-frame", "multi-span"),
    ("entrance-frame", "eccentric-lintel"),
    ("entrance-frame", "unequal-columns"),
    ("boardwalk-platform", "viewing-platform"),
]


@pytest.mark.parametrize(("family_id", "variant_id"), PUBLIC_STRUCTURAL_VARIANTS)
def test_public_structural_variants_use_real_acyclic_graphs(
    family_id: str, variant_id: str
) -> None:
    family = get_scene_family(family_id)
    assert family is not None
    variant = get_scene_variant(family, variant_id)
    assert variant is not None
    assert variant.availability == "public"
    assert variant.missing_capabilities == []
    graph = instantiate_scene_graph(family, variant_id)
    assert len(validate_scene_graph(family, variant_id)) == len(graph.nodes)
    assert all(node.maturity != "planned" for node in graph.nodes)
    assert any(node.role == "load" for node in graph.nodes)
    assert any(node.role == "connection" for node in graph.nodes)
    assert all(
        item.requires_source_trace
        for item in graph.connections
        if item.transfer not in {"manual", "area_to_line"}
    )


@pytest.mark.parametrize(
    ("family_id", "variant_id", "foundation_count"),
    [
        ("pergola-pavilion", "mono-pitch", 2),
        ("pergola-pavilion", "dual-pitch", 2),
        ("pergola-pavilion", "multi-bay", 3),
        ("signage-billboard", "double-post", 2),
        ("signage-billboard", "ground-mounted", 1),
        ("signage-billboard", "eccentric-panel", 1),
        ("entrance-frame", "multi-span", 3),
        ("entrance-frame", "eccentric-lintel", 2),
        ("entrance-frame", "unequal-columns", 2),
        ("boardwalk-platform", "viewing-platform", 2),
    ],
)
def test_ground_supported_variants_end_at_expected_foundations(
    family_id: str, variant_id: str, foundation_count: int
) -> None:
    family = get_scene_family(family_id)
    assert family is not None
    graph = instantiate_scene_graph(family, variant_id)
    foundations = [node for node in graph.nodes if node.role == "foundation"]
    assert len(foundations) == foundation_count
    downstream = downstream_node_ids(
        family,
        [next(node.id for node in graph.nodes if node.role == "load")],
        variant_id,
    )
    assert {node.id for node in foundations} <= set(downstream)


def test_wall_canopy_ends_at_anchor_and_never_creates_foundation() -> None:
    family = get_scene_family("canopy")
    assert family is not None
    graph = instantiate_scene_graph(family, "wall-cantilever")
    assert not any(node.role == "foundation" for node in graph.nodes)
    assert graph.nodes[-1].calculation_module == "wall_anchor"
    assert downstream_node_ids(
        family, ["canopy_loads"], "wall-cantilever"
    ) == ["secondary_beam", "wall_anchor"]


def _source_with_reactions(*envelopes: ReactionEnvelope) -> CalculationResult:
    return CalculationResult(
        trace_id="trace-upstream",
        project_name="transfer test",
        module="continuous_beam",
        mode="quick",
        status="passed",
        workflow_status="ready",
        quick_outcome="screening_passed",
        result_class="quick_estimate",
        standards=[],
        input_summary={},
        combinations=[],
        reaction_envelopes=list(envelopes),
    )


def _envelope(name: str, vertical_kn: float) -> ReactionEnvelope:
    return ReactionEnvelope(
        name=name,
        limit_state="ULS",
        combination_id="ULS-1",
        combination_name="ULS transfer",
        direction=LoadDirection.GRAVITY,
        components={"Vy": Quantity(value=vertical_kn, unit="kN")},
    )


def test_reaction_to_line_updates_only_nonvertical_frame_members() -> None:
    request = CalculationRequest.model_validate(
        {
            "mode": "quick",
            "module": "planar_frame",
            "inputs": {"spacing_m": 2.0},
            "typed_inputs": {
                "module": "planar_frame",
                "combination_id": "ULS-1",
                "combination_name": "ULS transfer",
                "limit_state": "ULS",
                "nodes": [
                    {"id": "left_base", "x": {"value": 0, "unit": "m"}, "y": {"value": 0, "unit": "m"}},
                    {"id": "left_top", "x": {"value": 0, "unit": "m"}, "y": {"value": 3, "unit": "m"}},
                    {"id": "right_top", "x": {"value": 4, "unit": "m"}, "y": {"value": 3, "unit": "m"}},
                    {"id": "right_base", "x": {"value": 4, "unit": "m"}, "y": {"value": 0, "unit": "m"}},
                ],
                "members": [
                    {
                        "id": member_id,
                        "start": start,
                        "end": end,
                        "area": {"value": 5000, "unit": "mm2"},
                        "inertia": {"value": 80000000, "unit": "mm4"},
                        "elastic_modulus": {"value": 200000, "unit": "MPa"},
                        "axial_capacity": {"value": 1000, "unit": "kN"},
                        "shear_capacity": {"value": 500, "unit": "kN"},
                        "moment_capacity": {"value": 300, "unit": "kN*m"},
                    }
                    for member_id, start, end in (
                        ("left_column", "left_base", "left_top"),
                        ("roof", "left_top", "right_top"),
                        ("right_column", "right_top", "right_base"),
                    )
                ],
                "restraints": [
                    {"node": "left_base", "ux": True, "uy": True, "rz": True},
                    {"node": "right_base", "ux": True, "uy": True, "rz": True},
                ],
                "displacement_limit": {"value": 20, "unit": "mm"},
            },
        }
    )
    connection = SceneConnection(
        id="roof-frame",
        source_node_id="roof_members",
        target_node_id="main_frame",
        transfer="reaction_to_line",
        support="left",
        conversion_input_key="spacing_m",
        requires_source_trace=True,
    )
    updated = _apply_reaction(
        request,
        connection,
        _source_with_reactions(
            _envelope("left_support", 8.0),
            _envelope("right_support", 8.0),
        ),
    )
    assert updated.typed_inputs is not None
    assert [item.member for item in updated.typed_inputs.uniform_loads] == ["roof"]
    assert updated.typed_inputs.uniform_loads[0].local_y.value == pytest.approx(-4.0)
    assert updated.inputs["reaction_source_trace_id"] == "trace-upstream"


def test_reaction_package_maps_wall_anchor_design_actions_without_losing_trace() -> None:
    request = CalculationRequest.model_validate(
        {
            "mode": "quick",
            "module": "wall_anchor",
            "typed_inputs": {
                "module": "wall_anchor",
                "plate_width": {"value": 300, "unit": "mm"},
                "plate_height": {"value": 300, "unit": "mm"},
                "plate_thickness": {"value": 14, "unit": "mm"},
                "rebar_count": {"value": 4, "unit": "1"},
                "rebar_rows": {"value": 2, "unit": "1"},
                "rebar_diameter": {"value": 16, "unit": "mm"},
                "rebar_fy": {"value": 360, "unit": "MPa"},
                "rebar_length": {"value": 600, "unit": "mm"},
                "concrete_fc": {"value": 14.3, "unit": "MPa"},
                "concrete_ft": {"value": 1.43, "unit": "MPa"},
                "edge_distance_x": {"value": 60, "unit": "mm"},
                "edge_distance_y": {"value": 60, "unit": "mm"},
                "n_design": {"value": 0, "unit": "kN"},
                "m_design": {"value": 0, "unit": "kN*m"},
                "v_design": {"value": 0, "unit": "kN"},
            },
        }
    )
    connection = SceneConnection(
        id="beam-wall",
        source_node_id="secondary_beam",
        target_node_id="wall_anchor",
        transfer="reaction_package",
        requires_source_trace=True,
    )
    source = _source_with_reactions(
        ReactionEnvelope(
            name="fixed_support",
            limit_state="ULS",
            combination_id="ULS-WIND",
            combination_name="ULS wind",
            direction=LoadDirection.X_POSITIVE,
            components={
                "Vx": Quantity(value=12, unit="kN"),
                "My": Quantity(value=18, unit="kN*m"),
            },
        )
    )
    updated = _apply_reaction(request, connection, source)
    assert updated.typed_inputs is not None
    assert updated.typed_inputs.n_design.value == pytest.approx(0)
    assert updated.typed_inputs.v_design.value == pytest.approx(12)
    assert updated.typed_inputs.m_design.value == pytest.approx(18)
    assert updated.inputs["reaction_source_trace_id"] == "trace-upstream"
