"""Independent reviewer probes, 2026-09-26; not engineering certification."""
import numpy as np
import pytest

from app.core.contact import (
    ContactError, solve_rectangular_contact, anchor_shear_distribution,
    rectangular_weld_peak_line_force,
)
from app.core.engine import calculate
from app.core.schemas import CalculationRequest


def packets(n=90, my=40):
    values = dict(N=n, Mx=0, My=my, Vx=0, Vy=0, T=0)
    return [dict(name="base", limit_state=state, combination_id=state,
                 combination_name="review-"+state,
                 components={key: dict(value=value, unit="kN" if key in {"N","Vx","Vy"} else "kN.m")
                             for key,value in values.items()}) for state in ("ULS","SLS")]


def test_reject_unstable_collinear_anchor_uplift_even_when_residual_is_zero():
    # Initial uniform plane exactly balances N but leaves rotation about x free.
    anchors=[dict(x_m=x,y_m=0.,stiffness_kn_m=250.) for x in (-.6,-.2,.2,.6)]
    with pytest.raises(ContactError):
        solve_rectangular_contact(2,2,-100,0,0,contact_stiffness_kn_m3=250,anchor_springs=anchors)


def test_top_rebar_check_retains_actual_combination():
    result=calculate(CalculationRequest(mode="quick", module="spread_footing",inputs=dict(
        length_m=2,width_m=1,thickness_mm=200,soil_cover_m=0,
        groundwater_condition="no_influence",upstream_reaction_envelopes=packets(),
        top_bar_dia_x_mm=14,top_bar_spacing_x_mm=150,
        top_bar_dia_y_mm=14,top_bar_spacing_y_mm=150)))
    top=next(c for c in result.checks if c.name=="X向顶筋")
    assert top.governing_combination == "review-ULS"


def test_actual_anchor_spacing_cannot_use_unrelated_default_capacity():
    from app.core.errors import CalculationInputError
    anchors=[dict(x_m=x,y_m=y,stiffness_kn_m=100000) for x in (-.001,.001) for y in (-.001,.001)]
    try:
        result=calculate(CalculationRequest(mode="quick",module="steel_baseplate_anchor",inputs=dict(
            upstream_reaction_envelopes=packets(100,0),contact_stiffness_kn_m3=1e7,
            anchor_springs=anchors,contact_model_source="independent geometry inconsistency probe")))
    except CalculationInputError:
        return  # Explicit refusal is acceptable; a favorable default pass is not.
    spacing=next(c for c in result.checks if c.name=="锚栓最小间距")
    assert not spacing.passed
    assert spacing.capacity.value <= 2.000001
    assert result.status != "passed"


def test_independent_rectangular_trapezoid_manufactured_pressure():
    # Separate 360x360 Gauss grid, no production clipping/integration calls.
    points,weights=np.polynomial.legendre.leggauss(360)
    x,y=np.meshgrid(points*1.5,points*.4,indexing="ij")
    area_weights=np.outer(weights,weights)*.6
    pressure=np.maximum(30+70*x/1.5-20*y/.4,0)
    target=[np.sum(area_weights*pressure),np.sum(area_weights*pressure*y),np.sum(area_weights*pressure*x)]
    result=solve_rectangular_contact(3,.8,*target)
    assert result.coefficients_kpa == pytest.approx([30,70,-20],abs=.002)
    assert result.qmax_kpa == pytest.approx(120,abs=.002)
    assert result.resultants() == pytest.approx(target,abs=1e-7)


