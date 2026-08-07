from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, pi
from collections.abc import Callable
from typing import Hashable, Literal

import numpy as np

from .errors import CalculationInputError


NodeId = Hashable


def _number(value: float, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        ) from exc
    if not isfinite(numeric):
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        )
    return numeric


def _positive(value: float, field_name: str) -> float:
    numeric = _number(value, field_name)
    if numeric <= 0:
        raise CalculationInputError(
            "non_positive_value", f"{field_name} 必须大于零。", field=field_name
        )
    return numeric


def _real_roots_in_interval(
    coefficients: list[float], lower: float, upper: float
) -> tuple[float, ...]:
    while coefficients and abs(coefficients[0]) <= 1e-14:
        coefficients.pop(0)
    if len(coefficients) <= 1:
        return ()
    roots = np.roots(coefficients)
    accepted: list[float] = []
    tolerance = max(1.0, upper - lower) * 1e-9
    for root in roots:
        if abs(float(root.imag)) > 1e-8:
            continue
        value = float(root.real)
        if lower - tolerance <= value <= upper + tolerance:
            value = min(upper, max(lower, value))
            if not any(abs(value - existing) <= tolerance for existing in accepted):
                accepted.append(value)
    return tuple(sorted(accepted))


# ---------------------------------------------------------------------------
# Continuous Euler-Bernoulli beam
# Base units: N, mm, MPa (= N/mm2), mm4.
# Positive nodal force and q_y act upward; positive rotation is counter-clockwise.
# Reported positive section moment is sagging.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContinuousBeamNode:
    id: NodeId


@dataclass(frozen=True)
class ContinuousBeamSpan:
    id: str
    start: NodeId
    end: NodeId
    length_mm: float
    elastic_modulus_mpa: float
    inertia_mm4: float
    q_y_n_per_mm: float = 0.0


@dataclass(frozen=True)
class ContinuousBeamSupport:
    node: NodeId
    vertical: bool = True
    rotation: bool = False


@dataclass(frozen=True)
class ContinuousBeamNodalLoad:
    node: NodeId
    fy_n: float = 0.0
    mz_nmm: float = 0.0


@dataclass(frozen=True)
class ContinuousBeamModel:
    nodes: tuple[ContinuousBeamNode, ...]
    spans: tuple[ContinuousBeamSpan, ...]
    supports: tuple[ContinuousBeamSupport, ...] = ()
    nodal_loads: tuple[ContinuousBeamNodalLoad, ...] = ()


@dataclass(frozen=True)
class ContinuousBeamNodeDisplacement:
    node: NodeId
    vertical_mm: float
    rotation_rad: float


@dataclass(frozen=True)
class ContinuousBeamReaction:
    node: NodeId
    vertical_n: float
    moment_nmm: float


@dataclass(frozen=True)
class ContinuousBeamSample:
    x_mm: float
    shear_n: float
    moment_nmm: float
    deflection_mm: float
    rotation_rad: float


@dataclass(frozen=True)
class LocatedExtremum:
    value: float
    x_mm: float


@dataclass(frozen=True)
class ContinuousBeamSpanExtrema:
    shear_min_n: LocatedExtremum
    shear_max_n: LocatedExtremum
    moment_min_nmm: LocatedExtremum
    moment_max_nmm: LocatedExtremum
    deflection_min_mm: LocatedExtremum
    deflection_max_mm: LocatedExtremum

    @property
    def moment_abs_max_nmm(self) -> float:
        return max(abs(self.moment_min_nmm.value), abs(self.moment_max_nmm.value))

    @property
    def deflection_abs_max_mm(self) -> float:
        return max(
            abs(self.deflection_min_mm.value), abs(self.deflection_max_mm.value)
        )


@dataclass(frozen=True)
class ContinuousBeamSpanResult:
    span: str
    start_shear_n: float
    start_end_moment_nmm: float
    end_shear_n: float
    end_end_moment_nmm: float
    samples: tuple[ContinuousBeamSample, ...]
    extrema: ContinuousBeamSpanExtrema

    @property
    def local_end_forces(self) -> tuple[float, float, float, float]:
        """Element-on-node forces ordered as Vi, Mi, Vj, Mj."""

        return (
            self.start_shear_n,
            self.start_end_moment_nmm,
            self.end_shear_n,
            self.end_end_moment_nmm,
        )


