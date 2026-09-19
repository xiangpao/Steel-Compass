from __future__ import annotations

import pytest

from app.core.errors import CalculationInputError
from app.core.space_frame import (
    SpaceFrameModel,
    SpaceMember,
    SpaceMemberUniformLoad,
    SpaceNodalLoad,
    SpaceNode,
    SpaceRestraint,
    analyze_space_frame,
    analyze_space_frame_stability,
)


def test_space_cantilever_axial_response_and_balance() -> None:
    model = SpaceFrameModel(
        nodes=(SpaceNode("A", 0, 0, 0), SpaceNode("B", 0, 0, 3)),
        members=(SpaceMember("C1", "A", "B", 4_000, 8e6, 8e6, 1e7),),
        restraints=(SpaceRestraint("A", True, True, True, True, True, True),),
        nodal_loads=(SpaceNodalLoad("B", fz_kn=-100),),
    )
    result = analyze_space_frame(model)
    expected_mm = -100_000 * 3_000 / (206_000 * 4_000)
    assert result.displacements["B"].uz_mm == pytest.approx(expected_mm)
    assert result.reactions["A"].fz_kn == pytest.approx(100)
    assert result.load_balance_kn == pytest.approx((0, 0, 0), abs=1e-9)


def test_space_frame_rejects_unstable_model() -> None:
    model = SpaceFrameModel(
        nodes=(SpaceNode("A", 0, 0, 0), SpaceNode("B", 1, 0, 0)),
        members=(SpaceMember("M1", "A", "B", 1_000, 1e6, 1e6, 1e6),),
        restraints=(SpaceRestraint("A", ux=True),),
    )
    with pytest.raises(CalculationInputError, match="不稳定"):
        analyze_space_frame(model)


def test_local_axis_rotation_changes_rectangular_member_stiffness() -> None:
    def cantilever(rotation: float) -> SpaceFrameModel:
        return SpaceFrameModel(
            nodes=(SpaceNode("A", 0, 0, 0), SpaceNode("B", 3, 0, 0)),
            members=(SpaceMember(
                "M1", "A", "B", 2_000, 1e6, 8e6, 1e6,
                local_axis_rotation_deg=rotation,
            ),),
            restraints=(SpaceRestraint("A", True, True, True, True, True, True),),
            nodal_loads=(SpaceNodalLoad("B", fz_kn=-10),),
        )

    strong = analyze_space_frame(cantilever(90))
    weak = analyze_space_frame(cantilever(0))
    assert abs(strong.displacements["B"].uz_mm) < abs(weak.displacements["B"].uz_mm)


def _compressed_cantilever(axial_kn: float) -> SpaceFrameModel:
    return SpaceFrameModel(
        nodes=(SpaceNode("A", 0, 0, 0), SpaceNode("B", 0, 0, 3)),
        members=(SpaceMember("C1", "A", "B", 4_000, 8e6, 8e6, 1e7),),
        restraints=(SpaceRestraint("A", True, True, True, True, True, True),),
        nodal_loads=(SpaceNodalLoad("B", fx_kn=5, fz_kn=-axial_kn),),
    )


def test_second_order_amplification_and_buckling_are_load_sensitive() -> None:
    low_model = _compressed_cantilever(10)
    high_model = _compressed_cantilever(100)
    low = analyze_space_frame_stability(low_model, analyze_space_frame(low_model))
    high = analyze_space_frame_stability(high_model, analyze_space_frame(high_model))
    assert high.amplification_ratio > low.amplification_ratio > 1.0
    assert high.buckling_factors[0] < low.buckling_factors[0]


def test_buckling_factor_below_one_blocks_analysis() -> None:
    # Euler reference pi^2*EI/(4L^2) = 451.8kN; 300kN is below buckling.
    model = _compressed_cantilever(600)
    with pytest.raises(CalculationInputError, match="弹性临界状态"):
        analyze_space_frame_stability(model, analyze_space_frame(model))


def test_uniform_member_load_preserves_simple_beam_reactions_and_zero_end_moments() -> None:
    model = SpaceFrameModel(
        nodes=(SpaceNode("A", 0, 0, 0), SpaceNode("B", 4, 0, 0)),
        members=(SpaceMember(
            "M1", "A", "B", 4_000, 8e6, 8e6, 1e7,
            start_releases=(False, False, False, False, True, False),
            end_releases=(False, False, False, False, True, False),
        ),),
        restraints=(
            SpaceRestraint("A", True, True, True, True, False, True),
            SpaceRestraint("B", False, True, True, False, False, False),
        ),
        member_uniform_loads=(SpaceMemberUniformLoad("M1", qz_kn_m=-10),),
    )
    result = analyze_space_frame(model)
    assert result.reactions["A"].fz_kn == pytest.approx(20)
    assert result.reactions["B"].fz_kn == pytest.approx(20)
    assert result.members["M1"].local_end_forces[4] / 1e6 == pytest.approx(0, abs=1e-9)
    assert result.members["M1"].local_end_forces[10] / 1e6 == pytest.approx(0, abs=1e-9)
    assert result.load_balance_kn == pytest.approx((0, 0, 0), abs=1e-9)
