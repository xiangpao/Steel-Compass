"""Independent reviewer probes; no production matrix or developer ODE oracle.

Public self-weight benchmark: https://www.mdpi.com/2071-1050/15/7/6075
Eq. (29), equivalently q_critical L^3 / EI = 7.8373 (rounded source).
The model is an ideal straight elastic column, not a Chinese-code approval.
"""
from dataclasses import replace

import pytest

from app.core.errors import CalculationInputError
from app.core.space_frame import (
    SpaceFrameModel, SpaceMember, SpaceMemberUniformLoad, SpaceNodalLoad,
    SpaceNode, SpaceRestraint, analyze_space_frame_stability,
    analyze_space_frame_stability_converged,
)


def self_weight_column(ratio):
    e, i, length = 206000., 1e8, 3000.
    q = ratio * 7.8373 * e * i / length**3
    return SpaceFrameModel(
        (SpaceNode('a', 0, 0, 0), SpaceNode('b', 0, 0, 3)),
        (SpaceMember('m', 'a', 'b', 10000, i, i, 1e7),),
        (SpaceRestraint('a', True, True, True, True, True, True),),
        member_uniform_loads=(SpaceMemberUniformLoad('m', qz_kn_m=-q),),
    )


def test_greenhill_variable_axial_stress_matches_published_coefficient():
    result = analyze_space_frame_stability(self_weight_column(.2), member_subdivisions=16)
    # 2e-5 accommodates source coefficient rounding and 16-element discretization.
    assert result.buckling_factors[0] == pytest.approx(5., rel=2e-5)
    assert result.buckling_factors[1] == pytest.approx(5., rel=2e-5)
    assert result.second_order.load_balance_kn == pytest.approx((0, 0, 0), abs=1e-8)


def test_greenhill_supercritical_distributed_selfweight_rejected():
    with pytest.raises(CalculationInputError) as caught:
        analyze_space_frame_stability(self_weight_column(1.001), member_subdivisions=16)
    assert caught.value.code == 'elastic_buckling_instability'


@pytest.mark.parametrize('axial', [-1000., 1000.])
def test_joint_results_and_envelopes_invariant_to_member_endpoint_reversal(axial):
    member = SpaceMember('m', 'a', 'b', 10000, 1e8, 1e8, 1e7,
                         rigid_offset_start_m=.3, rigid_offset_end_m=.4)
    model = SpaceFrameModel(
        (SpaceNode('a', 0, 0, 0), SpaceNode('b', 3, 0, 0)), (member,),
        (SpaceRestraint('a', True, True, True, True, True, True),),
        (SpaceNodalLoad('b', fx_kn=axial, fy_kn=-10, fz_kn=3, my_kn_m=2),),
        (SpaceMemberUniformLoad('m', qx_kn_m=-3, qy_kn_m=-2, qz_kn_m=1),),
    )
    reverse = replace(model, members=(replace(member, start='b', end='a',
        rigid_offset_start_m=.4, rigid_offset_end_m=.3),))
    direct = analyze_space_frame_stability_converged(model)
    backward = analyze_space_frame_stability_converged(reverse)
    for key in ('ux_mm', 'uy_mm', 'uz_mm', 'rx_rad', 'ry_rad', 'rz_rad'):
        assert getattr(direct.second_order.displacements['b'], key) == pytest.approx(
            getattr(backward.second_order.displacements['b'], key), rel=1e-8, abs=1e-9)
    first = direct.second_order.members['m'].along_member
    second = backward.second_order.members['m'].along_member
    assert first['status'] == second['status'] == 'complete'
    for key in ('maximum_moment_y_kn_m', 'maximum_moment_z_kn_m',
                'maximum_chord_deflection_mm', 'maximum_shear_y_kn', 'maximum_shear_z_kn'):
        assert first[key] == pytest.approx(second[key], rel=1e-7, abs=1e-8)


