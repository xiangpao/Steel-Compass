import pytest
from app.core.seismic import (
    SeismicInput,
    calculate_seismic_influence_alpha,
    calculate_base_shear_f_ek,
)

def test_seismic_influence_alpha_calculation():
    # 7度 设防, II 类场地, Tg = 0.35s
    alpha_horizontal = calculate_seismic_influence_alpha(
        intensity=7.0, site_class="II", period_s=0.35, is_rare=False
    )
    # 多遇地震 αmax = 0.08
    assert pytest.approx(alpha_horizontal, abs=1e-3) == 0.08

def test_base_shear_f_ek_calculation():
    inp = SeismicInput(
        intensity=8.0,
        site_class="II",
        total_gravity_kn=1000.0,
        fundamental_period_s=0.3,
    )
    res = calculate_base_shear_f_ek(inp)
    assert res["alpha1"] == 0.16
    assert res["f_ek_kn"] == 160.0