@dataclass(frozen=True)
class ContinuousBeamResult:
    displacements: dict[NodeId, ContinuousBeamNodeDisplacement]
    reactions: dict[NodeId, ContinuousBeamReaction]
    spans: dict[str, ContinuousBeamSpanResult]
    applied_load_vector: tuple[float, ...] = field(repr=False)


def _beam_stiffness(ei: float, length: float) -> np.ndarray:
    return ei / length**3 * np.array(
        [
            [12.0, 6.0 * length, -12.0, 6.0 * length],
            [6.0 * length, 4.0 * length**2, -6.0 * length, 2.0 * length**2],
            [-12.0, -6.0 * length, 12.0, -6.0 * length],
            [6.0 * length, 2.0 * length**2, -6.0 * length, 4.0 * length**2],
        ],
        dtype=float,
    )


def _beam_uniform_load_vector(q_y: float, length: float) -> np.ndarray:
    return np.array(
        [
            q_y * length / 2.0,
            q_y * length**2 / 12.0,
            q_y * length / 2.0,
            -q_y * length**2 / 12.0,
        ],
        dtype=float,
    )


def _validate_beam_topology(
    model: ContinuousBeamModel,
) -> tuple[dict[NodeId, int], dict[NodeId, ContinuousBeamSupport]]:
    if len(model.nodes) < 2:
        raise CalculationInputError(
            "missing_nodes", "连续梁至少需要两个节点。", field="nodes"
        )
    if not model.spans:
        raise CalculationInputError(
            "missing_spans", "连续梁至少需要一个跨。", field="spans"
        )

    indices: dict[NodeId, int] = {}
    for index, node in enumerate(model.nodes):
        if node.id in indices:
            raise CalculationInputError(
                "duplicate_node", f"节点编号 {node.id!r} 重复。", field="nodes"
            )
        indices[node.id] = index

    span_ids: set[str] = set()
    adjacency: dict[NodeId, set[NodeId]] = {node.id: set() for node in model.nodes}
    for span in model.spans:
        if span.id in span_ids:
            raise CalculationInputError(
                "duplicate_span", f"跨编号 {span.id!r} 重复。", field="spans"
            )
        span_ids.add(span.id)
        if span.start not in indices or span.end not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"跨 {span.id!r} 引用了不存在的节点。",
                field="spans",
            )
        if span.start == span.end:
            raise CalculationInputError(
                "zero_length_span", f"跨 {span.id!r} 两端节点相同。", field="spans"
            )
        _positive(span.length_mm, f"spans.{span.id}.length_mm")
        _positive(span.elastic_modulus_mpa, f"spans.{span.id}.elastic_modulus_mpa")
        _positive(span.inertia_mm4, f"spans.{span.id}.inertia_mm4")
        _number(span.q_y_n_per_mm, f"spans.{span.id}.q_y_n_per_mm")
        if span.end in adjacency[span.start]:
            raise CalculationInputError(
                "duplicate_connectivity",
                f"节点 {span.start!r} 与 {span.end!r} 之间存在重复跨。",
                field="spans",
            )
        adjacency[span.start].add(span.end)
        adjacency[span.end].add(span.start)

    if len(model.spans) != len(model.nodes) - 1 or any(
        len(neighbours) > 2 for neighbours in adjacency.values()
    ):
        raise CalculationInputError(
            "invalid_beam_topology",
            "连续梁必须是无分支、无闭环的单一路径。",
            field="spans",
        )
    visited: set[NodeId] = set()
    pending = [model.nodes[0].id]
    while pending:
        node_id = pending.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        pending.extend(adjacency[node_id] - visited)
    if len(visited) != len(model.nodes):
        raise CalculationInputError(
            "disconnected_beam", "连续梁包含未连接节点。", field="spans"
        )

    supports: dict[NodeId, ContinuousBeamSupport] = {}
    for support in model.supports:
        if support.node not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"支承引用了不存在的节点 {support.node!r}。",
                field="supports",
            )
        previous = supports.get(support.node)
        supports[support.node] = ContinuousBeamSupport(
            support.node,
            vertical=support.vertical or bool(previous and previous.vertical),
            rotation=support.rotation or bool(previous and previous.rotation),
        )
    if not supports:
        raise CalculationInputError(
            "singular_stiffness_matrix", "连续梁没有任何有效支承。", field="supports"
        )

    for load in model.nodal_loads:
        if load.node not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"节点荷载引用了不存在的节点 {load.node!r}。",
                field="nodal_loads",
            )
        _number(load.fy_n, "nodal_loads.fy_n")
        _number(load.mz_nmm, "nodal_loads.mz_nmm")
    return indices, supports


