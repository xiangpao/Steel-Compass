from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot, isfinite
from typing import Hashable

import numpy as np

from .errors import CalculationInputError


NodeId = Hashable


_LENGTH_TO_MM = {"mm": 1.0, "m": 1000.0}
_FORCE_TO_N = {"N": 1.0, "kN": 1000.0}
_MOMENT_TO_NMM = {"N*mm": 1.0, "kN*m": 1_000_000.0}
_LINE_LOAD_TO_N_PER_MM = {"N/mm": 1.0, "kN/m": 1.0}
_E_TO_MPA = {"MPa": 1.0, "GPa": 1000.0, "Pa": 1.0e-6}
_AREA_TO_MM2 = {"mm2": 1.0, "m2": 1.0e6}
_INERTIA_TO_MM4 = {"mm4": 1.0, "m4": 1.0e12}


def _convert(value: float, unit: str, factors: dict[str, float], *, field_name: str) -> float:
    if unit not in factors:
        raise CalculationInputError(
            "invalid_unit",
            f"{field_name} 的单位 {unit!r} 不受支持。",
            field=field_name,
            details={"unit": unit, "supported_units": sorted(factors)},
        )
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
    return numeric * factors[unit]


@dataclass(frozen=True)
class FrameNode:
    id: NodeId
    x: float
    y: float
    length_unit: str = "mm"


@dataclass(frozen=True)
class FrameMember:
    id: str
    start: NodeId
    end: NodeId
    area: float
    inertia: float
    elastic_modulus: float
    area_unit: str = "mm2"
    inertia_unit: str = "mm4"
    elastic_modulus_unit: str = "MPa"


@dataclass(frozen=True)
class NodeRestraint:
    node: NodeId
    ux: bool = False
    uy: bool = False
    rz: bool = False


@dataclass(frozen=True)
class NodalLoad:
    node: NodeId
    fx: float = 0.0
    fy: float = 0.0
    mz: float = 0.0
    force_unit: str = "N"
    moment_unit: str = "N*mm"


@dataclass(frozen=True)
class UniformMemberLoad:
    """Uniform load acting in a member's positive local-y direction."""

    member: str
    q_local_y: float
    unit: str = "N/mm"
    q_local_x: float = 0.0


@dataclass(frozen=True)
class ParametricFrameModel:
    nodes: tuple[FrameNode, ...]
    members: tuple[FrameMember, ...]
    restraints: tuple[NodeRestraint, ...] = ()
    nodal_loads: tuple[NodalLoad, ...] = ()
    uniform_loads: tuple[UniformMemberLoad, ...] = ()


@dataclass(frozen=True)
class NodeDisplacement:
    node: NodeId
    ux_mm: float
    uy_mm: float
    rz_rad: float


@dataclass(frozen=True)
class SupportReaction:
    node: NodeId
    fx_n: float
    fy_n: float
    mz_nmm: float

    @property
    def components_6dof(self) -> dict[str, float]:
        """Return a six-component container; out-of-plane terms are zero in 2D."""

        return {
            "Fx": self.fx_n,
            "Fy": self.fy_n,
            "Fz": 0.0,
            "Mx": 0.0,
            "My": 0.0,
            "Mz": self.mz_nmm,
        }


@dataclass(frozen=True)
class MemberSample:
    x_mm: float
    axial_n: float
    shear_n: float
    moment_nmm: float
    local_axial_displacement_mm: float
    local_transverse_displacement_mm: float
    global_ux_mm: float
    global_uy_mm: float


@dataclass(frozen=True)
class MemberExtrema:
    axial_abs_max_n: float
    axial_abs_max_at_mm: float
    shear_abs_max_n: float
    shear_abs_max_at_mm: float
    moment_abs_max_nmm: float
    moment_abs_max_at_mm: float
    local_transverse_abs_max_mm: float
    local_transverse_abs_max_at_mm: float
    global_displacement_abs_max_mm: float
    global_displacement_abs_max_at_mm: float


@dataclass(frozen=True)
class MemberResponse:
    member: str
    length_mm: float
    local_end_forces: tuple[float, float, float, float, float, float]
    samples: tuple[MemberSample, ...]
    extrema: MemberExtrema


