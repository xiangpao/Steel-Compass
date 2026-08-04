from __future__ import annotations

import pytest

from verification.steel_beam_reference import solve_udl_beam


def test_skyciv_mechanics_normalized_to_cn_steel_modulus() -> None:
    result = solve_udl_beam(
        support="simple",
        line_load_kn_m=10,
        span_m=10,
        elastic_modulus_mpa=206_000,
        inertia_mm4=1_500_000_000,
    )
    assert result.reaction_left_kn == pytest.approx(50)
    assert result.maximum_moment_kn_m == pytest.approx(125)
    assert result.maximum_deflection_mm == pytest.approx(4.21386, rel=1e-5)


def test_cantilever_udl_closed_form_reference() -> None:
    result = solve_udl_beam(
        support="cantilever",
        line_load_kn_m=3,
        span_m=2,
        elastic_modulus_mpa=206_000,
        inertia_mm4=80_000_000,
    )
    assert result.reaction_left_kn == pytest.approx(6)
    assert result.maximum_moment_kn_m == pytest.approx(6)
    assert result.maximum_deflection_mm == pytest.approx(
        3 * 2000**4 / (8 * 206_000 * 80_000_000)
    )
