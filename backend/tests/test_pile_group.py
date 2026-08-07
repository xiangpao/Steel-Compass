from __future__ import annotations

from dataclasses import replace
from math import hypot

import pytest

from app.core.errors import CalculationInputError
from app.core.pile_group import (
    InvestigatedPileCapacities,
    PileCapGeometry,
    PileCapMaterial,
    PileDefinition,
    PileGroupActions,
    PileGroupModel,
    SoilLayerJGJ94,
    analyze_rigid_pile_group,
    calculate_single_pile_capacity_jgj94,
)


def square_piles() -> tuple[PileDefinition, ...]:
    return (
        PileDefinition("p1", -800, -800, 400, "bored"),
        PileDefinition("p2", 800, -800, 400, "precast_pipe"),
        PileDefinition("p3", 800, 800, 400, "precast_square"),
        PileDefinition("p4", -800, 800, 400, "bored"),
    )


def model_with(
    actions: PileGroupActions,
    *,
    piles: tuple[PileDefinition, ...] | None = None,
    capacities: InvestigatedPileCapacities | None = None,
    cap: PileCapGeometry | None = None,
    material: PileCapMaterial | None = None,
) -> PileGroupModel:
    return PileGroupModel(
        piles=piles or square_piles(),
        capacities=capacities
        or InvestigatedPileCapacities(
            compression_kn=500,
            uplift_kn=200,
            horizontal_kn=100,
            source="勘察报告：单桩设计承载力表",
        ),
        cap=cap
        or PileCapGeometry(
            length_x_mm=3_000,
            width_y_mm=3_000,
            thickness_mm=500,
            column_x_mm=500,
            column_y_mm=500,
            cover_mm=70,
            bar_diameter_mm=20,
        ),
        material=material
        or PileCapMaterial(
            concrete_tensile_strength_mpa=1.43,
            rebar_yield_strength_mpa=360,
            provided_rebar_x_mm2_per_m=2_500,
            provided_rebar_y_mm2_per_m=2_500,
        ),
        actions=actions,
    )


def test_centered_compression_distributes_equally_and_balances() -> None:
    result = analyze_rigid_pile_group(model_with(PileGroupActions(n_kn=800)))
    for reaction in result.pile_reactions.values():
        assert reaction.compression_kn == pytest.approx(200)
        assert reaction.uplift_kn == 0
        assert reaction.horizontal_resultant_kn == 0
    assert result.balance.n_kn == pytest.approx(800)
    assert result.balance.mx_kn_m == pytest.approx(0, abs=1e-12)
    assert result.balance.my_kn_m == pytest.approx(0, abs=1e-12)
    assert result.balance.maximum_absolute_residual == pytest.approx(0, abs=1e-12)
    assert result.capacity_source.startswith("勘察报告")
    assert result.verification_status == "unverified"
    assert any("不从土层参数反算" in item for item in result.exclusions)


def test_single_and_double_eccentricity_follow_rigid_cap_closed_form() -> None:
    actions = PileGroupActions(n_kn=800, mx_kn_m=80, my_kn_m=40)
    result = analyze_rigid_pile_group(model_with(actions))
    # P=N/4 + Mx*y/sum(y^2) + My*x/sum(x^2), with x,y=+-800 mm.
    expected = {"p1": 162.5, "p2": 187.5, "p3": 237.5, "p4": 212.5}
    for pile_id, compression in expected.items():
        assert result.pile_reactions[pile_id].compression_kn == pytest.approx(compression)
    assert result.balance.n_kn == pytest.approx(actions.n_kn)
    assert result.balance.mx_kn_m == pytest.approx(actions.mx_kn_m)
    assert result.balance.my_kn_m == pytest.approx(actions.my_kn_m)

    single_axis = analyze_rigid_pile_group(
        model_with(PileGroupActions(n_kn=800, mx_kn_m=80))
    )
    assert single_axis.pile_reactions["p1"].compression_kn == pytest.approx(175)
    assert single_axis.pile_reactions["p2"].compression_kn == pytest.approx(175)
    assert single_axis.pile_reactions["p3"].compression_kn == pytest.approx(225)
    assert single_axis.pile_reactions["p4"].compression_kn == pytest.approx(225)


