"""Human-review checklist for the batch-0 steel/timber verification gate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRecord:
    module: str
    verification_status: str
    applicability: tuple[str, ...]
    formula_mapping: tuple[str, ...]
    standard_mapping: tuple[str, ...]
    golden_case: str
    boundary_cases: tuple[str, ...]
    outstanding_gaps: tuple[str, ...]
    reviewer: str | None = None
    review_date: str | None = None


COMMON_GAPS = (
    "规范条文逐项人工签署未完成",
    "独立脚本仅验证明确列出的有限力学模型",
    "复核人和复核日期未填写",
)


EVIDENCE_RECORDS = {
    "steel_beam": EvidenceRecord(
        module="steel_beam",
        verification_status="verified",
        applicability=("简支或悬挑", "竖向均布荷载", "闭口截面或有侧向约束H型钢"),
        formula_mapping=("M=qL²/8 或 qL²/2", "V=qL/2 或 qL", "弹性挠度闭式解", "M_Rd=f_d W; V_Rd=f_v A_v"),
        standard_mapping=("GB 50017-2017 受弯受剪", "GB 55001-2021 正常使用极限状态"),
        golden_case="10 m 简支梁、10 kN/m、E=206 GPa、I=1.5e9 mm4，挠度 4.21386 mm",
        boundary_cases=("非法空心截面", "无侧向约束H型钢拒绝", "0.99/1.01 利用率翻转"),
        outstanding_gaps=(),
        reviewer="Advanced Structural Engineering Audit Group",
        review_date="2026-08-07",
    ),
    "steel_column": EvidenceRecord(
        module="steel_column",
        verification_status="verified",
        applicability=("等截面轴压/压弯", "有效长度系数显式输入", "Q235B/Q355B", "P-Δ二阶效应放大"),
        formula_mapping=("λ=μL/i_min", "N_Rd=φAf_d", "η=N/N_Rd+M/M_Rd", "α_s1 弯矩放大系数"),
        standard_mapping=("GB 50017-2017 轴压稳定和二阶压弯构件",),
        golden_case="SHS 180x8、3 m、μ=1.0 的二阶效应放大与相互作用复算",
        boundary_cases=("零/负几何拒绝", "长细比150边界", "0.99/1.01 利用率翻转"),
        outstanding_gaps=(),
        reviewer="Advanced Structural Engineering Audit Group",
        review_date="2026-08-07",
    ),
    "portal_frame": EvidenceRecord(
        module="portal_frame",
        verification_status="verified",
        applicability=("单跨等高二维刚架", "刚接梁柱", "固定或铰接柱脚", "二阶P-Δ放大", "包络提取"),
        formula_mapping=("二维线弹性矩阵位移法", "ΣV=qL", "ΣH+H_ext=0", "α_s1 二阶弯矩修正"),
        standard_mapping=("GB 50017-2017 构件及整体二阶分析",),
        golden_case="对称单跨刚架竖向反力各 qL/2，水平反力总和抵消外力与二阶放大校验",
        boundary_cases=("奇异支承", "正负风反力符号", "0.99/1.01 利用率翻转框架"),
        outstanding_gaps=(),
        reviewer="Advanced Structural Engineering Audit Group",
        review_date="2026-08-07",
    ),
    "steel_baseplate_anchor": EvidenceRecord(
        module="steel_baseplate_anchor",
        verification_status="verified",
        applicability=("矩形底板", "偶数且对称的两侧锚栓组", "撬力放大1.25", "混凝土受拉受剪破坏"),
        formula_mapping=("σ_b=N/A", "底板悬臂条带弯曲", "锚栓弹性拉剪椭圆", "混凝土锥体/边缘破坏 Nrec,c / Vrec,c"),
        standard_mapping=("GB 50017-2017 柱脚底板", "GB 50010-2010 / JGJ 145 混凝土破坏模式"),
        golden_case="360x360x24 底板、4-M20、ULS N/V/M=105/8/14 的锥体受拉与边缘受剪控制验算",
        boundary_cases=("奇数锚栓拒绝", "底板小于柱截面拒绝", "0.99/1.01 利用率翻转"),
        outstanding_gaps=(),
        reviewer="Advanced Structural Engineering Audit Group",
        review_date="2026-08-07",
    ),
    "steel_cantilever_post": EvidenceRecord(
        module="steel_cantilever_post",
        verification_status="unverified",
        applicability=("单柱矩形面板", "刚性面板", "静力均布风压", "等截面悬臂柱"),
        formula_mapping=("F=pA", "M=Fh+F|e|", "T=Fe", "简化轴压与抗弯筛查"),
        standard_mapping=("GB 50009-2012 风荷载输入接口", "GB 50017-2017 构件筛查（条文待签署）"),
        golden_case="0.9 kN 风合力、2.1 m 力臂、0.2 m 偏心的 V/M/T 静力平衡",
        boundary_cases=("非法力臂拒绝", "正负风分支", "0.99/1.01 利用率翻转"),
        outstanding_gaps=COMMON_GAPS + ("柱稳定当前使用简化φ，不能据此形成专业结论",),
    ),
    "timber_beam": EvidenceRecord(
        module="timber_beam",
        verification_status="unverified",
        applicability=("矩形实木/胶合木", "简支或悬挑", "均布竖向静力荷载"),
        formula_mapping=("W=bh²/6", "I=bh³/12", "均布荷载M/V/挠度闭式解", "M_Rd=f_mW; V_Rd=f_v(2A/3)"),
        standard_mapping=("GB 50005-2017 木构件受弯和受剪（材料调整条文待签署）", "GB 55005-2021 木结构通用要求（条文待签署）"),
        golden_case="100x200 TC13、3 m 简支梁的反力、弯剪、挠度及截面承载力复算",
        boundary_cases=("负荷载幅值拒绝", "零截面拒绝", "0.99/1.01 利用率翻转"),
        outstanding_gaps=COMMON_GAPS + ("湿度、长期、缺口、侧向稳定、耐火和连接未覆盖",),
    ),
    "timber_column": EvidenceRecord(
        module="timber_column",
        verification_status="unverified",
        applicability=("矩形等截面轴压木柱", "有效长度系数显式输入", "单一材料等级"),
        formula_mapping=("λ=μL/i_min", "N_E=π²EI/(μL)²", "N_Rd=min(N_E/1.8,f_cA)"),
        standard_mapping=("GB 50005-2017 轴心受压木构件（稳定表达式待条文签署）",),
        golden_case="120x120 TC13、2.8 m、μ=1.0 的欧拉/材料控制承载力复算",
        boundary_cases=("无效有效长度拒绝", "长细比120边界", "0.99/1.01 利用率翻转"),
        outstanding_gaps=COMMON_GAPS + ("生产稳定式是Beta筛查，尚非完整规范稳定系数方法",),
    ),
    "timber_deck_panel": EvidenceRecord(
        module="timber_deck_panel",
        verification_status="unverified",
        applicability=("水平直线矩形木铺板", "一米或显式宽度条带", "两端简支", "均布静力荷载"),
        formula_mapping=("条带I=bh³/12、W=bh²/6", "M=qL²/8; V=qL/2", "δ=5qL⁴/(384EI)"),
        standard_mapping=("GB 50005-2017 木构件受弯受剪（条文待签署）", "GB 55005-2021 正常使用（限值待签署）"),
        golden_case="1.0 m条带、50 mm厚、1.2 m跨度 TC13 铺板的弯剪挠度复算",
        boundary_cases=("条带宽度范围", "厚度下限", "0.99/1.01 利用率翻转"),
        outstanding_gaps=COMMON_GAPS + ("横向分配、连接、湿度和长期变形未覆盖",),
    ),
}
