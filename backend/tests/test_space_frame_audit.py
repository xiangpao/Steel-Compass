from dataclasses import replace
from math import sqrt, tanh

import pytest

from app.core.space_frame import (
    SpaceFrameModel, SpaceMember, SpaceMemberUniformLoad, SpaceNodalLoad,
    SpaceNode, SpaceRestraint, analyze_space_frame, analyze_space_frame_stability,
)


def cantilever(**member_options):
    return SpaceFrameModel(
        (SpaceNode("A", 0, 0, 0), SpaceNode("B", 3, 0, 0)),
        (SpaceMember("m", "A", "B", 10000, 1e8, 1e8, 1e7, **member_options),),
        (SpaceRestraint("A", True, True, True, True, True, True),),
        (SpaceNodalLoad("B", fy_kn=-10),),
    )


@pytest.mark.parametrize("start,end", [(0.5, 0), (0, 0.5), (0.3, 0.4)])
def test_rigid_offsets_preserve_joint_moment_and_flexible_deflection(start, end):
    result = analyze_space_frame(cantilever(rigid_offset_start_m=start, rigid_offset_end_m=end))
    # Unit-load integration on flexible interval [a,L-b]: int P(L-x)^2/EI dx.
    expected = -10000 * ((3000-start*1000)**3-(end*1000)**3) / (3*206000*1e8)
    assert result.reactions["A"].mz_kn_m == pytest.approx(30)
    assert result.displacements["B"].uy_mm == pytest.approx(expected)


def test_uniform_load_on_full_member_includes_rigid_zones():
    model = replace(cantilever(rigid_offset_start_m=0.3, rigid_offset_end_m=0.4),
                    nodal_loads=(), member_uniform_loads=(SpaceMemberUniformLoad("m", qy_kn_m=-10),))
    result = analyze_space_frame(model)
    assert result.reactions["A"].fy_kn == pytest.approx(30)
    assert result.reactions["A"].mz_kn_m == pytest.approx(45)


def test_second_order_is_invariant_under_rotation_for_equal_inertias():
    model = cantilever()
    y = analyze_space_frame_stability(replace(model, nodal_loads=(SpaceNodalLoad("B", fx_kn=-1000, fy_kn=10),)))
    z = analyze_space_frame_stability(replace(model, nodal_loads=(SpaceNodalLoad("B", fx_kn=-1000, fz_kn=10),)))
    assert y.second_order.displacements["B"].uy_mm == pytest.approx(z.second_order.displacements["B"].uz_mm)
    assert y.buckling_factors[0] == pytest.approx(y.buckling_factors[1])


def test_axial_tension_increases_lateral_stiffness():
    model = replace(cantilever(),nodal_loads=(SpaceNodalLoad("B",fx_kn=1000,fy_kn=10),))
    result = analyze_space_frame_stability(model)
    assert abs(result.second_order.displacements["B"].uy_mm) < abs(analyze_space_frame(model).displacements["B"].uy_mm)


def test_released_member_stability_cannot_false_pass_near_critical_load():
    from app.core.errors import CalculationInputError
    model = replace(cantilever(end_releases=(False,False,False,False,True,True)),
                    nodal_loads=(SpaceNodalLoad("B",fx_kn=-5700,fy_kn=10),))
    with pytest.raises(CalculationInputError) as error:
        analyze_space_frame_stability(model)
    assert error.value.code == "released_member_stability_unavailable"


@pytest.mark.parametrize("elements,reference", [(1,12.000),(2,9.944),(3,9.885),(4,9.875),(5,9.872),(6,9.871)])
def test_tekla_published_euler_buckling_convergence(elements, reference):
    # Tekla 2026, ref_2ndorderbucklingeulerstrutbuckling: L=10m, EI=100Nm2, P=1N.
    model = SpaceFrameModel(
        tuple(SpaceNode(str(i), i*10/elements, 0, 0) for i in range(elements+1)),
        tuple(SpaceMember(str(i), str(i), str(i+1), 1000, 1e5, 1e5, 1e5,
                          elastic_modulus_mpa=1000, shear_modulus_mpa=400) for i in range(elements)),
        (SpaceRestraint("0", ux=True, uy=True, uz=True, rx=True), SpaceRestraint(str(elements), uy=True, uz=True)),
        (SpaceNodalLoad(str(elements), fx_kn=-0.001),),
    )
    assert analyze_space_frame_stability(model).buckling_factors[0] == pytest.approx(reference, abs=0.0006)


