from math import pi, sqrt, cos
import pytest
from app.core.errors import CalculationInputError
from app.core.space_frame import (SpaceFrameModel, SpaceMember, SpaceMemberUniformLoad, SpaceNode, SpaceRestraint, SpaceNodalLoad, analyze_space_frame_stability)


def pin_column(ratio=0.5, released=True, axis='y'):
    e, i, length = 206000., 1.e8, 3000.
    p = ratio*pi*pi*e*i/length**2
    release = (False, False, False, False, True, True) if released else (False,)*6
    return SpaceFrameModel(
        (SpaceNode('a',0,0,0),SpaceNode('b',3,0,0)),
        (SpaceMember('m','a','b',10000,i,i,1e7,start_releases=release,end_releases=release),),
        (SpaceRestraint('a',True,True,True,True,released,released),SpaceRestraint('b',False,True,True,False,released,released)),
        (SpaceNodalLoad('b',fx_kn=-p/1000),),
        (SpaceMemberUniformLoad('m',**{f'q{axis}_kn_m':-1.}),),
    )


@pytest.mark.parametrize('ratio',[0.2,0.99])
def test_released_pin_column_has_internal_buckling_modes(ratio):
    result=analyze_space_frame_stability(pin_column(ratio),member_subdivisions=8)
    reference=analyze_space_frame_stability(pin_column(ratio,released=False),member_subdivisions=8)
    assert result.buckling_factors[0] == pytest.approx(1/ratio,rel=4e-5)
    assert result.buckling_factors == pytest.approx(reference.buckling_factors)
    assert result.second_order.members['m'].local_end_forces[5] == pytest.approx(0,abs=1e-5)
    assert result.second_order.members['m'].local_end_forces[11] == pytest.approx(0,abs=1e-5)


def test_released_pin_column_rejects_supercritical_state():
    with pytest.raises(CalculationInputError) as error:
        analyze_space_frame_stability(pin_column(1.01),member_subdivisions=8)
    assert error.value.code in {'second_order_instability','elastic_buckling_instability'}


@pytest.mark.parametrize('axis',['y','z'])
@pytest.mark.parametrize('ratio',[0.2,0.8])
def test_pin_column_udl_second_order_interior_against_closed_form(axis,ratio):
    result=analyze_space_frame_stability(pin_column(ratio,axis=axis),member_subdivisions=12)
    envelope=result.second_order.members['m'].along_member
    p=ratio*pi*pi*206000*1e8/3000**2
    k=sqrt(p/(206000*1e8))
    # Exact EI*v'''' + P*v''=q; v(0)=v(L)=v''(0)=v''(L)=0.
    moment=(1/cos(k*1500)-1)/(k*k)
    displacement=(moment-3000**2/8)/p
    assert envelope['status']=='complete'
    assert envelope['maximum_moment_z_kn_m' if axis=='y' else 'maximum_moment_y_kn_m'] == pytest.approx(moment/1e6,rel=3e-4)
    assert envelope['maximum_chord_deflection_mm']==pytest.approx(displacement,rel=3e-4)
    assert envelope['end_moment_residual_nmm'] < 1e-4


def test_default_single_element_preserves_discrete_solution_but_not_complete_envelope():
    result=analyze_space_frame_stability(pin_column(0.2,released=False))
    assert result.buckling_factors[0]==pytest.approx(12/(.2*pi*pi))
    assert result.second_order.members['m'].along_member['status']=='incomplete'

