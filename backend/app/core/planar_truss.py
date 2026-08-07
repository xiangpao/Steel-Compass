from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
import numpy as np

from .errors import CalculationInputError


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


@dataclass(frozen=True)
class TrussNode:
    id: str
    x_m: float
    y_m: float


@dataclass(frozen=True)
class TrussMember:
    id: str
    start_node: str
    end_node: str
    area_cm2: float = 15.0
    radius_gyration_cm: float = 3.0    # 截面回转半径 i (cm)
    elastic_modulus_gpa: float = 206.0  # 钢材 Q235/Q355
    f_y_mpa: float = 235.0


@dataclass(frozen=True)
class TrussSupport:
    node: str
    fix_x: bool = True
    fix_y: bool = True


@dataclass(frozen=True)
class TrussNodalLoad:
    node: str
    fx_kn: float = 0.0
    fy_kn: float = 0.0


@dataclass(frozen=True)
class PlanarTrussInput:
    nodes: tuple[TrussNode, ...]
    members: tuple[TrussMember, ...]
    supports: tuple[TrussSupport, ...]
    loads: tuple[TrussNodalLoad, ...]
    compression_slenderness_limit: float = 150.0 # 受压长细比限值
    tension_slenderness_limit: float = 300.0     # 受拉长细比限值


@dataclass(frozen=True)
class TrussMemberResult:
    member_id: str
    length_m: float
    axial_force_kn: float           # >0 拉力, <0 压力
    force_type: str                 # "tension", "compression", "zero"
    slenderness_ratio: float        # 长细比 lambda
    slenderness_limit: float
    slenderness_passed: bool
    phi_stability: float            # 轴压稳定系数 phi
    capacity_kn: float              # 轴向承载力设计值
    utilization: float              # 应力/稳定利用率
    passed: bool


@dataclass(frozen=True)
class PlanarTrussOutput:
    member_results: tuple[TrussMemberResult, ...]
    node_displacements_mm: dict[str, tuple[float, float]]
    support_reactions_kn: dict[str, tuple[float, float]]
    overall_passed: bool
    max_slenderness_utilization: float
    max_strength_utilization: float


