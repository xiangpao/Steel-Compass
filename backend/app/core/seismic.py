"""GB 50011-2010 (2016年版) 建筑抗震设计规范：底部剪力法计算模块

提供设防烈度、场地类别、特征周期及自振周期影响下的地震影响系数 α1 计算，
以及结构总水平地震作用标准值 FEk 计算。
"""

from typing import Dict, Any, Tuple
from dataclasses import dataclass

# 8度设防烈度下的 αmax (多遇地震 / 罕遇地震)
INTENSITY_ALPHA_MAX = {
    6: {"frequent": 0.04, "rare": 0.28},
    7: {"frequent": 0.08, "rare": 0.50},  # 0.10g 设防
    7.5: {"frequent": 0.12, "rare": 0.72}, # 0.15g 设防
    8: {"frequent": 0.16, "rare": 0.90},  # 0.20g 设防
    8.5: {"frequent": 0.24, "rare": 1.20}, # 0.30g 设防
    9: {"frequent": 0.32, "rare": 1.40},
}

# 场地类别对应的特征周期 Tg (s) [第1组]
SITE_CHARACTERISTIC_PERIOD_GRP1 = {
    "I0": 0.20,
    "I1": 0.25,
    "II": 0.35,
    "III": 0.45,
    "IV": 0.65,
}

@dataclass
class SeismicInput:
    intensity: float  # 设防烈度: 6, 7, 7.5, 8, 8.5, 9
    site_class: str   # 场地类别: 'I0', 'I1', 'II', 'III', 'IV'
    total_gravity_kn: float  # 结构等效总重力荷载代表值 G_eq (kN)
    fundamental_period_s: float  # 结构基本自振周期 T1 (s)
    damping_ratio: float = 0.05  # 阻尼比 (钢结构通常取 0.05)
    is_rare_earthquake: bool = False  # 是否为罕遇地震验算

def calculate_seismic_influence_alpha(
    intensity: float,
    site_class: str,
    period_s: float,
    damping_ratio: float = 0.05,
    is_rare: bool = False,
) -> float:
    """依据 GB 50011-2010 第 5.1.4 条计算水平地震影响系数 α1"""
    if intensity not in INTENSITY_ALPHA_MAX:
        intensity = 7.0  # 默认按7度处理
    alpha_max = INTENSITY_ALPHA_MAX[intensity]["rare" if is_rare else "frequent"]
    tg = SITE_CHARACTERISTIC_PERIOD_GRP1.get(site_class, 0.35)

    # 阻尼调整系数 γ 与 衰减指数 γ1
    eta2 = 1.0 + (0.05 - damping_ratio) / (0.08 + 1.6 * damping_ratio)
    eta2 = max(0.55, eta2)
    
    gamma = 0.9 + (0.05 - damping_ratio) / (0.5 + 5.0 * damping_ratio)
    gamma = max(0.55, gamma)

    if period_s < 0.1:
        # 直线上升段
        eta1 = 0.02
        alpha = (0.45 + (eta2 - 0.45) * period_s / 0.1) * alpha_max
    elif period_s <= tg:
        # 水平段
        alpha = eta2 * alpha_max
    elif period_s <= 5 * tg:
        # 曲线下降段
        alpha = ((tg / period_s) ** gamma) * eta2 * alpha_max
    else:
        # 直线下降段
        alpha = (eta2 * (0.2 ** gamma) - 0.02 * (period_s - 5 * tg)) * alpha_max

    # 最小影响系数限值 (第 5.1.5 条)
    min_alpha = 0.2 * alpha_max
    return max(alpha, min_alpha)

def calculate_base_shear_f_ek(input_data: SeismicInput) -> Dict[str, Any]:
    """依据 GB 50011-2010 第 5.2.1 条采用底部剪力法计算总水平地震作用标准值 FEk"""
    alpha1 = calculate_seismic_influence_alpha(
        intensity=input_data.intensity,
        site_class=input_data.site_class,
        period_s=input_data.fundamental_period_s,
        damping_ratio=input_data.damping_ratio,
        is_rare=input_data.is_rare_earthquake,
    )
    # FEk = α1 * G_eq
    f_ek_kn = alpha1 * input_data.total_gravity_kn
    return {
        "alpha1": round(alpha1, 4),
        "f_ek_kn": round(f_ek_kn, 2),
        "g_eq_kn": input_data.total_gravity_kn,
        "intensity": input_data.intensity,
        "site_class": input_data.site_class,
    }
