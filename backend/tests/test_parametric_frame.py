from __future__ import annotations

from math import isclose

import pytest

from app.core.errors import CalculationInputError
from app.core.parametric_frame import (
    FrameMember,
    FrameNode,
    NodalLoad,
    NodeRestraint,
    ParametricFrameModel,
    UniformMemberLoad,
    solve_parametric_frame,
)


E = 200_000.0
A = 4_000.0
I = 80_000_000.0


def member(member_id: str, start: str, end: str) -> FrameMember:
    return FrameMember(member_id, start, end, A, I, E)


def test_cantilever_tip_load_matches_closed_form() -> None:
    length = 3_000.0
    force = -10_000.0
    result = solve_parametric_frame(
        ParametricFrameModel(
            nodes=(FrameNode("fixed", 0, 0), FrameNode("tip", length, 0)),
            members=(member("beam", "fixed", "tip"),),
            restraints=(NodeRestraint("fixed", ux=True, uy=True, rz=True),),
            nodal_loads=(NodalLoad("tip", fy=force),),
        ),
        samples_per_member=201,
    )
    expected_deflection = force * length**3 / (3 * E * I)
    expected_rotation = force * length**2 / (2 * E * I)
    assert result.displacements["tip"].uy_mm == pytest.approx(expected_deflection, rel=1e-10)
    assert result.displacements["tip"].rz_rad == pytest.approx(expected_rotation, rel=1e-10)
    assert result.reactions["fixed"].fy_n == pytest.approx(-force)
    assert result.reactions["fixed"].mz_nmm == pytest.approx(-force * length)
    assert result.members["beam"].extrema.moment_abs_max_nmm == pytest.approx(abs(force * length))


def test_simply_supported_uniform_load_matches_closed_form_and_balance() -> None:
    length = 6_000.0
    q = -2.0
    result = solve_parametric_frame(
        ParametricFrameModel(
            nodes=(FrameNode("a", 0, 0), FrameNode("b", length, 0)),
            members=(member("beam", "a", "b"),),
            restraints=(
                NodeRestraint("a", ux=True, uy=True),
                NodeRestraint("b", uy=True),
            ),
            uniform_loads=(UniformMemberLoad("beam", q),),
        ),
        samples_per_member=401,
    )
    expected_reaction = -q * length / 2
    expected_moment = abs(q) * length**2 / 8
    expected_deflection = 5 * q * length**4 / (384 * E * I)
    assert result.reactions["a"].fy_n == pytest.approx(expected_reaction, rel=1e-10)
    assert result.reactions["b"].fy_n == pytest.approx(expected_reaction, rel=1e-10)
    assert result.members["beam"].extrema.moment_abs_max_nmm == pytest.approx(expected_moment, rel=1e-8)
    assert result.members["beam"].extrema.moment_abs_max_at_mm == pytest.approx(length / 2)
    mid = result.members["beam"].samples[200]
    assert mid.local_transverse_displacement_mm == pytest.approx(expected_deflection, rel=1e-8)
    assert result.members["beam"].extrema.local_transverse_abs_max_at_mm == pytest.approx(length / 2)
    assert sum(item.fy_n for item in result.reactions.values()) + q * length == pytest.approx(0.0, abs=1e-8)
    assert result.reactions["a"].components_6dof == {
        "Fx": 0.0,
        "Fy": pytest.approx(expected_reaction),
        "Fz": 0.0,
        "Mx": 0.0,
        "My": 0.0,
        "Mz": 0.0,
    }