@pytest.mark.parametrize('axial_kn',[-1000.,1000.])
@pytest.mark.parametrize('offsets',[(0.,0.),(.3,.4)])
@pytest.mark.parametrize('qx',[0.,-2.])
def test_cantilever_recovery_matches_independent_ode(axial_kn,offsets,qx):
    from dataclasses import replace
    import numpy as np
    from scipy.integrate import solve_ivp
    from app.core.space_frame import analyze_space_frame_stability_converged
    from tests.test_space_frame_audit import cantilever
    a,b=offsets
    length=3000.
    q=-2.
    p0=-axial_kn*1000-qx*length
    # Independent shooting integration in physical coordinates. State is
    # displacement, slope, moment, effective shear; no production FE matrices.
    def solution(root_moment,locations):
        state=np.array([0.,0.,root_moment,10000-q*length])
        values=[]
        breaks=[0.,a*1000,length-b*1000,length]
        for left,right in zip(breaks[:-1],breaks[1:],strict=True):
            if right-left<1e-8: continue
            rigid=(left<a*1000-1e-8 or left>=length-b*1000-1e-8)
            def ode(x,y):
                return [y[1],0 if rigid else -y[2]/(206000*1e8),-y[3]+(p0+qx*x)*y[1],q]
            result=solve_ivp(ode,(left,right),state,rtol=1e-11,atol=1e-10,dense_output=True)
            for x in locations:
                if left-1e-8<=x<=right+1e-8:
                    values.append((x,result.sol(x)))
            state=result.y[:,-1]
        return state,values
    m0=solution(0,[])[0][2]
    m1=solution(1e6,[])[0][2]
    root=-m0*1e6/(m1-m0)
    model=replace(cantilever(rigid_offset_start_m=a,rigid_offset_end_m=b),
        nodal_loads=(SpaceNodalLoad('B',fx_kn=axial_kn,fy_kn=-10.),),
        member_uniform_loads=(SpaceMemberUniformLoad('m',qx_kn_m=qx,qy_kn_m=q),))
    actual=analyze_space_frame_stability_converged(model).second_order
    envelope=actual.members['m'].along_member
    assert envelope['status']=='complete'
    assert actual.displacements['B'].uy_mm==pytest.approx(solution(root,[])[0][0],rel=1e-4)
    assert actual.reactions['A'].mz_kn_m==pytest.approx(root/1e6,rel=1e-4)
    for station in envelope['stations']:
        reference=solution(root,[station['x_m']*1000])[1][0][1]
        assert station['mz_kn_m']==pytest.approx(reference[2]/1e6,abs=2e-4)
        assert station['uy_mm']==pytest.approx(reference[0],abs=2e-4)
    assert envelope['end_moment_residual_nmm']<1e-3


def test_released_faces_with_rigid_arms_have_flexible_span_buckling_length():
    from dataclasses import replace
    model=pin_column(.2)
    member=replace(model.members[0],rigid_offset_start_m=.3,rigid_offset_end_m=.4)
    result=analyze_space_frame_stability(replace(model,members=(member,)),member_subdivisions=12)
    assert result.buckling_factors[0]==pytest.approx(5*(3/2.3)**2,rel=1e-5)
    assert result.second_order.members['m'].along_member['status']=='complete'


def test_unsupported_envelope_metadata_does_not_unlock_member_checks():
    from app.core.scene_member_checks import _complete_envelope
    assert not _complete_envelope({'status':'complete'})
    assert not _complete_envelope({'status':'complete','method':'unrecognized'})


def test_both_torsional_releases_are_a_benign_spin_gauge_not_a_bending_mechanism():
    from dataclasses import replace
    model=pin_column(.2)
    released=(False,False,False,True,True,True)
    model=replace(model,members=(replace(model.members[0],start_releases=released,end_releases=released),))
    result=analyze_space_frame_stability(model,member_subdivisions=8)
    assert result.buckling_factors[0]==pytest.approx(5,rel=4e-5)
    envelope=result.second_order.members['m'].along_member
    assert envelope['status']=='complete'


def test_loaded_axial_double_release_is_rejected():
    from dataclasses import replace
    model=pin_column(.2)
    release=(True,False,False,False,True,True)
    model=replace(model,members=(replace(model.members[0],start_releases=release,end_releases=release),),
                  nodal_loads=(),member_uniform_loads=(SpaceMemberUniformLoad('m',qx_kn_m=-1.),))
    with pytest.raises(CalculationInputError):
        analyze_space_frame_stability(model,member_subdivisions=8)


def test_released_tip_translation_is_solved_as_internal_face_motion():
    from dataclasses import replace
    from app.core.space_frame import analyze_space_frame_stability_converged
    from tests.test_space_frame_audit import cantilever
    model=replace(cantilever(end_releases=(False,True,False,False,False,False)),
                  nodal_loads=(),member_uniform_loads=(SpaceMemberUniformLoad('m',qy_kn_m=-2),))
    result=analyze_space_frame_stability_converged(model).second_order
    envelope=result.members['m'].along_member
    assert envelope['status']=='complete'
    assert result.members['m'].local_end_forces[7]==pytest.approx(0,abs=1e-6)
    tip=max(envelope['stations'],key=lambda row:row['x_m'])
    assert tip['uy_mm']==pytest.approx(-2*3000**4/(8*206000*1e8),rel=1e-7)
    assert result.reactions['A'].fy_kn==pytest.approx(6)


def test_zero_requested_modes_cannot_disable_instability_rejection():
    with pytest.raises(CalculationInputError) as error:
        analyze_space_frame_stability(pin_column(1.5,released=False),mode_count=0,member_subdivisions=8)
    assert error.value.code=='invalid_stability_modes'