def _located_extrema(
    points: tuple[float, ...], evaluator: Callable[[float], float]
) -> tuple[LocatedExtremum, LocatedExtremum]:
    values = [(float(x), float(evaluator(x))) for x in points]
    minimum = min(values, key=lambda item: item[1])
    maximum = max(values, key=lambda item: item[1])
    return LocatedExtremum(minimum[1], minimum[0]), LocatedExtremum(
        maximum[1], maximum[0]
    )


def solve_continuous_beam(
    model: ContinuousBeamModel, *, samples_per_span: int = 101
) -> ContinuousBeamResult:
    """Solve a prismatic-per-span Euler-Bernoulli continuous beam.

    The solver is a linear-elastic direct-stiffness analysis. It does not perform
    section resistance, cracking, shear deformation, lateral stability or code
    compliance checks.
    """

    if samples_per_span < 2:
        raise CalculationInputError(
            "invalid_sample_count",
            "每跨采样点数至少为 2。",
            field="samples_per_span",
        )
    indices, supports = _validate_beam_topology(model)
    dof_count = 2 * len(model.nodes)
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    loads = np.zeros(dof_count, dtype=float)
    prepared: dict[str, tuple[ContinuousBeamSpan, np.ndarray, np.ndarray, tuple[int, ...]]] = {}

    for span in model.spans:
        length = float(span.length_mm)
        ei = float(span.elastic_modulus_mpa) * float(span.inertia_mm4)
        local_k = _beam_stiffness(ei, length)
        fixed_load = _beam_uniform_load_vector(float(span.q_y_n_per_mm), length)
        start_index, end_index = indices[span.start], indices[span.end]
        dofs = (
            2 * start_index,
            2 * start_index + 1,
            2 * end_index,
            2 * end_index + 1,
        )
        stiffness[np.ix_(dofs, dofs)] += local_k
        loads[list(dofs)] += fixed_load
        prepared[span.id] = (span, local_k, fixed_load, dofs)

    for load in model.nodal_loads:
        index = indices[load.node]
        loads[2 * index] += float(load.fy_n)
        loads[2 * index + 1] += float(load.mz_nmm)

    restrained: list[int] = []
    for node_id, support in supports.items():
        index = indices[node_id]
        if support.vertical:
            restrained.append(2 * index)
        if support.rotation:
            restrained.append(2 * index + 1)
    restrained = sorted(set(restrained))
    free = [dof for dof in range(dof_count) if dof not in restrained]
    displacement = np.zeros(dof_count, dtype=float)
    if free:
        kff = stiffness[np.ix_(free, free)]
        if np.linalg.matrix_rank(kff) < len(free):
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "连续梁支承不足或存在刚体自由度。",
                field="supports",
            )
        try:
            displacement[free] = np.linalg.solve(kff, loads[free])
        except np.linalg.LinAlgError as exc:
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "连续梁刚度矩阵奇异。",
                field="supports",
            ) from exc
    reaction_vector = stiffness @ displacement - loads

    node_displacements = {
        node.id: ContinuousBeamNodeDisplacement(
            node.id,
            vertical_mm=float(displacement[2 * index]),
            rotation_rad=float(displacement[2 * index + 1]),
        )
        for index, node in enumerate(model.nodes)
    }
    reactions = {
        node_id: ContinuousBeamReaction(
            node_id,
            vertical_n=float(reaction_vector[2 * indices[node_id]])
            if support.vertical
            else 0.0,
            moment_nmm=float(reaction_vector[2 * indices[node_id] + 1])
            if support.rotation
            else 0.0,
        )
        for node_id, support in supports.items()
    }

    span_results: dict[str, ContinuousBeamSpanResult] = {}
    for span_id, (span, local_k, fixed_load, dofs) in prepared.items():
        length = float(span.length_mm)
        ei = float(span.elastic_modulus_mpa) * float(span.inertia_mm4)
        q = float(span.q_y_n_per_mm)
        local_displacement = displacement[list(dofs)]
        end_forces = local_k @ local_displacement - fixed_load
        vi, mi, vj, mj = (float(value) for value in end_forces)
        v0, theta0 = float(local_displacement[0]), float(local_displacement[1])

        def shear(x: float) -> float:
            return vi + q * x

        def moment(x: float) -> float:
            return -mi + vi * x + q * x**2 / 2.0

        def rotation(x: float) -> float:
            return theta0 + (-mi * x + vi * x**2 / 2.0 + q * x**3 / 6.0) / ei

        def deflection(x: float) -> float:
            return v0 + theta0 * x + (
                -mi * x**2 / 2.0 + vi * x**3 / 6.0 + q * x**4 / 24.0
            ) / ei

        shear_points = (0.0, length)
        moment_points = [0.0, length]
        if abs(q) > 1e-14:
            zero_shear = -vi / q
            if 0.0 < zero_shear < length:
                moment_points.append(zero_shear)
        deflection_points = [0.0, length]
        deflection_points.extend(
            _real_roots_in_interval(
                [q / 6.0, vi / 2.0, -mi, ei * theta0], 0.0, length
            )
        )
        shear_min, shear_max = _located_extrema(shear_points, shear)
        moment_min, moment_max = _located_extrema(tuple(moment_points), moment)
        deflection_min, deflection_max = _located_extrema(
            tuple(deflection_points), deflection
        )
        x_values = np.linspace(0.0, length, samples_per_span)
        samples = tuple(
            ContinuousBeamSample(
                x_mm=float(x),
                shear_n=shear(float(x)),
                moment_nmm=moment(float(x)),
                deflection_mm=deflection(float(x)),
                rotation_rad=rotation(float(x)),
            )
            for x in x_values
        )
        span_results[span_id] = ContinuousBeamSpanResult(
            span=span_id,
            start_shear_n=vi,
            start_end_moment_nmm=mi,
            end_shear_n=vj,
            end_end_moment_nmm=mj,
            samples=samples,
            extrema=ContinuousBeamSpanExtrema(
                shear_min,
                shear_max,
                moment_min,
                moment_max,
                deflection_min,
                deflection_max,
            ),
        )

    return ContinuousBeamResult(
        displacements=node_displacements,
        reactions=reactions,
        spans=span_results,
        applied_load_vector=tuple(float(value) for value in loads),
    )


