from __future__ import annotations

from math import hypot

import pytest

from app.core.errors import CalculationInputError
from app.core.structural_solvers import (
    ContinuousBeamModel,
    ContinuousBeamNode,
    ContinuousBeamSpan,
    ContinuousBeamSupport,
    RectangularRCTwoWaySlabInput,
    TrussMember,
    TrussModel,
    TrussNodalLoad,
    TrussNode,
    TrussRestraint,
    analyze_rectangular_rc_two_way_slab,
    solve_continuous_beam,
    solve_planar_truss,
)


E_STEEL = 200_000.0
I_BEAM = 80_000_000.0


def test_simply_supported_continuous_beam_matches_closed_form() -> None:
    length = 6_000.0
    q = -2.0
    result = solve_continuous_beam(
        ContinuousBeamModel(
            nodes=(ContinuousBeamNode("a"), ContinuousBeamNode("b")),
            spans=(
                ContinuousBeamSpan(
                    "span", "a", "b", length, E_STEEL, I_BEAM, q
                ),
            ),
            supports=(ContinuousBeamSupport("a"), ContinuousBeamSupport("b")),
        ),
        samples_per_span=41,
    )
    response = result.spans["span"]
    expected_reaction = -q * length / 2.0
    expected_moment = abs(q) * length**2 / 8.0
    expected_deflection = 5.0 * q * length**4 / (384.0 * E_STEEL * I_BEAM)

    assert result.reactions["a"].vertical_n == pytest.approx(expected_reaction)
    assert result.reactions["b"].vertical_n == pytest.approx(expected_reaction)
    assert response.extrema.moment_max_nmm.value == pytest.approx(expected_moment)
    assert response.extrema.moment_max_nmm.x_mm == pytest.approx(length / 2.0)
    assert response.extrema.deflection_min_mm.value == pytest.approx(
        expected_deflection, rel=1e-10
    )
    assert response.extrema.deflection_min_mm.x_mm == pytest.approx(length / 2.0)
    assert len(response.samples) == 41
    assert sum(item.vertical_n for item in result.reactions.values()) + q * length == pytest.approx(0.0)


def test_two_equal_spans_match_classical_support_moment_and_reactions() -> None:
    length = 4_000.0
    q = -3.0
    result = solve_continuous_beam(
        ContinuousBeamModel(
            nodes=tuple(ContinuousBeamNode(name) for name in ("a", "b", "c")),
            spans=(
                ContinuousBeamSpan("left", "a", "b", length, E_STEEL, I_BEAM, q),
                ContinuousBeamSpan("right", "b", "c", length, E_STEEL, I_BEAM, q),
            ),
            supports=tuple(ContinuousBeamSupport(name) for name in ("a", "b", "c")),
        )
    )
    load = abs(q)
    assert result.reactions["a"].vertical_n == pytest.approx(3 * load * length / 8)
    assert result.reactions["b"].vertical_n == pytest.approx(5 * load * length / 4)
    assert result.reactions["c"].vertical_n == pytest.approx(3 * load * length / 8)
    # Internal support section moment is hogging and is continuous from both spans.
    left_support_moment = result.spans["left"].samples[-1].moment_nmm
    right_support_moment = result.spans["right"].samples[0].moment_nmm
    assert left_support_moment == pytest.approx(-load * length**2 / 8)
    assert right_support_moment == pytest.approx(left_support_moment)
    assert sum(item.vertical_n for item in result.reactions.values()) == pytest.approx(
        2 * load * length
    )


def test_fixed_fixed_beam_reports_end_forces_and_between_node_extrema() -> None:
    length = 5_000.0
    q = -2.4
    result = solve_continuous_beam(
        ContinuousBeamModel(
            nodes=(ContinuousBeamNode("a"), ContinuousBeamNode("b")),
            spans=(
                ContinuousBeamSpan("span", "a", "b", length, E_STEEL, I_BEAM, q),
            ),
            supports=(
                ContinuousBeamSupport("a", rotation=True),
                ContinuousBeamSupport("b", rotation=True),
            ),
        )
    )
    response = result.spans["span"]
    load = abs(q)
    expected_reaction = load * length / 2.0
    expected_hogging = -load * length**2 / 12.0
    expected_sagging = load * length**2 / 24.0
    assert response.start_shear_n == pytest.approx(expected_reaction)
    assert response.end_shear_n == pytest.approx(expected_reaction)
    assert response.samples[0].moment_nmm == pytest.approx(expected_hogging)
    assert response.samples[-1].moment_nmm == pytest.approx(expected_hogging)
    assert response.extrema.moment_max_nmm.value == pytest.approx(expected_sagging)
    assert response.extrema.moment_max_nmm.x_mm == pytest.approx(length / 2.0)
    assert result.reactions["a"].moment_nmm == pytest.approx(load * length**2 / 12.0)
    assert result.reactions["b"].moment_nmm == pytest.approx(-load * length**2 / 12.0)