def test_member_checks_distinguish_tension_from_compression_end_action_signs():
    from app.core.scene_member_checks import calculate_scene_member_checks
    from verification.landscape_safety_cases import landscape_frame
    profile, sections=landscape_frame()
    geometry=profile.geometry.model_copy(update={'members':profile.geometry.members[:1]})
    zero={'n_kn':0.,'vy_kn':0.,'vz_kn':0.,'my_kn_m':0.,'mz_kn_m':0.,'t_kn_m':0.}
    results={}
    for name,sign in [('compression',1),('tension',-1)]:
        results[name]={'member_end_forces':{'C1':{'start':{**zero,'n_kn':sign*600},'end':{**zero,'n_kn':-sign*600}}}}
    item=calculate_scene_member_checks(geometry,results,{'C1':sections[0]},{'C1':'Q355B'})['items'][0]
    cases={case['case_id']:case for case in item['case_checks']}
    assert cases['tension']['axial_biaxial_utilization']==pytest.approx(600/(sections[0].area_mm2*305/1000),abs=1e-5)
    assert cases['compression']['axial_biaxial_utilization']>cases['tension']['axial_biaxial_utilization']


def test_truss_actions_use_member_axis_for_explicit_unavailable_stability_boundary():
    from app.core.space_frame import analyze_space_frame
    model=SpaceFrameModel((SpaceNode('a',0,0,0),SpaceNode('b',0,0,3)),
        (SpaceMember('m','a','b',1000,1e5,1e5,1e5,behavior='truss'),),
        (SpaceRestraint('a',True,True,True,True,True,True),SpaceRestraint('b',True,True,False,True,True,True)),
        (SpaceNodalLoad('b',fz_kn=-1),))
    first=analyze_space_frame(model)
    second=analyze_space_frame_stability(model,first).second_order
    assert first.members['m'].local_end_forces[0]==pytest.approx(1000)
    assert second.members['m'].local_end_forces[0]==pytest.approx(1000)
    assert second.members['m'].along_member['status']=='incomplete'