def test_tekla_published_second_order_cantilever():
    # Tekla 2026, ref_2ndorderlinearsimplecantilever, one finite element, no shear deformation.
    model = SpaceFrameModel(
        (SpaceNode("A",0,0,0), SpaceNode("B",10,0,0)),
        (SpaceMember("m","A","B",10000,2.5e11/206000,2.5e11/206000,1e7),),
        (SpaceRestraint("A",True,True,True,True,True,True),),
        (SpaceNodalLoad("B",fx_kn=-4,fy_kn=-0.045),),
    )
    result = analyze_space_frame_stability(model).second_order
    assert result.displacements["B"].uy_mm == pytest.approx(-167.7, abs=0.05)
    assert result.reactions["A"].mz_kn_m == pytest.approx(1.121, abs=0.0005)
    # End actions must use the same second-order equilibrium as support reactions.
    assert result.members["m"].local_end_forces[5] / 1e6 == pytest.approx(1.121, abs=0.0005)
    assert result.members["m"].local_end_forces[11] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("axis", ["y", "z"])
@pytest.mark.parametrize("offsets", [(0.0, 0.0), (0.3, 0.4)])
@pytest.mark.parametrize("uniform", [False, True])
@pytest.mark.parametrize("axial_kn", [-1000.0, 1000.0])
def test_second_order_member_end_actions_match_joint_equilibrium(axis, offsets, uniform, axial_kn):
    tip_load = SpaceNodalLoad("B", fx_kn=axial_kn, **{f"f{axis}_kn": -10.0})
    model = replace(
        cantilever(rigid_offset_start_m=offsets[0], rigid_offset_end_m=offsets[1]),
        nodal_loads=(tip_load,),
        member_uniform_loads=(SpaceMemberUniformLoad("m", **{f"q{axis}_kn_m": -2.0}),) if uniform else (),
    )
    result = analyze_space_frame_stability(model).second_order
    forces = result.members["m"].local_end_forces
    reaction = result.reactions["A"]
    # The member is aligned with global X: its local and global force axes match.
    expected_root = (
        reaction.fx_kn * 1000, reaction.fy_kn * 1000, reaction.fz_kn * 1000,
        reaction.mx_kn_m * 1e6, reaction.my_kn_m * 1e6, reaction.mz_kn_m * 1e6,
    )
    expected_tip = (axial_kn * 1000, -10000 if axis == "y" else 0,
                    -10000 if axis == "z" else 0, 0, 0, 0)
    assert forces[:6] == pytest.approx(expected_root, abs=1e-6)
    assert forces[6:] == pytest.approx(expected_tip, abs=1e-6)
    assert result.load_balance_kn == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


@pytest.mark.parametrize("elements", [10, 20])
def test_dlubal_0042_axial_tension_cantilever_against_independent_closed_form(elements):
    # Dlubal Verification 0042 (2015), RSTAB 8.05.0030, no shear deformation.
    # https://www.dlubal.com/en/downloads-and-information/examples-and-tutorials/verification-examples/000042
    # Its RSTAB table is 3266.163 mm; the printed analytical 3266.136 mm differs
    # from the source's own formula (42-16). Do not copy a production result.
    elastic_modulus = 210000.0
    inertia = 80.0**4 / 12
    alpha = sqrt(1600 / (elastic_modulus * inertia))
    reference = 7650 / 1600 * (10000 - tanh(alpha * 10000) / alpha)
    assert reference == pytest.approx(3266.163, abs=0.0005)
    model = SpaceFrameModel(
        tuple(SpaceNode(str(i), i * 10 / elements, 0, 0) for i in range(elements + 1)),
        tuple(SpaceMember(str(i), str(i), str(i + 1), 6400, inertia, inertia,
                          1e6, elastic_modulus_mpa=elastic_modulus) for i in range(elements)),
        (SpaceRestraint("0", True, True, True, True, True, True),),
        (SpaceNodalLoad(str(elements), fx_kn=1.6, fz_kn=7.65),),
    )
    result = analyze_space_frame_stability(model).second_order
    # 0.0005 mm is half the published three-decimal RSTAB rounding unit.
    assert result.displacements[str(elements)].uz_mm == pytest.approx(reference, abs=0.0005)
    assert result.displacements[str(elements)].ux_mm == pytest.approx(1600 * 10000 / (elastic_modulus * 6400))
