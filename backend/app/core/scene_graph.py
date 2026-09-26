from __future__ import annotations

from collections import defaultdict, deque
from math import hypot

from .engine import calculate
from .errors import CalculationInputError
from .seismic import SeismicActionPackage, build_screening_seismic_package
from .design_profiles import (
    CustomSectionDefinition,
    ProjectGeotechnicalProfile,
    SceneStructuralProfile,
    STEEL_SECTIONS,
)
from .scene_catalog import get_scene_variant, instantiate_scene_graph
from .scene_schemas import (
    SceneConnection,
    SceneFamily,
    SceneGraphTemplate,
    SceneLoadItem,
    SceneNodeCalculation,
    SceneNodeResult,
    SceneRevisionResult,
)
from .schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    CalculationResult,
    ConnectionEffectInput,
    ContinuousBeamInputs,
    FrameUniformLoadInput,
    LoadDirection,
    LoadItem,
    LoadKind,
    PlanarFrameInputs,
    PileGroupCapInputs,
    PlainMasonryWallInputs,
    SixComponentEffectInputs,
    SiteRCWallInputs,
    SiteWallLoadCaseInputs,
    SteelInfillWallInputs,
    TimberConnectionInputs,
    TypedInputValue,
    WallAnchorInputs,
)
from .site_profile import ProjectSiteProfile
from .scene_space_frame import analyze_scene_space_frame
from .scene_typed_adapters import MODELS as SCENE_TYPED_MODELS, adapt_scene_requests, apply_vertical_line, saved_section_properties, include_member_self_weight


_SITE_WALL_TYPED_INPUTS = (
    SiteRCWallInputs,
    SteelInfillWallInputs,
    PlainMasonryWallInputs,
)

_SEISMIC_SCREENING_FAMILIES = {
    "pergola-pavilion",
    "canopy",
    "signage-billboard",
    "landscape-wall-fence",
    "entrance-frame",
    "boardwalk-platform",
}


def required_scene_conditions(variant) -> list[str]:
    """Return catalog-declared required project conditions."""

    profile = variant.condition_profile
    if profile is None:
        return []
    return [
        name
        for name in ("wind", "snow", "seismic")
        if getattr(profile, name) == "required"
    ]


def validate_scene_site_profile(
    variant, site_profile: ProjectSiteProfile | None
) -> list[str]:
    """Reject missing required conditions instead of silently substituting values."""

    required = required_scene_conditions(variant)
    if not required:
        return []
    if site_profile is None:
        raise CalculationInputError(
            "missing_scene_conditions",
            "当前场景尚未完成项目条件向导。",
            details={"required_conditions": required},
        )
    try:
        site_profile.require_conditions(required)
    except ValueError as exc:
        raise CalculationInputError(
            "incomplete_scene_conditions",
            "当前场景所需的项目条件尚未完成。",
            details={"required_conditions": required, "reason": str(exc)},
        ) from exc
    return required


def _scene_gravity_representative_value(
    graph: SceneGraphTemplate,
    calculated: dict[str, CalculationResult],
    load_cases: list[SceneLoadItem],
) -> float:
    """Use terminal support reactions first; fall back to direct kN actions."""

    source_nodes = {item.source_node_id for item in graph.connections}
    terminal_ids = [node.id for node in graph.nodes if node.id not in source_nodes]
    reaction_total = 0.0
    for node_id in terminal_ids:
        result = calculated.get(node_id)
        if result is None:
            continue
        for key in ("base_vertical", "vertical", "left_vertical", "right_vertical"):
            value = result.reactions.get(key)
            if value is not None and value.unit == "kN" and value.value > 0:
                reaction_total += value.value
    if reaction_total > 0:
        return reaction_total
    factors = {"self_weight": 1.0, "dead": 1.0, "live": 0.5, "snow": 0.5}
    return sum(
        float(item.adopted_value or 0.0) * factors.get(item.kind, 0.0)
        for item in load_cases
        if item.unit == "kN"
    )


def _graph_for(
    family: SceneFamily, variant_id: str | None = None
) -> SceneGraphTemplate:
    return (
        instantiate_scene_graph(family, variant_id)
        if variant_id is not None
        else family.graph_template
    )


