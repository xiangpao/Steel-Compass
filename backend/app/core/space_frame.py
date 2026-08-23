from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, isfinite, radians, sin, sqrt
from typing import Literal

import numpy as np
from scipy.linalg import eigvals

from .errors import CalculationInputError


MAX_SPACE_FRAME_NODES = 200
MAX_SPACE_FRAME_MEMBERS = 400


@dataclass(frozen=True)
class SpaceNode:
    id: str
    x_m: float
    y_m: float
    z_m: float


@dataclass(frozen=True)
class SpaceMember:
    id: str
    start: str
    end: str
    area_mm2: float
    iy_mm4: float
    iz_mm4: float
    torsion_mm4: float
    elastic_modulus_mpa: float = 206_000.0
    shear_modulus_mpa: float = 79_000.0
    behavior: Literal["frame", "truss"] = "frame"
    start_releases: tuple[bool, bool, bool, bool, bool, bool] = (False,) * 6
    end_releases: tuple[bool, bool, bool, bool, bool, bool] = (False,) * 6
    rigid_offset_start_m: float = 0.0
    rigid_offset_end_m: float = 0.0
    local_axis_rotation_deg: float = 0.0


@dataclass(frozen=True)
class SpaceRestraint:
    node: str
    ux: bool = False
    uy: bool = False
    uz: bool = False
    rx: bool = False
    ry: bool = False
    rz: bool = False


@dataclass(frozen=True)
class SpaceNodalLoad:
    node: str
    fx_kn: float = 0.0
    fy_kn: float = 0.0
    fz_kn: float = 0.0
    mx_kn_m: float = 0.0
    my_kn_m: float = 0.0
    mz_kn_m: float = 0.0


@dataclass(frozen=True)
class SpaceMemberUniformLoad:
    member: str
    qx_kn_m: float = 0.0
    qy_kn_m: float = 0.0
    qz_kn_m: float = 0.0


@dataclass(frozen=True)
class SpaceFrameModel:
    nodes: tuple[SpaceNode, ...]
    members: tuple[SpaceMember, ...]
    restraints: tuple[SpaceRestraint, ...] = ()
    nodal_loads: tuple[SpaceNodalLoad, ...] = ()
    member_uniform_loads: tuple[SpaceMemberUniformLoad, ...] = ()


@dataclass(frozen=True)
class SpaceNodeResult:
    node: str
    ux_mm: float
    uy_mm: float
    uz_mm: float
    rx_rad: float
    ry_rad: float
    rz_rad: float


@dataclass(frozen=True)
class SpaceReaction:
    node: str
    fx_kn: float
    fy_kn: float
    fz_kn: float
    mx_kn_m: float
    my_kn_m: float
    mz_kn_m: float


@dataclass(frozen=True)
class SpaceMemberResult:
    member: str
    local_end_forces: tuple[float, ...]


@dataclass(frozen=True)
class SpaceFrameResult:
    displacements: dict[str, SpaceNodeResult]
    reactions: dict[str, SpaceReaction]
    members: dict[str, SpaceMemberResult]
    load_balance_kn: tuple[float, float, float]
    member_uniform_loads_local: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SpaceStabilityResult:
    second_order: SpaceFrameResult
    buckling_factors: tuple[float, ...]
    amplification_ratio: float


def _finite_positive(value: float, field_name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0:
        raise CalculationInputError("invalid_space_frame_property", f"{field_name} 必须是有限正数", field=field_name)
    return numeric


def _local_axes(
    start: np.ndarray,
    end: np.ndarray,
    local_axis_rotation_deg: float = 0.0,
) -> tuple[np.ndarray, float]:
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length <= 1e-9:
        raise CalculationInputError("zero_length_member", "空间杆件起点和终点不得重合", field="members")
    ex = delta / length
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(ex, reference))) > 0.95:
        reference = np.array([0.0, 1.0, 0.0])
    ey = np.cross(reference, ex)
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    if abs(local_axis_rotation_deg) > 1e-12:
        angle = radians(local_axis_rotation_deg)
        rotated_ey = cos(angle) * ey + sin(angle) * ez
        rotated_ez = -sin(angle) * ey + cos(angle) * ez
        ey, ez = rotated_ey, rotated_ez
    return np.vstack((ex, ey, ez)), length


