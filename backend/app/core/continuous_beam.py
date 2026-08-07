from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

import numpy as np

from .errors import CalculationInputError
from .structural_solvers import (
    ContinuousBeamModel,
    ContinuousBeamNode,
    ContinuousBeamSpan,
    ContinuousBeamSupport,
    solve_continuous_beam,
)


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
class ContinuousBeamSpanInput:
    span_id: str
    length_m: float
    b_mm: float = 250.0
    h_mm: float = 500.0
    dead_load_kn_m: float = 10.0
    live_load_kn_m: float = 15.0
    elastic_modulus_gpa: float = 30.0
    f_c_mpa: float = 14.3       # 混凝土轴心抗压强度设计值 (N/mm2)
    f_t_mpa: float = 1.43       # 混凝土轴心抗拉强度设计值 (N/mm2)
    f_y_mpa: float = 360.0      # 纵向受拉钢筋抗拉强度设计值 (N/mm2)
    f_yv_mpa: float = 270.0     # 箍筋抗拉强度设计值 (N/mm2)
    as_mm2: float = 1200.0      # 配置纵向受拉钢筋面积 (mm2)
    asv_s_mm2_mm: float = 1.0   # 单位长度配置箍筋面积 (A_sv / s, mm2/mm)


@dataclass(frozen=True)
class ContinuousBeamInput:
    spans: tuple[ContinuousBeamSpanInput, ...]
    gamma_g: float = 1.3
    gamma_q: float = 1.5
    enable_plastic_redistribution: bool = True
    redistribution_ratio: float = 0.20   # GB 50010 允许最大 20% 调幅
    deflection_limit_ratio: float = 400.0 # L / 400
    material_type: Literal["concrete", "steel"] = "concrete"


@dataclass(frozen=True)
class SpanEnvelopeResult:
    span_id: str
    length_m: float
    m_sagging_max_knm: float       # 最大正弯矩 (跨中受拉)
    m_sagging_max_x_m: float
    m_hogging_max_knm: float       # 最大负弯矩 (支座受拉，绝对值)
    m_hogging_max_x_m: float
    v_max_kn: float                # 最大剪力绝对值
    v_max_x_m: float
    deflection_max_mm: float       # 最大挠度
    deflection_max_x_m: float
    # 调幅后设计内力
    m_design_sagging_knm: float
    m_design_hogging_knm: float
    moment_capacity_knm: float
    shear_capacity_kn: float
    flexure_utilization: float
    shear_utilization: float
    deflection_utilization: float
    flexure_passed: bool
    shear_passed: bool
    deflection_passed: bool


@dataclass(frozen=True)
class ContinuousBeamOutput:
    spans_results: tuple[SpanEnvelopeResult, ...]
    reactions_max_kn: dict[str, float]
    reactions_min_kn: dict[str, float]
    redistribution_applied: bool
    redistribution_ratio_used: float
    overall_passed: bool
    envelope_points: tuple[dict[str, float], ...]
    notes: tuple[str, ...]


def _compute_section_properties(
    b_mm: float, h_mm: float
) -> tuple[float, float, float]:
    """返回 (Area_mm2, Inertia_mm4, Wx_mm3)"""
    area = b_mm * h_mm
    inertia = b_mm * (h_mm ** 3) / 12.0
    wx = b_mm * (h_mm ** 2) / 6.0
    return area, inertia, wx


