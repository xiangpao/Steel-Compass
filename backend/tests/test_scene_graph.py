from __future__ import annotations

import pytest

from app.core.errors import CalculationInputError
from app.core.design_profiles import (
    FoundationDesignSpecification,
    GroundwaterDesignProfile,
    MemberSpecification,
    ProjectGeotechnicalProfile,
    SceneStructuralProfile,
    SurfaceExposureProfile,
)
from app.core.scene_catalog import (
    SCENE_FAMILIES,
    get_scene_family,
    get_scene_variant,
    instantiate_scene_graph,
)
from app.core.scene_graph import (
    _apply_reaction,
    downstream_node_ids,
    execute_scene,
    validate_scene_graph,
)
from app.core.engine import calculate
from app.core.scene_schemas import (
    SceneConnection,
    SceneNodeCalculation,
    SceneRevisionResult,
)
from app.core.scenarios import SCENARIOS
from app.core.schemas import (
    CalculationRequest,
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
        "boardwalk-platform",
        "bench-planter",
        "water-feature-pool",
        "landscape-bridge",
        "retaining-facility",
    }
    for family in SCENE_FAMILIES:
        for variant in family.variants:
            order = validate_scene_graph(family, variant.id)
            graph = instantiate_scene_graph(family, variant.id)
            assert "load" in {node.role for node in graph.nodes}
            assert len(order) == len(graph.nodes)


def test_steel_pergola_structural_variants_are_public() -> None:
    family = get_scene_family("pergola-pavilion")
    assert family is not None
    public_variants = [item for item in family.variants if item.availability == "public"]
    assert [item.id for item in public_variants] == [
        "guided-grid",
        "flat-single",
        "mono-pitch",
        "dual-pitch",
        "multi-bay",
    ]

    variant = next(item for item in public_variants if item.id == "flat-single")
    assert variant.material_systems == ["钢"]
    capability_by_material = {
        item.material_system: item for item in variant.capabilities
    }
    assert capability_by_material["钢"].availability == "public"
    assert capability_by_material["钢"].graph_template_id == (
        "pergola-flat-single-steel-chain"
    )
    assert capability_by_material["木"].availability == "development"
    assert capability_by_material["木"].missing_capabilities
    assert capability_by_material["钢木混合"].availability == "development"

    for variant_id in ("mono-pitch", "dual-pitch", "multi-bay"):
        item = get_scene_variant(family, variant_id)
        assert item is not None
        assert item.availability == "public"
        assert item.material_systems == ["钢"]
        assert item.missing_capabilities == []


def test_steel_single_span_pergola_has_split_support_chain() -> None:
    family = get_scene_family("pergola-pavilion")
    assert family is not None
    graph = instantiate_scene_graph(family, "flat-single")
    assert [node.id for node in graph.nodes] == [
        "environment",
        "roof_members",
        "main_frame",
        "base_left",
        "base_right",
        "foundation_left",
        "foundation_right",
    ]
    assert graph.nodes[1].input_bindings == {
        "span_m": "frame_spacing_m",
        "tributary_width_m": "purlin_spacing_m",
    }
    assert graph.nodes[3].calculation_module == "steel_baseplate_anchor"
    assert graph.nodes[4].calculation_module == "steel_baseplate_anchor"
    assert [item.transfer for item in graph.connections] == [
        "area_to_line",
        "reaction_to_line",
        "reaction_package",
        "reaction_package",
        "reaction_package",
        "reaction_package",
    ]
    assert all(
        item.requires_source_trace for item in graph.connections[1:]
    )


def test_wall_canopy_has_no_foundation_and_column_canopy_has_full_support_chain() -> None:
    family = get_scene_family("canopy")
    assert family is not None
    wall_graph = instantiate_scene_graph(family, "wall-cantilever")
    assert "foundation" not in {node.role for node in wall_graph.nodes}
    assert [node.id for node in wall_graph.nodes] == [
        "canopy_loads",
        "secondary_beam",
        "wall_anchor",
    ]
    assert wall_graph.nodes[-1].calculation_module == "wall_anchor"
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