@pytest.mark.parametrize(
    ("nodes", "members", "restraints", "load_node"),
    [
        (
            (("l0", 0, 0), ("r0", 6_000, 0), ("lt", 0, 3_000), ("rt", 6_000, 4_000)),
            (("lc", "l0", "lt"), ("roof", "lt", "rt"), ("rc", "r0", "rt")),
            (("l0", True, True, True), ("r0", True, True, True)),
            "rt",
        ),
        (
            (("l0", 0, 0), ("r0", 6_000, 0), ("lt", 0, 3_000), ("ridge", 3_000, 4_000), ("rt", 6_000, 3_000)),
            (("lc", "l0", "lt"), ("rl", "lt", "ridge"), ("rr", "ridge", "rt"), ("rc", "r0", "rt")),
            (("l0", True, True, True), ("r0", True, True, True)),
            "ridge",
        ),
        (
            (("b0", 0, 0), ("b1", 4_000, 0), ("b2", 8_000, 0), ("t0", 0, 3_000), ("t1", 4_000, 3_000), ("t2", 8_000, 3_000)),
            (("c0", "b0", "t0"), ("c1", "b1", "t1"), ("c2", "b2", "t2"), ("r0", "t0", "t1"), ("r1", "t1", "t2")),
            (("b0", True, True, True), ("b1", True, True, True), ("b2", True, True, True)),
            "t1",
        ),
        (
            (("l0", 0, 0), ("r0", 5_000, 0), ("lt", 0, 2_500), ("rt", 5_000, 4_000)),
            (("lc", "l0", "lt"), ("roof", "lt", "rt"), ("rc", "r0", "rt")),
            (("l0", True, True, True), ("r0", True, True, True)),
            "lt",
        ),
        (
            (("fixed", 0, 0), ("tip", 3_000, 500)),
            (("cantilever", "fixed", "tip"),),
            (("fixed", True, True, True),),
            "tip",
        ),
    ],
    ids=["mono-pitch", "dual-pitch-ridge", "multi-bay", "unequal-columns", "cantilever"],
)
def test_parameterized_geometries_solve_and_balance(
    nodes: tuple[tuple[str, float, float], ...],
    members: tuple[tuple[str, str, str], ...],
    restraints: tuple[tuple[str, bool, bool, bool], ...],
    load_node: str,
) -> None:
    fx, fy = 2_500.0, -7_500.0
    model = ParametricFrameModel(
        nodes=tuple(FrameNode(*item) for item in nodes),
        members=tuple(member(*item) for item in members),
        restraints=tuple(NodeRestraint(*item) for item in restraints),
        nodal_loads=(NodalLoad(load_node, fx=fx, fy=fy),),
    )
    result = solve_parametric_frame(model)
    assert all(isclose(value.ux_mm, value.ux_mm) for value in result.displacements.values())
    assert sum(item.fx_n for item in result.reactions.values()) + fx == pytest.approx(0.0, abs=1e-6)
    assert sum(item.fy_n for item in result.reactions.values()) + fy == pytest.approx(0.0, abs=1e-6)
    coordinate_by_id = {node_id: (x, y) for node_id, x, y in nodes}
    support_moment = sum(
        reaction.mz_nmm
        + coordinate_by_id[node_id][0] * reaction.fy_n
        - coordinate_by_id[node_id][1] * reaction.fx_n
        for node_id, reaction in result.reactions.items()
    )
    load_x, load_y = coordinate_by_id[load_node]
    assert support_moment + load_x * fy - load_y * fx == pytest.approx(0.0, abs=1e-5)
    for response in result.members.values():
        assert response.length_mm > 0
        assert len(response.local_end_forces) == 6
        assert len(response.samples) == 101


def test_common_engineering_units_are_converted() -> None:
    result = solve_parametric_frame(
        ParametricFrameModel(
            nodes=(FrameNode("a", 0, 0, "m"), FrameNode("b", 3, 0, "m")),
            members=(
                FrameMember(
                    "beam", "a", "b", 0.004, 8e-5, 200, "m2", "m4", "GPa"
                ),
            ),
            restraints=(NodeRestraint("a", ux=True, uy=True, rz=True),),
            nodal_loads=(NodalLoad("b", fy=-10, force_unit="kN"),),
        )
    )
    assert result.displacements["b"].uy_mm == pytest.approx(-5.625)


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (
            ParametricFrameModel(
                nodes=(FrameNode("a", 0, 0), FrameNode("b", 0, 0)),
                members=(member("m", "a", "b"),),
                restraints=(NodeRestraint("a", ux=True, uy=True, rz=True),),
            ),
            "zero_length_member",
        ),
        (
            ParametricFrameModel(
                nodes=(FrameNode("a", 0, 0, "cm"), FrameNode("b", 1, 0)),
                members=(member("m", "a", "b"),),
                restraints=(NodeRestraint("a", ux=True, uy=True, rz=True),),
            ),
            "invalid_unit",
        ),
        (
            ParametricFrameModel(
                nodes=(FrameNode("a", 0, 0), FrameNode("b", 1_000, 0)),
                members=(member("m", "a", "b"),),
                nodal_loads=(NodalLoad("b", fy=-1_000),),
            ),
            "singular_stiffness_matrix",
        ),
        (
            ParametricFrameModel(
                nodes=(FrameNode("a", 0, 0), FrameNode("b", 1_000, 0)),
                members=(member("m", "a", "b"),),
                restraints=(NodeRestraint("a", uy=True), NodeRestraint("b", uy=True)),
            ),
            "singular_stiffness_matrix",
        ),
    ],
)
def test_invalid_models_return_structured_errors(
    model: ParametricFrameModel, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        solve_parametric_frame(model)
    assert caught.value.code == code
    assert caught.value.as_dict()["code"] == code
