from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import cos, isfinite, radians, sin, sqrt
from typing import Literal

import numpy as np
from scipy.linalg import eigh
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import ArpackNoConvergence, eigsh, splu

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
    along_member: dict[str, object] | None = None


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


def _rigid_arm_transform(member: SpaceMember) -> np.ndarray:
    """Joint DOFs to flexible-face DOFs: u_face = u_joint + theta x r."""
    transform = np.eye(12)
    for base, arm in ((0, member.rigid_offset_start_m * 1000), (6, -member.rigid_offset_end_m * 1000)):
        if not isfinite(arm) or (base == 0 and arm < 0) or (base == 6 and arm > 0):
            raise CalculationInputError("invalid_rigid_offset", "刚性偏移必须为有限非负数", field="rigid_offset")
        transform[base + 1, base + 5] = arm
        transform[base + 2, base + 4] = -arm
    return transform


def _frame_local_stiffness(member: SpaceMember, length_mm: float, *, apply_releases: bool = True) -> np.ndarray:
    arm = _rigid_arm_transform(member)
    return arm.T @ _frame_face_stiffness(member, length_mm, apply_releases=apply_releases) @ arm


def _frame_face_stiffness(member: SpaceMember, length_mm: float, *, apply_releases: bool = True) -> np.ndarray:
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
    # Two torsional releases contain an unloaded rigid spin. Its null mode is
    # orthogonal to retained DOFs, so a pseudoinverse gives the correct static
    # condensation instead of silently retaining an uncondensed bending block.
    condensed = k_rr - k_rc @ np.linalg.pinv(k_cc, hermitian=True) @ k_rc.T
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
    released_solution = np.linalg.pinv(k_cc, hermitian=True) @ load[released]
    if np.linalg.norm(k_cc @ released_solution - load[released]) > 1e-8 * max(np.linalg.norm(load), 1.):
        raise CalculationInputError("loaded_release_mechanism", "释放的内部自由度存在无法平衡的荷载", field="members")
    condensed[retained] -= k_rc @ released_solution
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
    full_stiffness = _frame_face_stiffness(member, length_mm, apply_releases=False)
    result = _rigid_arm_transform(member).T @ _condense_local_load(member, full_stiffness, fixed)
    # Distributed load acts over the full physical member, including rigid arms.
    for base, arm in ((0, member.rigid_offset_start_m * 1000), (6, -member.rigid_offset_end_m * 1000)):
        result[base:base + 3] += np.array([qx, qy, qz]) * abs(arm)
        result[base + 4] -= qz * abs(arm) * arm / 2
        result[base + 5] += qy * abs(arm) * arm / 2
    return result


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
        if member.behavior == "truss":
            rotation, _ = _local_axes(coordinates[node_index[member.start]], coordinates[node_index[member.end]], member.local_axis_rotation_deg)
            for base in (0, 3, 6, 9):
                forces[base:base+3] = rotation @ forces[base:base+3]
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



def _geometric_face_stiffness(axial: float, length: float, axial_gradient: float = 0.) -> np.ndarray:
    """Consistent initial-stress matrix, axial positive in compression (N/mm)."""
    plane = axial / (30 * length) * np.array([
        [36, 3*length, -36, 3*length],
        [3*length, 4*length**2, -3*length, -length**2],
        [-36, -3*length, 36, -3*length],
        [3*length, -length**2, -3*length, 4*length**2],
    ])
    if abs(axial_gradient) > 1e-14:
        # Three-point Gauss integrates linear P(x) times quartic H'(x)H'(x)
        # exactly. No average-force approximation for member self-weight.
        plane = np.zeros((4, 4))
        for coordinate, weight in zip(*np.polynomial.legendre.leggauss(3), strict=True):
            t = (coordinate+1)/2
            derivative = np.array([(-6*t+6*t*t)/length, 1-4*t+3*t*t,
                                   (6*t-6*t*t)/length, -2*t+3*t*t])
            p = axial + axial_gradient*length*(t-.5)
            plane += weight*length/2*p*np.outer(derivative,derivative)
    result = np.zeros((12, 12))
    for indices, sign in (((1, 5, 7, 11), 1), ((2, 4, 8, 10), -1)):
        signs = np.diag([1, sign, 1, sign])
        result[np.ix_(indices, indices)] = signs @ plane @ signs
    return result