# ---------------------------------------------------------------------------
# Linear 2D truss
# Base units: N, mm, MPa (= N/mm2), mm2.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrussNode:
    id: NodeId
    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class TrussMember:
    id: str
    start: NodeId
    end: NodeId
    area_mm2: float
    elastic_modulus_mpa: float


@dataclass(frozen=True)
class TrussRestraint:
    node: NodeId
    ux: bool = False
    uy: bool = False


@dataclass(frozen=True)
class TrussNodalLoad:
    node: NodeId
    fx_n: float = 0.0
    fy_n: float = 0.0


@dataclass(frozen=True)
class TrussModel:
    nodes: tuple[TrussNode, ...]
    members: tuple[TrussMember, ...]
    restraints: tuple[TrussRestraint, ...]
    nodal_loads: tuple[TrussNodalLoad, ...] = ()


@dataclass(frozen=True)
class TrussNodeDisplacement:
    node: NodeId
    ux_mm: float
    uy_mm: float


@dataclass(frozen=True)
class TrussReaction:
    node: NodeId
    fx_n: float
    fy_n: float

    @property
    def components_6dof(self) -> dict[str, float]:
        return {
            "Fx": self.fx_n,
            "Fy": self.fy_n,
            "Fz": 0.0,
            "Mx": 0.0,
            "My": 0.0,
            "Mz": 0.0,
        }


@dataclass(frozen=True)
class TrussMemberResult:
    member: str
    length_mm: float
    axial_force_n: float
    stress_mpa: float
    strain: float