def test_uplift_is_reported_separately_from_compression() -> None:
    result = analyze_rigid_pile_group(model_with(PileGroupActions(n_kn=-400)))
    for reaction in result.pile_reactions.values():
        assert reaction.compression_kn == 0
        assert reaction.uplift_kn == pytest.approx(100)
        assert reaction.uplift_utilization == pytest.approx(0.5)
    uplift_check = next(
        check for check in result.group_capacity_checks if check.name == "单桩最大抗拔"
    )
    assert uplift_check.demand == pytest.approx(100)
    assert uplift_check.passed
    assert result.balance.n_kn == pytest.approx(-400)


def test_horizontal_force_and_torsion_are_distributed_with_exact_balance() -> None:
    actions = PileGroupActions(
        n_kn=600,
        vx_kn=40,
        vy_kn=20,
        torsion_kn_m=30,
    )
    result = analyze_rigid_pile_group(model_with(actions))
    # Direct shear is 10/5 kN per pile. Torsion adds tangential force with
    # factor T/sum(r^2)=30000/[4(800^2+800^2)].
    torsion_factor = 30_000 / (4 * (800**2 + 800**2))
    p1 = result.pile_reactions["p1"]
    assert p1.horizontal_x_kn == pytest.approx(10 + torsion_factor * 800)
    assert p1.horizontal_y_kn == pytest.approx(5 - torsion_factor * 800)
    assert p1.horizontal_resultant_kn == pytest.approx(
        hypot(p1.horizontal_x_kn, p1.horizontal_y_kn)
    )
    assert result.balance.vx_kn == pytest.approx(actions.vx_kn)
    assert result.balance.vy_kn == pytest.approx(actions.vy_kn)
    assert result.balance.torsion_kn_m == pytest.approx(actions.torsion_kn_m)
    assert result.balance.maximum_absolute_residual == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize(
    ("actions", "check_name", "factor", "expected_passed"),
    [
        (PileGroupActions(n_kn=4 * 500 * 0.99), "单桩最大受压", 0.99, True),
        (PileGroupActions(n_kn=4 * 500 * 1.01), "单桩最大受压", 1.01, False),
        (PileGroupActions(n_kn=-4 * 200 * 0.99), "单桩最大抗拔", 0.99, True),
        (PileGroupActions(n_kn=-4 * 200 * 1.01), "单桩最大抗拔", 1.01, False),
        (PileGroupActions(n_kn=0, vx_kn=4 * 100 * 0.99), "单桩最大水平力", 0.99, True),
        (PileGroupActions(n_kn=0, vx_kn=4 * 100 * 1.01), "单桩最大水平力", 1.01, False),
    ],
)
def test_capacity_thresholds_flip_at_099_and_101(
    actions: PileGroupActions,
    check_name: str,
    factor: float,
    expected_passed: bool,
) -> None:
    result = analyze_rigid_pile_group(model_with(actions))
    check = next(item for item in result.group_capacity_checks if item.name == check_name)
    assert check.utilization == pytest.approx(factor)
    assert check.passed is expected_passed
    assert all(
        reaction.screening_passed is expected_passed
        for reaction in result.pile_reactions.values()
    )