def _poly_derivative(coefficients: np.ndarray) -> np.ndarray:
    return coefficients[1:]*np.arange(1, len(coefficients))


def _polynomial_stations(polynomials: list[np.ndarray], length: float) -> np.ndarray:
    points = {0., length, length/2}
    for coefficients in polynomials:
        for root in np.polynomial.polynomial.polyroots(_poly_derivative(coefficients)):
            if abs(complex(root).imag) < 1e-7 and 0 < float(complex(root).real) < length:
                points.add(float(complex(root).real))
    return np.array(sorted(points))


def _arm_geometric(member: SpaceMember, length: float, qx: float, initial_axial: float) -> np.ndarray:
    result = np.zeros((12, 12))
    a, b = member.rigid_offset_start_m*1000, member.rigid_offset_end_m*1000
    for base, arm, coordinate in ((0, a, a/2), (6, b, length-b/2)):
        integral = (initial_axial+qx*coordinate)*arm
        result[base+4, base+4] = integral
        result[base+5, base+5] = integral
    return result


def _member_envelope(member: SpaceMember, length: float, q: np.ndarray,
                     segments: list[tuple[np.ndarray, np.ndarray, float]],
                     face_displacements: np.ndarray, joint_u: np.ndarray,
                     joint_forces: np.ndarray, initial_axial: float) -> dict[str, object]:
    """Recover moment/shear by second-order equilibrium and displacement extrema.

    Each segment obeys Mz=M0-V0*x-qy*x²/2+integral(P(x)*v'(x),x).
    P(x) may vary linearly. Flexible displacements use Hermite interpolation;
    the UDL bubble is exact at zero prestress and preserves end moments when P
    is constant. Rigid arms use their actual straight, rotating displacement.
    """
    a, b = member.rigid_offset_start_m*1000, member.rigid_offset_end_m*1000
    flexible = length-a-b
    count = len(segments)
    step = flexible/count
    descriptors = [(a+index*step,step,u,f,p,False) for index,(u,f,p) in enumerate(segments)]
    # The two sides of a released interface have distinct displacement traces.
    # In particular, a sliding flexible face must never be used as the rigid
    # arm tip: the latter always follows its joint's rigid-body kinematics.
    arm_face_u = _rigid_arm_transform(member) @ joint_u
    if a:
        arm_u=np.concatenate((joint_u[:6],arm_face_u[:6]))
        # The flexible face action is opposite the action at the end of the arm.
        arm_f=np.concatenate((joint_forces[:6],-segments[0][1][:6]))
        descriptors.insert(0,(0.,a,arm_u,arm_f,initial_axial+q[0]*a/2,True))
    if b:
        arm_u=np.concatenate((arm_face_u[6:],joint_u[6:]))
        arm_f=np.concatenate((-segments[-1][1][6:],joint_forces[6:]))
        descriptors.append((length-b,b,arm_u,arm_f,initial_axial+q[0]*(length-b/2),True))
    stations=[]
    defect=moment_scale=end_residual=0.
    maximum_my=maximum_mz=maximum_vy=maximum_vz=maximum_delta=0.
    evaluate = np.polynomial.polynomial.polyval
    for start_x,span,u,forces,axial,rigid in descriptors:
        def shape(v0,t0,v1,t1,ei,load):
            # Direct coefficients of the exact same Hermite + UDL bubble.
            # Avoid thousands of temporary Polynomial objects per load case.
            coefficients=np.zeros(5)
            coefficients[0]=v0
            if rigid:
                coefficients[1]=(v1-v0)/span
            else:
                coefficients[1]=t0
                coefficients[2]=3*(v1-v0)/span**2-(2*t0+t1)/span
                coefficients[3]=2*(v0-v1)/span**3+(t0+t1)/span**2
                if abs(q[0])<=1e-10:
                    bubble=load/(24*ei)
                    coefficients[2]+=bubble*span**2
                    coefficients[3]-=bubble*2*span
                    coefficients[4]=bubble
            return coefficients
        v=shape(u[1],u[5],u[7],u[11],member.elastic_modulus_mpa*member.iz_mm4,q[1])
        w=shape(u[2],-u[4],u[8],-u[10],member.elastic_modulus_mpa*member.iy_mm4,q[2])
        def stress_displacement_integral(displacement):
            # Coefficients of integral[(P_start+qx*x)*v'(x)] with value 0 at x=0.
            integral=np.zeros(6)
            integral[1:5]=(axial-q[0]*span/2)*displacement[1:]
            integral[2:6]+=q[0]*displacement[1:]*np.arange(1,5)/np.arange(2,6)
            return integral
        mz=stress_displacement_integral(v)
        mz[:3]+=np.array([forces[5],-forces[1],-q[1]/2])
        my=-stress_displacement_integral(w)
        my[:3]+=np.array([forces[4],forces[2],q[2]/2])
        vy=-_poly_derivative(mz); vz=_poly_derivative(my)
        chord_delta_v=v.copy(); chord_delta_w=w.copy()
        chord_slope_v=(joint_u[7]-joint_u[1])/length
        chord_slope_w=(joint_u[8]-joint_u[2])/length
        chord_delta_v[:2]-=np.array([joint_u[1]+chord_slope_v*start_x,chord_slope_v])
        chord_delta_w[:2]-=np.array([joint_u[2]+chord_slope_w*start_x,chord_slope_w])
        deflection_squared=np.convolve(chord_delta_v,chord_delta_v)+np.convolve(chord_delta_w,chord_delta_w)
        defect_z=np.zeros(6) if rigid else mz.copy()
        defect_y=np.zeros(6) if rigid else my.copy()
        if not rigid:
            defect_z[:3]+=member.elastic_modulus_mpa*member.iz_mm4*_poly_derivative(_poly_derivative(v))
            defect_y[:3]-=member.elastic_modulus_mpa*member.iy_mm4*_poly_derivative(_poly_derivative(w))
        points=_polynomial_stations([my,mz,vy,vz,deflection_squared,defect_y,defect_z],span)
        moment_y=evaluate(points,my); moment_z=evaluate(points,mz)
        shear_y=evaluate(points,vy); shear_z=evaluate(points,vz)
        delta=np.sqrt(np.maximum(0.,evaluate(points,deflection_squared)))
        displacements_y=evaluate(points,v); displacements_z=evaluate(points,w)
        maximum_my=max(maximum_my,float(np.max(np.abs(moment_y))))
        maximum_mz=max(maximum_mz,float(np.max(np.abs(moment_z))))
        maximum_vy=max(maximum_vy,float(np.max(np.abs(shear_y))))
        maximum_vz=max(maximum_vz,float(np.max(np.abs(shear_z))))
        maximum_delta=max(maximum_delta,float(np.max(delta)))
        defect=max(defect,float(np.max(np.abs(evaluate(points,defect_y)))),float(np.max(np.abs(evaluate(points,defect_z)))))
        moment_scale=max(moment_scale,maximum_my,maximum_mz)
        stations.extend({'x_m':float((start_x+xx)/1000),'uy_mm':float(dy),'uz_mm':float(dz),
                         'my_kn_m':float(my_value/1e6),'mz_kn_m':float(mz_value/1e6),
                         'vy_kn':float(vy_value/1000),'vz_kn':float(vz_value/1000),
                         'chord_deflection_mm':float(displacement),'rigid_arm':rigid}
                        for xx,dy,dz,my_value,mz_value,vy_value,vz_value,displacement in
                        zip(points,displacements_y,displacements_z,moment_y,moment_z,shear_y,shear_z,delta,strict=True))
        end_residual=max(end_residual,abs(float(evaluate(span,mz))+forces[11]),abs(float(evaluate(span,my))+forces[10]))
    relative_defect=defect/max(moment_scale,1.)
    has_axial=any(abs(item[2])>1e-6 for item in segments)
    complete=(relative_defect<=.02 and end_residual<=max(1e-4,moment_scale*1e-8)
              and (not has_axial or count>=4))
    return {'status':'complete' if complete else 'incomplete',
            'method':'initial-stress-equilibrium-polynomial-extrema-v1',
            'verification_status':'unverified','segments':count,
            'constitutive_relative_residual':relative_defect,'end_moment_residual_nmm':end_residual,
            'maximum_moment_y_kn_m':maximum_my/1e6,'maximum_moment_z_kn_m':maximum_mz/1e6,
            'maximum_shear_y_kn':maximum_vy/1000,'maximum_shear_z_kn':maximum_vz/1000,
            'maximum_chord_deflection_mm':maximum_delta,'stations':stations,
            'released_face_displacement_jumps': {
                'basis': 'flexible-face-minus-rigid-arm-face; local translations mm and rotations rad',
                'start': [float(value) for value in face_displacements[:6]-arm_face_u[:6]],
                'end': [float(value) for value in face_displacements[-6:]-arm_face_u[6:]],
            },
            'scope':'Euler-Bernoulli straight prismatic member, rigid arms, linear initial axial stress; small rotations',
            'incomplete_reason':None if complete else '沿杆恢复残差或细分数尚未达到能力要求'}


