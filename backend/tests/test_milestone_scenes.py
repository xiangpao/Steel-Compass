from __future__ import annotations

import pytest

from app.core.engine import calculate
from app.core.scene_catalog import (
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from app.core.scene_graph import execute_scene
from app.core.scene_schemas import SceneNodeCalculation
from app.core.schemas import (
    CalculationModule,
    CalculationRequest,
    LoadDirection,
    LoadItem,
    LoadKind,
    Quantity,
    ReactionEnvelope,
)


def _request(module: CalculationModule, inputs: dict | None = None, *, mode: str = "quick", loads: list[LoadItem] | None = None) -> CalculationRequest:
    return CalculationRequest(
        schema_version="3.1",
        mode=mode,
        module=module,
        project_name="里程碑黄金算例",
        confirmed_assumptions=True,
        inputs=inputs or {},
        loads=loads or [],
    )


def _confirmed_loads(variant):
    return [
        item.model_copy(
            update={
                "confirmed": True,
                "adopted_value": item.recommended_default or item.adopted_value or 0.5,
            },
            deep=True,
        )
        for item in (variant.load_package.items if variant.load_package else [])
    ]


def _execute_public_variant(family_id: str, variant_id: str, values: dict[str, object]):
    family = get_scene_family(family_id)
    assert family is not None
    variant = get_scene_variant(family, variant_id)
    assert variant is not None and variant.availability == "public"
    graph = instantiate_scene_graph(family, variant_id)
    calculations: list[SceneNodeCalculation] = []
    for node in graph.nodes:
        if not node.calculation_module:
            continue
        module = CalculationModule(node.calculation_module)
        inputs = {
            target: values[source]
            for target, source in node.input_bindings.items()
            if source in values
        }
        if module in {
            CalculationModule.STEEL_BEAM,
            CalculationModule.PORTAL_FRAME,
            CalculationModule.CONCRETE_BEAM,
        }:
            inputs.setdefault("reaction_conversion_spacing_m", 1.0)
        if module in {
            CalculationModule.SPREAD_FOOTING,
            CalculationModule.STRIP_FOOTING,
        }:
            inputs.update(
                soil_capacity_kpa=120,
                soil_source="方案快算显式假定",
                groundwater_known=True,
            )
        calculations.append(
            SceneNodeCalculation(
                node_id=node.id,
                calculation=_request(module, inputs),
            )
        )
    return execute_scene(
        family,
        variant_id,
        "quick",
        calculations,
        [node.id for node in graph.nodes if not node.calculation_module],
        load_cases=_confirmed_loads(variant),
    )


@pytest.mark.parametrize(
    ("family_id", "variant_id", "values"),
    [
        (
            "boardwalk-platform",
            "straight",
            {
                "secondary_spacing_m": 0.6,
                "primary_span_m": 3.0,
                "main_span_m": 3.0,
                "primary_spacing_m": 2.0,
                "column_height_m": 2.8,
                "panel_unit_width_m": 1.0,
            },
        ),
        (
            "canopy",
            "single-row",
            {"cantilever_m": 1.8, "width_m": 3.0, "column_height_m": 3.0, "support": "cantilever"},
        ),
        (
            "canopy",
            "double-row",
            {"main_span_m": 3.0, "secondary_spacing_m": 1.0, "frame_span_m": 4.0, "column_height_m": 3.0, "frame_spacing_m": 3.0},
        ),
        (
            "signage-billboard",
            "single-post",
            {"height_m": 2.8, "panel_area_m2": 1.5, "panel_cg_height_m": 2.1, "panel_eccentricity_m": 0.0},
        ),
        (
            "entrance-frame",
            "single-span",
            {"span_m": 5.0, "height_m": 3.2, "bay_spacing_m": 3.0},
        ),
        (
            "landscape-wall-fence",
            "constrained-masonry",
            {"height_m": 2.0, "thickness_mm": 240.0, "column_spacing_m": 3.0, "wall_length_m": 6.0},
        ),
        (
            "bench-planter",
            "bench",
            {"seat_span_m": 1.2, "seat_thickness_mm": 120.0, "support_spacing_m": 1.5},
        ),
        (
            "bench-planter",
            "planter",
            {"wall_height_m": 0.8, "wall_thickness_mm": 180.0, "planter_length_m": 4.0, "soil_unit_weight_kn_m3": 18.0, "soil_friction_angle_deg": 30.0},
        ),
        ("retaining-facility", "cantilever-rc", {}),
    ],
)
def test_public_batch_variants_execute_real_transfer_chain(family_id, variant_id, values):
    result = _execute_public_variant(family_id, variant_id, values)
    if family_id in {"canopy", "signage-billboard", "entrance-frame"}:
        # These fixtures include uplift/eccentric baseplates outside N/A contact.
        # Keep downstream reactions, but explicitly report the missing check.
        assert result.workflow_status == "capability_unavailable"
        calculations = [n.calculation_result for n in result.node_results.values() if n.calculation_result]
        assert any(any(w.code == "baseplate_partial_contact_unresolved" for w in r.warnings) for r in calculations)
        assert any(r.module == CalculationModule.SPREAD_FOOTING for r in calculations)
        return
    assert result.workflow_status == "ready"
    assert result.completed_nodes == result.total_required_nodes
    assert not result.missing_nodes
    assert result.quick_outcome in {"screening_passed", "screening_failed"}


def test_typed_inputs_are_schema_31_and_preserve_declared_units():
    request = CalculationRequest(
        schema_version="3.1",
        mode="quick",
        module="steel_beam",
        confirmed_assumptions=True,
        typed_inputs={
            "module": "steel_beam",
            "values": {
                "span_m": {"value": 3.0, "unit": "m"},
                "section_type": "RHS",
            },
        },
        loads=[LoadItem(kind="live", value=1.0, unit="kN/m", source="golden", confirmed=True)],
    )
    assert request.inputs["span_m"] == 3.0
    assert request.typed_inputs is not None
    assert request.typed_inputs.values["span_m"].unit == "m"


def test_typed_input_rejects_dimensionally_incompatible_units():
    with pytest.raises(ValueError, match="expects unit"):
        CalculationRequest(
            schema_version="3.1",
            mode="quick",
            module="steel_beam",
            confirmed_assumptions=True,
            typed_inputs={
                "module": "steel_beam",
                "values": {"span_m": {"value": 3.0, "unit": "kN"}},
            },
        )


def test_transferred_reaction_does_not_refactor_upstream_effects():
    raw = [
        ReactionEnvelope(
            name="base",
            limit_state="SLS",
            combination_id="sls-1",
            combination_name="SLS-标准组合-活荷载控制",
            direction=LoadDirection.GRAVITY,
            components={"N": Quantity(value=100, unit="kN")},
        ).model_dump(mode="json"),
        ReactionEnvelope(
            name="base",
            limit_state="ULS",
            combination_id="uls-1",
            combination_name="ULS-活荷载控制",
            direction=LoadDirection.GRAVITY,
            components={"N": Quantity(value=145, unit="kN")},
        ).model_dump(mode="json"),
    ]
    result = calculate(
        _request(
            CalculationModule.SPREAD_FOOTING,
            {
                "upstream_reaction_envelopes": raw,
                "length_m": 1.0,
                "width_m": 1.0,
                "thickness_mm": 2000,
                "column_x_mm": 300,
                "column_y_mm": 300,
                "embedment_m": 1.0,
                "soil_cover_m": 0.0,
                "soil_capacity_kpa": 1000,
                "soil_source": "golden",
                "groundwater_known": True,
            },
        )
    )
    assert result.reactions["N_service"].value == pytest.approx(150.0)
    assert result.reactions["N_design"].value == pytest.approx(210.0)


def test_positive_and_negative_sign_wind_keep_direction_in_reaction_packet():
    for direction in (LoadDirection.X_POSITIVE, LoadDirection.X_NEGATIVE):
        result = calculate(
            _request(
                CalculationModule.STEEL_CANTILEVER_POST,
                loads=[
                    LoadItem(
                        kind=LoadKind.WIND,
                        value=0.6,
                        unit="kN/m2",
                        source="golden wind",
                        direction=direction,
                        confirmed=True,
                    )
                ],
            )
        )
        first = result.reaction_envelopes[0]
        assert first.direction is direction
        assert first.components["Vx"].value * (1 if direction is LoadDirection.X_POSITIVE else -1) >= 0


@pytest.mark.parametrize("module, inputs", [
    (CalculationModule.MASONRY_WALL, {"height_m": 2.0, "thickness_mm": 240, "column_spacing_m": 3.0}),
    (CalculationModule.RC_WALL, {"height_m": 1.2, "thickness_mm": 180, "bar_dia_mm": 12, "bar_spacing_mm": 200}),
])
def test_negative_wall_wind_preserves_signed_reaction_and_positive_demand(module, inputs):
    result = calculate(
        _request(
            module,
            inputs,
            loads=[LoadItem(kind=LoadKind.WIND, value=0.5, unit="kN/m2", source="golden wind", direction=LoadDirection.X_NEGATIVE, confirmed=True)],
        )
    )
    negative = [item for item in result.reaction_envelopes if item.direction is LoadDirection.X_NEGATIVE]
    assert negative
    assert all(item.components["Vx"].value <= 0 for item in negative)
    assert result.steps[0].result.value >= 0


def test_unverified_professional_result_remains_incomplete():
    result = calculate(
        _request(
            CalculationModule.RETAINING_WALL,
            mode="professional",
            inputs={
                "retained_height_m": 1.5,
                "base_width_m": 1.6,
                "toe_length_m": 0.45,
                "stem_thickness_mm": 200,
                "base_thickness_m": 0.35,
                "soil_unit_weight_kn_m3": 18,
                "soil_friction_angle_deg": 30,
                "surcharge_kpa": 0,
                "water_level_depth_m": 0,
                "submerged_depth_m": 0,
                "soil_capacity_kpa": 120,
                "base_friction_coefficient": 0.35,
                "stem_moment_capacity_kn_m_per_m": 80,
                "soil_source": "勘察报告第5页",
                "groundwater_known": True,
            },
            loads=[LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m", source="勘察报告", confirmed=True)],
        )
    )
    assert result.status == "incomplete"
    assert result.engineering_status == "incomplete"
    assert result.result_class == "professional_check"


def test_boardwalk_load_change_reaches_downstream_foundation_and_six_components():
    values = {
        "secondary_spacing_m": 0.6,
        "primary_span_m": 3.0,
        "main_span_m": 3.0,
        "primary_spacing_m": 2.0,
        "column_height_m": 2.8,
        "panel_unit_width_m": 1.0,
    }
    base = _execute_public_variant("boardwalk-platform", "straight", values)
    family = get_scene_family("boardwalk-platform")
    assert family is not None
    variant = get_scene_variant(family, "straight")
    assert variant is not None
    changed_loads = _confirmed_loads(variant)
    live = next(item for item in changed_loads if item.id == "boardwalk-live")
    live.adopted_value = 7.0
    live.override_reason = "independent load sensitivity check"
    graph = instantiate_scene_graph(family, "straight")
    calculations: list[SceneNodeCalculation] = []
    for node in graph.nodes:
        if not node.calculation_module:
            continue
        module = CalculationModule(node.calculation_module)
        inputs = {
            target: values[source]
            for target, source in node.input_bindings.items()
            if source in values
        }
        if module in {CalculationModule.STEEL_BEAM, CalculationModule.PORTAL_FRAME}:
            inputs.setdefault("reaction_conversion_spacing_m", 1.0)
        if module is CalculationModule.SPREAD_FOOTING:
            inputs.update(soil_capacity_kpa=120, soil_source="golden", groundwater_known=True)
        calculations.append(
            SceneNodeCalculation(node_id=node.id, calculation=_request(module, inputs))
        )
    changed = execute_scene(
        family,
        "straight",
        "quick",
        calculations,
        [node.id for node in graph.nodes if not node.calculation_module],
        load_cases=changed_loads,
    )
    base_n = base.node_results["foundation_left"].calculation_result.reactions["N_service"].value
    changed_n = changed.node_results["foundation_left"].calculation_result.reactions["N_service"].value
    assert changed_n > base_n
    for node_result in changed.node_results.values():
        if node_result.calculation_result:
            for envelope in node_result.calculation_result.reaction_envelopes:
                assert set(envelope.components) == {"N", "Vx", "Vy", "Mx", "My", "T"}