@dataclass(frozen=True)
class TrussResult:
    displacements: dict[NodeId, TrussNodeDisplacement]
    reactions: dict[NodeId, TrussReaction]
    members: dict[str, TrussMemberResult]
    applied_load_vector: tuple[float, ...] = field(repr=False)


@dataclass(frozen=True)
class _PreparedTrussMember:
    definition: TrussMember
    length_mm: float
    c: float
    s: float
    dofs: tuple[int, int, int, int]


def solve_planar_truss(model: TrussModel) -> TrussResult:
    """Solve a pin-jointed, small-displacement, axial-only 2D truss."""

    if len(model.nodes) < 2:
        raise CalculationInputError(
            "missing_nodes", "平面桁架至少需要两个节点。", field="nodes"
        )
    if not model.members:
        raise CalculationInputError(
            "missing_members", "平面桁架至少需要一根杆件。", field="members"
        )
    indices: dict[NodeId, int] = {}
    coordinates: dict[NodeId, tuple[float, float]] = {}
    for index, node in enumerate(model.nodes):
        if node.id in indices:
            raise CalculationInputError(
                "duplicate_node", f"节点编号 {node.id!r} 重复。", field="nodes"
            )
        indices[node.id] = index
        coordinates[node.id] = (
            _number(node.x_mm, f"nodes.{node.id}.x_mm"),
            _number(node.y_mm, f"nodes.{node.id}.y_mm"),
        )

    dof_count = 2 * len(model.nodes)
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    prepared: dict[str, _PreparedTrussMember] = {}
    connected: set[NodeId] = set()
    connectivity: set[frozenset[NodeId]] = set()
    for member in model.members:
        if member.id in prepared:
            raise CalculationInputError(
                "duplicate_member", f"杆件编号 {member.id!r} 重复。", field="members"
            )
        if member.start not in indices or member.end not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"杆件 {member.id!r} 引用了不存在的节点。",
                field="members",
            )
        if member.start == member.end:
            raise CalculationInputError(
                "zero_length_member",
                f"杆件 {member.id!r} 两端节点相同。",
                field="members",
            )
        pair = frozenset((member.start, member.end))
        if pair in connectivity:
            raise CalculationInputError(
                "duplicate_connectivity",
                f"节点 {member.start!r} 与 {member.end!r} 之间存在重复杆件。",
                field="members",
            )
        connectivity.add(pair)
        x1, y1 = coordinates[member.start]
        x2, y2 = coordinates[member.end]
        dx, dy = x2 - x1, y2 - y1
        length = float(np.hypot(dx, dy))
        if length <= 1e-12:
            raise CalculationInputError(
                "zero_length_member", f"杆件 {member.id!r} 长度为零。", field="members"
            )
        area = _positive(member.area_mm2, f"members.{member.id}.area_mm2")
        elastic_modulus = _positive(
            member.elastic_modulus_mpa,
            f"members.{member.id}.elastic_modulus_mpa",
        )
        c, s = dx / length, dy / length
        vector = np.array([-c, -s, c, s], dtype=float)
        member_stiffness = elastic_modulus * area / length * np.outer(vector, vector)
        start_index, end_index = indices[member.start], indices[member.end]
        dofs = (
            2 * start_index,
            2 * start_index + 1,
            2 * end_index,
            2 * end_index + 1,
        )
        stiffness[np.ix_(dofs, dofs)] += member_stiffness
        prepared[member.id] = _PreparedTrussMember(member, length, c, s, dofs)
        connected.update((member.start, member.end))
    if connected != set(indices):
        raise CalculationInputError(
            "disconnected_node", "平面桁架包含未连接节点。", field="nodes"
        )

    restraints: dict[NodeId, TrussRestraint] = {}
    for restraint in model.restraints:
        if restraint.node not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"约束引用了不存在的节点 {restraint.node!r}。",
                field="restraints",
            )
        previous = restraints.get(restraint.node)
        restraints[restraint.node] = TrussRestraint(
            restraint.node,
            ux=restraint.ux or bool(previous and previous.ux),
            uy=restraint.uy or bool(previous and previous.uy),
        )
    if not restraints:
        raise CalculationInputError(
            "singular_stiffness_matrix", "平面桁架没有任何约束。", field="restraints"
        )

    loads = np.zeros(dof_count, dtype=float)
    for load in model.nodal_loads:
        if load.node not in indices:
            raise CalculationInputError(
                "unknown_node",
                f"节点荷载引用了不存在的节点 {load.node!r}。",
                field="nodal_loads",
            )
        index = indices[load.node]
        loads[2 * index] += _number(load.fx_n, "nodal_loads.fx_n")
        loads[2 * index + 1] += _number(load.fy_n, "nodal_loads.fy_n")

    restrained: list[int] = []
    for node_id, restraint in restraints.items():
        index = indices[node_id]
        if restraint.ux:
            restrained.append(2 * index)
        if restraint.uy:
            restrained.append(2 * index + 1)
    restrained = sorted(set(restrained))
    free = [dof for dof in range(dof_count) if dof not in restrained]
    displacements = np.zeros(dof_count, dtype=float)
    if free:
        kff = stiffness[np.ix_(free, free)]
        if np.linalg.matrix_rank(kff) < len(free):
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "平面桁架不稳定、约束不足或包含机构。",
                field="restraints",
            )
        try:
            displacements[free] = np.linalg.solve(kff, loads[free])
        except np.linalg.LinAlgError as exc:
            raise CalculationInputError(
                "singular_stiffness_matrix", "平面桁架刚度矩阵奇异。", field="restraints"
            ) from exc
    reactions_vector = stiffness @ displacements - loads

    node_displacements = {
        node.id: TrussNodeDisplacement(
            node.id,
            ux_mm=float(displacements[2 * index]),
            uy_mm=float(displacements[2 * index + 1]),
        )
        for index, node in enumerate(model.nodes)
    }
    reactions = {
        node_id: TrussReaction(
            node_id,
            fx_n=float(reactions_vector[2 * indices[node_id]])
            if restraint.ux
            else 0.0,
            fy_n=float(reactions_vector[2 * indices[node_id] + 1])
            if restraint.uy
            else 0.0,
        )
        for node_id, restraint in restraints.items()
    }
    member_results: dict[str, TrussMemberResult] = {}
    for member_id, member in prepared.items():
        local_displacement = displacements[list(member.dofs)]
        extension = float(
            np.dot(
                np.array([-member.c, -member.s, member.c, member.s]),
                local_displacement,
            )
        )
        strain = extension / member.length_mm
        axial_force = (
            float(member.definition.elastic_modulus_mpa)
            * float(member.definition.area_mm2)
            * strain
        )
        member_results[member_id] = TrussMemberResult(
            member=member_id,
            length_mm=member.length_mm,
            axial_force_n=axial_force,
            stress_mpa=axial_force / float(member.definition.area_mm2),
            strain=strain,
        )

    return TrussResult(
        displacements=node_displacements,
        reactions=reactions,
        members=member_results,
        applied_load_vector=tuple(float(value) for value in loads),
    )