def analyze_space_frame_stability(model: SpaceFrameModel, first_order: SpaceFrameResult | None = None,
                                  *, mode_count: int = 5, member_subdivisions: int = 1) -> SpaceStabilityResult:
    """Initial-stress beam-column FE analysis retaining released-face/internal DOFs.

    A released local face coordinate is an independent unknown, not an elastically
    condensed joint coordinate. K and Kg retain these coordinates through both
    the tangent solve and the generalized buckling eigenproblem. Subdivision is
    internal and does not alter the user's nodes, member IDs or applied loads.
    """
    if not isinstance(member_subdivisions, int) or not 1 <= member_subdivisions <= 32:
        raise CalculationInputError('invalid_member_subdivisions', '杆件细分数必须为1至32的整数', field='member_subdivisions')
    if not isinstance(mode_count, int) or not 1 <= mode_count <= 20:
        raise CalculationInputError('invalid_stability_modes', '稳定模态数必须为1至20的整数', field='mode_count')
    first = first_order or analyze_space_frame(model)
    # Under nonpositive initial compression everywhere, Kg is negative
    # semidefinite by its strain-energy integral. There is no positive load
    # multiplier to seek; iterating on its large zero eigenspace is unnecessary
    # and can exhaust ARPACK even though the tensile structure is stable.
    frame_axial_ends = [value for member in model.members if member.behavior == 'frame'
                       for value in (first.members[member.id].local_end_forces[0],
                                     -first.members[member.id].local_end_forces[6])]
    axial_roundoff = max((abs(value) for value in frame_axial_ends), default=0.) * 1e-12
    has_compression = any(
        member.behavior == 'frame' and max(
            first.members[member.id].local_end_forces[0],
            -first.members[member.id].local_end_forces[6],
        ) > axial_roundoff for member in model.members
    )
    node_index = {node.id: index for index, node in enumerate(model.nodes)}
    coordinates = [np.array([node.x_m,node.y_m,node.z_m])*1000 for node in model.nodes]
    joint_size = len(model.nodes)*6
    size = joint_size
    assembled = []
    spin_gauges = set()
    for member in model.members:
        ii, jj = node_index[member.start], node_index[member.end]
        rotation, length = _local_axes(coordinates[ii],coordinates[jj],member.local_axis_rotation_deg)
        joint_dofs = list(range(ii*6,ii*6+6))+list(range(jj*6,jj*6+6))
        transform = np.zeros((12,12))
        for offset in (0,3,6,9):
            transform[offset:offset+3,offset:offset+3]=rotation
        q = np.zeros(3)
        for load in model.member_uniform_loads:
            if load.member == member.id:
                q += rotation @ np.array([load.qx_kn_m,load.qy_kn_m,load.qz_kn_m])
        if member.behavior == 'truss':
            if _released_dofs(member) or member.rigid_offset_start_m or member.rigid_offset_end_m:
                raise CalculationInputError('unsupported_truss_stability_detail', '桁架稳定模型不支持释放或刚臂', field='members')
            elastic = _truss_global_stiffness(member, rotation[0], length)
            assembled.append((member,joint_dofs,np.eye(12),elastic,np.zeros((12,12)),np.zeros(12),np.zeros(12),[],length,q,transform))
            continue
        count = member_subdivisions
        dimension = (count+1)*6
        released = _released_dofs(member)
        extra = (count-1)*6+len(released)
        dofs = joint_dofs+list(range(size,size+extra))
        size += extra
        if 3 in released and 9 in released:
            # Only the unloaded rigid torsional spin is gauged. Transverse
            # release mechanisms remain in the stability eigenproblem.
            spin_gauges.add(dofs[12+(count-1)*6+released.index(3)])
        mapping = np.zeros((dimension,len(dofs)))
        arm = _rigid_arm_transform(member)
        endpoint_mapping = arm @ transform
        for row in range(12):
            mesh_row = row if row < 6 else dimension-12+row
            if row in released:
                mapping[mesh_row,12+(count-1)*6+released.index(row)]=1.
            else:
                mapping[mesh_row,:12]=endpoint_mapping[row]
        for index in range((count-1)*6):
            mapping[6+index,12+index]=1.
        flexible = length-(member.rigid_offset_start_m+member.rigid_offset_end_m)*1000
        step = flexible/count
        bare = replace(member,start_releases=(False,)*6,end_releases=(False,)*6,rigid_offset_start_m=0.,rigid_offset_end_m=0.)
        elastic = np.zeros((dimension,dimension))
        geometric = np.zeros_like(elastic)
        mesh_load = np.zeros(dimension)
        pieces=[]
        for index in range(count):
            indices=list(range(index*6,index*6+12))
            ke=_frame_face_stiffness(bare,step,apply_releases=False)
            axial=float(first.members[member.id].local_end_forces[0])+q[0]*(member.rigid_offset_start_m*1000+(index+.5)*step)
            kg=_geometric_face_stiffness(axial,step,q[0])
            fe=_uniform_local_load_vector(bare,np.eye(3),step,SpaceMemberUniformLoad(member.id,*q))
            elastic[np.ix_(indices,indices)]+=ke
            geometric[np.ix_(indices,indices)]+=kg
            mesh_load[indices]+=fe
            pieces.append((indices,ke,kg,fe,axial))
        arm_load=np.zeros(12)
        for base, offset in ((0,member.rigid_offset_start_m*1000),(6,-member.rigid_offset_end_m*1000)):
            arm_load[base:base+3]+=q*abs(offset)
            arm_load[base+4]-=q[2]*abs(offset)*offset/2
            arm_load[base+5]+=q[1]*abs(offset)*offset/2
        assembled.append((member,dofs,mapping,elastic,geometric,mesh_load,arm_load,pieces,length,q,transform))
    rows=[]; columns=[]; elastic_values=[]; geometric_values=[]
    load_vector=np.zeros(size)
    for load in model.nodal_loads:
        base=node_index[load.node]*6
        load_vector[base:base+6]+=np.array([load.fx_kn*1000,load.fy_kn*1000,load.fz_kn*1000,load.mx_kn_m*1e6,load.my_kn_m*1e6,load.mz_kn_m*1e6])
    for member,dofs,mapping,ke,kg,fe,arm_load,pieces,length,q,transform in assembled:
        local_k=mapping.T@ke@mapping
        local_g=mapping.T@kg@mapping
        if member.behavior == 'frame':
            arm_g = _arm_geometric(member, length, q[0], first.members[member.id].local_end_forces[0])
            local_g[:12,:12] += transform.T@arm_g@transform
        rr,cc=np.nonzero((local_k != 0)|(local_g != 0))
        rows.extend(np.array(dofs)[rr]); columns.extend(np.array(dofs)[cc])
        elastic_values.extend(local_k[rr,cc]); geometric_values.extend(local_g[rr,cc])
        local_load=mapping.T@fe
        local_load[:12]+=transform.T@arm_load
        load_vector[dofs]+=local_load
    elastic=coo_matrix((elastic_values,(rows,columns)),shape=(size,size)).tocsc()
    geometric=coo_matrix((geometric_values,(rows,columns)),shape=(size,size)).tocsc()
    restrained=set(spin_gauges)
    for restraint in model.restraints:
        base=node_index[restraint.node]*6
        restrained.update(base+offset for offset,active in enumerate((restraint.ux,restraint.uy,restraint.uz,restraint.rx,restraint.ry,restraint.rz)) if active)
    free=np.array([index for index in range(size) if index not in restrained and
                   (abs(elastic[index,index])>1e-12 or abs(load_vector[index])>1e-10)],dtype=int)
    k=elastic[free,:][:,free]; kg=geometric[free,:][:,free]
    # Diagonal scaling removes the force/rotation unit disparity from the solve.
    scaling=1/np.sqrt(np.maximum(k.diagonal(),1e-30))
    scale=diags(scaling)
    ks=(scale@k@scale).tocsc(); gs=(scale@kg@scale).tocsc()
    try:
        elastic_lu=splu(ks)
        if np.min(np.abs(elastic_lu.U.diagonal()))<1e-12:
            raise np.linalg.LinAlgError('elastic mechanism')
        factors=[]
        if has_compression and gs.nnz and np.max(np.abs(gs.data))>1e-14:
            if len(free)<=300:
                values=eigh(gs.toarray(),ks.toarray(),eigvals_only=True)
            else:
                values=eigsh(gs,k=min(max(mode_count,1),len(free)-1),M=ks,which='LA',return_eigenvectors=False,tol=1e-9)
            factors=sorted(1/float(value) for value in values if value>1e-10)[:mode_count]
        if factors and factors[0]<=1.0+1e-9:
            raise CalculationInputError('elastic_buckling_instability',f'最低弹性屈曲系数为{factors[0]:.6g}，已达到弹性临界状态',field='geometry')
        tangent=ks-gs
        solved=scaling*splu(tangent.tocsc()).solve(scaling*load_vector[free])
        if not np.all(np.isfinite(solved)):
            raise np.linalg.LinAlgError('non-finite solution')
    except CalculationInputError:
        raise
    except ArpackNoConvergence as exc:
        raise CalculationInputError(
            'buckling_eigen_solver_not_converged',
            '弹性屈曲特征迭代未收敛，无法判定稳定状态；这不等于结构已失稳',
            field='geometry', details={'converged_mode_count': len(exc.eigenvalues)},
        ) from exc
    except (np.linalg.LinAlgError,RuntimeError,ValueError) as exc:
        raise CalculationInputError('second_order_instability','二阶模型存在机构或切线刚度不稳定，请检查支承与释放',field='geometry') from exc
    displacement=np.zeros(size); displacement[free]=solved
    full_reaction=(elastic-geometric)@displacement-load_vector
    node_results={}; reactions={}
    for node_id,index in node_index.items():
        values=displacement[index*6:index*6+6]
        node_results[node_id]=SpaceNodeResult(node_id,*map(float,values))
        reaction=full_reaction[index*6:index*6+6]/np.array([1000,1000,1000,1e6,1e6,1e6])
        reactions[node_id]=SpaceReaction(node_id,*map(float,reaction))
    member_results={}; local_uniform={}
    for member,dofs,mapping,ke,kg,fe,arm_load,pieces,length,q,transform in assembled:
        u=mapping@displacement[dofs]
        mesh_forces=(ke-kg)@u-fe
        if member.behavior=='truss':
            forces=transform@mesh_forces
            envelope={'status':'incomplete', 'verification_status':'unverified',
                      'incomplete_reason':'桁架杆仅恢复局部轴力；桁架几何刚度和杆件自身屈曲不在本次梁柱模型覆盖内'}
        else:
            face_forces=np.concatenate((mesh_forces[:6],mesh_forces[-6:]))
            # Forces on released faces are zero by their own equilibrium equations.
            joint_u=transform@displacement[dofs[:12]]
            arm_g = _arm_geometric(member, length, q[0], first.members[member.id].local_end_forces[0])
            forces=_rigid_arm_transform(member).T@face_forces-arm_load-arm_g@joint_u
            recovered=[]
            for indices,ek,eg,ef,axial in pieces:
                eu=u[indices]
                recovered.append((eu,(ek-eg)@eu-ef,axial))
            envelope=_member_envelope(member,length,q,recovered,u,joint_u,forces,
                                      first.members[member.id].local_end_forces[0])
        member_results[member.id]=SpaceMemberResult(member.id,tuple(map(float,forces)),envelope)
        local_uniform[member.id]=tuple(map(float,q))
    total_load=np.zeros(3)
    for load in model.nodal_loads:
        total_load+=np.array([load.fx_kn,load.fy_kn,load.fz_kn])
    member_lookup={member.id:member for member in model.members}
    for load in model.member_uniform_loads:
        member=member_lookup[load.member]
        length=np.linalg.norm(coordinates[node_index[member.end]]-coordinates[node_index[member.start]])/1000
        total_load+=np.array([load.qx_kn_m,load.qy_kn_m,load.qz_kn_m])*length
    total_reaction=full_reaction[:joint_size].reshape((-1,6))[:,:3].sum(axis=0)/1000
    second=SpaceFrameResult(node_results,reactions,member_results,tuple(map(float,total_load+total_reaction)),local_uniform,
                            ('首阶轴力初应力法；显式释放面与内部细分；不含大位移、材料非线性及桁架自身屈曲',))
    first_max=max(sqrt(item.ux_mm**2+item.uy_mm**2+item.uz_mm**2) for item in first.displacements.values())
    second_max=max(sqrt(item.ux_mm**2+item.uy_mm**2+item.uz_mm**2) for item in second.displacements.values())
    return SpaceStabilityResult(second,tuple(factors),second_max/first_max if first_max>1e-12 else 1.)