def _released_dofs(member: SpaceMember) -> list[int]:
    return [
        index
        for index, active in enumerate((*member.start_releases, *member.end_releases))
        if active
    ]


def _frame_local_stiffness(member: SpaceMember, length_mm: float, *, apply_releases: bool = True) -> np.ndarray:
    e = _finite_positive(member.elastic_modulus_mpa, "elastic_modulus_mpa")
    g = _finite_positive(member.shear_modulus_mpa, "shear_modulus_mpa")
    a = _finite_positive(member.area_mm2, "area_mm2")
    iy = _finite_positive(member.iy_mm4, "iy_mm4")
    iz = _finite_positive(member.iz_mm4, "iz_mm4")
    torsion = _finite_positive(member.torsion_mm4, "torsion_mm4")
    offset = (member.rigid_offset_start_m + member.rigid_offset_end_m) * 1000
    if offset >= length_mm - 1e-6:
        raise CalculationInputError(
            "invalid_rigid_offset",
            f"杆件 {member.id} 两端刚性偏移之和必须小于杆件长度",
            field="rigid_offset",
        )
    length = length_mm - offset
    k = np.zeros((12, 12), dtype=float)

    axial = e * a / length
    for i, j, sign in ((0, 0, 1), (0, 6, -1), (6, 0, -1), (6, 6, 1)):
        k[i, j] += sign * axial

    torsional = g * torsion / length
    for i, j, sign in ((3, 3, 1), (3, 9, -1), (9, 3, -1), (9, 9, 1)):
        k[i, j] += sign * torsional

    def add_bending(indices: tuple[int, int, int, int], ei: float, rotation_sign: float) -> None:
        l2 = length * length
        l3 = l2 * length
        base = np.array(
            [
                [12 * ei / l3, 6 * ei / l2, -12 * ei / l3, 6 * ei / l2],
                [6 * ei / l2, 4 * ei / length, -6 * ei / l2, 2 * ei / length],
                [-12 * ei / l3, -6 * ei / l2, 12 * ei / l3, -6 * ei / l2],
                [6 * ei / l2, 2 * ei / length, -6 * ei / l2, 4 * ei / length],
            ],
            dtype=float,
        )
        signs = np.diag([1.0, rotation_sign, 1.0, rotation_sign])
        block = signs @ base @ signs
        for row, global_row in enumerate(indices):
            for col, global_col in enumerate(indices):
                k[global_row, global_col] += block[row, col]

    add_bending((1, 5, 7, 11), e * iz, 1.0)
    add_bending((2, 4, 8, 10), e * iy, -1.0)
    released = _released_dofs(member) if apply_releases else []
    if not released:
        return k
    retained = [index for index in range(12) if index not in released]
    k_rr = k[np.ix_(retained, retained)]
    k_rc = k[np.ix_(retained, released)]
    k_cc = k[np.ix_(released, released)]
    condensed = k_rr
    if k_cc.size and np.linalg.matrix_rank(k_cc) == len(released):
        condensed = k_rr - k_rc @ np.linalg.solve(k_cc, k_rc.T)
    result = np.zeros((12, 12), dtype=float)
    result[np.ix_(retained, retained)] = condensed
    return result


def _condense_local_load(member: SpaceMember, full_stiffness: np.ndarray, load: np.ndarray) -> np.ndarray:
    released = _released_dofs(member)
    if not released:
        return load
    retained = [index for index in range(12) if index not in released]
    k_rc = full_stiffness[np.ix_(retained, released)]
    k_cc = full_stiffness[np.ix_(released, released)]
    condensed = np.zeros(12, dtype=float)
    condensed[retained] = load[retained]
    if k_cc.size and np.linalg.matrix_rank(k_cc) == len(released):
        condensed[retained] -= k_rc @ np.linalg.solve(k_cc, load[released])
    return condensed