def _calculate_rc_capacities(
    b_mm: float,
    h_mm: float,
    f_c_mpa: float,
    f_t_mpa: float,
    f_y_mpa: float,
    f_yv_mpa: float,
    as_mm2: float,
    asv_s_mm2_mm: float,
    cover_mm: float = 35.0,
) -> tuple[float, float]:
    """计算混凝土矩形截面受弯与受剪承载力 (kN.m, kN)。

    遵照 GB 50010 正截面受弯与斜截面受剪承载力公式。
    """
    h0 = h_mm - cover_mm
    if h0 <= 0:
        raise CalculationInputError(
            "invalid_effective_depth",
            "有效高度 h0 必须大于零。",
            field="h_mm",
        )
    # 受弯承载力 Mu
    alpha_1 = 1.0
    # x = f_y * A_s / (alpha_1 * f_c * b)
    x = (f_y_mpa * as_mm2) / (alpha_1 * f_c_mpa * b_mm)
    # 相对受压区高度限制
    x_clamped = min(x, 0.55 * h0)
    mu_nmm = alpha_1 * f_c_mpa * b_mm * x_clamped * (h0 - 0.5 * x_clamped)
    mu_knm = mu_nmm / 1e6

    # 受剪承载力 Vu = 0.7 * f_t * b * h0 + f_yv * (A_sv / s) * h0
    vu_n = 0.7 * f_t_mpa * b_mm * h0 + f_yv_mpa * asv_s_mm2_mm * h0
    vu_kn = vu_n / 1000.0

    return mu_knm, vu_kn