def test_cap_punching_shear_bending_and_minimum_rebar_match_independent_math() -> None:
    result = analyze_rigid_pile_group(model_with(PileGroupActions(n_kn=1_000)))
    checks = {check.name: check for check in result.cap_checks}
    effective_depth = 500 - 70 - 20 / 2
    perimeter = 2 * (500 + 500 + 2 * effective_depth)
    punching_capacity = 0.7 * 1.43 * perimeter * effective_depth / 1_000
    shear_capacity = 0.7 * 1.43 * 3_000 * effective_depth / 1_000
    # Each side contains two piles of 250 kN beyond the d-section.
    bending_demand = 2 * 250 * (800 - 500 / 2) / 1_000
    provided_total = 2_500 * 3_000 / 1_000
    bending_capacity = provided_total * 360 * 0.9 * effective_depth / 1_000_000
    minimum_total = 0.0015 * 3_000 * effective_depth

    assert result.effective_depth_mm == pytest.approx(effective_depth)
    assert checks["承台柱边冲切"].demand == pytest.approx(1_000)
    assert checks["承台柱边冲切"].capacity == pytest.approx(punching_capacity)
    assert checks["承台X向单向剪切"].demand == pytest.approx(500)
    assert checks["承台Y向单向剪切"].demand == pytest.approx(500)
    assert checks["承台X向单向剪切"].capacity == pytest.approx(shear_capacity)
    assert checks["承台Y向单向剪切"].capacity == pytest.approx(shear_capacity)
    assert checks["承台X向弯曲"].demand == pytest.approx(bending_demand)
    assert checks["承台Y向弯曲"].demand == pytest.approx(bending_demand)
    assert checks["承台X向弯曲"].capacity == pytest.approx(bending_capacity)
    assert checks["承台Y向弯曲"].capacity == pytest.approx(bending_capacity)
    assert checks["承台X向最小配筋"].demand == pytest.approx(minimum_total)
    assert checks["承台X向最小配筋"].capacity == pytest.approx(provided_total)


def test_insufficient_reinforcement_is_a_hard_screening_failure() -> None:
    material = replace(
        model_with(PileGroupActions(0)).material,
        provided_rebar_x_mm2_per_m=100,
    )
    result = analyze_rigid_pile_group(
        model_with(PileGroupActions(n_kn=600), material=material)
    )
    minimum = next(
        check for check in result.cap_checks if check.name == "承台X向最小配筋"
    )
    assert not minimum.passed
    assert not result.screening_passed


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (
            model_with(
                PileGroupActions(100),
                piles=(
                    PileDefinition("p1", -800, 0, 400, "bored"),
                    PileDefinition("p2", 0, 0, 400, "bored"),
                    PileDefinition("p3", 800, 0, 400, "bored"),
                ),
            ),
            "invalid_pile_layout",
        ),
        (
            model_with(
                PileGroupActions(100),
                piles=(
                    PileDefinition("p1", -800, -800, 400, "bored"),
                    PileDefinition("p2", -650, -800, 400, "bored"),
                    PileDefinition("p3", 800, 800, 400, "bored"),
                    PileDefinition("p4", -800, 800, 400, "bored"),
                ),
            ),
            "overlapping_piles",
        ),
        (
            model_with(
                PileGroupActions(100),
                piles=(
                    PileDefinition("p1", -1_400, -800, 400, "bored"),
                    *square_piles()[1:],
                ),
            ),
            "pile_outside_cap",
        ),
        (
            model_with(
                PileGroupActions(100),
                capacities=InvestigatedPileCapacities(500, 200, 100, ""),
            ),
            "missing_capacity_source",
        ),
    ],
)
def test_illegal_layouts_and_missing_investigation_source_are_rejected(
    model: PileGroupModel, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        analyze_rigid_pile_group(model)
    assert caught.value.code == code


def test_jgj94_single_pile_capacity_calculation() -> None:
    layers = (
        SoilLayerJGJ94("Clay", thickness_m=5.0, q_sik_kpa=40.0),
        SoilLayerJGJ94("Sand", thickness_m=10.0, q_sik_kpa=60.0),
    )
    res = calculate_single_pile_capacity_jgj94(
        pile_type="bored",
        diameter_or_side_m=0.8,
        soil_layers=layers,
        q_pk_kpa=2000.0,
    )
    u = 0.8 * 3.141592653589793
    ap = 3.141592653589793 * 0.4**2
    expected_qs = (40.0 * 5.0 + 60.0 * 10.0) * u
    expected_qp = 2000.0 * ap
    assert res.q_sk_kn == pytest.approx(expected_qs)
    assert res.q_pk_kn == pytest.approx(expected_qp)
    assert res.q_uk_kn == pytest.approx(expected_qs + expected_qp)
    assert res.q_ra_kn == pytest.approx((expected_qs + expected_qp) / 2.0)