def test_wall_canopy_is_public_with_real_wall_anchor_chain() -> None:
    family = get_scene_family("canopy")
    assert family is not None
    variant = get_scene_variant(family, "wall-cantilever")
    assert variant is not None
    assert variant.availability == "public"
    assert variant.missing_capabilities == []
    graph = instantiate_scene_graph(family, "wall-cantilever")
    assert [node.calculation_module for node in graph.nodes] == [
        None,
        "steel_beam",
        "wall_anchor",
    ]
    assert [item.transfer for item in graph.connections] == [
        "manual",
        "reaction_package",
    ]


def test_purlin_reaction_is_traceable_and_converted_without_zero_placeholder() -> None:
    purlin = next(item for item in SCENARIOS if item.id == "pergola-purlin")
    source = calculate(
        CalculationRequest(
            mode="quick",
            module=purlin.module,
            project_name=purlin.title,
            confirmed_assumptions=True,
            inputs=purlin.inputs,
            loads=[item.model_copy(update={"confirmed": True}) for item in purlin.loads],
        )
    )
    frame = next(item for item in SCENARIOS if item.id == "pergola-frame")
    target = CalculationRequest(
        mode="quick",
        module=frame.module,
        project_name=frame.title,
        confirmed_assumptions=True,
        inputs={**frame.inputs, "purlin_spacing_m": 1.0},
        loads=[],
    )
    family = get_scene_family("pergola-pavilion")
    assert family is not None
    connection = instantiate_scene_graph(family, "flat-single").connections[1]
    transferred = _apply_reaction(target, connection, source)

    assert transferred.inputs["reaction_source_trace_id"] == source.trace_id
    assert transferred.inputs["reaction_source_node_id"] == "roof_members"
    assert transferred.inputs["reaction_transfer"] == "reaction_to_line"
    assert transferred.inputs["upstream_reaction_envelopes"]
    assert all(
        envelope["transferred_line_load"]["value"] != 0
        for envelope in transferred.inputs["upstream_reaction_envelopes"]
    )
    assert transferred.loads == []


