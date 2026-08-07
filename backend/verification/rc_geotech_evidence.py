"""Machine-readable evidence inventory for RC and geotechnical modules.

The inventory records what has been independently cross-checked and, more
importantly, what is still missing.  ``verification_status`` must remain
``unverified`` until every gap is closed and a reviewer/date are recorded.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormulaMapping:
    check: str
    equation: str
    standard_topic: str
    mapping_status: str = "candidate_pending_clause_review"


@dataclass(frozen=True)
class ModuleEvidence:
    module: str
    applicability: tuple[str, ...]
    excluded_scope: tuple[str, ...]
    formula_mappings: tuple[FormulaMapping, ...]
    golden_case: str
    independent_reference: str
    boundary_cases: tuple[str, ...]
    open_gaps: tuple[str, ...]
    verification_status: str = "unverified"
    reviewer: str | None = None
    review_date: str | None = None


RC_GEOTECH_EVIDENCE: dict[str, ModuleEvidence] = {
    "concrete_beam": ModuleEvidence(
        module="concrete_beam",
        applicability=("矩形单筋梁", "简支或悬挑", "静力均布竖向荷载"),
        excluded_scope=("连续梁", "双筋梁", "扭转", "抗震", "疲劳"),
        formula_mappings=(
            FormulaMapping("受弯", "x=fy*As/(fc*b); Mu=fy*As*(h0-x/2)", "GB/T 50010-2010（2024局部修订）受弯承载力"),
            FormulaMapping("受剪", "Vc=0.7*ft*b*h0+fyv*Asv*h0/s", "GB/T 50010-2010（2024局部修订）受剪承载力"),
            FormulaMapping("挠度与裂缝", "Ie近似与钢筋应力近似", "GB 55001-2021 SLS；GB/T 50010-2010（2024局部修订）裂缝与变形"),
        ),
        golden_case="RC-BEAM-001: C30/HRB400, 250x450, 3 m 简支均布荷载",
        independent_reference="rc_rectangular_flexure + simple_span_udl",
        boundary_cases=("有效高度<=0", "最小/最大配筋", "利用率0.99/1.01"),
        open_gaps=("精确条文号与适用条件人工签署", "裂缝长期效应独立复算", "有效刚度和挠度独立复算", "认可软件对照"),
    ),
    "concrete_slab": ModuleEvidence(
        module="concrete_slab",
        applicability=("1 m宽单向板条带", "简支或悬挑", "不配置受剪箍筋"),
        excluded_scope=("双向板", "冲切", "板柱体系", "复杂连续支承"),
        formula_mappings=(
            FormulaMapping("受弯", "x=fy*As/(fc*b); Mu=fy*As*(h0-x/2)", "GB/T 50010-2010（2024局部修订）板受弯承载力"),
            FormulaMapping("受剪", "Vc=0.7*ft*b*h0", "GB/T 50010-2010（2024局部修订）不配置箍筋板受剪"),
            FormulaMapping("配筋", "As=1000/s*pi*d^2/4", "GB/T 50010-2010（2024局部修订）板最小配筋"),
        ),
        golden_case="RC-SLAB-001: C30/HRB400, h=150, d12@150, 3 m 简支条带",
        independent_reference="bar_area + rc_rectangular_flexure + simple_span_udl",
        boundary_cases=("钢筋间距边界", "有效高度<=0", "利用率0.99/1.01"),
        open_gaps=("精确条文号人工签署", "裂缝/挠度长期效应独立复算", "双向作用不适用提示复核", "认可软件对照"),
    ),
    "concrete_column": ModuleEvidence(
        module="concrete_column",
        applicability=("矩形或圆形普通RC柱", "轴压", "单向偏压初筛"),
        excluded_scope=("双向偏压", "二阶精细分析", "抗震柱", "复杂配筋布置"),
        formula_mappings=(
            FormulaMapping("长细比", "lambda=mu*L/i", "结构稳定基本关系"),
            FormulaMapping("轴压", "Nu=0.9*phi*(fc*Ac+fy*As)", "GB/T 50010-2010（2024局部修订）轴心受压"),
            FormulaMapping("偏压", "N/Nu+M/Mu<=1", "GB/T 50010-2010（2024局部修订）偏压；当前为简化筛查"),
        ),
        golden_case="RC-COL-001: C30/HRB400, 300x300, L=3 m, As=1608 mm2",
        independent_reference="rc_rectangular_column",
        boundary_cases=("钢筋面积>=毛截面", "负荷载", "利用率0.99/1.01"),
        open_gaps=("phi模型精确条文映射", "真实偏压截面平衡独立实现", "二阶效应", "圆柱独立黄金算例", "认可软件对照"),
    ),
    "masonry_wall": ModuleEvidence(
        module="masonry_wall",
        applicability=("RC构造柱约束的直线等高砌体填充墙", "规则柱距", "平面外风压"),
        excluded_scope=("无约束纯砌体高墙", "复杂开洞", "地震", "沉降"),
        formula_mappings=(
            FormulaMapping("平面外作用", "q=p*H; M=q*L^2/8; V=q*L/2", "GB 50003-2011 砌体墙片受力模型"),
            FormulaMapping("弯曲应力", "sigma=M/W; W=1000*t^2/6", "GB 50003-2011 砌体受弯"),
            FormulaMapping("构造柱间距", "L<=4 m（当前项目规则）", "GB 50003-2011 构造要求；待逐条复核"),
        ),
        golden_case="MAS-WALL-001: H=2 m, L=3 m, t=240 mm, p=0.5 kPa",
        independent_reference="masonry_wall_strip",
        boundary_cases=("负风压按方向保留", "柱距上限", "利用率0.99/1.01"),
        open_gaps=("材料强度等级与砌筑砂浆映射", "开洞限制", "构造柱/圈梁协同模型", "精确条文号与认可软件对照"),
    ),
    "rc_wall": ModuleEvidence(
        module="rc_wall",
        applicability=("1 m墙宽悬臂条带", "风压", "单层水平填土的可选主动土压力"),
        excluded_scope=("墙顶约束", "双向板作用", "地震", "复杂分层土", "裂缝正式设计"),
        formula_mappings=(
            FormulaMapping("主动土压力", "Ka=tan^2(45-phi/2); Pa=0.5*Ka*gamma*H^2+Ka*q*H", "GB 50007-2011 主动土压力模型"),
            FormulaMapping("墙身弯矩", "M=p*H^2/2+Msoil", "悬臂墙条带静力模型"),
            FormulaMapping("配筋承载力", "Mu=fy*As*0.85h", "GB/T 50010-2010（2024局部修订）受弯；当前简化筛查"),
        ),
        golden_case="RC-WALL-001: H=1.2 m, t=180 mm, d12@200, p=0.3 kPa",
        independent_reference="rc_wall_cantilever",
        boundary_cases=("土高不得超过墙高", "负压力拒绝", "利用率0.99/1.01"),
        open_gaps=("最小配筋检查方向需生产代码复核", "裂缝与长期效应", "墙根锚固", "精确条文号与认可软件对照"),
    ),
    "spread_footing": ModuleEvidence(
        module="spread_footing",
        applicability=("刚性矩形独立基础初筛", "中心或双向偏心", "全接触线性基底压力"),
        excluded_scope=("局部脱开后的非线性接触结论", "沉降", "软弱下卧层", "液化", "复杂地基"),
        formula_mappings=(
            FormulaMapping("基底压力", "q=N/(BL)*(1+/-6ex/L+/-6ey/B)", "GB 50007-2011 偏心基础"),
            FormulaMapping("冲切", "Vc=0.7*ft*um*h0; um=2*(cx+cy+2h0)", "GB/T 50010-2010（2024局部修订）基础冲切"),
            FormulaMapping("稳定", "V<=mu*N; M<=N*B/2; uplift<=effective weight", "GB 55003-2021 基础稳定与抗浮"),
        ),
        golden_case="FND-SPREAD-001: 2x2x0.5 m, 300x300柱, 中心荷载",
        independent_reference="effective_foundation_weight + spread_footing_pressure",
        boundary_cases=("柱尺寸>=基础", "局部脱开", "地下水折减", "上拔", "利用率0.99/1.01"),
        open_gaps=("地基承载力修正与勘察输入边界", "局部接触非线性", "埋深/地下水几何定义复核", "冲切完整系数映射", "认可软件对照"),
    ),
    "strip_footing": ModuleEvidence(
        module="strip_footing",
        applicability=("每延米均匀墙荷载", "横向偏心", "全接触线性基底压力"),
        excluded_scope=("纵向不均匀沉降", "交叉条基", "弹性地基梁", "局部脱开后的非线性接触结论"),
        formula_mappings=(
            FormulaMapping("基底压力", "q=N/B*(1+/-6e/B)", "GB 50007-2011 偏心条形基础"),
            FormulaMapping("横向弯剪", "M=q*a^2/2; V=q*(a-h0)", "GB/T 50010-2010（2024局部修订）基础底板"),
            FormulaMapping("稳定", "V<=mu*N; M<=N*B/2", "GB 55003-2021 基础稳定"),
        ),
        golden_case="FND-STRIP-001: B=1.2 m, t=0.4 m, 240 mm墙居中",
        independent_reference="effective_foundation_weight + strip_footing_pressure",
        boundary_cases=("墙宽>=基础宽", "正负偏心抵消", "局部脱开", "利用率0.99/1.01"),
        open_gaps=("地基变形", "非线性接触", "地下水与埋深定义复核", "精确条文号与认可软件对照"),
    ),
    "retaining_wall": ModuleEvidence(
        module="retaining_wall",
        applicability=("水平填土", "单一土层", "直线RC悬臂挡墙", "静水压力"),
        excluded_scope=("地震", "整体稳定", "沉降", "软基", "被动土压力常规贡献", "加筋土"),
        formula_mappings=(
            FormulaMapping("主动土压力", "Ka=tan^2(45-phi/2); Pa=0.5*Ka*gamma*H^2+Ka*q*H", "GB 50007-2011 主动土压力模型"),
            FormulaMapping("静水压力", "Pw=0.5*gammaw*Hw^2", "静水压力基本关系；GB 55003-2021 抗浮边界"),
            FormulaMapping("基底稳定", "q=N/B*(1+/-6e/B); sliding/overturning/uplift", "GB 50007-2011；GB 55003-2021"),
        ),
        golden_case="RET-WALL-001: H=1.5 m, B=1.6 m, phi=30 deg, gamma=18",
        independent_reference="cantilever_retaining_wall",
        boundary_cases=("水位超过墙高", "局部脱开", "零摩擦", "利用率0.99/1.01"),
        open_gaps=("墙踵/墙趾底板配筋尚未完整", "墙身裂缝与锚固", "整体稳定", "精确条文号与认可软件对照"),
    ),
}


def evidence_is_signed(record: ModuleEvidence) -> bool:
    """Return true only for a complete, explicitly signed evidence record."""

    return (
        record.verification_status == "independently_verified"
        and record.reviewer is not None
        and record.review_date is not None
        and not record.open_gaps
        and all(
            mapping.mapping_status == "reviewed_and_signed"
            for mapping in record.formula_mappings
        )
    )