def solve_planar_truss(inp: PlanarTrussInput) -> PlanarTrussOutput:
    """平面桁架矩阵位移法求解与 GB 50017 杆件细长比/稳定性验算。"""
    if not inp.nodes:
        raise CalculationInputError("missing_nodes", "桁架至少需要一个节点。", field="nodes")
    if not inp.members:
        raise CalculationInputError("missing_members", "桁架至少需要一根杆件。", field="members")
    if not inp.supports:
        raise CalculationInputError("missing_supports", "桁架至少需要一个支承约束。", field="supports")

    node_dict = {n.id: n for n in inp.nodes}
    num_nodes = len(inp.nodes)
    node_indices = {n.id: i for i, n in enumerate(inp.nodes)}

    # 自由度: 每个节点 (ux, uy) 共 2 * num_nodes 个自由度
    dof_count = num_nodes * 2
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    applied_loads = np.zeros(dof_count, dtype=float)

    # 1. 组装刚度矩阵
    prepared_members = []
    for m in inp.members:
        if m.start_node not in node_dict or m.end_node not in node_dict:
            raise CalculationInputError(
                "unknown_node", f"杆件 {m.id} 引用了不存在的节点。", field="members"
            )
        n1 = node_dict[m.start_node]
        n2 = node_dict[m.end_node]
        dx_m = n2.x_m - n1.x_m
        dy_m = n2.y_m - n1.y_m
        length_m = hypot(dx_m, dy_m)
        if length_m <= 1e-6:
            raise CalculationInputError(
                "zero_length", f"杆件 {m.id} 长度为零。", field="members"
            )

        area_mm2 = _positive(m.area_cm2, f"members[{m.id}].area_cm2") * 100.0
        e_mpa = _positive(m.elastic_modulus_gpa, f"members[{m.id}].elastic_modulus_gpa") * 1000.0
        i_cm = _positive(m.radius_gyration_cm, f"members[{m.id}].radius_gyration_cm")

        # 杆件方向余弦
        cos_a = dx_m / length_m
        sin_a = dy_m / length_m

        ea_l = (e_mpa * area_mm2) / (length_m * 1000.0) # N/mm

        # 2D 桁架单元刚度矩阵 (4x4)
        # [ c^2, cs, -c^2, -cs ]
        # [ cs, s^2, -cs, -s^2 ]
        # ...
        k_elem = ea_l * np.array([
            [cos_a**2, cos_a*sin_a, -cos_a**2, -cos_a*sin_a],
            [cos_a*sin_a, sin_a**2, -cos_a*sin_a, -sin_a**2],
            [-cos_a**2, -cos_a*sin_a, cos_a**2, cos_a*sin_a],
            [-cos_a*sin_a, -sin_a**2, cos_a*sin_a, sin_a**2],
        ], dtype=float)

        idx1 = node_indices[m.start_node]
        idx2 = node_indices[m.end_node]
        dofs = [idx1*2, idx1*2+1, idx2*2, idx2*2+1]

        for r_i in range(4):
            for c_i in range(4):
                stiffness[dofs[r_i], dofs[c_i]] += k_elem[r_i, c_i]

        prepared_members.append({
            "def": m,
            "length_m": length_m,
            "area_mm2": area_mm2,
            "e_mpa": e_mpa,
            "i_cm": i_cm,
            "cos_a": cos_a,
            "sin_a": sin_a,
            "dofs": dofs,
            "ea_l": ea_l,
        })

    # 2. 组装外荷载
    for ld in inp.loads:
        if ld.node in node_indices:
            idx = node_indices[ld.node]
            applied_loads[idx * 2] += _number(ld.fx_kn, f"loads[{ld.node}].fx_kn") * 1000.0 # N
            applied_loads[idx * 2 + 1] += _number(ld.fy_kn, f"loads[{ld.node}].fy_kn") * 1000.0

    # 3. 施加约束条件
    restrained_dofs = set()
    for sup in inp.supports:
        if sup.node in node_indices:
            idx = node_indices[sup.node]
            if sup.fix_x:
                restrained_dofs.add(idx * 2)
            if sup.fix_y:
                restrained_dofs.add(idx * 2 + 1)

    free_dofs = sorted(set(range(dof_count)) - restrained_dofs)
    if not free_dofs:
        raise CalculationInputError("over_constrained", "桁架所有自由度均被约束。", field="supports")

    displacements = np.zeros(dof_count, dtype=float)
    k_ff = stiffness[np.ix_(free_dofs, free_dofs)]
    
    try:
        displacements[free_dofs] = np.linalg.solve(k_ff, applied_loads[free_dofs])
    except np.linalg.LinAlgError as exc:
        raise CalculationInputError("unstable_truss", "桁架刚度矩阵奇异，结构几何可变或缺少约束。", field="supports") from exc

    # 反力
    reactions = stiffness @ displacements - applied_loads

    # 4. 杆件内力与规范验算 (GB 50017)
    member_results: list[TrussMemberResult] = []
    overall_passed = True
    max_slenderness_util = 0.0
    max_strength_util = 0.0

    for pm in prepared_members:
        m = pm["def"]
        dofs = pm["dofs"]
        u_elem = displacements[dofs] # [u1x, u1y, u2x, u2y] in mm

        # 伸长量 delta_l = (u2x - u1x)*cos + (u2y - u1y)*sin
        delta_l_mm = (u_elem[2] - u_elem[0]) * pm["cos_a"] + (u_elem[3] - u_elem[1]) * pm["sin_a"]
        axial_n = pm["ea_l"] * delta_l_mm # N
        axial_kn = axial_n / 1000.0

        if abs(axial_kn) < 1e-4:
            force_type = "zero"
        elif axial_kn > 0:
            force_type = "tension"
        else:
            force_type = "compression"

        # 长细比 lambda = L_mm / (i_cm * 10)
        i_mm = pm["i_cm"] * 10.0
        lambda_ratio = (pm["length_m"] * 1000.0) / i_mm
        slenderness_limit = inp.compression_slenderness_limit if force_type == "compression" else inp.tension_slenderness_limit
        slenderness_passed = lambda_ratio <= slenderness_limit
        slenderness_util = lambda_ratio / max(slenderness_limit, 1.0)
        max_slenderness_util = max(max_slenderness_util, slenderness_util)

        # 承载力与稳定
        f_y = m.f_y_mpa
        if force_type == "compression":
            # GB 50017 轴压稳定系数近解
            lambda_bar = (lambda_ratio / 3.14159) * ((f_y / pm["e_mpa"]) ** 0.5)
            phi = 1.0 / (1.0 + 0.25 * (lambda_bar ** 2)) if lambda_bar > 0.2 else 1.0
            capacity_kn = (phi * pm["area_mm2"] * f_y) / 1000.0
            utilization = abs(axial_kn) / max(capacity_kn, 1e-6)
        else: # tension or zero
            phi = 1.0
            capacity_kn = (pm["area_mm2"] * f_y) / 1000.0
            utilization = abs(axial_kn) / max(capacity_kn, 1e-6)

        max_strength_util = max(max_strength_util, utilization)
        passed = slenderness_passed and (utilization <= 1.0)
        if not passed:
            overall_passed = False

        member_results.append(
            TrussMemberResult(
                member_id=m.id,
                length_m=pm["length_m"],
                axial_force_kn=axial_kn,
                force_type=force_type,
                slenderness_ratio=lambda_ratio,
                slenderness_limit=slenderness_limit,
                slenderness_passed=slenderness_passed,
                phi_stability=phi,
                capacity_kn=capacity_kn,
                utilization=utilization,
                passed=passed,
            )
        )

    # 整理位移与反力
    node_displacements = {
        n.id: (float(displacements[i*2]), float(displacements[i*2+1]))
        for i, n in enumerate(inp.nodes)
    }

    support_reactions = {
        sup.node: (float(reactions[node_indices[sup.node]*2] / 1000.0), float(reactions[node_indices[sup.node]*2+1] / 1000.0))
        for sup in inp.supports
    }

    return PlanarTrussOutput(
        member_results=tuple(member_results),
        node_displacements_mm=node_displacements,
        support_reactions_kn=support_reactions,
        overall_passed=overall_passed,
        max_slenderness_utilization=max_slenderness_util,
        max_strength_utilization=max_strength_util,
    )