def _uniform_local_load_vector(member: SpaceMember, rotation: np.ndarray, length_mm: float, load: SpaceMemberUniformLoad) -> np.ndarray:
    if member.behavior == "truss":
        raise CalculationInputError(
            "unsupported_truss_member_load",
            f"桁架杆件 {member.id} 不接受横向均布荷载，请先分配到桁架节点",
            field="member_uniform_loads",
        )
    effective_length = length_mm - (member.rigid_offset_start_m + member.rigid_offset_end_m) * 1000
    global_q_n_mm = np.array([load.qx_kn_m, load.qy_kn_m, load.qz_kn_m], dtype=float)
    qx, qy, qz = rotation @ global_q_n_mm
    fixed = np.zeros(12, dtype=float)
    fixed[[0, 6]] = qx * effective_length / 2
    fixed[[1, 7]] = qy * effective_length / 2
    fixed[5] = qy * effective_length**2 / 12
    fixed[11] = -fixed[5]
    fixed[[2, 8]] = qz * effective_length / 2
    fixed[4] = -qz * effective_length**2 / 12
    fixed[10] = -fixed[4]
    full_stiffness = _frame_local_stiffness(member, length_mm, apply_releases=False)
    return _condense_local_load(member, full_stiffness, fixed)


def _assemble_load_vector(
    model: SpaceFrameModel,
    node_index: dict[str, int],
    prepared: dict[str, tuple[np.ndarray, np.ndarray, tuple[int, ...], float]],
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    load_vector = np.zeros(len(model.nodes) * 6, dtype=float)
    for load in model.nodal_loads:
        if load.node not in node_index:
            raise CalculationInputError("unknown_space_load_node", f"荷载引用了不存在的节点 {load.node}", field="nodal_loads")
        base = node_index[load.node] * 6
        load_vector[base : base + 6] += np.array(
            [load.fx_kn * 1000, load.fy_kn * 1000, load.fz_kn * 1000, load.mx_kn_m * 1e6, load.my_kn_m * 1e6, load.mz_kn_m * 1e6]
        )
    member_by_id = {member.id: member for member in model.members}
    fixed_end_loads: dict[str, np.ndarray] = {}
    local_uniform_loads: dict[str, np.ndarray] = {}
    for load in model.member_uniform_loads:
        member = member_by_id.get(load.member)
        if member is None:
            raise CalculationInputError("unknown_space_member_load", f"均布荷载引用了不存在的杆件 {load.member}", field="member_uniform_loads")
        _, transform, dofs, length = prepared[member.id]
        local_q = transform[0:3, 0:3] @ np.array([load.qx_kn_m, load.qy_kn_m, load.qz_kn_m], dtype=float)
        local_uniform_loads[member.id] = local_uniform_loads.get(member.id, np.zeros(3, dtype=float)) + local_q
        local_fixed = _uniform_local_load_vector(member, transform[0:3, 0:3], length, load)
        fixed_end_loads[member.id] = fixed_end_loads.get(member.id, np.zeros(12, dtype=float)) + local_fixed
        load_vector[list(dofs)] += transform.T @ local_fixed
    return load_vector, fixed_end_loads, local_uniform_loads


def _truss_global_stiffness(member: SpaceMember, direction: np.ndarray, length_mm: float) -> np.ndarray:
    e = _finite_positive(member.elastic_modulus_mpa, "elastic_modulus_mpa")
    a = _finite_positive(member.area_mm2, "area_mm2")
    outer = np.outer(direction, direction) * (e * a / length_mm)
    k = np.zeros((12, 12), dtype=float)
    k[0:3, 0:3] = outer
    k[0:3, 6:9] = -outer
    k[6:9, 0:3] = -outer
    k[6:9, 6:9] = outer
    return k


def analyze_space_frame(model: SpaceFrameModel) -> SpaceFrameResult:
    if not model.nodes or not model.members:
        raise CalculationInputError("incomplete_space_frame", "空间模型至少需要节点和杆件", field="geometry")
    if len(model.nodes) > MAX_SPACE_FRAME_NODES or len(model.members) > MAX_SPACE_FRAME_MEMBERS:
        raise CalculationInputError(
            "space_frame_limit_exceeded",
            f"单个场景最多 {MAX_SPACE_FRAME_NODES} 个节点、{MAX_SPACE_FRAME_MEMBERS} 根杆件，请拆分场景",
            field="geometry",
        )
    node_index: dict[str, int] = {}
    coordinates: list[np.ndarray] = []
    for node in model.nodes:
        if node.id in node_index:
            raise CalculationInputError("duplicate_space_node", f"节点 {node.id} 重复", field="nodes")
        values = np.array([node.x_m, node.y_m, node.z_m], dtype=float)
        if not np.all(np.isfinite(values)):
            raise CalculationInputError("invalid_space_node", f"节点 {node.id} 坐标必须为有限数值", field="nodes")
        node_index[node.id] = len(coordinates)
        coordinates.append(values * 1000.0)

    size = len(model.nodes) * 6
    stiffness = np.zeros((size, size), dtype=float)
    prepared: dict[str, tuple[np.ndarray, np.ndarray, tuple[int, ...], float]] = {}
    member_ids: set[str] = set()
    for member in model.members:
        if member.id in member_ids:
            raise CalculationInputError("duplicate_space_member", f"杆件 {member.id} 重复", field="members")
        member_ids.add(member.id)
        if member.start not in node_index or member.end not in node_index:
            raise CalculationInputError("unknown_space_member_node", f"杆件 {member.id} 引用了不存在的节点", field="members")
        start_index = node_index[member.start]
        end_index = node_index[member.end]
        rotation, length = _local_axes(
            coordinates[start_index], coordinates[end_index], member.local_axis_rotation_deg
        )
        dofs = tuple(range(start_index * 6, start_index * 6 + 6)) + tuple(range(end_index * 6, end_index * 6 + 6))
        if member.behavior == "truss":
            local = _truss_global_stiffness(member, rotation[0], length)
            transform = np.eye(12)
            global_matrix = local
        else:
            local = _frame_local_stiffness(member, length)
            transform = np.zeros((12, 12), dtype=float)
            transform[0:3, 0:3] = rotation
            transform[3:6, 3:6] = rotation
            transform[6:9, 6:9] = rotation
            transform[9:12, 9:12] = rotation
            global_matrix = transform.T @ local @ transform
        stiffness[np.ix_(dofs, dofs)] += global_matrix
        prepared[member.id] = (local, transform, dofs, length)

    load_vector, fixed_end_loads, local_uniform_loads = _assemble_load_vector(model, node_index, prepared)

    restrained: set[int] = set()
    for restraint in model.restraints:
        if restraint.node not in node_index:
            raise CalculationInputError("unknown_space_restraint_node", f"支承引用了不存在的节点 {restraint.node}", field="restraints")
        base = node_index[restraint.node] * 6
        for offset, active in enumerate((restraint.ux, restraint.uy, restraint.uz, restraint.rx, restraint.ry, restraint.rz)):
            if active:
                restrained.add(base + offset)
    candidate_free = [index for index in range(size) if index not in restrained]
    inactive = {
        index
        for index in candidate_free
        if np.max(np.abs(stiffness[index, :])) <= 1e-10
        and abs(load_vector[index]) <= 1e-10
    }
    free = np.array([index for index in candidate_free if index not in inactive], dtype=int)
    if not restrained or free.size == 0:
        raise CalculationInputError("invalid_space_restraints", "空间模型必须同时具有约束自由度和可变形自由度", field="restraints")
    reduced = stiffness[np.ix_(free, free)]
    try:
        condition_number = float(np.linalg.cond(reduced))
        if not isfinite(condition_number) or condition_number > 1e14:
            raise np.linalg.LinAlgError("ill-conditioned")
        free_displacements = np.linalg.solve(reduced, load_vector[free])
    except np.linalg.LinAlgError as exc:
        raise CalculationInputError(
            "unstable_space_frame",
            "空间模型不稳定或存在机构，请检查支承、杆件连接和铰接设置",
            field="geometry",
        ) from exc
    displacements = np.zeros(size, dtype=float)
    displacements[free] = free_displacements
    reaction_vector = stiffness @ displacements - load_vector

    node_results: dict[str, SpaceNodeResult] = {}
    reactions: dict[str, SpaceReaction] = {}
    for node, index in node_index.items():
        values = displacements[index * 6 : index * 6 + 6]
        node_results[node] = SpaceNodeResult(node, *[float(item) for item in values])
        reaction = reaction_vector[index * 6 : index * 6 + 6]
        reactions[node] = SpaceReaction(
            node,
            float(reaction[0] / 1000),
            float(reaction[1] / 1000),
            float(reaction[2] / 1000),
            float(reaction[3] / 1e6),
            float(reaction[4] / 1e6),
            float(reaction[5] / 1e6),
        )
    member_results: dict[str, SpaceMemberResult] = {}
    for member in model.members:
        local, transform, dofs, _ = prepared[member.id]
        member_displacements = displacements[list(dofs)]
        forces = local @ (transform @ member_displacements) if member.behavior == "frame" else local @ member_displacements
        forces -= fixed_end_loads.get(member.id, np.zeros(12, dtype=float))
        member_results[member.id] = SpaceMemberResult(member.id, tuple(float(item) for item in forces))
    total_load = load_vector.reshape((-1, 6))[:, :3].sum(axis=0) / 1000
    total_reaction = reaction_vector.reshape((-1, 6))[:, :3].sum(axis=0) / 1000
    balance = total_load + total_reaction
    return SpaceFrameResult(
        displacements=node_results,
        reactions=reactions,
        members=member_results,
        load_balance_kn=tuple(float(item) for item in balance),
        member_uniform_loads_local={member_id: tuple(float(value) for value in values) for member_id, values in local_uniform_loads.items()},
    )


def analyze_space_frame_stability(
    model: SpaceFrameModel,
    first_order: SpaceFrameResult | None = None,
    *,
    mode_count: int = 5,
) -> SpaceStabilityResult:
    """Run a geometric-stiffness second-order step and elastic eigen-buckling.

    Axial forces are taken from the first-order state. The method is suitable
    for the current small-displacement steel frame scope; it explicitly fails
    when the tangent matrix loses stability instead of returning a false pass.
    """

    first = first_order or analyze_space_frame(model)
    node_index = {node.id: index for index, node in enumerate(model.nodes)}
    coordinates = [np.array([node.x_m, node.y_m, node.z_m], dtype=float) * 1000 for node in model.nodes]
    size = len(model.nodes) * 6
    elastic = np.zeros((size, size), dtype=float)
    geometric = np.zeros((size, size), dtype=float)
    prepared: dict[str, tuple[np.ndarray, np.ndarray, tuple[int, ...], float]] = {}

    for member in model.members:
        start_index = node_index[member.start]
        end_index = node_index[member.end]
        rotation, length = _local_axes(
            coordinates[start_index], coordinates[end_index], member.local_axis_rotation_deg
        )
        dofs = tuple(range(start_index * 6, start_index * 6 + 6)) + tuple(range(end_index * 6, end_index * 6 + 6))
        if member.behavior == "truss":
            local = _truss_global_stiffness(member, rotation[0], length)
            transform = np.eye(12)
            global_elastic = local
        else:
            local = _frame_local_stiffness(member, length)
            transform = np.zeros((12, 12), dtype=float)
            for offset in (0, 3, 6, 9):
                transform[offset : offset + 3, offset : offset + 3] = rotation
            global_elastic = transform.T @ local @ transform
        elastic[np.ix_(dofs, dofs)] += global_elastic
        prepared[member.id] = (local, transform, dofs, length)

        axial = max(float(first.members[member.id].local_end_forces[0]), 0.0)
        if axial <= 1e-6 or member.behavior != "frame":
            continue
        effective_length = length - (member.rigid_offset_start_m + member.rigid_offset_end_m) * 1000
        p_over_30l = axial / (30 * effective_length)
        plane = p_over_30l * np.array(
            [
                [36, 3 * effective_length, -36, 3 * effective_length],
                [3 * effective_length, 4 * effective_length**2, -3 * effective_length, -effective_length**2],
                [-36, -3 * effective_length, 36, -3 * effective_length],
                [3 * effective_length, -effective_length**2, -3 * effective_length, 4 * effective_length**2],
            ],
            dtype=float,
        )
        local_geometric = np.zeros((12, 12), dtype=float)
        for indices in ((1, 5, 7, 11), (2, 4, 8, 10)):
            for row, target_row in enumerate(indices):
                for column, target_column in enumerate(indices):
                    local_geometric[target_row, target_column] += plane[row, column]
        global_geometric = transform.T @ local_geometric @ transform
        geometric[np.ix_(dofs, dofs)] += global_geometric

    load_vector, fixed_end_loads, local_uniform_loads = _assemble_load_vector(model, node_index, prepared)
    restrained: set[int] = set()
    for restraint in model.restraints:
        base = node_index[restraint.node] * 6
        for offset, active in enumerate((restraint.ux, restraint.uy, restraint.uz, restraint.rx, restraint.ry, restraint.rz)):
            if active:
                restrained.add(base + offset)
    candidate_free = [index for index in range(size) if index not in restrained]
    free = np.array([
        index for index in candidate_free
        if np.max(np.abs(elastic[index, :])) > 1e-10 or abs(load_vector[index]) > 1e-10
    ], dtype=int)
    k = elastic[np.ix_(free, free)]
    kg = geometric[np.ix_(free, free)]
    tangent = k - kg
    try:
        condition_number = float(np.linalg.cond(tangent))
        if not isfinite(condition_number) or condition_number > 1e14:
            raise np.linalg.LinAlgError("ill-conditioned tangent stiffness")
        solved = np.linalg.solve(tangent, load_vector[free])
    except np.linalg.LinAlgError as exc:
        raise CalculationInputError(
            "second_order_instability",
            "P-Δ切线刚度矩阵不稳定；请检查支承、构件刚度和轴压水平",
            field="geometry",
        ) from exc

    factors: list[float] = []
    if np.max(np.abs(kg)) > 1e-12:
        values = eigvals(k, kg)
        factors = sorted(
            float(value.real)
            for value in values
            if abs(float(value.imag)) < 1e-7 and isfinite(float(value.real)) and float(value.real) > 1e-6
        )[:mode_count]
    if factors and factors[0] <= 1.0:
        raise CalculationInputError(
            "elastic_buckling_instability",
            f"当前组合的最低弹性屈曲系数为 {factors[0]:.3f}，模型已达到或超过弹性临界状态",
            field="geometry",
        )

    displacements = np.zeros(size, dtype=float)
    displacements[free] = solved
    reaction_vector = tangent @ solved - load_vector[free]
    full_reaction = np.zeros(size, dtype=float)
    full_reaction[free] = reaction_vector
    full_reaction += (elastic - geometric) @ displacements - load_vector - full_reaction
    node_results: dict[str, SpaceNodeResult] = {}
    reactions: dict[str, SpaceReaction] = {}
    for node_id, index in node_index.items():
        values = displacements[index * 6 : index * 6 + 6]
        node_results[node_id] = SpaceNodeResult(node_id, *[float(item) for item in values])
        reaction = full_reaction[index * 6 : index * 6 + 6]
        reactions[node_id] = SpaceReaction(
            node_id,
            float(reaction[0] / 1000), float(reaction[1] / 1000), float(reaction[2] / 1000),
            float(reaction[3] / 1e6), float(reaction[4] / 1e6), float(reaction[5] / 1e6),
        )
    member_results: dict[str, SpaceMemberResult] = {}
    for member in model.members:
        local, transform, dofs, _ = prepared[member.id]
        member_displacements = displacements[list(dofs)]
        forces = local @ (transform @ member_displacements) if member.behavior == "frame" else local @ member_displacements
        forces -= fixed_end_loads.get(member.id, np.zeros(12, dtype=float))
        member_results[member.id] = SpaceMemberResult(member.id, tuple(float(item) for item in forces))
    total_load = load_vector.reshape((-1, 6))[:, :3].sum(axis=0) / 1000
    total_reaction = full_reaction.reshape((-1, 6))[:, :3].sum(axis=0) / 1000
    second = SpaceFrameResult(
        displacements=node_results,
        reactions=reactions,
        members=member_results,
        load_balance_kn=tuple(float(item) for item in total_load + total_reaction),
        member_uniform_loads_local={member_id: tuple(float(value) for value in values) for member_id, values in local_uniform_loads.items()},
        warnings=("P-Δ采用首阶轴力形成几何刚度；大位移或材料非线性不在当前范围",),
    )
    first_max = max(sqrt(item.ux_mm**2 + item.uy_mm**2 + item.uz_mm**2) for item in first.displacements.values())
    second_max = max(sqrt(item.ux_mm**2 + item.uy_mm**2 + item.uz_mm**2) for item in second.displacements.values())
    return SpaceStabilityResult(
        second_order=second,
        buckling_factors=tuple(factors),
        amplification_ratio=(second_max / first_max if first_max > 1e-12 else 1.0),
    )