@pytest.mark.parametrize('axis', ['y', 'z'])
@pytest.mark.parametrize('axial_kn', [-1000., 0., 1000.])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('axial_udl', [0., -2.])
def test_sliding_flexible_face_and_rigid_arm_match_independent_transfer_solution(axis, axial_kn, reverse, axial_udl):
    """Exact constant-coefficient ODE transfer, independent of production FE.

    End shear release: V_eff(l)=0. The joint at L is transversely restrained,
    but rotation is free: M(l)+P*b*theta(l)-q*b²/2=0. The beam face may slide
    relative to the arm: v_beam(l) need not equal -b*theta(l).
    """
    import numpy as np
    from scipy.linalg import expm
    from scipy.integrate import solve_ivp
    from dataclasses import replace
    from app.core.space_frame import analyze_space_frame_stability_converged
    length, arm, q, ei = 3000., 400., -2., 206000*1e8
    p = -axial_kn*1000-axial_udl*length
    flexible = length-arm
    generator = np.zeros((5,5))
    generator[0,1] = 1
    generator[1,2] = -1/ei
    generator[2,1] = p
    generator[2,3] = -1
    generator[3,4] = q
    if axial_udl:
        def fundamental_ode(x, flattened):
            varying = generator.copy()
            varying[2,1] = p+axial_udl*x
            return (varying @ flattened.reshape((5,5))).ravel()
        fundamental = solve_ivp(fundamental_ode,(0,flexible),np.eye(5).ravel(),
                                rtol=1e-11,atol=1e-12,dense_output=True)
        def transfer_at(x):
            return fundamental.sol(x).reshape((5,5))
    else:
        def transfer_at(x):
            return expm(generator*x)
    transfer = transfer_at(flexible)
    arm_p_integral = (p+axial_udl*(length-arm/2))*arm
    constant = transfer @ np.array([0.,0.,0.,-q*flexible,1.])
    response = transfer @ np.array([0.,0.,1.,0.,0.])
    root_moment = -(constant[2]+arm_p_integral*constant[1]-q*arm**2/2)/(response[2]+arm_p_integral*response[1])
    initial = np.array([0.,0.,root_moment,-q*flexible,1.])
    tip = transfer @ initial
    release = (False, axis=='y', axis=='z', False, False, False)
    member = SpaceMember('m','a','b',10000,1e8,1e8,1e7,end_releases=release,rigid_offset_end_m=.4)
    if reverse:
        member = replace(member,start='b',end='a',start_releases=release,end_releases=(False,)*6,
                         rigid_offset_start_m=.4,rigid_offset_end_m=0.)
    model = SpaceFrameModel((SpaceNode('a',0,0,0),SpaceNode('b',3,0,0)),(member,),
        (SpaceRestraint('a',True,True,True,True,True,True),SpaceRestraint('b',uy=True,uz=True)),
        (SpaceNodalLoad('b',fx_kn=axial_kn),),
        (SpaceMemberUniformLoad('m',qx_kn_m=axial_udl,**{f'q{axis}_kn_m':q}),))
    result = analyze_space_frame_stability_converged(model).second_order
    envelope = result.members['m'].along_member
    assert envelope['status']=='complete'
    assert envelope['end_moment_residual_nmm'] < 1e-3
    rotation = result.displacements['b'].rz_rad if axis=='y' else -result.displacements['b'].ry_rad
    assert rotation == pytest.approx(tip[1],rel=1e-5)
    reaction = result.reactions['a'].mz_kn_m if axis=='y' else -result.reactions['a'].my_kn_m
    assert reaction == pytest.approx(root_moment/1e6,rel=1e-5)
    for station in envelope['stations']:
        physical_x = length-station['x_m']*1000 if reverse else station['x_m']*1000
        if station['rigid_arm']:
            expected_v = (physical_x-length)*tip[1]
            delta = physical_x-flexible
            expected_m = tip[2]+tip[1]*((p+axial_udl*flexible)*delta+axial_udl*delta**2/2)-q*delta**2/2
        else:
            reference = transfer_at(physical_x) @ initial
            expected_v, expected_m = reference[0], reference[2]
        # Local transverse basis flips only for local y when reversing the x axis.
        sign = -1 if reverse and axis=='y' else 1
        assert station[f'u{axis}_mm'] == pytest.approx(sign*expected_v,abs=1e-5)
        moment_key = 'mz_kn_m' if axis=='y' else 'my_kn_m'
        moment_sign = sign if axis=='y' else -sign
        assert station[moment_key] == pytest.approx(moment_sign*expected_m/1e6,abs=1e-5)
    assert abs(tip[0]+arm*tip[1]) > .1  # Nonzero actual release slip.
    jump = envelope['released_face_displacement_jumps']['start' if reverse else 'end'][1 if axis=='y' else 2]
    assert jump == pytest.approx((-1 if reverse and axis=='y' else 1)*(tip[0]+arm*tip[1]),abs=1e-5)


def test_sparse_pure_tension_frame_has_no_positive_buckling_modes():
    from math import tanh
    model = SpaceFrameModel((SpaceNode('a',0,0,0),SpaceNode('mid',1.5,0,0),SpaceNode('b',3,0,0)),
        (SpaceMember('left','a','mid',10000,1e8,1e8,1e7),SpaceMember('right','mid','b',10000,1e8,1e8,1e7)),
        (SpaceRestraint('a',True,True,True,True,True,True),),
        (SpaceNodalLoad('b',fx_kn=1000,fy_kn=1),))
    result = analyze_space_frame_stability(model,member_subdivisions=32)
    alpha = sqrt(1e6/(206000*1e8))
    reference = 1000/1e6*(3000-tanh(alpha*3000)/alpha)
    assert result.buckling_factors==()
    assert result.second_order.displacements['b'].uy_mm==pytest.approx(reference,rel=1e-6)


def test_eigen_iteration_failure_is_not_reported_as_structural_instability(monkeypatch):
    import numpy as np
    from scipy.sparse.linalg import ArpackNoConvergence
    import app.core.space_frame as solver
    def no_convergence(*args,**kwargs):
        raise ArpackNoConvergence('injected iteration exhaustion',np.array([]),np.empty((0,0)))
    monkeypatch.setattr(solver,'eigsh',no_convergence)
    model = SpaceFrameModel(tuple(SpaceNode(str(i),i,0,0) for i in range(5)),
        tuple(SpaceMember(str(i),str(i),str(i+1),10000,1e8,1e8,1e7) for i in range(4)),
        (SpaceRestraint('0',True,True,True,True,True,True),),
        (SpaceNodalLoad('4',fx_kn=-1,fy_kn=1),))
    with pytest.raises(CalculationInputError) as error:
        analyze_space_frame_stability(model,member_subdivisions=32)
    assert error.value.code=='buckling_eigen_solver_not_converged'
