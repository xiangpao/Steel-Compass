import importlib.util
import pytest


def solver():
    assert importlib.util.find_spec('app.core.contact') is not None, 'compression-only contact solver missing'
    from app.core.contact import solve_rectangular_contact
    return solve_rectangular_contact


def test_uniaxial_detachment_analytical_triangle():
    r = solver()(2, 1, 100, 0, 40)
    assert r.qmax_kpa == pytest.approx(111.111111111, abs=1e-6)
    assert r.area_m2 == pytest.approx(1.8, abs=1e-8)
    assert r.resultants() == pytest.approx((100, 0, 40), abs=1e-7)


@pytest.mark.parametrize('mx,my', [(20,20),(-20,20),(20,-20),(-20,-20),(0,60),(60,0)])
def test_biaxial_contact_balance_and_nonnegative_pressure(mx,my):
    r = solver()(2, 2, 100, mx, my)
    assert r.resultants() == pytest.approx((100,mx,my), abs=1e-7)
    assert r.area_m2 < 4
    assert r.qmin_kpa >= 0


@pytest.mark.parametrize('factor,partial', [(0.99,False),(1.01,True)])
def test_kern_boundary(factor,partial):
    r=solver()(2,1,100,0,100/3*factor)
    assert (r.area_m2 < 2-1e-10) is partial
    assert r.resultants() == pytest.approx((100,0,100/3*factor),abs=1e-7)


@pytest.mark.parametrize('n,mx,my', [(-10,0,0),(0,1,0),(100,0,100),(100,60,0)])
def test_no_equilibrium_rejected(n,mx,my):
    solve=solver()
    from app.core.contact import ContactError
    with pytest.raises(ContactError):
        solve(2,1,n,mx,my)


def test_anchor_compatibility_pure_uplift_and_mixed_bending():
    anchors=[{'x_m':x,'y_m':y,'stiffness_kn_m':100000} for x in (-0.13,0.13) for y in (-0.13,0.13)]
    for n,mx,my in [(-100,0,0),(80,14,6),(0,10,-5)]:
        r=solver()(.36,.36,n,mx,my,contact_stiffness_kn_m3=1e7,anchor_springs=anchors)
        assert r.resultants() == pytest.approx((n,mx,my),abs=1e-7)
        for a,t in zip(anchors,r.anchor_tensions_kn):
            gap=-r.pressure_plane(a['x_m'],a['y_m'])/1e7
            assert t == pytest.approx(a['stiffness_kn_m']*max(gap,0),abs=1e-8)
        if n == -100:
            assert r.area_m2 == pytest.approx(0)
            assert r.anchor_tensions_kn == pytest.approx([25]*4,abs=1e-7)

def test_biaxial_triangular_corner_closed_form():
    # q=600*(x+y-1), triangle (0,1),(1,0),(1,1):
    # volume = 600*0.5/3=100; pressure-weighted centroid (.75,.75).
    r=solver()(2,2,100,75,75)
    assert r.qmax_kpa == pytest.approx(600,abs=1e-6)
    assert r.area_m2 == pytest.approx(.5,abs=1e-9)
    assert r.coefficients_kpa == pytest.approx([-600,600,600],abs=1e-6)


def test_anchor_biaxial_triangle_manufactured_closed_form():
    # Independent analytical triangle + point springs. Uniform ksoil=1000,
    # each anchor k=10 gives ratio .01 m²; no production integration reference.
    p=600
    anchors=[{'x_m':x,'y_m':y,'stiffness_kn_m':10} for x in (-.8,.8) for y in (-.8,.8)]
    n=p/6-.01*p*4.6
    m=p/8+.8*.01*p*2.6
    r=solver()(2,2,n,m,m,contact_stiffness_kn_m3=1000,anchor_springs=anchors)
    assert r.coefficients_kpa == pytest.approx([-p,p,p],abs=1e-6)
    assert r.anchor_tensions_kn == pytest.approx([15.6,6,6,0],abs=1e-7)