def test_unequal_anchor_stiffness_all_uplift_manufactured_plane():
    anchors=[dict(x_m=x,y_m=y,stiffness_kn_m=k) for x,y,k in
             [(-.8,-.3,100),(.7,-.3,200),(.6,.25,400),(-.5,.3,150)]]
    # w=-.1+.02*x-.03*y, everywhere negative on rectangle.
    tensions=[a["stiffness_kn_m"]*(.1-.02*a["x_m"]+.03*a["y_m"]) for a in anchors]
    target=(-sum(tensions),-sum(t*a["y_m"] for t,a in zip(tensions,anchors)),
            -sum(t*a["x_m"] for t,a in zip(tensions,anchors)))
    result=solve_rectangular_contact(2,1,*target,contact_stiffness_kn_m3=3000,anchor_springs=anchors)
    assert result.anchor_tensions_kn == pytest.approx(tensions,abs=1e-7)
    assert result.area_m2 == 0
    assert result.resultants() == pytest.approx(target,abs=1e-7)


def test_shear_origin_translation_keeps_physical_force_vectors():
    anchors=[dict(x_m=x,y_m=y) for x,y in [(-.4,-.1),(.2,-.2),(.5,.3),(-.1,.4)]]
    vx,vy,torque=17,-23,11
    before=anchor_shear_distribution(anchors,vx,vy,torque)
    dx,dy=.37,-.21
    translated=[dict(x_m=a["x_m"]+dx,y_m=a["y_m"]+dy) for a in anchors]
    after=anchor_shear_distribution(translated,vx,vy,torque+dx*vy-dy*vx)
    assert np.array(after) == pytest.approx(np.array(before),abs=1e-12)
    assert sum(a["x_m"]*v[1]-a["y_m"]*v[0] for a,v in zip(anchors,before)) == pytest.approx(torque)


def test_nonsquare_weld_against_independent_line_quadrature():
    # Assemble line area moments by 8-point Gauss integration of all four edges.
    g,w=np.polynomial.legendre.leggauss(8)
    coords=[]; quadrature=[]
    for y in (-60,60):
        coords.extend((float(x),y) for x in g*150); quadrature.extend(w*150)
    for x in (-150,150):
        coords.extend((x,float(y)) for y in g*60); quadrature.extend(w*60)
    xy=np.array(coords); qw=np.array(quadrature)
    length=sum(qw); ix=sum(qw*xy[:,1]**2); iy=sum(qw*xy[:,0]**2)
    # N=31, Vx=7, Vy=-13, Mx=2, My=-5, T=3, all simultaneous.
    expected=0
    for x in (-150,150):
        for y in (-60,60):
            f=np.array([31000/length+2e6*y/ix-5e6*x/iy,
                        7000/length-3e6*y/(ix+iy),-13000/length+3e6*x/(ix+iy)])
            expected=max(expected,np.linalg.norm(f))
    assert rectangular_weld_peak_line_force(300,120,31,7,-13,2,-5,3) == pytest.approx(expected,rel=1e-12)


def test_distinct_combination_ids_with_missing_names_keep_own_weight_factor():
    base=dict(length_m=2,width_m=1,thickness_mm=200,soil_cover_m=0,
              groundwater_condition="no_influence")
    first,second=packets(10,0),packets(90,0)
    for case,ident,leading in ((first[0],"A","permanent"),(second[0],"B","uplift")):
        case.update(combination_name=None,combination_id=ident,leading_action=leading)
    def run(cases):
        result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs=dict(
            base,upstream_reaction_envelopes=cases)))
        return {c.name:c.demand.value for c in result.checks}
    a,b,together=run(first),run(second),run(first+second)
    for name in ("X向单向剪切","Y向单向剪切","柱边冲切"):
        assert together[name] == pytest.approx(max(a[name],b[name]),abs=1e-8)


def test_nonuniform_body_weight_never_reports_ready_structural_design():
    result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs=dict(
        length_m=2,width_m=1,thickness_mm=200,soil_cover_m=0,
        footing_concrete_volume_m3=.6,total_foundation_height_m=.4,
        groundwater_condition="no_influence",upstream_reaction_envelopes=packets(100,0))))
    assert result.status == "incomplete"
    assert result.workflow_status == "capability_unavailable"
    assert result.verification_status == "unverified"
    assert all(s["distributed_weight_model"] == "unresolved_nonuniform_weight" for s in result.contact_solutions)
