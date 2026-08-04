from __future__ import annotations

from collections import defaultdict, deque

from .engine import calculate
from .errors import CalculationInputError
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
    LoadDirection,
    LoadItem,
    LoadKind,
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
        envelope_names = {"left_support", "left_base"}
    elif connection.support == "right":
        envelope_names = {"right_support", "right_base"}
    else:
        envelope_names = {"base", "fixed_support", "footing_base"}
    upstream_envelopes = [
        item
        for item in source.reaction_envelopes
        if item.name in envelope_names
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

    converted_envelopes = [item.model_dump(mode="json") for item in upstream_envelopes]
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
            vertical_component = components.get("Vy") or components.get("N")
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
    updated_inputs = {
        **calculation.inputs,
        "reaction_source_node_id": connection.source_node_id,
        "reaction_source_trace_id": source.trace_id,
        "upstream_reaction_envelopes": converted_envelopes,
        "reaction_transfer": connection.transfer,
    }
    if conversion_scale is not None:
        updated_inputs["reaction_conversion_scale_m"] = conversion_scale
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
                confirmed=True,
            )
        ]
    return calculation.model_copy(
        update={
            "inputs": updated_inputs,
            "loads": updated_loads,
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
            if any(item.confirmed and item.adopted_value is not None for item in scene_loads):
                missing_mappings.extend(item.id for item in scene_loads if item.confirmed)
            continue
        mapped: list[LoadItem] = []
        existing_by_preset = {
            item.preset_id: item
            for item in calculation.loads
            if item.preset_id is not None
        }
        for item in scene_loads:
            if not item.confirmed or item.adopted_value is None:
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
                        confirmed=True,
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


def execute_scene(
    family: SceneFamily,
    variant_id: str,
    mode: CalculationMode,
    node_calculations: list[SceneNodeCalculation],
    confirmed_input_nodes: list[str],
    stale_node_ids: list[str] | None = None,
    load_cases: list[SceneLoadItem] | None = None,
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

    confirmed = set(confirmed_input_nodes)
    unknown_confirmed = sorted(confirmed - set(nodes))
    if unknown_confirmed:
        raise CalculationInputError(
            "unknown_confirmed_node",
            "确认列表包含不存在的场景节点。",
            details={"node_ids": unknown_confirmed},
        )
    resolved_loads = _resolved_load_cases(
        family, variant_id, load_cases or [], graph
    )
    calculations, missing_load_mappings = _apply_scene_loads(
        calculations, resolved_loads
    )
    unconfirmed_loads = [
        item.label
        for item in resolved_loads
        if not item.confirmed or item.adopted_value is None
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
            if node_id in confirmed:
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
                            or "输入、边界和传力假定已由用户确认。"
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
                        else "该节点尚未确认输入和假定。"
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

        effective_calculation = calculation
        for connection in dependencies:
            source_result = calculated.get(connection.source_node_id)
            if (
                source_result is not None
                and connection.transfer
                in {"reaction_to_line", "reaction_package", "combination_package"}
            ):
                effective_calculation = _apply_reaction(
                    effective_calculation, connection, source_result
                )
        result = calculate(effective_calculation)
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
                if professional_gate
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
    load_contract_complete = not unconfirmed_loads and not missing_load_mappings
    workflow_states = {
        node_results[node_id].workflow_status for node_id in required_ids
    }
    if any(node_results[node_id].stale for node_id in required_ids):
        workflow_status = "stale"
    elif "capability_unavailable" in workflow_states:
        workflow_status = "capability_unavailable"
    elif (
        "missing_inputs" in workflow_states
        or unconfirmed_loads
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
    }
    for result in calculated.values():
        catalog_versions.update(result.catalog_versions)

    warnings = [*family.boundaries]
    if unconfirmed_loads:
        warnings.append("以下场景荷载尚未确认或缺少采用值：" + "、".join(unconfirmed_loads))
    if missing_load_mappings:
        warnings.append(
            "以下场景荷载尚未映射到计算节点："
            + "、".join(missing_load_mappings)
        )
    warnings.extend(
        node.quick_assumption
        for node in graph.nodes
        if node.id in confirmed
        and node.quick_assumption
        and mode is CalculationMode.QUICK
    )
    if mode is CalculationMode.PROFESSIONAL and verification_status == "unverified":
        warnings.append("场景含未独立验证节点，专业模式不得输出通过结论。")

    return SceneRevisionResult(
        scene_family_id=family.id,
        scene_variant_id=variant_id,
        mode=mode,
        status=legacy_status,
        workflow_status=workflow_status,
        engineering_status=engineering_status,
        quick_outcome=quick_outcome,
        result_class=(
            "quick_estimate"
            if mode is CalculationMode.QUICK
            else "professional_check"
        ),
        verification_status=verification_status,
        graph_template_id=graph.id,
        load_cases=resolved_loads,
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