def test_pressure_resultants_against_independent_tensor_quadrature():
    import numpy as np
    nodes,weights=np.polynomial.legendre.leggauss(300)
    u,v=np.meshgrid(nodes,nodes)
    w=weights[:,None]*weights[None,:]
    for mx,my in [(20,20),(50,-30),(-60,-60)]:
        r=solver()(2,2,100,mx,my)
        a,b,c=r.coefficients_kpa
        q=np.maximum(a+b*u+c*v,0)
        assert [np.sum(q*w),np.sum(q*v*w),np.sum(q*u*w)] == pytest.approx([100,mx,my],abs=.003)


def packets(n,mx=0,my=0,name='case'):
    return [dict(name='base',limit_state=ls,combination_name=f'{name}-{ls}',components={
        k:{'value':v,'unit':'kN' if k=='N' else 'kN·m'} for k,v in {'N':n,'Mx':mx,'My':my}.items()
    }) for ls in ('SLS','ULS')]


def test_foundation_real_contact_integration_and_combination_envelopes():
    from app.core.engine import calculate
    from app.core.schemas import CalculationRequest
    # 2*1*.2*25=10 kN footing weight: SLS total100, ULS total103.
    # ULS triangle length=3*(1-40/103); exact strip integrations independent.
    def run(cases):
        return calculate(CalculationRequest(mode='quick',module='spread_footing',inputs={
            'length_m':2,'width_m':1,'thickness_mm':200,'soil_cover_m':0,
            'groundwater_condition':'no_influence','upstream_reaction_envelopes':cases,
            'top_bar_dia_x_mm':14,'top_bar_spacing_x_mm':150,
            'top_bar_dia_y_mm':14,'top_bar_spacing_y_mm':150,
        }))
    r=run(packets(90,my=40))
    q=next(c for c in r.checks if c.name=='地基承载力')
    assert q.demand.value == pytest.approx(111.111111111,abs=1e-6)
    assert r.workflow_status == 'ready'
    assert r.verification_status == 'unverified'
    a=3*(1-40/103);qmax=206/a;start=1-a
    def integral(x):
        lo=max(x,start)
        return qmax/(2*a)*((1-start)**2-(lo-start)**2)
    # default h0=200-50-14/2=143mm; positive column face .15m.
    shear=next(c for c in r.checks if c.name=='X向单向剪切')
    assert shear.demand.value == pytest.approx(integral(.15+.143)-6.5*(1-.15-.143),abs=1e-7)
    # Critical rectangle width=.3+.143, centred; pressure is affine within it.
    inside=(.3+.143)**2*qmax/a*(-start)
    punch=next(c for c in r.checks if c.name=='柱边冲切')
    assert punch.demand.value == pytest.approx(90-inside+6.5*(.3+.143)**2,abs=1e-7)
    a_case=packets(90,my=40,name='A'); b_case=packets(90,mx=35,name='B')
    both=run(a_case+b_case)
    left,right=run(a_case),run(b_case)
    for check in both.checks:
        if check.name in {'地基承载力','基底脱开区比例','X向单向剪切','Y向单向剪切','柱边冲切','X向底筋','Y向底筋'}:
            refs=[next(c for c in v.checks if c.name==check.name) for v in (left,right)]
            assert check.demand.value == pytest.approx(max(c.demand.value for c in refs))
            assert check.governing_combination in {'A-SLS','B-SLS','A-ULS','B-ULS'}


def test_baseplate_coupled_output_does_not_claim_tension_plate_complete():
    from app.core.engine import calculate
    from app.core.schemas import CalculationRequest
    springs=[{'x_m':x,'y_m':y,'stiffness_kn_m':100000} for x in (-.13,.13) for y in (-.13,.13)]
    r=calculate(CalculationRequest(mode='quick',module='steel_baseplate_anchor',inputs={
        'upstream_reaction_envelopes':packets(-100),'contact_stiffness_kn_m3':1e7,
        'anchor_springs':springs,'contact_model_source':'explicit test model',
    }))
    assert r.status == 'incomplete'
    assert r.quick_outcome is None
    assert r.contact_solutions[0]['anchor_tensions_kn'] == pytest.approx([25]*4,abs=1e-7)
    assert any(w.code=='baseplate_tension_plate_design_pending' for w in r.warnings)
    assert not any(c.name in {'底板悬臂弯曲','柱底角焊缝承载力（快算）'} for c in r.checks)