@dataclass(frozen=True)
class ParametricFrameResult:
    displacements: dict[NodeId, NodeDisplacement]
    reactions: dict[NodeId, SupportReaction]
    members: dict[str, MemberResponse]
    applied_load_vector: tuple[float, ...] = field(repr=False)


@dataclass(frozen=True)
class _PreparedMember:
    definition: FrameMember
    start_index: int
    end_index: int
    length_mm: float
    c: float
    s: float
    elastic_modulus_mpa: float
    area_mm2: float
    inertia_mm4: float
    local_stiffness: np.ndarray
    transform: np.ndarray
    dofs: tuple[int, int, int, int, int, int]


def _local_stiffness(e: float, a: float, inertia: float, length: float) -> np.ndarray:
    ea_l = e * a / length
    ei = e * inertia
    return np.array(
        [
            [ea_l, 0.0, 0.0, -ea_l, 0.0, 0.0],
            [0.0, 12 * ei / length**3, 6 * ei / length**2, 0.0, -12 * ei / length**3, 6 * ei / length**2],
            [0.0, 6 * ei / length**2, 4 * ei / length, 0.0, -6 * ei / length**2, 2 * ei / length],
            [-ea_l, 0.0, 0.0, ea_l, 0.0, 0.0],
            [0.0, -12 * ei / length**3, -6 * ei / length**2, 0.0, 12 * ei / length**3, -6 * ei / length**2],
            [0.0, 6 * ei / length**2, 2 * ei / length, 0.0, -6 * ei / length**2, 4 * ei / length],
        ],
        dtype=float,
    )