# ---------------------------------------------------------------------------
# Rectangular isotropic RC slab: bounded elastic coefficient interface.
# ---------------------------------------------------------------------------


SlabSupportCondition = Literal["four_edges_simply_supported", "four_edges_fixed"]


@dataclass(frozen=True)
class RectangularRCTwoWaySlabInput:
    short_span_m: float
    long_span_m: float
    thickness_mm: float
    elastic_modulus_mpa: float
    uniform_load_kpa: float
    support_condition: SlabSupportCondition
    poisson_ratio: float = 0.2


@dataclass(frozen=True)
class RectangularRCTwoWaySlabResult:
    support_condition: SlabSupportCondition
    aspect_ratio: float
    plate_rigidity_nmm: float
    positive_moment_short_knm_per_m: float
    positive_moment_long_knm_per_m: float
    negative_moment_short_knm_per_m: float
    negative_moment_long_knm_per_m: float
    positive_coefficient_short: float
    positive_coefficient_long: float
    negative_coefficient_short: float
    negative_coefficient_long: float
    directional_moment_share_short: float
    directional_moment_share_long: float
    maximum_deflection_mm: float
    deflection_coefficient: float
    method: str
    verification_status: str
    applicability: tuple[str, ...]
    exclusions: tuple[str, ...]