def test_translation_release_with_rigid_arm_does_not_false_complete_under_axial_load():
    # Flexible face may slide while the rigid-arm tip joint is laterally fixed.
    # Recovery must retain both sides' displacement traces at the sliding face.
    model = SpaceFrameModel(
        (SpaceNode('a', 0, 0, 0), SpaceNode('b', 3, 0, 0)),
        (SpaceMember('m', 'a', 'b', 10000, 1e8, 1e8, 1e7,
                     end_releases=(False, True, False, False, False, False),
                     rigid_offset_end_m=.4),),
        (SpaceRestraint('a', True, True, True, True, True, True),
         SpaceRestraint('b', uy=True, uz=True)),
        (SpaceNodalLoad('b', fx_kn=-1000),),
        (SpaceMemberUniformLoad('m', qy_kn_m=-2),),
    )
    envelope = analyze_space_frame_stability_converged(model).second_order.members['m'].along_member
    assert envelope['status'] == 'complete'
    assert envelope['end_moment_residual_nmm'] < 1e-3
    interface = [row for row in envelope['stations'] if abs(row['x_m']-2.6) < 1e-8]
    beam_face = next(row for row in interface if not row['rigid_arm'])
    arm_face = next(row for row in interface if row['rigid_arm'])
    assert beam_face['mz_kn_m'] == pytest.approx(arm_face['mz_kn_m'], abs=1e-8)
    assert abs(beam_face['uy_mm']-arm_face['uy_mm']) > .7


def test_zero_axial_does_not_clear_explicit_incomplete_stability_scope():
    from app.core.scene_member_checks import calculate_scene_member_checks
    from verification.landscape_safety_cases import landscape_frame
    profile, sections = landscape_frame()
    geometry = profile.geometry.model_copy(update={'members': profile.geometry.members[:1]})
    zero = dict(n_kn=0., vy_kn=0., vz_kn=0., my_kn_m=0., mz_kn_m=0., t_kn_m=0.)
    result = dict(analysis_basis='second_order',
                  stability_scope=dict(status='incomplete', excluded_truss_member_ids=['C1']),
                  member_end_forces={'C1': dict(start=zero, end=zero,
                      along_member=dict(status='incomplete', incomplete_reason='truss Kg excluded'))})
    package = calculate_scene_member_checks(geometry, {'LC': result}, {'C1': sections[0]}, {'C1': 'Q355B'})
    assert package['status'] == 'incomplete'


def test_pergola_package_retains_incomplete_case_scope(monkeypatch):
    import app.core.pergola_analysis as package_module
    from app.core.pergola_loads import PergolaLoadPackage
    from verification.landscape_safety_cases import landscape_frame, pressure
    profile, sections = landscape_frame()
    def incomplete_case(*args, **kwargs):
        return dict(analysis_basis='second_order',
                    stability_scope=dict(status='incomplete', excluded_truss_member_ids=['brace']),
                    load_balance_kn=[0., 0., 0.], maximum_translation_mm=0.)
    monkeypatch.setattr(package_module, 'analyze_scene_space_frame', incomplete_case)
    package = package_module.analyze_pergola_package(profile,
        PergolaLoadPackage((pressure('G'), pressure('Q')), (), (), ()), sections)
    assert package['stability_scope'] == dict(status='incomplete',
        incomplete_cases=['G', 'Q'], excluded_truss_member_ids=['brace'])
    assert package['member_checks']['status'] == 'incomplete'


def test_sliding_rigid_arm_zero_axial_matches_hand_integrated_beam():
    # Free arm rotation transmits its UDL couple q*b²/2, but no face shear.
    # Integrate the flexible beam's curvature directly: no FE/ODE oracle.
    length, arm, ei, q = 2600., 400., 206000.*1e8, -2.
    expected_rotation = q*length**3/(6*ei) - q*arm**2*length/(2*ei)
    expected_face_deflection = q*length**4/(8*ei) - q*arm**2*length**2/(4*ei)
    model = SpaceFrameModel(
        (SpaceNode('a', 0, 0, 0), SpaceNode('b', 3, 0, 0)),
        (SpaceMember('m', 'a', 'b', 10000, 1e8, 1e8, 1e7,
            end_releases=(False, True, False, False, False, False), rigid_offset_end_m=.4),),
        (SpaceRestraint('a', True, True, True, True, True, True), SpaceRestraint('b', uy=True, uz=True)),
        member_uniform_loads=(SpaceMemberUniformLoad('m', qy_kn_m=q),),
    )
    result = analyze_space_frame_stability_converged(model).second_order
    envelope = result.members['m'].along_member
    assert envelope['status'] == 'complete'
    assert result.displacements['b'].rz_rad == pytest.approx(expected_rotation, rel=1e-9)
    interface = [row for row in envelope['stations'] if abs(row['x_m']-2.6)<1e-8]
    flexible_face = next(row for row in interface if not row['rigid_arm'])
    rigid_face = next(row for row in interface if row['rigid_arm'])
    assert flexible_face['uy_mm'] == pytest.approx(expected_face_deflection, rel=1e-9)
    assert rigid_face['uy_mm'] == pytest.approx(-arm*expected_rotation, rel=1e-9)