def test_steel_single_span_pergola_executes_full_traceable_chain() -> None:
    family = get_scene_family("pergola-pavilion")
    assert family is not None
    purlin = next(item for item in SCENARIOS if item.id == "pergola-purlin")
    frame = next(item for item in SCENARIOS if item.id == "pergola-frame")
    footing = next(item for item in SCENARIOS if item.id == "sign-spread-footing")
    calculations = [
        SceneNodeCalculation(
            node_id="roof_members",
            calculation=CalculationRequest(
                mode="quick",
                module=purlin.module,
                project_name="pergola purlin",
                confirmed_assumptions=True,
                inputs={
                    **purlin.inputs,
                    "span_m": 3.0,
                    "tributary_width_m": 1.0,
                },
                loads=[],
            ),
        ),
        SceneNodeCalculation(
            node_id="main_frame",
            calculation=CalculationRequest(
                mode="quick",
                module=frame.module,
                project_name="pergola frame",
                confirmed_assumptions=True,
                inputs={
                    **frame.inputs,
                    "span_m": 4.0,
                    "height_m": 3.0,
                    "purlin_spacing_m": 1.0,
                },
                loads=[],
            ),
        ),
        *[
            SceneNodeCalculation(
                node_id=node_id,
                calculation=CalculationRequest(
                    mode="quick",
                    module="steel_baseplate_anchor",
                    project_name=f"pergola {node_id}",
                    confirmed_assumptions=True,
                    inputs={},
                    loads=[],
                ),
            )
            for node_id in ("base_left", "base_right")
        ],
        *[
            SceneNodeCalculation(
                node_id=node_id,
                calculation=CalculationRequest(
                    mode="quick",
                    module=footing.module,
                    project_name=f"pergola {node_id}",
                    confirmed_assumptions=True,
                    inputs=footing.inputs,
                    loads=[],
                ),
            )
            for node_id in ("foundation_left", "foundation_right")
        ],
    ]
    variant = get_scene_variant(family, "flat-single")
    assert variant is not None and variant.load_package is not None
    load_cases = [
        item.model_copy(
            update={
                "adopted_value": (
                    item.adopted_value
                    if item.adopted_value is not None
                    else 0.30
                ),
                "confirmed": True,
                "override_reason": (
                    "测试风雪向导值"
                    if item.value_type == "calculated"
                    else item.override_reason
                ),
            },
            deep=True,
        )
        for item in variant.load_package.items
    ]
    result = execute_scene(
        family,
        "flat-single",
        "quick",
        calculations,
        ["environment"],
        load_cases=load_cases,
    )

    assert result.workflow_status == "ready", result.model_dump_json(indent=2)
    assert result.engineering_status is None
    assert result.quick_outcome in {"screening_passed", "screening_failed"}
    assert result.completed_nodes == result.total_required_nodes == 7
    assert result.missing_nodes == []
    for node_id in (
        "main_frame",
        "base_left",
        "base_right",
        "foundation_left",
        "foundation_right",
    ):
        calculation = result.node_results[node_id].calculation_result
        assert calculation is not None
        assert calculation.reaction_envelopes
    frame_result = result.node_results["main_frame"].calculation_result
    assert frame_result is not None
    uls = next(item for item in frame_result.combinations if item.limit_state == "ULS")
    assert uls.factored_by_kind["upstream_line_load"].value != 0
    left = next(
        item
        for item in frame_result.reaction_envelopes
        if item.name == "left_base" and item.combination_id == uls.combination_id
    )
    right = next(
        item
        for item in frame_result.reaction_envelopes
        if item.name == "right_base" and item.combination_id == uls.combination_id
    )
    assert left.components["N"].value + right.components["N"].value == pytest.approx(
        uls.total.value * 4,
        rel=1e-6,
    )

    geotechnical = ProjectGeotechnicalProfile(
        stage="scheme_estimate",
        regional_hint_id="zj-inland-alluvial",
        confirmed_soil_class="可塑黏性土",
        bearing_capacity_kpa=100,
        bearing_capacity_source="区域参考档，用户确认",
        groundwater=GroundwaterDesignProfile(
            condition="no_influence", source="现场资料确认无影响"
        ),
    )
    members = [
        MemberSpecification(node_id="roof_members", member_role="beam", material_grade="Q355B", section_catalog_id="rhs-200x100x6", section_type="RHS", section_name="矩形管 200×100×6", effective_length_m=3, unbraced_length_m=3, selection_source="recommended"),
        MemberSpecification(node_id="main_frame", member_role="beam", material_grade="Q355B", section_catalog_id="rhs-300x150x8", section_type="RHS", section_name="矩形管 300×150×8", effective_length_m=4, unbraced_length_m=4, selection_source="recommended"),
        MemberSpecification(node_id="main_frame", member_role="column", material_grade="Q355B", section_catalog_id="shs-200x8", section_type="SHS", section_name="方管 200×200×8", effective_length_m=3, unbraced_length_m=3, selection_source="recommended"),
    ]
    foundations = [
        FoundationDesignSpecification(node_id=node_id, foundation_system_id="spread", selection_source="recommended", length_m=1.5, width_m=1.5, thickness_mm=450, embedment_m=1, concrete_grade="C30", rebar_grade="HRB400", bar_diameter_mm=14, bar_spacing_mm=150)
        for node_id in ("foundation_left", "foundation_right")
    ]
    explicit = execute_scene(
        family,
        "flat-single",
        "quick",
        calculations,
        load_cases=load_cases,
        geotechnical_profile=geotechnical,
        structural_profile=SceneStructuralProfile(
            stage="scheme_estimate",
            exposure=SurfaceExposureProfile(
                vertical_enclosure="none",
                top_cover="solid_roof",
                roof_form="flat",
                source="测试场景",
            ),
            members=members,
            foundations=foundations,
        ),
        strict_site_conditions=False,
    )
    assert explicit.result_class == "scheme_estimate"
    assert explicit.structural_profile is not None
    left_foundation = explicit.node_results["foundation_left"].calculation_result
    assert left_foundation is not None
    assert left_foundation.input_summary["footing_length"].value == 1.5
    assert left_foundation.input_summary["soil_capacity"].value == 100


def test_boardwalk_and_pool_default_paths_are_public() -> None:
    boardwalk = get_scene_family("boardwalk-platform")
    pool = get_scene_family("water-feature-pool")
    assert boardwalk is not None and pool is not None
    straight = get_scene_variant(boardwalk, "straight")
    buried = get_scene_variant(pool, "rect-buried")
    assert straight is not None and buried is not None
    assert straight.availability == "public"
    assert buried.availability == "public"
    assert straight.material_systems == ["木面板+钢构"]
    assert "柱脚混凝土锚固破坏" in straight.missing_capabilities
    assert buried.material_systems == ["钢筋混凝土"]
    assert buried.missing_capabilities == []


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