def validate_scene_graph(
    family: SceneFamily, variant_id: str | None = None
) -> list[str]:
    graph = _graph_for(family, variant_id)
    node_ids = [node.id for node in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise CalculationInputError(
            "duplicate_scene_node",
            "场景图包含重复节点编号。",
            details={"scene_family_id": family.id, "variant_id": variant_id},
        )
    valid_ids = set(node_ids)
    for connection in graph.connections:
        if (
            connection.source_node_id not in valid_ids
            or connection.target_node_id not in valid_ids
        ):
            raise CalculationInputError(
                "unknown_scene_node",
                "场景连接引用了不存在的节点。",
                details={"connection_id": connection.id},
            )
        if (
            connection.output_unit
            and connection.input_unit
            and connection.output_unit != connection.input_unit
        ):
            raise CalculationInputError(
                "incompatible_scene_units",
                "场景连接两端单位不兼容。",
                details={
                    "connection_id": connection.id,
                    "output_unit": connection.output_unit,
                    "input_unit": connection.input_unit,
                },
            )

    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for connection in graph.connections:
        outgoing[connection.source_node_id].append(connection.target_node_id)
        indegree[connection.target_node_id] += 1
    queue = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(node_ids):
        raise CalculationInputError(
            "cyclic_scene_graph",
            "场景传力链不能包含循环连接。",
            details={"scene_family_id": family.id, "variant_id": variant_id},
        )
    return order


def downstream_node_ids(
    family: SceneFamily,
    changed_node_ids: list[str],
    variant_id: str | None = None,
) -> list[str]:
    graph = _graph_for(family, variant_id)
    valid_ids = {node.id for node in graph.nodes}
    unknown = sorted(set(changed_node_ids) - valid_ids)
    if unknown:
        raise CalculationInputError(
            "unknown_changed_node",
            "修改列表包含不存在的场景节点。",
            details={"node_ids": unknown},
        )
    outgoing: dict[str, list[str]] = defaultdict(list)
    for connection in graph.connections:
        outgoing[connection.source_node_id].append(connection.target_node_id)
    stale: set[str] = set()
    queue = deque(changed_node_ids)
    while queue:
        current = queue.popleft()
        for target in outgoing[current]:
            if target not in stale:
                stale.add(target)
                queue.append(target)
    return [
        node_id
        for node_id in validate_scene_graph(family, variant_id)
        if node_id in stale
    ]


def _reaction_value(
    result: CalculationResult, support: str, suffix: str
) -> float | None:
    candidates = (
        [f"{support}_{suffix}"] if support in {"left", "right"} else []
    ) + [f"base_{suffix}", suffix]
    for key in candidates:
        quantity = result.reactions.get(key)
        if quantity is not None:
            return quantity.value
    return None


def _typed_reaction_input(
    calculation: CalculationRequest,
    connection: SceneConnection,
    converted_envelopes: list[dict],
):
    """Map an upstream effect into an already-typed analysis request.

    Schema 3.2 solvers intentionally do not consume the legacy ``inputs``
    reaction sidecar.  Scene execution therefore updates only the explicit
    load/effect fields that are already present (or can be inferred from frame
    geometry) while preserving the typed public contract.
    """

    typed = calculation.typed_inputs
    if typed is None or not converted_envelopes:
        return typed

    combination_id = getattr(typed, "combination_id", None)
    limit_state = getattr(typed, "limit_state", None)
    selected = [
        item
        for item in converted_envelopes
        if combination_id and item.get("combination_id") == combination_id
    ]
    if not selected:
        selected = [
            item
            for item in converted_envelopes
            if limit_state and item.get("limit_state") == limit_state
        ]
    if not selected:
        selected = list(converted_envelopes)

    if calculation.inputs.get('slab_edge_id') and isinstance(typed, ContinuousBeamInputs):
        values={**calculation.inputs.get('scene_parameters',{}),**calculation.inputs}
        a=float(values['short_span_m']);b=float(values['long_span_m'])
        vector=selected[0]
        total=float(vector['components']['N']['value'])
        pressure=total/(a*b)
        edge_length=sum(span.length.value for span in typed.spans)
        position=0.;spans=[]
        for span in typed.spans:
            midpoint=position+span.length.value/2
            tributary_width=min(midpoint,edge_length-midpoint,a/2)
            spans.append(span.model_copy(update={'uniform_load_local_y':TypedInputValue(value=span.uniform_load_local_y.value-pressure*tributary_width,unit='kN/m')},deep=True))
            position+=span.length.value
        return typed.model_copy(update={'spans':spans,
            'combination_id':vector['combination_id'], 'combination_name':vector.get('combination_name') or vector['combination_id'],
            'limit_state':vector['limit_state']},deep=True)

    if connection.transfer == "reaction_to_line" and isinstance(
        typed, (PlanarFrameInputs, ContinuousBeamInputs)
    ):
        transferred = selected[0].get("transferred_line_load")
        if not isinstance(transferred, dict):
            raise CalculationInputError(
                "missing_transferred_line_load",
                "Schema 3.2 杆系节点需要组合一致的上游线荷载。",
                details={"connection_id": connection.id},
            )
        line_value = -float(transferred.get("value", 0.0))
        line_load = TypedInputValue(value=line_value, unit="kN/m")
        if isinstance(typed, ContinuousBeamInputs):
            return typed.model_copy(
                update={
                    'combination_id': selected[0].get('combination_id') or typed.combination_id,
                    'combination_name': selected[0].get('combination_name') or typed.combination_name,
                    'limit_state': selected[0].get('limit_state', typed.limit_state),
                    "spans": [
                        span.model_copy(
                            update={"uniform_load_local_y": line_load}, deep=True
                        )
                        for span in typed.spans
                    ]
                },
                deep=True,
            )

        if calculation.inputs.get("scene_adapter_version"):
            return apply_vertical_line(typed, line_value).model_copy(update={
                "combination_id": selected[0]["combination_id"],
                "combination_name": selected[0].get("combination_name") or selected[0]["combination_id"],
                "limit_state": selected[0]["limit_state"],
            }, deep=True)
        uniform_loads = list(typed.uniform_loads)
        if not uniform_loads:
            coordinates = {
                item.id: (item.x.value, item.y.value) for item in typed.nodes
            }
            target_members = [
                member.id
                for member in typed.members
                if abs(
                    coordinates[member.end][0] - coordinates[member.start][0]
                )
                > 1.0e-12
            ]
            uniform_loads = [
                FrameUniformLoadInput(member=member_id, local_y=line_load)
                for member_id in target_members
            ]
        else:
            uniform_loads = [
                item.model_copy(update={"local_y": line_load}, deep=True)
                for item in uniform_loads
            ]
        if not uniform_loads:
            raise CalculationInputError(
                "missing_frame_load_target",
                "无法从平面框架几何识别承接上游线荷载的非竖向杆件。",
                details={"connection_id": connection.id},
            )
        return typed.model_copy(update={"uniform_loads": uniform_loads}, deep=True)

    if connection.transfer in {"reaction_package", "combination_package"} and isinstance(
        typed, WallAnchorInputs
    ):
        def component_value(item: dict, key: str) -> float:
            raw = item.get("components", {}).get(key)
            return float(raw.get("value", 0.0)) if isinstance(raw, dict) else 0.0

        governing_axial = max(selected, key=lambda item: abs(component_value(item, "N")))
        bending = max(
            (
                max(
                    abs(component_value(item, "Mx")),
                    abs(component_value(item, "My")),
                )
                for item in selected
            ),
            default=0.0,
        )
        shear = max(
            (
                hypot(
                    component_value(item, "Vx"),
                    component_value(item, "Vy"),
                )
                for item in selected
            ),
            default=0.0,
        )
        return typed.model_copy(
            update={
                "n_design": TypedInputValue(
                    value=component_value(governing_axial, "N"), unit="kN"
                ),
                "m_design": TypedInputValue(value=bending, unit="kN*m"),
                "v_design": TypedInputValue(value=shear, unit="kN"),
            },
            deep=True,
        )

    if connection.transfer in {"reaction_package", "combination_package"} and isinstance(
        typed, TimberConnectionInputs
    ):
        def component(item: dict, key: str, unit: str) -> TypedInputValue:
            raw = item.get("components", {}).get(key)
            return TypedInputValue(
                value=float(raw.get("value", 0.0)) if isinstance(raw, dict) else 0.0,
                unit=unit,
            )

        effects = [
            ConnectionEffectInput(
                combination_id=str(
                    item.get("combination_id") or f"scene-{index + 1}"
                ),
                combination_name=str(
                    item.get("combination_name") or f"scene effect {index + 1}"
                ),
                limit_state=item.get("limit_state", "ULS"),
                axial=component(item, "N", "kN"),
                shear_x=component(item, "Vx", "kN"),
                shear_y=component(item, "Vy", "kN"),
                moment_x=component(item, "Mx", "kN*m"),
                moment_y=component(item, "My", "kN*m"),
                torsion=component(item, "T", "kN*m"),
            )
            for index, item in enumerate(selected)
        ]
        return typed.model_copy(update={"effects": effects}, deep=True)

    if connection.transfer in {"reaction_package", "combination_package"} and isinstance(
        typed, PileGroupCapInputs
    ):
        item = selected[0]

        def pile_component(key: str, unit: str) -> TypedInputValue:
            raw = item.get("components", {}).get(key)
            return TypedInputValue(
                value=float(raw.get("value", 0.0)) if isinstance(raw, dict) else 0.0,
                unit=unit,
            )

        return typed.model_copy(
            update={
                "combination_id": str(
                    item.get("combination_id") or typed.combination_id
                ),
                "combination_name": str(
                    item.get("combination_name") or typed.combination_name
                ),
                "limit_state": item.get("limit_state", typed.limit_state),
                "effects": SixComponentEffectInputs(
                    axial=pile_component("N", "kN"),
                    shear_x=pile_component("Vx", "kN"),
                    shear_y=pile_component("Vy", "kN"),
                    moment_x=pile_component("Mx", "kN*m"),
                    moment_y=pile_component("My", "kN*m"),
                    torsion=pile_component("T", "kN*m"),
                ),
            },
            deep=True,
        )
    return typed


def _apply_reaction(
    calculation: CalculationRequest,
    connection: SceneConnection,
    source: CalculationResult,
) -> CalculationRequest:
    vertical = _reaction_value(source, connection.support, "vertical")
    if vertical is None and not source.reaction_envelopes:
        raise CalculationInputError(
            "missing_source_reaction",
            "上游节点没有可传递的竖向反力。",
            details={
                "source_node_id": connection.source_node_id,
                "target_node_id": connection.target_node_id,
            },
        )
    horizontal = _reaction_value(source, connection.support, "horizontal") or 0.0
    moment = _reaction_value(source, connection.support, "moment") or 0.0
    if connection.support == "left":
        envelope_names = {"left_support", "left_base", "left_wall_support"}
    elif connection.support == "right":
        envelope_names = {"right_support", "right_base", "right_wall_support"}
    else:
        envelope_names = {"base", "fixed_support", "footing_base"}
    upstream_envelopes = [
        item
        for item in source.reaction_envelopes
        if item.name in envelope_names
    ]
    if not upstream_envelopes and source.reaction_envelopes and connection.support in {
        "left",
        "base",
        "right",
    }:
        grouped: dict[str, list] = defaultdict(list)
        for item in source.reaction_envelopes:
            grouped[item.combination_id or item.combination_name].append(item)
        upstream_envelopes = [
            items[0]
            if connection.support == "left"
            else items[-1]
            if connection.support == "right"
            else items[len(items) // 2]
            for items in grouped.values()
        ]
    if not upstream_envelopes and len(
        {item.name for item in source.reaction_envelopes}
    ) == 1:
        upstream_envelopes = list(source.reaction_envelopes)
    if connection.requires_source_trace and not upstream_envelopes:
        raise CalculationInputError(
            "missing_source_reaction_envelope",
            "该传力连接要求组合一致的上游反力包。",
            details={
                "source_node_id": connection.source_node_id,
                "target_node_id": connection.target_node_id,
                "source_trace_id": source.trace_id,
            },
        )

    def _tag_governing_envelopes(envelope_list: list[dict]) -> list[dict]:
        if not envelope_list:
            return envelope_list
        tagged = [dict(item) for item in envelope_list]
        max_n = max((float(item.get("components", {}).get("N", {}).get("value", 0.0)) for item in tagged), default=0.0)
        min_n = min((float(item.get("components", {}).get("N", {}).get("value", 0.0)) for item in tagged), default=0.0)
        max_m = max((abs(float(item.get("components", {}).get("My", {}).get("value", 0.0))) for item in tagged), default=0.0)
        for item in tagged:
            comp = item.get("components", {})
            n_val = float(comp.get("N", {}).get("value", 0.0))
            m_val = abs(float(comp.get("My", {}).get("value", 0.0)))
            tags = []
            if abs(n_val - max_n) < 1e-6:
                tags.append("N_max")
            if abs(n_val - min_n) < 1e-6 and n_val < 0:
                tags.append("N_uplift")
            if abs(m_val - max_m) < 1e-6:
                tags.append("M_max")
            item["governing_tags"] = tags or ["general"]
        return tagged

    converted_envelopes = _tag_governing_envelopes([item.model_dump(mode="json") for item in upstream_envelopes])
    for envelope in converted_envelopes:
        combination=next((c for c in source.combinations if c.combination_id==envelope.get('combination_id')),None)
        if combination is not None:
            envelope['action_factors']=dict(combination.factors)
    # Beam local transverse reaction becomes downstream vertical/axial force.
    # Do this at the coordinate interface, never infer it from a zero N value.
    beam_modules = {CalculationModule.STEEL_BEAM, CalculationModule.TIMBER_BEAM,
                    CalculationModule.CONCRETE_BEAM, CalculationModule.CONCRETE_SLAB,
                    CalculationModule.TIMBER_DECK_PANEL, CalculationModule.CONTINUOUS_BEAM,
                    CalculationModule.PLANAR_FRAME, CalculationModule.PLANAR_TRUSS,
                    CalculationModule.TWO_WAY_SLAB}
    if source.module in beam_modules and connection.transfer in {"reaction_package", "combination_package"}:
        for item in converted_envelopes:
            components = item["components"]
            components["N"] = dict(components["Vy"])
            components["Vy"] = {"value": 0.0, "unit": "kN"}
    conversion_scale: float | None = None
    if connection.transfer == "reaction_to_line":
        key = connection.conversion_input_key
        if not key:
            raise CalculationInputError(
                "missing_reaction_conversion_parameter",
                "反力转线荷载连接缺少换算参数。",
                details={"connection_id": connection.id},
            )
        conversion_scale = float(calculation.inputs.get(key, 0))
        if conversion_scale <= 0:
            raise CalculationInputError(
                "invalid_reaction_conversion_parameter",
                "反力转线荷载的间距必须大于零。",
                field=key,
                details={"connection_id": connection.id},
            )
        for envelope in converted_envelopes:
            components = envelope.get("components", {})
            vertical_component = components.get("Vy")
            if vertical_component is None or abs(float(vertical_component.get("value", 0.0))) < 1e-12:
                vertical_component = components.get("N")
            if vertical_component is None:
                raise CalculationInputError(
                    "missing_vertical_reaction_component",
                    "反力转线荷载要求每个组合包含竖向反力分量。",
                    details={
                        "connection_id": connection.id,
                        "combination_name": envelope.get("combination_name"),
                    },
                )
            envelope["transferred_line_load"] = {
                "value": vertical_component["value"] / conversion_scale,
                "unit": "kN/m",
            }
    previous = calculation.inputs.get('upstream_reaction_envelopes', [])
    if previous and connection.transfer in {'reaction_package','combination_package'}:
        # Multiple physical members meeting at the same support contribute to
        # one real vector per combination. Never overwrite the first member.
        combined={ (item.get('combination_id'),item.get('limit_state')):dict(item) for item in previous }
        for item in converted_envelopes:
            key=(item.get('combination_id'),item.get('limit_state'))
            if key not in combined:
                combined[key]=item
                continue
            old=combined[key]
            components={}
            for component in ('N','Vx','Vy','Mx','My','T'):
                first=old['components'][component];second=item['components'][component]
                if first['unit']!=second['unit']:
                    raise CalculationInputError('scene_reaction_unit_mismatch','汇合反力单位不一致。')
                components[component]={'value':first['value']+second['value'],'unit':first['unit']}
            combined[key]={**old,'components':components}
        converted_envelopes=list(combined.values())
    updated_inputs = {
        **calculation.inputs,
        "reaction_source_node_id": connection.source_node_id,
        "reaction_source_trace_id": source.trace_id,
        "upstream_reaction_envelopes": converted_envelopes,
        "reaction_transfer": connection.transfer,
    }
    if conversion_scale is not None:
        updated_inputs["reaction_conversion_scale_m"] = conversion_scale
    updated_typed_inputs = _typed_reaction_input(
        calculation, connection, converted_envelopes
    )
    if calculation.module is CalculationModule.SPREAD_FOOTING:
        updated_inputs.update(
            {
                "horizontal_x_kn": horizontal,
                "moment_y_kn_m": moment,
                "uplift_kn": (
                    abs(vertical)
                    if vertical is not None and vertical < 0
                    else calculation.inputs.get("uplift_kn", 0)
                ),
            }
        )
    updated_loads = calculation.loads
    if calculation.module is CalculationModule.SPREAD_FOOTING and vertical is not None:
        updated_loads = [
            LoadItem(
                kind=LoadKind.DEAD,
                value=max(vertical, 0),
                unit="kN",
                source=(
                    f"场景节点 {connection.source_node_id} "
                    f"的 {connection.support} 支座反力"
                ),
                source_reference=f"trace:{source.trace_id}",
            )
        ]
    return calculation.model_copy(
        update={
            "inputs": updated_inputs,
            "loads": updated_loads,
            "typed_inputs": updated_typed_inputs,
        },
        deep=True,
    )


def _resolved_load_cases(
    family: SceneFamily,
    variant_id: str,
    submitted: list[SceneLoadItem],
    graph: SceneGraphTemplate,
) -> list[SceneLoadItem]:
    variant = get_scene_variant(family, variant_id)
    if variant is None:
        raise CalculationInputError(
            "unknown_scene_variant",
            "所选场景变体不存在。",
            details={"scene_family_id": family.id, "variant_id": variant_id},
        )
    package_items = {
        item.id: item
        for item in (variant.load_package.items if variant.load_package else [])
    }
    if not submitted:
        return [item.model_copy(deep=True) for item in package_items.values()]
    if len({item.id for item in submitted}) != len(submitted):
        raise CalculationInputError(
            "duplicate_scene_load",
            "同一个场景荷载不能重复提交。",
        )
    node_ids = {node.id for node in graph.nodes}
    resolved: list[SceneLoadItem] = []
    for item in submitted:
        catalog_item = package_items.get(item.id)
        if catalog_item is None and item.value_type != "project_defined":
            raise CalculationInputError(
                "unknown_scene_load",
                "场景荷载不属于当前场景荷载包。",
                details={"load_case_id": item.id},
            )
        if item.application_target not in node_ids:
            raise CalculationInputError(
                "unknown_load_target",
                "场景荷载引用了不存在的计算节点。",
                details={
                    "load_case_id": item.id,
                    "application_target": item.application_target,
                },
            )
        if catalog_item is not None:
            immutable_fields = (
                "kind",
                "unit",
                "distribution",
                "direction",
                "application_target",
            )
            changed = [
                field
                for field in immutable_fields
                if getattr(item, field) != getattr(catalog_item, field)
            ]
            if changed:
                raise CalculationInputError(
                    "scene_load_contract_changed",
                    "目录荷载的类型、单位、方向或作用目标不能直接修改。",
                    details={"load_case_id": item.id, "fields": changed},
                )
            if (
                catalog_item.value_type in {"fixed", "reference_range"}
                and item.adopted_value != catalog_item.recommended_default
                and not (item.override_reason or "").strip()
            ):
                raise CalculationInputError(
                    "scene_load_override_reason_required",
                    "覆盖场景荷载建议值时必须填写原因。",
                    details={"load_case_id": item.id},
                )
        if (
            item.value_type == "project_defined"
            and item.source_reference.strip()
            in {"", "由用户填写项目资料名称、页码或条款"}
        ):
            raise CalculationInputError(
                "project_load_source_required",
                "项目自定义荷载必须填写可复核资料来源。",
                details={"load_case_id": item.id},
            )
        resolved.append(item.model_copy(deep=True))
    submitted_ids = {item.id for item in submitted}
    resolved.extend(
        item.model_copy(deep=True)
        for item in package_items.values()
        if item.id not in submitted_ids
    )
    return resolved


def _apply_scene_loads(
    calculations: dict[str, CalculationRequest],
    load_cases: list[SceneLoadItem],
) -> tuple[dict[str, CalculationRequest], list[str]]:
    by_target: dict[str, list[SceneLoadItem]] = defaultdict(list)
    for item in load_cases:
        by_target[item.application_target].append(item)

    updated = dict(calculations)
    missing_mappings: list[str] = []
    supported_kinds = {item.value for item in LoadKind}
    supported_directions = {item.value for item in LoadDirection}
    for node_id, scene_loads in by_target.items():
        calculation = calculations.get(node_id)
        if calculation is None:
            # Load records targeting a manual/environment node are
            # provenance entries, not member actions.  They are carried into
            # the immutable revision and consumed by that node's parameter
            # contract rather than forced into CalculationRequest.loads.
            continue
        if calculation.module.value in SCENE_TYPED_MODELS and not isinstance(calculation.typed_inputs, _SITE_WALL_TYPED_INPUTS):
            # Scene adapters own these typed load contracts.
            continue
        if isinstance(calculation.typed_inputs, _SITE_WALL_TYPED_INPUTS):
            typed = calculation.typed_inputs
            dead_total = sum(
                float(item.adopted_value or 0.0)
                for item in scene_loads
                if item.kind in {"dead", "self_weight"}
                and item.unit in {"kPa", "kN/m2"}
            )
            wind_by_sign = {
                -1 if item.direction == "x_negative" else 1: float(
                    item.adopted_value or 0.0
                )
                for item in scene_loads
                if item.kind == "wind"
                and item.unit in {"kPa", "kN/m2"}
                and item.direction in {"x_positive", "x_negative"}
            }
            existing_cases = list(typed.load_cases)
            mapped_cases: list[SiteWallLoadCaseInputs] = []
            for index, existing in enumerate(existing_cases):
                sign = -1 if existing.wind_pressure.value < 0 else 1
                wind = wind_by_sign.get(sign)
                if wind is None:
                    wind = abs(existing.wind_pressure.value)
                mapped_cases.append(
                    existing.model_copy(
                        update={
                            "wind_pressure": TypedInputValue(
                                value=sign * wind, unit="kPa"
                            ),
                            "additional_dead_load": TypedInputValue(
                                value=dead_total, unit="kPa"
                            ),
                        },
                        deep=True,
                    )
                )
            if not mapped_cases:
                mapped_cases = [
                    SiteWallLoadCaseInputs(
                        combination_id=f"scene-wall-wind-{'negative' if sign < 0 else 'positive'}",
                        combination_name=(
                            "场景反向风" if sign < 0 else "场景正向风"
                        ),
                        limit_state="ULS",
                        wind_pressure=TypedInputValue(
                            value=sign * wind, unit="kPa"
                        ),
                        additional_dead_load=TypedInputValue(
                            value=dead_total, unit="kPa"
                        ),
                    )
                    for sign, wind in sorted(wind_by_sign.items(), reverse=True)
                ]
            updated[node_id] = calculation.model_copy(
                update={
                    "typed_inputs": typed.model_copy(
                        update={"load_cases": mapped_cases}, deep=True
                    )
                },
                deep=True,
            )
            calculation = updated[node_id]
        mapped: list[LoadItem] = []
        existing_by_preset = {
            item.preset_id: item
            for item in calculation.loads
            if item.preset_id is not None
        }
        for item in scene_loads:
            if item.adopted_value is None:
                continue
            direct_units = {
                CalculationModule.SPREAD_FOOTING: {"kN"},
                CalculationModule.STRIP_FOOTING: {"kN/m"},
                CalculationModule.STEEL_COLUMN: {"kN"},
                CalculationModule.CONCRETE_COLUMN: {"kN"},
                CalculationModule.TIMBER_COLUMN: {"kN"},
            }.get(calculation.module, {"kN/m", "kN/m2"})
            if (
                item.unit in direct_units
                and item.kind in supported_kinds
                and item.direction in supported_directions
            ):
                mapped.append(
                    LoadItem(
                        kind=LoadKind(item.kind),
                        value=item.adopted_value,
                        unit=item.unit,
                        source=item.label,
                        direction=LoadDirection(item.direction),
                        preset_id=item.id,
                        source_reference=f"scene-load:{item.id}",
                        override_reason=item.override_reason,
                    )
                )
                continue
            derived = existing_by_preset.get(item.id)
            if derived is None or derived.source_reference != f"scene-load:{item.id}":
                missing_mappings.append(item.id)
            else:
                mapped.append(derived.model_copy(deep=True))
        if mapped:
            updated[node_id] = calculation.model_copy(
                update={"loads": mapped}, deep=True
            )
    return updated, sorted(set(missing_mappings))


def _calculate_scene_cases(adapted, dependencies, calculated):
    """Run every source combination without synthesizing a component envelope."""
    run_results = []
    transfers = [(c, calculated[c.source_node_id]) for c in dependencies
        if c.source_node_id in calculated
        and c.transfer in {'reaction_to_line', 'reaction_package', 'combination_package'}]
    for template in adapted:
        typed_module = template.module.value in SCENE_TYPED_MODELS
        if typed_module:
            template = template.model_copy(update={'inputs':{**template.inputs,'scene_adapter_version':'1.0'}},deep=True)
            if template.module is CalculationModule.PILE_GROUP_CAP and not transfers:
                raise CalculationInputError('scene_adapter_missing_inputs', '桩承台缺少上游组合反力。', details={'missing_fields':['upstream_reaction_envelopes']})
        case_ids = sorted({(e.combination_id or e.combination_name,e.limit_state)
            for _,source in transfers for e in source.reaction_envelopes}) if typed_module else []
        if len(adapted)>1 and case_ids:
            template_case=(template.typed_inputs.combination_id,template.typed_inputs.limit_state)
            if template_case not in case_ids:
                raise CalculationInputError('scene_adapter_missing_inputs','本地作用与上游反力缺少一致组合。',details={'missing_fields':[f'combination:{template_case[0]}']})
            case_ids=[template_case]
        for case in case_ids or [None]:
            effective=template.model_copy(deep=True)
            if transfers:
                # Recomputing a saved request must not add its old reaction
                # sidecar to this revision's fresh incoming members.
                fresh_inputs=dict(effective.inputs)
                fresh_inputs.pop('upstream_reaction_envelopes',None)
                effective=effective.model_copy(update={'inputs':fresh_inputs},deep=True)
            for connection,source in transfers:
                if case is not None:
                    envelopes=[e for e in source.reaction_envelopes if (e.combination_id or e.combination_name,e.limit_state)==case]
                    if not envelopes:
                        raise CalculationInputError('scene_adapter_missing_inputs','多个上游节点缺少一致组合。',details={'missing_fields':[f'combination:{case[0]}:{connection.source_node_id}']})
                    source=source.model_copy(update={'reaction_envelopes':envelopes},deep=True)
                effective=_apply_reaction(effective,connection,source)
            if typed_module and effective.inputs.get("scene_adapter_generated"):
                effective=include_member_self_weight(effective)
            run_results.append(calculate(effective))
    if len(run_results)==1:return run_results[0]
    # Keep the governing case's displayed scalar summary; concatenate explicit
    # per-case checks/reactions for all downstream selection and audit.
    def rank(result):
        return ({'incomplete':3,'failed':2,'passed':1}.get(result.status,0),
                max((c.utilization for c in result.checks),default=0))
    governing=max(run_results,key=rank)
    return governing.model_copy(update={
        'reaction_envelopes':[e for result in run_results for e in result.reaction_envelopes],
        'checks':[c for result in run_results for c in result.checks],
        'combinations':[c for result in run_results for c in result.combinations],
        'assumptions':list(dict.fromkeys(a for result in run_results for a in result.assumptions)),
        'verification_status':'unverified',
    },deep=True)


def execute_scene(
    family: SceneFamily,
    variant_id: str,
    mode: CalculationMode,
    node_calculations: list[SceneNodeCalculation],
    stale_node_ids: list[str] | None = None,
    load_cases: list[SceneLoadItem] | None = None,
    # Legacy internal keyword retained so 3.1 test fixtures and saved command
    # replays can still be read; Schema 3.2 API requests no longer expose it.
    confirmed_input_nodes: list[str] | None = None,
    site_profile: ProjectSiteProfile | None = None,
    geotechnical_profile: ProjectGeotechnicalProfile | None = None,
    structural_profile: SceneStructuralProfile | None = None,
    custom_sections: list[CustomSectionDefinition] | None = None,
    strict_site_conditions: bool = False,
) -> SceneRevisionResult:
    mode = CalculationMode(mode)
    variant = get_scene_variant(family, variant_id)
    if variant is None:
        raise CalculationInputError(
            "unknown_scene_variant",
            "所选场景变体不存在。",
            details={"scene_family_id": family.id, "variant_id": variant_id},
        )
    if family.availability != "public" or variant.availability != "public":
        raise CalculationInputError(
            "scene_in_development",
            "该场景仍在开发中，当前不能创建计算修订。",
            details={"scene_family_id": family.id, "variant_id": variant_id},
        )

    applied_conditions = (
        validate_scene_site_profile(variant, site_profile)
        if strict_site_conditions
        else []
    )

    graph = instantiate_scene_graph(family, variant_id)
    order = validate_scene_graph(family, variant_id)
    nodes = {node.id: node for node in graph.nodes}
    calculations = {item.node_id: item.calculation for item in node_calculations}
    if len(calculations) != len(node_calculations):
        raise CalculationInputError(
            "duplicate_scene_calculation",
            "同一场景节点不能提交多份计算输入。",
        )
    unknown_calculations = sorted(set(calculations) - set(nodes))
    if unknown_calculations:
        raise CalculationInputError(
            "unknown_scene_calculation_node",
            "计算输入引用了不存在的场景节点。",
            details={"node_ids": unknown_calculations},
        )

    active_nodes = [
        node for node in graph.nodes if node.applicability != "not_applicable"
    ]
    foundation_nodes = [
        node
        for node in active_nodes
        if node.role == "foundation"
        and node.calculation_module in {"spread_footing", "strip_footing"}
    ]
    steel_nodes = [
        node
        for node in active_nodes
        if node.calculation_module in {"steel_beam", "steel_column", "portal_frame", "continuous_beam", "planar_frame"}
    ]
    submitted_foundation_nodes = [node for node in foundation_nodes if node.id in calculations]
    submitted_steel_nodes = [node for node in steel_nodes if node.id in calculations]
    if strict_site_conditions and submitted_foundation_nodes and geotechnical_profile is None:
        raise CalculationInputError(
            "missing_geotechnical_profile",
            "场景包含浅基础，必须先保存区域参考土质档或项目勘察参数；不再采用隐藏承载力和地下水默认值。",
        )
    if strict_site_conditions and (submitted_foundation_nodes or submitted_steel_nodes) and structural_profile is None:
        raise CalculationInputError(
            "missing_structural_profile",
            "必须显式确认构件截面和基础尺寸；前端默认值不得作为完整场景设计输入。",
        )
    if structural_profile is not None:
        specified_foundations = {item.node_id for item in structural_profile.foundations}
        missing_foundations = [
            node.label for node in submitted_foundation_nodes if node.id not in specified_foundations
        ]
        if missing_foundations:
            raise CalculationInputError(
                "missing_foundation_specification",
                "以下基础节点缺少显式尺寸：" + "、".join(missing_foundations),
            )
        specified_member_roles = {
            (item.node_id, item.member_role) for item in structural_profile.members
        }
        missing_members: list[str] = []
        for node in submitted_steel_nodes:
            required_roles = (
                {"beam", "column"}
                if node.calculation_module in {"portal_frame", "planar_frame"}
                else {"beam"}
                if node.calculation_module in {"steel_beam", "continuous_beam"}
                else {"column"}
            )
            missing_members.extend(
                f"{node.label}（{role}）"
                for role in required_roles
                if (node.id, role) not in specified_member_roles
            )
        if missing_members:
            raise CalculationInputError(
                "missing_member_specification",
                "以下钢构件节点缺少显式材料与截面：" + "、".join(missing_members),
            )

        section_by_id = {item.id: item for item in STEEL_SECTIONS}
        section_by_id.update({item.id: item for item in (custom_sections or [])})
        for specification in structural_profile.members:
            calculation = calculations.get(specification.node_id)
            if calculation is None:
                continue
            entry = section_by_id.get(specification.section_catalog_id)
            if entry is None:
                raise CalculationInputError(
                    "unknown_section_catalog_entry",
                    f"截面目录中不存在 {specification.section_catalog_id}",
                )
            if calculation.module.value in {"continuous_beam", "planar_frame"}:
                updates = saved_section_properties(specification, entry)
                calculations[specification.node_id] = calculation.model_copy(
                    update={"inputs": {**calculation.inputs, **updates}}, deep=True)
                continue
            dimensions = dict(entry.dimensions)
            # The current member engine evaluates I-shaped candidates with the
            # same geometric property path as H sections.
            section_type = "H" if entry.family == "I" else entry.family
            if calculation.module is CalculationModule.PORTAL_FRAME:
                updates = {
                    "steel_grade": specification.material_grade,
                    (
                        "beam_section"
                        if specification.member_role == "beam"
                        else "column_section"
                    ): {"section_type": section_type, **dimensions},
                }
                existing_other = (
                    "column_section"
                    if specification.member_role == "beam"
                    else "beam_section"
                )
                if existing_other in calculation.inputs:
                    updates[existing_other] = calculation.inputs[existing_other]
            else:
                updates = {
                    "section_type": section_type,
                    "steel_grade": specification.material_grade,
                    "effective_length_m": specification.effective_length_m,
                    "unbraced_length_m": specification.unbraced_length_m,
                    **dimensions,
                }
            calculations[specification.node_id] = calculation.model_copy(
                update={"inputs": {**calculation.inputs, **updates}}, deep=True
            )

        for specification in structural_profile.foundations:
            calculation = calculations.get(specification.node_id)
            if calculation is None:
                continue
            updates: dict[str, object] = {
                "length_m": specification.length_m,
                "width_m": specification.width_m,
                "thickness_mm": specification.thickness_mm,
                "embedment_m": specification.embedment_m,
                "concrete_grade": specification.concrete_grade,
                "rebar_grade": specification.rebar_grade,
                "bar_dia_x_mm": specification.bar_diameter_mm,
                "bar_dia_y_mm": specification.bar_diameter_mm,
                "bar_spacing_x_mm": specification.bar_spacing_mm,
                "bar_spacing_y_mm": specification.bar_spacing_mm,
                "bar_dia_mm": specification.bar_diameter_mm,
                "bar_spacing_mm": specification.bar_spacing_mm,
                "foundation_system_id": specification.foundation_system_id,
                "selection_source": specification.selection_source,
                "explicit_design_profile": True,
            }
            if geotechnical_profile is not None:
                groundwater = geotechnical_profile.groundwater
                updates.update(
                    {
                        "soil_capacity_kpa": geotechnical_profile.bearing_capacity_kpa,
                        "soil_source": geotechnical_profile.bearing_capacity_source,
                        "groundwater_condition": (
                            "no_influence"
                            if groundwater.condition == "no_influence"
                            else "known_water_table"
                            if groundwater.condition == "known_levels"
                            else "unknown"
                        ),
                        "groundwater_source": groundwater.source,
                    }
                )
                if groundwater.condition == "known_levels":
                    updates["water_table_depth_m"] = max(
                        0.0, -(groundwater.service_level_m or 0.0)
                    )
            calculations[specification.node_id] = calculation.model_copy(
                update={"inputs": {**calculation.inputs, **updates}}, deep=True
            )

    recorded_input_nodes = {
        node_id for node_id, node in nodes.items() if node.calculation_module is None
    }
    resolved_loads = _resolved_load_cases(
        family, variant_id, load_cases or [], graph
    )
    calculations, missing_load_mappings = _apply_scene_loads(
        calculations, resolved_loads
    )
    missing_load_values = [
        item.label
        for item in resolved_loads
        if item.adopted_value is None
    ]
    stale = set(stale_node_ids or [])
    incoming: dict[str, list[SceneConnection]] = defaultdict(list)
    for connection in graph.connections:
        incoming[connection.target_node_id].append(connection)

    node_results: dict[str, SceneNodeResult] = {}
    calculated: dict[str, CalculationResult] = {}
    for node_id in order:
        node = nodes[node_id]
        if node.applicability == "not_applicable":
            node_results[node_id] = SceneNodeResult(
                node_id=node.id,
                label=node.label,
                status="not_applicable",
                maturity=node.maturity,
                applicability=node.applicability,
                workflow_status="ready",
                engineering_status="passed",
                verification_status=node.verification_status,
            )
            continue
        dependencies = incoming[node_id]
        blocked_dependencies = [
            connection.source_node_id
            for connection in dependencies
            if node_results[connection.source_node_id].workflow_status != "ready"
            and not (
                connection.source_node_id in calculated
                and calculated[connection.source_node_id].reaction_envelopes
                and node_results[connection.source_node_id].workflow_status == "capability_unavailable"
            )
        ]
        if blocked_dependencies:
            blocked_by_capability = any(
                node_results[source_id].workflow_status
                == "capability_unavailable"
                for source_id in blocked_dependencies
            )
            node_results[node_id] = SceneNodeResult(
                node_id=node.id,
                label=node.label,
                status="incomplete",
                maturity=node.maturity,
                applicability=node.applicability,
                workflow_status=(
                    "capability_unavailable"
                    if blocked_by_capability
                    else "missing_inputs"
                ),
                engineering_status="incomplete",
                verification_status=node.verification_status,
                message="上游节点尚未完成：" + "、".join(blocked_dependencies),
                stale=node.id in stale,
            )
            continue

        calculation = calculations.get(node_id)
        if node.calculation_module is None:
            if node_id in recorded_input_nodes:
                if (
                    mode is CalculationMode.PROFESSIONAL
                    and node.verification_status != "independently_verified"
                ):
                    node_results[node_id] = SceneNodeResult(
                        node_id=node.id,
                        label=node.label,
                        status="incomplete",
                        maturity=node.maturity,
                        applicability=node.applicability,
                        workflow_status="capability_unavailable",
                        engineering_status="incomplete",
                        verification_status=node.verification_status,
                        message="该节点仅有快算假定，尚未完成专业验证。",
                        stale=False,
                    )
                else:
                    node_results[node_id] = SceneNodeResult(
                        node_id=node.id,
                        label=node.label,
                        status="completed",
                        maturity=node.maturity,
                        applicability=node.applicability,
                        workflow_status="ready",
                        engineering_status=None,
                        verification_status=node.verification_status,
                        message=(
                            node.quick_assumption
                            or "输入、边界和传力条件已录入。"
                        ),
                        stale=False,
                    )
                    forwarded = [
                        calculated[connection.source_node_id]
                        for connection in dependencies
                        if connection.source_node_id in calculated
                    ]
                    if len(forwarded) == 1:
                        calculated[node_id] = forwarded[0]
            elif node.applicability == "required":
                node_results[node_id] = SceneNodeResult(
                    node_id=node.id,
                    label=node.label,
                    status="incomplete",
                    maturity=node.maturity,
                    applicability=node.applicability,
                    workflow_status=(
                        "capability_unavailable"
                        if node.maturity == "planned"
                        else "missing_inputs"
                    ),
                    engineering_status="incomplete",
                    verification_status=node.verification_status,
                    message=(
                        "该节点计算能力尚未开放。"
                        if node.maturity == "planned"
                        else "该节点尚缺少必要输入。"
                    ),
                    stale=node.id in stale,
                )
            else:
                node_results[node_id] = SceneNodeResult(
                    node_id=node.id,
                    label=node.label,
                    status="not_applicable",
                    maturity=node.maturity,
                    applicability=node.applicability,
                    workflow_status="ready",
                    engineering_status=(
                        None if mode is CalculationMode.QUICK else "passed"
                    ),
                    verification_status=node.verification_status,
                )
            continue

        if calculation is None:
            node_results[node_id] = SceneNodeResult(
                node_id=node.id,
                label=node.label,
                status="incomplete",
                maturity=node.maturity,
                applicability=node.applicability,
                workflow_status="missing_inputs",
                engineering_status="incomplete",
                verification_status=node.verification_status,
                message="缺少该节点的计算输入。",
                stale=node.id in stale,
            )
            continue
        if calculation.module.value != node.calculation_module:
            raise CalculationInputError(
                "scene_module_mismatch",
                "场景节点与提交的计算模块不一致。",
                details={
                    "node_id": node_id,
                    "expected": node.calculation_module,
                    "actual": calculation.module.value,
                },
            )

        try:
            adapted = adapt_scene_requests(calculation, family.id, variant_id, node_id, resolved_loads)
            result = _calculate_scene_cases(adapted, dependencies, calculated)
        except CalculationInputError as exc:
            if exc.code not in {"typed_input_module_mismatch", "scene_adapter_missing_inputs"}:
                raise
            node_results[node_id] = SceneNodeResult(
                node_id=node.id, label=node.label, status="incomplete",
                maturity=node.maturity, applicability=node.applicability,
                workflow_status="missing_inputs" if exc.code == "scene_adapter_missing_inputs" else "capability_unavailable", engineering_status="incomplete",
                verification_status=node.verification_status,
                message=exc.message,
            )
            continue
        calculated[node_id] = result
        professional_gate = (
            mode is CalculationMode.PROFESSIONAL
            and node.verification_status != "independently_verified"
            and result.status != "failed"
        )
        calculation_engineering_status = result.engineering_status
        node_results[node_id] = SceneNodeResult(
            node_id=node.id,
            label=node.label,
            status="incomplete" if professional_gate else result.status,
            maturity=node.maturity,
            applicability=node.applicability,
            workflow_status=(
                "capability_unavailable"
                if professional_gate or result.workflow_status == "capability_unavailable"
                else "ready"
                if result.status in {"passed", "failed"}
                else "missing_inputs"
            ),
            engineering_status=(
                "incomplete"
                if professional_gate
                else calculation_engineering_status
            ),
            quick_outcome=result.quick_outcome,
            verification_status=node.verification_status,
            calculation_result=result,
            message=(
                "计算已完成，但该模块尚未通过独立验证，不能形成专业结论。"
                if professional_gate
                else None
            ),
            stale=False,
        )

    required_ids = [
        node.id
        for node in graph.nodes
        if node.applicability == "required" and node.required
    ]
    completed_count = sum(
        node_results[node_id].workflow_status == "ready"
        for node_id in required_ids
    )
    missing = [
        node_results[node_id].label
        for node_id in required_ids
        if node_results[node_id].workflow_status != "ready"
    ]
    any_failed = any(
        node_results[node_id].engineering_status == "failed"
        for node_id in required_ids
    )
    any_screening_failed = any(
        node_results[node_id].quick_outcome == "screening_failed"
        or (
            node_results[node_id].calculation_result is not None
            and node_results[node_id].calculation_result.status == "failed"
        )
        for node_id in required_ids
    )
    load_contract_complete = not missing_load_values and not missing_load_mappings
    workflow_states = {
        node_results[node_id].workflow_status for node_id in required_ids
    }
    if any(node_results[node_id].stale for node_id in required_ids):
        workflow_status = "stale"
    elif "capability_unavailable" in workflow_states:
        workflow_status = "capability_unavailable"
    elif (
        "missing_inputs" in workflow_states
        or missing_load_values
        or missing_load_mappings
    ):
        workflow_status = "missing_inputs"
    else:
        workflow_status = "ready"

    if mode is CalculationMode.QUICK:
        engineering_status = None
        quick_outcome = (
            "screening_failed"
            if any_screening_failed
            else "screening_passed"
            if workflow_status == "ready"
            else None
        )
        legacy_status = (
            "failed"
            if quick_outcome == "screening_failed"
            else "passed"
            if quick_outcome == "screening_passed"
            else "incomplete"
        )
    else:
        quick_outcome = None
        if any_failed:
            engineering_status = "failed"
        elif completed_count == len(required_ids) and load_contract_complete:
            engineering_status = "passed"
        else:
            engineering_status = "incomplete"
        legacy_status = engineering_status

    all_verified = all(
        nodes[node_id].verification_status == "independently_verified"
        for node_id in required_ids
    )
    verification_status = (
        "independently_verified" if all_verified else "unverified"
    )
    catalog_versions = {
        "scenes": graph.version,
        "scene_loads": (
            variant.load_package.version
            if variant.load_package is not None
            else "none"
        ),
        "scene_conditions": "3.9",
    }
    for result in calculated.values():
        catalog_versions.update(result.catalog_versions)

    seismic_package: SeismicActionPackage | None = None
    supports_screening_seismic = (
        variant.condition_profile.seismic == "required"
        if variant.condition_profile is not None
        else family.id in _SEISMIC_SCREENING_FAMILIES
    )
    if (
        site_profile
        and supports_screening_seismic
        and site_profile.is_condition_complete("seismic")
    ):
        seismic_package = build_screening_seismic_package(
            site_profile,
            _scene_gravity_representative_value(graph, calculated, resolved_loads),
        )
        catalog_versions["seismic"] = seismic_package.catalog_version
    if site_profile:
        catalog_versions.update(site_profile.catalog_versions)
    if geotechnical_profile:
        catalog_versions.update(geotechnical_profile.catalog_versions)
    if structural_profile:
        catalog_versions.update(structural_profile.catalog_versions)

    space_frame_analysis: dict[str, object] | None = None
    if (
        family.id == "pergola-pavilion"
        and variant_id == "guided-grid"
        and structural_profile is not None
        and structural_profile.geometry is not None
    ):
        space_frame_analysis = analyze_scene_space_frame(
            structural_profile,
            resolved_loads,
            custom_sections,
        )
        catalog_versions["space_frame_solver"] = (
            "steel-compass-space-frame-adapter-2.1-unverified"
        )

    stability_incomplete = bool(space_frame_analysis and (space_frame_analysis.get("stability_scope") or {}).get("status") == "incomplete")
    if stability_incomplete:
        if workflow_status != "stale": workflow_status = "capability_unavailable"
        if quick_outcome != "screening_failed": quick_outcome = None
        if engineering_status == "passed": engineering_status = "incomplete"
        if legacy_status != "failed": legacy_status = "incomplete"
    warnings = [*family.boundaries]
    if stability_incomplete:
        warnings.append("空间分析稳定范围未完整覆盖当前模型，不能形成筛查通过结论。")
    if family.id == "boardwalk-platform" and variant_id == "viewing-platform":
        warnings.append("四边简支板按显式45度几何分担区传力；边梁分段均布逼近三角/梯形荷载，四角各汇总相邻两边梁。此方案级分配不是弹性板精确边界反力。")
    if missing_load_values:
        warnings.append("以下场景荷载缺少采用值：" + "、".join(missing_load_values))
    if missing_load_mappings:
        warnings.append(
            "以下场景荷载尚未映射到计算节点："
            + "、".join(missing_load_mappings)
        )
    warnings.extend(
        node.quick_assumption
        for node in graph.nodes
        if node.id in recorded_input_nodes
        and node.quick_assumption
        and mode is CalculationMode.QUICK
    )
    if mode is CalculationMode.PROFESSIONAL and verification_status == "unverified":
        warnings.append("场景含未独立验证节点，专业模式不得输出通过结论。")
    if (
        site_profile
        and variant.condition_profile is not None
        and variant.condition_profile.seismic == "not_supported"
        and site_profile.is_condition_complete("seismic")
    ):
        warnings.append("本版本未对该高级场景叠加地震作用。")
    if seismic_package is not None:
        warnings.append("等效地震作用为未独立验证的方案筛查结果，不可直接用于施工图或送审。")

    requested_stage = (
        structural_profile.stage
        if structural_profile is not None
        else geotechnical_profile.stage
        if geotechnical_profile is not None
        else "scheme_estimate"
    )
    project_check_ready = (
        requested_stage == "project_check"
        and geotechnical_profile is not None
        and geotechnical_profile.stage == "project_check"
        and structural_profile is not None
        and structural_profile.stage == "project_check"
        and verification_status == "independently_verified"
        and workflow_status == "ready"
    )
    if requested_stage == "project_check" and not project_check_ready:
        warnings.append("已请求工程校核，但场景仍包含未独立验证模块或资料不完整；本次仅生成方案测算结论。")

    return SceneRevisionResult(
        scene_family_id=family.id,
        scene_variant_id=variant_id,
        mode=mode,
        status=legacy_status,
        workflow_status=workflow_status,
        engineering_status=engineering_status,
        quick_outcome=quick_outcome,
        result_class="project_check" if project_check_ready else "scheme_estimate",
        requested_stage=requested_stage,
        verification_status=verification_status,
        graph_template_id=graph.id,
        load_cases=resolved_loads,
        site_profile=(site_profile.model_dump(mode="json") if site_profile else None),
        geotechnical_profile=(
            geotechnical_profile.model_dump(mode="json")
            if geotechnical_profile
            else None
        ),
        structural_profile=(
            structural_profile.model_dump(mode="json")
            if structural_profile
            else None
        ),
        space_frame_analysis=space_frame_analysis,
        seismic_action_package=(
            seismic_package.model_dump(mode="json") if seismic_package else None
        ),
        applied_conditions=applied_conditions,
        completed_nodes=completed_count,
        total_required_nodes=len(required_ids),
        node_results=node_results,
        missing_nodes=missing,
        stale_node_ids=[
            node_id for node_id in order if node_results[node_id].stale
        ],
        control_path=[nodes[node_id].label for node_id in order],
        warnings=warnings,
        catalog_versions=catalog_versions,
    )