def test_continuous_beam_accepts_unequal_spans_and_rigidities() -> None:
    q_left, q_right = -1.5, -2.25
    result = solve_continuous_beam(
        ContinuousBeamModel(
            nodes=tuple(ContinuousBeamNode(name) for name in ("a", "b", "c")),
            spans=(
                ContinuousBeamSpan("left", "a", "b", 3_500, E_STEEL, 55e6, q_left),
                ContinuousBeamSpan("right", "b", "c", 5_250, 190_000, 125e6, q_right),
            ),
            supports=tuple(ContinuousBeamSupport(name) for name in ("a", "b", "c")),
        )
    )
    left_at_support = result.spans["left"].samples[-1].moment_nmm
    right_at_support = result.spans["right"].samples[0].moment_nmm
    assert left_at_support == pytest.approx(right_at_support, abs=1e-6)
    assert sum(item.vertical_n for item in result.reactions.values()) + (
        q_left * 3_500 + q_right * 5_250
    ) == pytest.approx(0.0, abs=1e-7)
    assert result.spans["left"].extrema.deflection_abs_max_mm > 0
    assert result.spans["right"].extrema.deflection_abs_max_mm > 0


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (
            ContinuousBeamModel(
                nodes=(ContinuousBeamNode("a"), ContinuousBeamNode("b")),
                spans=(ContinuousBeamSpan("s", "a", "b", 1_000, E_STEEL, I_BEAM),),
            ),
            "singular_stiffness_matrix",
        ),
        (
            ContinuousBeamModel(
                nodes=tuple(ContinuousBeamNode(name) for name in ("a", "b", "c", "d")),
                spans=(
                    ContinuousBeamSpan("ab", "a", "b", 1_000, E_STEEL, I_BEAM),
                    ContinuousBeamSpan("bc", "b", "c", 1_000, E_STEEL, I_BEAM),
                    ContinuousBeamSpan("bd", "b", "d", 1_000, E_STEEL, I_BEAM),
                ),
                supports=(ContinuousBeamSupport("a"), ContinuousBeamSupport("c")),
            ),
            "invalid_beam_topology",
        ),
    ],
)
def test_invalid_continuous_beams_raise_structured_errors(
    model: ContinuousBeamModel, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        solve_continuous_beam(model)
    assert caught.value.code == code


def test_single_truss_bar_matches_axial_closed_form() -> None:
    length = 2_000.0
    area = 500.0
    force = 10_000.0
    result = solve_planar_truss(
        TrussModel(
            nodes=(TrussNode("a", 0, 0), TrussNode("b", length, 0)),
            members=(TrussMember("bar", "a", "b", area, E_STEEL),),
            restraints=(
                TrussRestraint("a", ux=True, uy=True),
                TrussRestraint("b", uy=True),
            ),
            nodal_loads=(TrussNodalLoad("b", fx_n=force),),
        )
    )
    expected_extension = force * length / (E_STEEL * area)
    assert result.displacements["b"].ux_mm == pytest.approx(expected_extension)
    assert result.members["bar"].axial_force_n == pytest.approx(force)
    assert result.members["bar"].stress_mpa == pytest.approx(force / area)
    assert result.reactions["a"].fx_n == pytest.approx(-force)
    assert result.reactions["b"].fy_n == pytest.approx(0.0)


def test_symmetric_triangle_truss_forces_and_global_balance() -> None:
    half_width, height = 2_000.0, 3_000.0
    length = hypot(half_width, height)
    load = 24_000.0
    area = 800.0
    result = solve_planar_truss(
        TrussModel(
            nodes=(
                TrussNode("a", -half_width, 0),
                TrussNode("b", half_width, 0),
                TrussNode("c", 0, height),
            ),
            members=(
                TrussMember("left", "a", "c", area, E_STEEL),
                TrussMember("right", "b", "c", area, E_STEEL),
                TrussMember("tie", "a", "b", area, E_STEEL),
            ),
            restraints=(
                TrussRestraint("a", ux=True, uy=True),
                TrussRestraint("b", uy=True),
            ),
            nodal_loads=(TrussNodalLoad("c", fy_n=-load),),
        )
    )
    expected_diagonal = -load * length / (2.0 * height)
    expected_tie = load * half_width / (2.0 * height)
    assert result.members["left"].axial_force_n == pytest.approx(expected_diagonal)
    assert result.members["right"].axial_force_n == pytest.approx(expected_diagonal)
    assert result.members["tie"].axial_force_n == pytest.approx(expected_tie)
    assert result.reactions["a"].fy_n == pytest.approx(load / 2.0)
    assert result.reactions["b"].fy_n == pytest.approx(load / 2.0)
    assert sum(item.fx_n for item in result.reactions.values()) == pytest.approx(0.0, abs=1e-8)
    assert sum(item.fy_n for item in result.reactions.values()) - load == pytest.approx(0.0, abs=1e-8)
    # A pin-roller support pair permits horizontal strain of the tie, so the
    # apex need not remain at x=0 in the deformed configuration.
    assert result.displacements["c"].uy_mm < 0


def test_unstable_truss_is_rejected() -> None:
    model = TrussModel(
        nodes=(TrussNode("a", 0, 0), TrussNode("b", 1_000, 0)),
        members=(TrussMember("bar", "a", "b", 100, E_STEEL),),
        restraints=(TrussRestraint("a", ux=True, uy=True),),
        nodal_loads=(TrussNodalLoad("b", fx_n=1_000),),
    )
    with pytest.raises(CalculationInputError) as caught:
        solve_planar_truss(model)
    assert caught.value.code == "singular_stiffness_matrix"


def test_square_simply_supported_slab_is_symmetric() -> None:
    result = analyze_rectangular_rc_two_way_slab(
        RectangularRCTwoWaySlabInput(
            short_span_m=4.0,
            long_span_m=4.0,
            thickness_mm=120,
            elastic_modulus_mpa=30_000,
            uniform_load_kpa=5.0,
            support_condition="four_edges_simply_supported",
        )
    )
    assert result.positive_moment_short_knm_per_m == pytest.approx(
        result.positive_moment_long_knm_per_m
    )
    assert result.directional_moment_share_short == pytest.approx(0.5)
    assert result.directional_moment_share_long == pytest.approx(0.5)
    assert result.negative_moment_short_knm_per_m == 0
    assert result.negative_moment_long_knm_per_m == 0
    assert result.maximum_deflection_mm > 0
    assert result.method == "one_term_rayleigh_ritz_elastic_coefficient"
    assert result.verification_status == "analytical_elastic_only"
    assert any("不计算钢筋" in exclusion for exclusion in result.exclusions)


def test_fixed_slab_has_hogging_and_lower_elastic_deflection() -> None:
    common = dict(
        short_span_m=4.0,
        long_span_m=5.0,
        thickness_mm=140,
        elastic_modulus_mpa=31_500,
        uniform_load_kpa=6.5,
    )
    simply_supported = analyze_rectangular_rc_two_way_slab(
        RectangularRCTwoWaySlabInput(
            **common, support_condition="four_edges_simply_supported"
        )
    )
    fixed = analyze_rectangular_rc_two_way_slab(
        RectangularRCTwoWaySlabInput(**common, support_condition="four_edges_fixed")
    )
    assert fixed.maximum_deflection_mm < simply_supported.maximum_deflection_mm
    assert fixed.negative_moment_short_knm_per_m < 0
    assert fixed.negative_moment_long_knm_per_m < 0
    assert fixed.positive_moment_short_knm_per_m > 0
    assert fixed.positive_moment_long_knm_per_m > 0
    assert fixed.directional_moment_share_short + fixed.directional_moment_share_long == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"long_span_m": 8.1}, "outside_two_way_scope"),
        ({"long_span_m": 3.5}, "invalid_span_order"),
        ({"thickness_mm": 20}, "outside_thin_plate_scope"),
        ({"poisson_ratio": 0.5}, "invalid_poisson_ratio"),
        ({"uniform_load_kpa": -1}, "invalid_load"),
        ({"support_condition": "mixed_edges"}, "unsupported_edge_condition"),
    ],
)
def test_two_way_slab_rejects_inputs_outside_method_scope(
    changes: dict[str, float | str], code: str
) -> None:
    values: dict[str, float | str] = {
        "short_span_m": 4.0,
        "long_span_m": 6.0,
        "thickness_mm": 120,
        "elastic_modulus_mpa": 30_000,
        "uniform_load_kpa": 5.0,
        "support_condition": "four_edges_simply_supported",
        "poisson_ratio": 0.2,
    }
    values.update(changes)
    with pytest.raises(CalculationInputError) as caught:
        analyze_rectangular_rc_two_way_slab(  # type: ignore[arg-type]
            RectangularRCTwoWaySlabInput(**values)  # type: ignore[arg-type]
        )
    assert caught.value.code == code
