import pytest

from app.core.engine import calculate
from app.core.foundation import _reaction_combinations
from app.core.loads import transferred_axial_load_envelope
from app.core.schemas import CalculationRequest, ReactionEnvelope


def packet(name="case", n=10, vx=0, vy=0, mx=0, my=0):
    return [dict(name="base", limit_state=ls, combination_name=f"{name}-{ls}",
                 direction="uplift" if n < 0 else "gravity", components={
        k: {"value": v, "unit": "kN" if k in ("N","Vx","Vy") else "kN.m"}
        for k,v in dict(N=n,Vx=vx,Vy=vy,Mx=mx,My=my,T=0).items()
    }) for ls in ("SLS","ULS")]


@pytest.mark.parametrize("module", ["steel_column", "concrete_column"])
def test_column_retains_moments_and_original_combination_vectors(module):
    source = packet(mx=100)
    result = calculate(CalculationRequest(mode="quick", module=module, inputs={"upstream_reaction_envelopes": source}))
    assert result.input_summary["design_moment"].value >= 100
    assert any(not check.passed for check in result.checks)
    for reaction in result.reaction_envelopes:
        assert reaction.components["Mx"].value == 100
        assert reaction.components["My"].value == 0


def test_explicit_zero_axial_is_not_replaced_by_transverse_shear():
    envelope = transferred_axial_load_envelope(packet(n=0,vy=90))
    assert all(item.total.value == 0 for item in envelope.combinations)


def test_foundation_anti_sliding_envelopes_utilization_not_force():
    def run(p):
        result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs={
            "upstream_reaction_envelopes": p,"soil_cover_m":0,"groundwater_depth_m":5}))
        return next(c for c in result.checks if c.name == "抗滑稳定")
    a,b=packet("A",n=1000,vx=100),packet("B",n=10,vx=90)
    weak,combined=run(b),run(a+b)
    assert combined.utilization == pytest.approx(weak.utilization)
    assert not combined.passed
    assert combined.governing_combination == "B-SLS"


def test_foundation_uplift_keeps_favorable_permanent_factor():
    raw=packet("上拔控制",n=-100)[1]
    updated,_=_reaction_combinations([ReactionEnvelope.model_validate(raw)],100,0)
    assert updated[0].components["N"].value == pytest.approx(-10)


def test_submerged_footing_buoyancy_is_not_deducted_twice():
    result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs={
        "upstream_reaction_envelopes":packet(n=0), "soil_cover_m":0,
        "groundwater_known":True,"groundwater_depth_m":0}))
    check=next(c for c in result.checks if c.name=="地下水抗浮稳定系数")
    # Fully submerged concrete without superstructure: gross weight/buoyancy=25/10.
    assert check.capacity.value == pytest.approx(2.5)


def test_punching_uses_integrated_pressure_and_its_own_governing_combination():
    def run(p):
        result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs={
            "upstream_reaction_envelopes":p,"soil_cover_m":0,"groundwater_depth_m":5}))
        return next(c for c in result.checks if c.name=="柱边冲切")
    a,b=packet("A",n=1000),packet("B",n=800,mx=200)
    assert run(a+b).demand.value == pytest.approx(run(a).demand.value)
    assert run(a+b).governing_combination == "A-ULS"


def test_baseplate_pure_moment_never_claims_zero_bearing_as_pass():
    result=calculate(CalculationRequest(mode="quick",module="steel_baseplate_anchor",inputs={"moment_x_kn_m":10}))
    # Partial-contact/anchor coupling requires a different pressure model.
    assert result.status == "incomplete" or all(c.demand.value > 0 for c in result.checks[:2])
    assert result.quick_outcome != "screening_passed"


def test_full_contact_baseplate_uses_peak_corner_pressure():
    result = calculate(CalculationRequest(mode="quick",module="steel_baseplate_anchor",inputs={
        "upstream_reaction_envelopes": packet(n=100,mx=5), "concrete_bearing_capacity_mpa":1.0}))
    bearing = result.checks[0]
    assert bearing.demand.value == pytest.approx(100000 / 360**2 + 6 * 5e6 / 360**3)
    assert not bearing.passed


def test_baseplate_weld_has_its_own_governing_combination():
    result=calculate(CalculationRequest(mode="quick",module="steel_baseplate_anchor",inputs={
        "upstream_reaction_envelopes":packet("pressure",n=100000)+packet("weld",n=1000,mx=50)}))
    check=next(c for c in result.checks if c.name=="柱底角焊缝承载力（快算）")
    assert check.demand.value == pytest.approx(500)
    assert check.governing_combination == "weld-ULS"


def test_foundation_detachment_does_not_claim_complete_linear_structural_checks():
    result=calculate(CalculationRequest(mode="quick",module="spread_footing",inputs={
        "upstream_reaction_envelopes":packet(n=10,mx=100)}))
    assert result.status == "incomplete"
    assert result.workflow_status == "capability_unavailable"
    assert result.quick_outcome is None


@pytest.mark.parametrize("module", ["planar_frame", "planar_truss", "two_way_slab"])
def test_planar_vertical_reaction_is_converted_at_column_base_interface(module):
    from app.core.scene_graph import _apply_reaction
    from app.core.scene_schemas import SceneConnection
    from app.core.schemas import CalculationModule
    source = calculate(CalculationRequest(mode="quick",module="steel_beam"))
    source.module = CalculationModule(module)
    source.reaction_envelopes = [ReactionEnvelope.model_validate(p) for p in packet(n=0,vy=10,vx=5)]
    target = _apply_reaction(CalculationRequest(mode="quick",module="steel_baseplate_anchor"),
        SceneConnection(id="c",source_node_id="a",target_node_id="b",transfer="reaction_package"),source)
    for p in target.inputs["upstream_reaction_envelopes"]:
        assert p["components"]["N"]["value"] == 10
        assert p["components"]["Vy"]["value"] == 0
        assert p["components"]["Vx"]["value"] == 5