def _ritz_shape_terms(
    x: np.ndarray,
    y: np.ndarray,
    a: float,
    b: float,
    power: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    u, v = pi * x / a, pi * y / b
    if power == 1:
        gx, gy = np.sin(u), np.sin(v)
        gx_u, gy_v = np.cos(u), np.cos(v)
        gx_uu, gy_vv = -np.sin(u), -np.sin(v)
    else:
        gx, gy = np.sin(u) ** 2, np.sin(v) ** 2
        gx_u, gy_v = np.sin(2.0 * u), np.sin(2.0 * v)
        gx_uu, gy_vv = 2.0 * np.cos(2.0 * u), 2.0 * np.cos(2.0 * v)
    phi = gx * gy
    phi_xx = (pi / a) ** 2 * gx_uu * gy
    phi_yy = (pi / b) ** 2 * gx * gy_vv
    phi_xy = (pi / a) * (pi / b) * gx_u * gy_v
    return phi, phi_xx, phi_yy, phi_xy, gx, gy


def analyze_rectangular_rc_two_way_slab(
    slab: RectangularRCTwoWaySlabInput,
) -> RectangularRCTwoWaySlabResult:
    """Return bounded linear-elastic plate coefficients, not RC resistance.

    A one-term Rayleigh-Ritz field is used. ``sin(pi*x/a)sin(pi*y/b)`` models
    four simply supported edges and ``sin^2(pi*x/a)sin^2(pi*y/b)`` models four
    fixed edges. The interface intentionally rejects mixed edges, openings,
    concentrated loads and aspect ratios outside two-way action.
    """

    short_span_m = _positive(slab.short_span_m, "short_span_m")
    long_span_m = _positive(slab.long_span_m, "long_span_m")
    thickness = _positive(slab.thickness_mm, "thickness_mm")
    elastic_modulus = _positive(slab.elastic_modulus_mpa, "elastic_modulus_mpa")
    uniform_load = _number(slab.uniform_load_kpa, "uniform_load_kpa")
    poisson = _number(slab.poisson_ratio, "poisson_ratio")
    if long_span_m < short_span_m:
        raise CalculationInputError(
            "invalid_span_order",
            "long_span_m 不得小于 short_span_m。",
            field="long_span_m",
        )
    aspect_ratio = long_span_m / short_span_m
    if aspect_ratio > 2.0 + 1e-12:
        raise CalculationInputError(
            "outside_two_way_scope",
            "长短边比大于 2.0，超出本双向板弹性接口范围。",
            field="long_span_m",
            details={"aspect_ratio": aspect_ratio, "maximum": 2.0},
        )
    if uniform_load < 0:
        raise CalculationInputError(
            "invalid_load", "均布面荷载不得小于零。", field="uniform_load_kpa"
        )
    if not 0.0 <= poisson < 0.5:
        raise CalculationInputError(
            "invalid_poisson_ratio",
            "泊松比必须满足 0 <= nu < 0.5。",
            field="poisson_ratio",
        )
    if slab.support_condition not in (
        "four_edges_simply_supported",
        "four_edges_fixed",
    ):
        raise CalculationInputError(
            "unsupported_edge_condition",
            "仅支持四边简支或四边固定且四边边界相同。",
            field="support_condition",
        )
    short_span_mm = short_span_m * 1000.0
    long_span_mm = long_span_m * 1000.0
    thickness_ratio = thickness / short_span_mm
    if not 0.01 <= thickness_ratio <= 0.10:
        raise CalculationInputError(
            "outside_thin_plate_scope",
            "板厚与短跨比必须位于 0.01 至 0.10，超出薄板弹性模型范围。",
            field="thickness_mm",
            details={"thickness_to_short_span": thickness_ratio},
        )

    rigidity = elastic_modulus * thickness**3 / (12.0 * (1.0 - poisson**2))
    q_n_per_mm2 = uniform_load * 0.001
    power = 1 if slab.support_condition == "four_edges_simply_supported" else 2

    # Gauss integration derives the geometry-specific coefficient from the
    # admissible elastic field rather than hiding a design-code table.
    points, weights = np.polynomial.legendre.leggauss(32)
    x = (points + 1.0) * short_span_mm / 2.0
    y = (points + 1.0) * long_span_mm / 2.0
    xx, yy = np.meshgrid(x, y, indexing="ij")
    wx, wy = np.meshgrid(weights, weights, indexing="ij")
    jacobian = short_span_mm * long_span_mm / 4.0
    integration_weights = wx * wy * jacobian
    phi, phi_xx, phi_yy, phi_xy, _, _ = _ritz_shape_terms(
        xx, yy, short_span_mm, long_span_mm, power
    )
    load_integral = float(np.sum(phi * integration_weights))
    curvature_integral = float(
        np.sum(
            (
                phi_xx**2
                + phi_yy**2
                + 2.0 * poisson * phi_xx * phi_yy
                + 2.0 * (1.0 - poisson) * phi_xy**2
            )
            * integration_weights
        )
    )
    amplitude_mm = (
        q_n_per_mm2 * load_integral / (rigidity * curvature_integral)
        if q_n_per_mm2 > 0
        else 0.0
    )

    def moments_at(x_mm: float, y_mm: float) -> tuple[float, float]:
        x_value = np.array([[x_mm]], dtype=float)
        y_value = np.array([[y_mm]], dtype=float)
        _, dxx, dyy, _, _, _ = _ritz_shape_terms(
            x_value, y_value, short_span_mm, long_span_mm, power
        )
        moment_short_n = -rigidity * amplitude_mm * float(
            dxx[0, 0] + poisson * dyy[0, 0]
        )
        moment_long_n = -rigidity * amplitude_mm * float(
            dyy[0, 0] + poisson * dxx[0, 0]
        )
        return moment_short_n / 1000.0, moment_long_n / 1000.0

    positive_short, positive_long = moments_at(
        short_span_mm / 2.0, long_span_mm / 2.0
    )
    if power == 2:
        negative_short, _ = moments_at(0.0, long_span_mm / 2.0)
        _, negative_long = moments_at(short_span_mm / 2.0, 0.0)
    else:
        negative_short = negative_long = 0.0

    denominator_short = uniform_load * short_span_m**2
    denominator_long = uniform_load * long_span_m**2
    if uniform_load > 0:
        positive_coefficient_short = positive_short / denominator_short
        positive_coefficient_long = positive_long / denominator_long
        negative_coefficient_short = negative_short / denominator_short
        negative_coefficient_long = negative_long / denominator_long
        deflection_coefficient = (
            amplitude_mm * rigidity / (q_n_per_mm2 * short_span_mm**4)
        )
    else:
        positive_coefficient_short = positive_coefficient_long = 0.0
        negative_coefficient_short = negative_coefficient_long = 0.0
        deflection_coefficient = 0.0
    moment_sum = abs(positive_short) + abs(positive_long)
    share_short = abs(positive_short) / moment_sum if moment_sum else 0.5

    return RectangularRCTwoWaySlabResult(
        support_condition=slab.support_condition,
        aspect_ratio=aspect_ratio,
        plate_rigidity_nmm=rigidity,
        positive_moment_short_knm_per_m=positive_short,
        positive_moment_long_knm_per_m=positive_long,
        negative_moment_short_knm_per_m=negative_short,
        negative_moment_long_knm_per_m=negative_long,
        positive_coefficient_short=positive_coefficient_short,
        positive_coefficient_long=positive_coefficient_long,
        negative_coefficient_short=negative_coefficient_short,
        negative_coefficient_long=negative_coefficient_long,
        directional_moment_share_short=share_short,
        directional_moment_share_long=1.0 - share_short,
        maximum_deflection_mm=amplitude_mm,
        deflection_coefficient=deflection_coefficient,
        method="one_term_rayleigh_ritz_elastic_coefficient",
        verification_status="analytical_elastic_only",
        applicability=(
            "规则矩形、等厚、各向同性、线弹性薄板",
            "全板均布竖向荷载",
            "四边全部简支或四边全部固定",
            "长短边比不大于 2.0",
        ),
        exclusions=(
            "不计算钢筋、裂缝、冲切、剪切或规范承载力",
            "不覆盖混合边界、开洞、集中荷载、柱帽和不规则板",
            "不考虑长期、徐变、收缩、开裂刚度或几何非线性",
        ),
    )