def _transform(c: float, s: float) -> np.ndarray:
    return np.array(
        [
            [c, s, 0.0, 0.0, 0.0, 0.0],
            [-s, c, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, c, s, 0.0],
            [0.0, 0.0, 0.0, -s, c, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _prepare_model(
    model: ParametricFrameModel,
) -> tuple[list[FrameNode], dict[NodeId, int], list[_PreparedMember]]:
    if not model.nodes:
        raise CalculationInputError("missing_nodes", "二维框架至少需要一个节点。", field="nodes")
    if not model.members:
        raise CalculationInputError("missing_members", "二维框架至少需要一个杆件。", field="members")

    node_indices: dict[NodeId, int] = {}
    coordinates: list[tuple[float, float]] = []
    for index, node in enumerate(model.nodes):
        if node.id in node_indices:
            raise CalculationInputError(
                "duplicate_node", f"节点编号 {node.id!r} 重复。", field="nodes"
            )
        node_indices[node.id] = index
        coordinates.append(
            (
                _convert(node.x, node.length_unit, _LENGTH_TO_MM, field_name=f"nodes[{node.id}].x"),
                _convert(node.y, node.length_unit, _LENGTH_TO_MM, field_name=f"nodes[{node.id}].y"),
            )
        )

    member_ids: set[str] = set()
    prepared: list[_PreparedMember] = []
    for member in model.members:
        if member.id in member_ids:
            raise CalculationInputError(
                "duplicate_member", f"杆件编号 {member.id!r} 重复。", field="members"
            )
        member_ids.add(member.id)
        if member.start not in node_indices or member.end not in node_indices:
            raise CalculationInputError(
                "unknown_member_node",
                f"杆件 {member.id!r} 引用了不存在的节点。",
                field=f"members[{member.id}]",
                details={"start": member.start, "end": member.end},
            )
        start_index = node_indices[member.start]
        end_index = node_indices[member.end]
        start = coordinates[start_index]
        end = coordinates[end_index]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = hypot(dx, dy)
        if length <= 1.0e-9:
            raise CalculationInputError(
                "zero_length_member",
                f"杆件 {member.id!r} 的长度为零。",
                field=f"members[{member.id}]",
            )
        area = _convert(member.area, member.area_unit, _AREA_TO_MM2, field_name=f"members[{member.id}].area")
        inertia = _convert(
            member.inertia,
            member.inertia_unit,
            _INERTIA_TO_MM4,
            field_name=f"members[{member.id}].inertia",
        )
        elastic_modulus = _convert(
            member.elastic_modulus,
            member.elastic_modulus_unit,
            _E_TO_MPA,
            field_name=f"members[{member.id}].elastic_modulus",
        )
        if min(area, inertia, elastic_modulus) <= 0.0:
            raise CalculationInputError(
                "invalid_member_property",
                f"杆件 {member.id!r} 的面积、惯性矩和弹性模量必须大于零。",
                field=f"members[{member.id}]",
                details={"area_mm2": area, "inertia_mm4": inertia, "elastic_modulus_mpa": elastic_modulus},
            )
        c, s = dx / length, dy / length
        k_local = _local_stiffness(elastic_modulus, area, inertia, length)
        transform = _transform(c, s)
        dofs = (
            start_index * 3,
            start_index * 3 + 1,
            start_index * 3 + 2,
            end_index * 3,
            end_index * 3 + 1,
            end_index * 3 + 2,
        )
        prepared.append(
            _PreparedMember(
                definition=member,
                start_index=start_index,
                end_index=end_index,
                length_mm=length,
                c=c,
                s=s,
                elastic_modulus_mpa=elastic_modulus,
                area_mm2=area,
                inertia_mm4=inertia,
                local_stiffness=k_local,
                transform=transform,
                dofs=dofs,
            )
        )
    return list(model.nodes), node_indices, prepared


def _samples(
    member: _PreparedMember,
    local_displacements: np.ndarray,
    local_end_forces: np.ndarray,
    q_local_y: float,
    count: int,
    q_local_x: float = 0.0,
) -> tuple[tuple[MemberSample, ...], MemberExtrema]:
    length = member.length_mm
    x_values = np.linspace(0.0, length, count)
    result: list[MemberSample] = []
    for x in x_values:
        ratio = x / length
        axial_displacement = (1.0 - ratio) * local_displacements[0] + ratio * local_displacements[3]
        axial_displacement += q_local_x*x*(length-x)/(2*member.elastic_modulus_mpa*member.area_mm2)
        transverse_displacement = (
            local_displacements[1]
            + local_displacements[2] * x
            + (
                -local_end_forces[2] * x**2 / 2.0
                + local_end_forces[1] * x**3 / 6.0
                + q_local_y * x**4 / 24.0
            )
            / (member.elastic_modulus_mpa * member.inertia_mm4)
        )
        axial = -local_end_forces[0] - q_local_x*x
        shear = local_end_forces[1] + q_local_y * x
        moment = -local_end_forces[2] + local_end_forces[1] * x + q_local_y * x**2 / 2.0
        global_ux = member.c * axial_displacement - member.s * transverse_displacement
        global_uy = member.s * axial_displacement + member.c * transverse_displacement
        result.append(
            MemberSample(
                x_mm=float(x),
                axial_n=float(axial),
                shear_n=float(shear),
                moment_nmm=float(moment),
                local_axial_displacement_mm=float(axial_displacement),
                local_transverse_displacement_mm=float(transverse_displacement),
                global_ux_mm=float(global_ux),
                global_uy_mm=float(global_uy),
            )
        )
    samples = tuple(result)
    axial_peak = max(samples, key=lambda item: abs(item.axial_n))
    shear_peak = max(samples, key=lambda item: abs(item.shear_n))
    moment_peak = max(samples, key=lambda item: abs(item.moment_nmm))
    transverse_peak = max(
        samples, key=lambda item: abs(item.local_transverse_displacement_mm)
    )
    global_peak = max(
        samples, key=lambda item: hypot(item.global_ux_mm, item.global_uy_mm)
    )
    extrema = MemberExtrema(
        axial_abs_max_n=abs(axial_peak.axial_n),
        axial_abs_max_at_mm=axial_peak.x_mm,
        shear_abs_max_n=abs(shear_peak.shear_n),
        shear_abs_max_at_mm=shear_peak.x_mm,
        moment_abs_max_nmm=abs(moment_peak.moment_nmm),
        moment_abs_max_at_mm=moment_peak.x_mm,
        local_transverse_abs_max_mm=abs(
            transverse_peak.local_transverse_displacement_mm
        ),
        local_transverse_abs_max_at_mm=transverse_peak.x_mm,
        global_displacement_abs_max_mm=hypot(
            global_peak.global_ux_mm, global_peak.global_uy_mm
        ),
        global_displacement_abs_max_at_mm=global_peak.x_mm,
    )
    return samples, extrema


def solve_parametric_frame(
    model: ParametricFrameModel, *, samples_per_member: int = 101
) -> ParametricFrameResult:
    """Solve a linear-elastic 2D Euler-Bernoulli frame in an N-mm-MPa basis."""

    if (
        isinstance(samples_per_member, bool)
        or not isinstance(samples_per_member, int)
        or samples_per_member < 2
    ):
        raise CalculationInputError(
            "invalid_sample_count",
            "每根杆件至少需要两个采样点。",
            field="samples_per_member",
        )
    nodes, node_indices, members = _prepare_model(model)
    dof_count = len(nodes) * 3
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    applied_loads = np.zeros(dof_count, dtype=float)

    member_by_id = {member.definition.id: member for member in members}
    q_by_member = {member.definition.id: 0.0 for member in members}
    qx_by_member = {member.definition.id: 0.0 for member in members}
    for load in model.uniform_loads:
        if load.member not in member_by_id:
            raise CalculationInputError(
                "unknown_loaded_member",
                f"均布荷载引用了不存在的杆件 {load.member!r}。",
                field="uniform_loads",
            )
        q_by_member[load.member] += _convert(
            load.q_local_y,
            load.unit,
            _LINE_LOAD_TO_N_PER_MM,
            field_name=f"uniform_loads[{load.member}]",
        )
        qx_by_member[load.member] += _convert(load.q_local_x,load.unit,_LINE_LOAD_TO_N_PER_MM,field_name=f"uniform_loads[{load.member}].local_x")

    equivalent_local_by_member: dict[str, np.ndarray] = {}
    for member in members:
        k_global = member.transform.T @ member.local_stiffness @ member.transform
        dofs = np.asarray(member.dofs)
        stiffness[np.ix_(dofs, dofs)] += k_global
        q = q_by_member[member.definition.id]
        qx = qx_by_member[member.definition.id]
        length = member.length_mm
        equivalent_local = np.array(
            [qx*length/2, q * length / 2.0, q * length**2 / 12.0, qx*length/2, q * length / 2.0, -q * length**2 / 12.0],
            dtype=float,
        )
        applied_loads[dofs] += member.transform.T @ equivalent_local
        equivalent_local_by_member[member.definition.id] = equivalent_local

    for load in model.nodal_loads:
        if load.node not in node_indices:
            raise CalculationInputError(
                "unknown_loaded_node",
                f"节点荷载引用了不存在的节点 {load.node!r}。",
                field="nodal_loads",
            )
        index = node_indices[load.node] * 3
        applied_loads[index] += _convert(load.fx, load.force_unit, _FORCE_TO_N, field_name=f"nodal_loads[{load.node}].fx")
        applied_loads[index + 1] += _convert(load.fy, load.force_unit, _FORCE_TO_N, field_name=f"nodal_loads[{load.node}].fy")
        applied_loads[index + 2] += _convert(load.mz, load.moment_unit, _MOMENT_TO_NMM, field_name=f"nodal_loads[{load.node}].mz")

    restrained: set[int] = set()
    restrained_nodes: set[NodeId] = set()
    restraint_masks: dict[NodeId, list[bool]] = {}
    for restraint in model.restraints:
        if restraint.node not in node_indices:
            raise CalculationInputError(
                "unknown_restrained_node",
                f"约束引用了不存在的节点 {restraint.node!r}。",
                field="restraints",
            )
        base = node_indices[restraint.node] * 3
        mask = restraint_masks.setdefault(restraint.node, [False, False, False])
        for offset, active in enumerate((restraint.ux, restraint.uy, restraint.rz)):
            if active:
                restrained.add(base + offset)
                restrained_nodes.add(restraint.node)
                mask[offset] = True
    if not restrained:
        raise CalculationInputError(
            "singular_stiffness_matrix", "二维框架没有任何有效约束。", field="restraints"
        )

    free = sorted(set(range(dof_count)) - restrained)
    displacements = np.zeros(dof_count, dtype=float)
    if free:
        kff = stiffness[np.ix_(free, free)]
        try:
            condition = float(np.linalg.cond(kff))
        except np.linalg.LinAlgError as exc:
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "二维框架刚度矩阵奇异，请检查支承、连接和构件拓扑。",
                field="restraints",
            ) from exc
        if not isfinite(condition) or condition > 1.0e14:
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "二维框架刚度矩阵奇异或病态，请检查支承、连接和构件拓扑。",
                field="restraints",
                details={"condition_number": condition},
            )
        try:
            displacements[free] = np.linalg.solve(kff, applied_loads[free])
        except np.linalg.LinAlgError as exc:
            raise CalculationInputError(
                "singular_stiffness_matrix",
                "二维框架刚度矩阵奇异，请检查支承、连接和构件拓扑。",
                field="restraints",
            ) from exc

    reactions_vector = stiffness @ displacements - applied_loads
    displacement_results = {
        node.id: NodeDisplacement(
            node=node.id,
            ux_mm=float(displacements[index * 3]),
            uy_mm=float(displacements[index * 3 + 1]),
            rz_rad=float(displacements[index * 3 + 2]),
        )
        for index, node in enumerate(nodes)
    }
    reaction_results = {
        node_id: SupportReaction(
            node=node_id,
            fx_n=float(reactions_vector[node_indices[node_id] * 3])
            if restraint_masks[node_id][0]
            else 0.0,
            fy_n=float(reactions_vector[node_indices[node_id] * 3 + 1])
            if restraint_masks[node_id][1]
            else 0.0,
            mz_nmm=float(reactions_vector[node_indices[node_id] * 3 + 2])
            if restraint_masks[node_id][2]
            else 0.0,
        )
        for node_id in restrained_nodes
    }
    member_results: dict[str, MemberResponse] = {}
    for member in members:
        dofs = np.asarray(member.dofs)
        local_displacements = member.transform @ displacements[dofs]
        local_end_forces = (
            member.local_stiffness @ local_displacements
            - equivalent_local_by_member[member.definition.id]
        )
        samples, extrema = _samples(
            member,
            local_displacements,
            local_end_forces,
            q_by_member[member.definition.id],
            samples_per_member,
            qx_by_member[member.definition.id],
        )
        member_results[member.definition.id] = MemberResponse(
            member=member.definition.id,
            length_mm=member.length_mm,
            local_end_forces=tuple(float(value) for value in local_end_forces),  # type: ignore[arg-type]
            samples=samples,
            extrema=extrema,
        )
    return ParametricFrameResult(
        displacements=displacement_results,
        reactions=reaction_results,
        members=member_results,
        applied_load_vector=tuple(float(value) for value in applied_loads),
    )


@dataclass(frozen=True)
class PortalFrameGeneratorInput:
    span_m: float = 18.0
    height_m: float = 6.0
    roof_slope: float = 0.10     # 坡度 1:10
    num_spans: int = 1
    has_rocking_column: bool = False
    column_area_cm2: float = 70.0
    column_inertia_cm4: float = 12000.0
    beam_area_cm2: float = 55.0
    beam_inertia_cm4: float = 8000.0
    steel_f_y_mpa: float = 235.0


@dataclass(frozen=True)
class GB51022CheckResult:
    member_id: str
    axial_n_kn: float
    moment_m_knm: float
    shear_v_kn: float
    lambda_x: float
    lambda_y: float
    phi_x: float
    phi_y: float
    phi_b: float
    strength_utilization: float
    in_plane_stability_utilization: float
    out_of_plane_stability_utilization: float
    overall_passed: bool


def generate_portal_frame_model(
    inp: PortalFrameGeneratorInput,
) -> ParametricFrameModel:
    """参数化一键生成单跨/多跨门式刚架线弹性拓扑模型。"""
    if inp.span_m <= 0 or inp.height_m <= 0:
        raise CalculationInputError(
            "invalid_dimensions", "跨度与柱高必须大于零。", field="span_m"
        )
    if inp.num_spans < 1:
        raise CalculationInputError(
            "invalid_num_spans", "跨数至少为 1。", field="num_spans"
        )

    nodes: list[FrameNode] = []
    members: list[FrameMember] = []
    restraints: list[NodeRestraint] = []

    h_apex_mm = (inp.height_m + (inp.span_m / 2.0) * inp.roof_slope) * 1000.0
    h_col_mm = inp.height_m * 1000.0
    span_mm = inp.span_m * 1000.0

    col_area_mm2 = inp.column_area_cm2 * 100.0
    col_inertia_mm4 = inp.column_inertia_cm4 * 10000.0
    beam_area_mm2 = inp.beam_area_cm2 * 100.0
    beam_inertia_mm4 = inp.beam_inertia_cm4 * 10000.0
    e_mpa = 206000.0  # 钢材 Q235/Q355 206 GPa

    node_counter = 0

    for s in range(inp.num_spans):
        x_start = s * span_mm
        x_mid = x_start + span_mm / 2.0
        x_end = x_start + span_mm

        # 节点
        n_bot_left = f"N_B_{s}"
        n_top_left = f"N_T_{s}"
        n_apex = f"N_A_{s}"
        n_top_right = f"N_T_{s+1}"
        n_bot_right = f"N_B_{s+1}"

        if s == 0:
            nodes.append(FrameNode(n_bot_left, x_start, 0.0))
            nodes.append(FrameNode(n_top_left, x_start, h_col_mm))
            restraints.append(NodeRestraint(n_bot_left, ux=True, uy=True, rz=True))
            # 外柱
            members.append(
                FrameMember(
                    f"Col_{s}",
                    n_bot_left,
                    n_top_left,
                    col_area_mm2,
                    col_inertia_mm4,
                    e_mpa,
                )
            )

        nodes.append(FrameNode(n_apex, x_mid, h_apex_mm))
        nodes.append(FrameNode(n_bot_right, x_end, 0.0))
        nodes.append(FrameNode(n_top_right, x_end, h_col_mm))

        # 基础约束
        restraints.append(NodeRestraint(n_bot_right, ux=True, uy=True, rz=not inp.has_rocking_column))

        # 内部/右侧柱 (如果是摇晃柱，惯性矩极小)
        cur_col_inertia = col_inertia_mm4 / 100.0 if (inp.has_rocking_column and s > 0) else col_inertia_mm4
        members.append(
            FrameMember(
                f"Col_{s+1}",
                n_bot_right,
                n_top_right,
                col_area_mm2,
                cur_col_inertia,
                e_mpa,
            )
        )

        # 斜梁 (左坡与右坡)
        members.append(
            FrameMember(
                f"Beam_{s}_L",
                n_top_left if s == 0 else f"N_T_{s}",
                n_apex,
                beam_area_mm2,
                beam_inertia_mm4,
                e_mpa,
            )
        )
        members.append(
            FrameMember(
                f"Beam_{s}_R",
                n_apex,
                n_top_right,
                beam_area_mm2,
                beam_inertia_mm4,
                e_mpa,
            )
        )

    return ParametricFrameModel(
        nodes=tuple(nodes),
        members=tuple(members),
        restraints=tuple(restraints),
    )


def calculate_gb51022_member_check(
    member_id: str,
    axial_n_kn: float,
    moment_m_knm: float,
    shear_v_kn: float,
    b_f_mm: float = 200.0,
    t_f_mm: float = 10.0,
    h_web_max_mm: float = 500.0,
    h_web_min_mm: float = 300.0,
    t_w_mm: float = 6.0,
    l_0x_m: float = 6.0,
    l_0y_m: float = 3.0,
    f_y_mpa: float = 235.0,
) -> GB51022CheckResult:
    """按 GB 51022-2015 门式刚架轻型房屋钢结构技术规范进行变截面柱/梁压弯构件稳定验算。"""

    n_n = abs(axial_n_kn) * 1000.0
    m_nmm = abs(moment_m_knm) * 1e6
    v_n = abs(shear_v_kn) * 1000.0

    # 平均截面高度 (变截面取平均值近似)
    h_avg = (h_web_max_mm + h_web_min_mm) / 2.0
    area_mm2 = 2.0 * b_f_mm * t_f_mm + h_avg * t_w_mm
    
    # 截面惯性矩 Ix, Iy
    i_x_mm4 = (b_f_mm * ((h_avg + 2 * t_f_mm) ** 3 - h_avg ** 3) + t_w_mm * (h_avg ** 3)) / 12.0
    i_y_mm4 = 2.0 * (t_f_mm * (b_f_mm ** 3) / 12.0)
    
    w_x_mm3 = i_x_mm4 / ((h_avg / 2.0) + t_f_mm)
    w_y_mm3 = i_y_mm4 / (b_f_mm / 2.0)

    # 回转半径 rx, ry
    r_x = (i_x_mm4 / area_mm2) ** 0.5
    r_y = (i_y_mm4 / area_mm2) ** 0.5

    # 细长比
    lambda_x = (l_0x_m * 1000.0) / r_x
    lambda_y = (l_0y_m * 1000.0) / r_y

    # 规范轴压稳定系数 (GB 50017 / GB 51022 b类截面近似)
    lambda_bar_x = (lambda_x / 3.14159) * (f_y_mpa / 206000.0) ** 0.5
    lambda_bar_y = (lambda_y / 3.14159) * (f_y_mpa / 206000.0) ** 0.5

    phi_x = 1.0 / (1.0 + 0.25 * (lambda_bar_x ** 2)) if lambda_bar_x > 0.2 else 1.0
    phi_y = 1.0 / (1.0 + 0.25 * (lambda_bar_y ** 2)) if lambda_bar_y > 0.2 else 1.0
    phi_b = min(1.0, 1.07 - (lambda_y / 120.0) ** 2)

    # 强度利用率
    sigma_strength = (n_n / area_mm2) + (m_nmm / w_x_mm3)
    strength_util = sigma_strength / f_y_mpa

    # 平面内稳定 utilization
    # N / (phi_x * A * f) + beta_mx * M / (gamma_x * W_x * (1 - N / N_ex) * f)
    n_ex = (3.14159 ** 2 * 206000.0 * area_mm2) / (lambda_x ** 2)
    in_plane_util = (n_n / (phi_x * area_mm2 * f_y_mpa)) + (1.0 * m_nmm / (1.05 * w_x_mm3 * max(1.0 - n_n / max(n_ex, 1e-6), 0.1) * f_y_mpa))

    # 平面外稳定 utilization
    out_of_plane_util = (n_n / (phi_y * area_mm2 * f_y_mpa)) + (m_nmm / (phi_b * w_x_mm3 * f_y_mpa))

    overall_passed = max(strength_util, in_plane_util, out_of_plane_util) <= 1.0

    return GB51022CheckResult(
        member_id=member_id,
        axial_n_kn=axial_n_kn,
        moment_m_knm=moment_m_knm,
        shear_v_kn=shear_v_kn,
        lambda_x=lambda_x,
        lambda_y=lambda_y,
        phi_x=phi_x,
        phi_y=phi_y,
        phi_b=phi_b,
        strength_utilization=strength_util,
        in_plane_stability_utilization=in_plane_util,
        out_of_plane_stability_utilization=out_of_plane_util,
        overall_passed=overall_passed,
    )


__all__ = [
    "FrameMember",
    "FrameNode",
    "MemberExtrema",
    "MemberResponse",
    "MemberSample",
    "NodalLoad",
    "NodeDisplacement",
    "NodeRestraint",
    "ParametricFrameModel",
    "ParametricFrameResult",
    "SupportReaction",
    "UniformMemberLoad",
    "PortalFrameGeneratorInput",
    "GB51022CheckResult",
    "generate_portal_frame_model",
    "calculate_gb51022_member_check",
    "solve_parametric_frame",
]