def calculate_continuous_beam_engine(
    inp: ContinuousBeamInput,
) -> ContinuousBeamOutput:
    """多跨连续梁矩阵求解、活载包络分析、GB 50010 塑性内力重分配及抗弯/受剪验算。"""

    if not inp.spans:
        raise CalculationInputError(
            "missing_spans", "连续梁至少需要一个跨。", field="spans"
        )

    # 1. 校验与推导基本模型参数
    num_spans = len(inp.spans)
    node_ids = tuple(f"N{i}" for i in range(num_spans + 1))
    
    # 支承：端节点与中间节点均为竖向约束，端节点自由转动（简支连续梁）
    supports = tuple(
        ContinuousBeamSupport(node=node_id, vertical=True, rotation=False)
        for node_id in node_ids
    )

    # 收集各跨截面及刚度
    spans_model_base: list[dict] = []
    for idx, sp in enumerate(inp.spans):
        length_mm = _positive(sp.length_m, f"spans[{idx}].length_m") * 1000.0
        b_mm = _positive(sp.b_mm, f"spans[{idx}].b_mm")
        h_mm = _positive(sp.h_mm, f"spans[{idx}].h_mm")
        e_mpa = _positive(sp.elastic_modulus_gpa, f"spans[{idx}].elastic_modulus_gpa") * 1000.0
        
        _, inertia_mm4, _ = _compute_section_properties(b_mm, h_mm)

        spans_model_base.append(
            {
                "id": sp.span_id,
                "start": node_ids[idx],
                "end": node_ids[idx + 1],
                "length_mm": length_mm,
                "elastic_modulus_mpa": e_mpa,
                "inertia_mm4": inertia_mm4,
                "dead_n_mm": _number(sp.dead_load_kn_m, f"spans[{idx}].dead_load_kn_m"), # 1 kN/m = 1 N/mm
                "live_n_mm": _number(sp.live_load_kn_m, f"spans[{idx}].live_load_kn_m"),
            }
        )

    # 2. 活载布载模式生成 (Live Load Patterns)
    # 工况列表: (pattern_name, span_load_multipliers)
    patterns: list[tuple[str, list[float]]] = []
    
    # 恒载单独 (Pattern 0)
    patterns.append(("Dead_Only", [0.0] * num_spans))
    # 奇数跨满活载
    patterns.append(("Odd_Spans_Live", [1.0 if i % 2 == 0 else 0.0 for i in range(num_spans)]))
    # 偶数跨满活载
    patterns.append(("Even_Spans_Live", [1.0 if i % 2 == 1 else 0.0 for i in range(num_spans)]))

    # 各中间支座两邻跨活载
    for i in range(num_spans - 1):
        multipliers = [0.0] * num_spans
        multipliers[i] = 1.0
        multipliers[i + 1] = 1.0
        patterns.append((f"Support_N{i+1}_Live", multipliers))

    # 全跨活载
    patterns.append(("All_Spans_Live", [1.0] * num_spans))

    # 针对每个 Pattern 进行矩阵求解
    samples_per_span = 101
    pattern_results = []
    
    for pat_name, live_mults in patterns:
        spans_def = tuple(
            ContinuousBeamSpan(
                id=item["id"],
                start=item["start"],
                end=item["end"],
                length_mm=item["length_mm"],
                elastic_modulus_mpa=item["elastic_modulus_mpa"],
                inertia_mm4=item["inertia_mm4"],
                q_y_n_per_mm=-(inp.gamma_g * item["dead_n_mm"] + inp.gamma_q * live_mults[idx] * item["live_n_mm"]),
            )
            for idx, item in enumerate(spans_model_base)
        )
        model = ContinuousBeamModel(
            nodes=tuple(ContinuousBeamNode(nid) for nid in node_ids),
            spans=spans_def,
            supports=supports,
        )
        res = solve_continuous_beam(model, samples_per_span=samples_per_span)
        pattern_results.append((pat_name, res))

    # 3. 提取全梁多工况内力包络 (Envelope Extraction)
    # 按跨整理所有采样点
    span_samples_envelope: dict[str, list[dict[str, float]]] = {sp.span_id: [] for sp in inp.spans}
    
    for s_idx, sp in enumerate(inp.spans):
        span_id = sp.span_id
        num_points = samples_per_span
        
        # 初始化采样点包络
        for p in range(num_points):
            x_mm = (spans_model_base[s_idx]["length_mm"] / (num_points - 1)) * p
            span_samples_envelope[span_id].append(
                {
                    "x_m": x_mm / 1000.0,
                    "m_max_nmm": -1e20,
                    "m_min_nmm": 1e20,
                    "v_max_n": -1e20,
                    "v_min_n": 1e20,
                    "w_max_mm": -1e20,
                    "w_min_mm": 1e20,
                }
            )

        for _, res in pattern_results:
            span_res = res.spans[span_id]
            for p, sample in enumerate(span_res.samples):
                point = span_samples_envelope[span_id][p]
                point["m_max_nmm"] = max(point["m_max_nmm"], sample.moment_nmm)
                point["m_min_nmm"] = min(point["m_min_nmm"], sample.moment_nmm)
                point["v_max_n"] = max(point["v_max_n"], sample.shear_n)
                point["v_min_n"] = min(point["v_min_n"], sample.shear_n)
                point["w_max_mm"] = max(point["w_max_mm"], abs(sample.deflection_mm))

    # 提取支座反力包络
    reactions_max: dict[str, float] = {nid: -1e20 for nid in node_ids}
    reactions_min: dict[str, float] = {nid: 1e20 for nid in node_ids}

    for _, res in pattern_results:
        for nid, reac in res.reactions.items():
            str_nid = str(nid)
            reactions_max[str_nid] = max(reactions_max[str_nid], reac.vertical_n / 1000.0)
            reactions_min[str_nid] = min(reactions_min[str_nid], reac.vertical_n / 1000.0)

    # 4. GB 50010 塑性内力重分配 (Plastic Moment Redistribution)
    redistribution_ratio = min(max(inp.redistribution_ratio, 0.0), 0.20) if inp.enable_plastic_redistribution else 0.0

    span_results: list[SpanEnvelopeResult] = []
    envelope_points_export: list[dict[str, float]] = []
    overall_passed = True
    notes: list[str] = []

    if redistribution_ratio > 0:
        notes.append(f"按 GB 50010-2010 规范进行了 {redistribution_ratio*100:.1f}% 支座弯矩塑性调幅。")

    for s_idx, sp in enumerate(inp.spans):
        span_id = sp.span_id
        samples = span_samples_envelope[span_id]
        length_m = sp.length_m
        
        # 寻找弹性包络下的正弯矩与负弯矩峰值
        # 求解器定义: 向上凸/正弯矩为 sagging (+), 下凹/负弯矩为 hogging (-)
        m_sagging_max_nmm = max(pt["m_max_nmm"] for pt in samples)
        m_sagging_pt = max(samples, key=lambda pt: pt["m_max_nmm"])
        
        m_hogging_min_nmm = min(pt["m_min_nmm"] for pt in samples) # 负值
        m_hogging_pt = min(samples, key=lambda pt: pt["m_min_nmm"])
        
        v_max_n = max(max(abs(pt["v_max_n"]), abs(pt["v_min_n"])) for pt in samples)
        v_max_pt = max(samples, key=lambda pt: max(abs(pt["v_max_n"]), abs(pt["v_min_n"])))

        w_max_mm = max(pt["w_max_mm"] for pt in samples)
        w_max_pt = max(samples, key=lambda pt: pt["w_max_mm"])

        # 调幅后设计弯矩
        # 支座负弯矩降低 (1 - beta)，跨中正弯矩相应调高
        m_hogging_design_knm = abs(m_hogging_min_nmm) / 1e6 * (1.0 - redistribution_ratio)
        m_sagging_design_knm = (m_sagging_max_nmm / 1e6) + (abs(m_hogging_min_nmm) / 1e6 * redistribution_ratio * 0.5)

        # 截面承载力计算
        if inp.material_type == "concrete":
            m_cap_knm, v_cap_kn = _calculate_rc_capacities(
                b_mm=sp.b_mm,
                h_mm=sp.h_mm,
                f_c_mpa=sp.f_c_mpa,
                f_t_mpa=sp.f_t_mpa,
                f_y_mpa=sp.f_y_mpa,
                f_yv_mpa=sp.f_yv_mpa,
                as_mm2=sp.as_mm2,
                asv_s_mm2_mm=sp.asv_s_mm2_mm,
            )
        else: # steel
            _, _, wx_mm3 = _compute_section_properties(sp.b_mm, sp.h_mm)
            m_cap_knm = (wx_mm3 * sp.f_y_mpa) / 1e6
            v_cap_kn = (sp.b_mm * sp.h_mm * (sp.f_y_mpa / 1.732)) / 1000.0

        # 利用率与判定
        governing_m_design = max(m_sagging_design_knm, m_hogging_design_knm)
        flexure_util = governing_m_design / max(m_cap_knm, 1e-6)
        shear_util = (v_max_n / 1000.0) / max(v_cap_kn, 1e-6)

        deflection_limit_mm = (length_m * 1000.0) / max(inp.deflection_limit_ratio, 1.0)
        deflection_util = w_max_mm / max(deflection_limit_mm, 1e-6)

        flexure_passed = flexure_util <= 1.0
        shear_passed = shear_util <= 1.0
        deflection_passed = deflection_util <= 1.0

        if not (flexure_passed and shear_passed and deflection_passed):
            overall_passed = False

        span_results.append(
            SpanEnvelopeResult(
                span_id=span_id,
                length_m=length_m,
                m_sagging_max_knm=m_sagging_max_nmm / 1e6,
                m_sagging_max_x_m=m_sagging_pt["x_m"],
                m_hogging_max_knm=abs(m_hogging_min_nmm) / 1e6,
                m_hogging_max_x_m=m_hogging_pt["x_m"],
                v_max_kn=v_max_n / 1000.0,
                v_max_x_m=v_max_pt["x_m"],
                deflection_max_mm=w_max_mm,
                deflection_max_x_m=w_max_pt["x_m"],
                m_design_sagging_knm=m_sagging_design_knm,
                m_design_hogging_knm=m_hogging_design_knm,
                moment_capacity_knm=m_cap_knm,
                shear_capacity_kn=v_cap_kn,
                flexure_utilization=flexure_util,
                shear_utilization=shear_util,
                deflection_utilization=deflection_util,
                flexure_passed=flexure_passed,
                shear_passed=shear_passed,
                deflection_passed=deflection_passed,
            )
        )

        for pt in samples:
            envelope_points_export.append(
                {
                    "span_id": span_id,
                    "x_m": pt["x_m"],
                    "m_max_knm": pt["m_max_nmm"] / 1e6,
                    "m_min_knm": pt["m_min_nmm"] / 1e6,
                    "v_max_kn": pt["v_max_n"] / 1000.0,
                    "v_min_kn": pt["v_min_n"] / 1000.0,
                    "deflection_mm": pt["w_max_mm"],
                }
            )

    return ContinuousBeamOutput(
        spans_results=tuple(span_results),
        reactions_max_kn=reactions_max,
        reactions_min_kn=reactions_min,
        redistribution_applied=redistribution_ratio > 0,
        redistribution_ratio_used=redistribution_ratio,
        overall_passed=overall_passed,
        envelope_points=tuple(envelope_points_export),
        notes=tuple(notes),
    )