def test_anchor_shear_distribution_balances_asymmetric_group():
    from app.core.contact import anchor_shear_distribution
    anchors=[{'x_m':x,'y_m':y} for x,y in [(0,0),(.3,0),(.3,.2),(0,.4)]]
    vectors=anchor_shear_distribution(anchors,12,-8,5)
    assert sum(v[0] for v in vectors) == pytest.approx(12,abs=1e-10)
    assert sum(v[1] for v in vectors) == pytest.approx(-8,abs=1e-10)
    assert sum(a['x_m']*v[1]-a['y_m']*v[0] for a,v in zip(anchors,vectors)) == pytest.approx(5,abs=1e-10)
    square=[{'x_m':x,'y_m':y} for x in (-.1,.1) for y in (-.1,.1)]
    for actual,expected in zip(anchor_shear_distribution(square,0,0,4),[(5,-5),(-5,-5),(5,5),(-5,5)]):
        assert actual == pytest.approx(expected)


def test_continuous_square_weld_closed_form_axial_bending_and_torsion():
    from app.core.contact import rectangular_weld_peak_line_force
    assert rectangular_weld_peak_line_force(200,200,-80,0,0,0,0,0) == pytest.approx(100)
    # Square perimeter800mm, line Ix=5,333,333.333mm³; 4kNm gives75N/mm.
    assert rectangular_weld_peak_line_force(200,200,0,0,0,4,0,0) == pytest.approx(75)
    # T=4kNm, J=10,666,666.667mm³, r=sqrt(2)*100mm.
    assert rectangular_weld_peak_line_force(200,200,0,0,0,0,0,4) == pytest.approx(53.033008589,abs=1e-8)


def test_foundation_reverse_bending_matches_closed_form_and_requires_top_bars():
    from math import sqrt
    from app.core.engine import calculate
    from app.core.schemas import CalculationRequest
    r=calculate(CalculationRequest(mode='quick',module='spread_footing',inputs={
        'length_m':2,'width_m':1,'thickness_mm':200,'soil_cover_m':0,
        'groundwater_condition':'no_influence','upstream_reaction_envelopes':packets(90,my=40),
    }))
    a=3*(1-40/103); gap=2-a;k=206/a**2;dead=6.5
    t=(dead+sqrt(dead**2+2*k*dead*gap))/k
    peak=dead*(t+gap)**2/2-k*t**3/6
    top=r.contact_solutions[0]['top_reinforcement_requirements']['x']
    assert top['moment_kn_m'] == pytest.approx(peak,abs=1e-8)
    assert top['missing_inputs'] == ['top_bar_dia_x_mm','top_bar_spacing_x_mm']
    assert r.status == 'incomplete'
    assert any(w.code=='foundation_net_bending_inputs_incomplete' for w in r.warnings)


def test_explicit_weld_and_anchor_torsion_are_computed_while_flexible_plate_remains_pending():
    from app.core.engine import calculate
    from app.core.schemas import CalculationRequest
    p=packets(-80)
    for item in p:
        item['components']['T']={'value':4,'unit':'kN·m'}
    r=calculate(CalculationRequest(mode='quick',module='steel_baseplate_anchor',inputs={
        'upstream_reaction_envelopes':p,'contact_stiffness_kn_m3':1e7,
        'anchor_springs':[{'x_m':x,'y_m':y,'stiffness_kn_m':100000} for x in (-.1,.1) for y in (-.1,.1)],
        'contact_model_source':'explicit mechanics reference','continuous_perimeter_weld':True,
    }))
    for actual,expected in zip(r.contact_solutions[0]['anchor_shear_vectors_kn'],[(5,-5),(-5,-5),(5,5),(-5,5)]):
        assert actual == pytest.approx(expected)
    weld=next(c for c in r.checks if c.name=='柱底角焊缝承载力（快算）')
    assert weld.demand.value == pytest.approx((100**2+53.033008589**2)**.5*.8,abs=1e-7)
    assert r.status=='incomplete'
    assert not any(w.code=='baseplate_torsional_shear_pending' for w in r.warnings)