def analyze_space_frame_stability_converged(model: SpaceFrameModel, first_order: SpaceFrameResult | None = None,
                                            *, relative_tolerance: float = .005) -> SpaceStabilityResult:
    """Refine 4→8→16→32; preserve incomplete on unresolved envelope convergence."""
    first = first_order or analyze_space_frame(model)
    previous = analyze_space_frame_stability(model, first, member_subdivisions=4)
    for count in (8, 16, 32):
        current = analyze_space_frame_stability(model, first, member_subdivisions=count)
        maximum_error = 0.
        node_error = 0.
        for node_id, item in current.second_order.displacements.items():
            old = previous.second_order.displacements[node_id]
            new_vector=np.array([item.ux_mm,item.uy_mm,item.uz_mm])
            old_vector=np.array([old.ux_mm,old.uy_mm,old.uz_mm])
            node_error=max(node_error,float(np.linalg.norm(new_vector-old_vector))/max(float(np.linalg.norm(new_vector)),1e-4))
        if current.buckling_factors and previous.buckling_factors:
            node_error=max(node_error,abs(current.buckling_factors[0]-previous.buckling_factors[0])/current.buckling_factors[0])
        updated={}
        for member_id, item in current.second_order.members.items():
            envelope = item.along_member
            old = previous.second_order.members[member_id].along_member
            if envelope is None or old is None or 'maximum_moment_y_kn_m' not in envelope:
                updated[member_id]=item
                continue
            error=node_error
            for key in ('maximum_moment_y_kn_m','maximum_moment_z_kn_m','maximum_chord_deflection_mm'):
                error=max(error,abs(float(envelope[key])-float(old[key]))/max(abs(float(envelope[key])),1e-5))
            maximum_error=max(maximum_error,error)
            updated[member_id]=replace(item,along_member={**envelope,
                'mesh_convergence_relative': error, 'mesh_convergence_tolerance': relative_tolerance,
                'previous_segments': count//2,
                'status': envelope['status'] if error<=relative_tolerance else 'incomplete'})
        current=replace(current,second_order=replace(current.second_order,members=updated))
        if maximum_error<=relative_tolerance and all(
            item.along_member is None or 'segments' not in item.along_member or item.along_member['status']=='complete'
            for item in current.second_order.members.values()
        ):
            return current
        previous=current
    return current
