"""Scene fixtures are declared here, never imported from production defaults."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.core.scene_catalog import SCENE_FAMILIES, get_scene_family, get_scene_variant, instantiate_scene_graph
from app.core.scene_graph import execute_scene
from app.core.scene_schemas import SceneNodeCalculation
from app.core.schemas import CalculationRequest
from app.core.scene_typed_adapters import adapt_scene_requests, MODELS
from app.core.engine import calculate
from app.core.errors import CalculationInputError


EXPLICIT = {
    'frame_wind_exposed_height_m':1.2,
    'base_restraint':'fixed','poisson_ratio':0.2,
    'span_m':4.,'height_m':3.,'span_length_m':6.,'deck_width_m':2.5,'bay_spacing_m':3.,'roof_width_m':3.,
    'roof_member_tributary_width_m':1.,'reaction_conversion_spacing_m':1.,'post_height_m':2.5,
    'deflection_limit_mm':20.,'displacement_limit_mm':20.,'support_condition':'four_edges_simply_supported',
    'short_moment_capacity_kn_m_m':40.,'long_moment_capacity_kn_m_m':40.,'elastic_modulus_mpa':30000.,
    'beam_area_mm2':3456.,'beam_inertia_mm4':17e6,'beam_elastic_modulus_mpa':206000.,'beam_axial_capacity_kn':900.,'beam_shear_capacity_kn':200.,'beam_moment_capacity_kn_m':50.,'beam_self_weight_kn_m':0.271,
    'column_area_mm2':3456.,'column_inertia_mm4':12e6,'column_elastic_modulus_mpa':206000.,'column_axial_capacity_kn':900.,'column_shear_capacity_kn':200.,'column_moment_capacity_kn_m':50.,'column_self_weight_kn_m':0.271,
    'base_projection_m':0.2,'retained_soil_height_m':0.,'concrete_unit_weight_kn_m3':25.,'water_unit_weight_kn_m3':10.,'soil_unit_weight_kn_m3':18.,'soil_friction_angle_deg':30.,'surcharge_kpa':5.,'concrete_fc_mpa':14.3,'concrete_ft_mpa':1.43,'rebar_fy_mpa':360.,'rebar_es_mpa':200000.,
    'wall_vertical_as_mm2_m':1600.,'wall_horizontal_as_mm2_m':2400.,'base_x_as_mm2_m':1800.,'base_y_as_mm2_m':1800.,'wall_bar_diameter_mm':14.,'base_bar_diameter_mm':16.,'wall_cover_mm':35.,'base_cover_mm':40.,'minimum_reinforcement_ratio':0.002,'crack_width_limit_mm':0.2,'additional_ballast_kn':0.,'antifloat_factor':1.05,
    'girder_count':3.,'dead_load_kpa':0.8,'crowd_load_kpa':4.,'railing_load_kn_m':0.5,'wind_height_m':1.2,
    'timber_thickness_mm':80.,'timber_elastic_modulus_mpa':11000.,'timber_bending_strength_mpa':18.,'timber_shear_strength_mpa':2.,'timber_unit_weight_kn_m3':6.,'timber_deflection_limit_ratio':300.,
    'crossbeam_area_mm2':9000.,'crossbeam_inertia_mm4':240e6,'crossbeam_section_modulus_mm3':1200000.,'crossbeam_shear_area_mm2':5000.,'crossbeam_yield_strength_mpa':305.,'crossbeam_elastic_modulus_mpa':206000.,'crossbeam_unit_weight_kn_m3':78.5,
    'longitudinal_area_mm2':9000.,'longitudinal_inertia_mm4':600e6,'longitudinal_section_modulus_mm3':1200000.,'longitudinal_shear_area_mm2':5000.,'longitudinal_yield_strength_mpa':305.,'longitudinal_elastic_modulus_mpa':206000.,'longitudinal_unit_weight_kn_m3':78.5,
    'damping_ratio':0.02,'walking_frequency_hz':2.,'pedestrian_dynamic_force_n':280.,'acceleration_limit_m_s2':0.5,
    'deck_elevation_m':2.,'slab_thickness_mm':180.,'girder_width_mm':300.,'girder_height_mm':600.,
    'concrete_elastic_modulus_mpa':30000.,'concrete_compressive_strength_mpa':14.3,'concrete_tensile_strength_mpa':1.43,'rebar_yield_strength_mpa':360.,'concrete_density_kn_m3':25.,'maximum_reinforcement_ratio':0.04,'cover_mm':40.,'slab_bar_diameter_mm':12.,'slab_bar_spacing_mm':150.,'girder_bottom_area_mm2':4000.,'girder_top_area_mm2':3000.,'girder_stirrup_area_mm2':157.,'girder_stirrup_spacing_mm':150.,
    'minimum_vertical_frequency_hz':3.,'slab_deflection_ratio':250.,'girder_deflection_ratio':400.,'cracked_stiffness_factor':0.35,'railing_left_kn_m':1.,'railing_right_kn_m':1.,
    'cap_concrete_unit_weight_kn_m3':25.,'cap_groundwater_condition':'no_influence','cap_groundwater_source':'TEST explicitly no groundwater influence',
    'pile_spacing_x_mm':1600.,'pile_spacing_y_mm':1600.,'pile_size_mm':400.,'pile_type':'bored','compression_capacity_kn':500.,'uplift_capacity_kn':200.,'horizontal_capacity_kn':100.,'capacity_source':'TEST explicit geotechnical assumption',
    'cap_length_x_mm':3000.,'cap_width_y_mm':3000.,'cap_thickness_mm':500.,'cap_column_x_mm':500.,'cap_column_y_mm':500.,'cap_cover_mm':70.,'cap_bar_diameter_mm':20.,'cap_concrete_ft_mpa':1.43,'cap_rebar_fy_mpa':360.,'cap_provided_rebar_x_mm2_m':2500.,'cap_provided_rebar_y_mm2_m':2500.,'cap_minimum_reinforcement_ratio':0.0015,
    'base_slab_thickness_m':0.3,'wall_unit_weight_kn_m3':24.,'base_friction':0.6,'soil_bearing_kpa':300.,'material_compressive_design_kpa':1000.,'uplift_head_toe_m':0.,'uplift_head_heel_m':0.,'sliding_safety_factor':1.3,'overturning_safety_factor':1.6,
    'length_m':6.,'thickness_mm':180.,'support_spacing_m':3.,'opening_ratio':0.,'vertical_rebar_mm2_m':1200.,'horizontal_rebar_mm2_m':1200.,'bar_diameter_mm':12.,'slenderness_limit':150.,'infill_dead_load_kpa':0.5,'post_self_weight_kn_m':0.12,'post_area_mm2':3000.,'post_inertia_mm4':8e6,'post_section_modulus_mm3':8e4,'steel_elastic_modulus_mpa':206000.,'steel_yield_strength_mpa':235.,'effective_length_factor':1.,'maximum_post_spacing_m':3.,'masonry_unit_weight_kn_m3':19.,'masonry_bending_strength_mpa':0.4,'masonry_shear_strength_mpa':0.15,'masonry_compression_strength_mpa':2.,'minimum_thickness_mm':120.,'maximum_height_m':3.,
    # Explicit legacy-node screening fixture, including foundation and steel.
    'steel_grade':'Q355B','section_type':'RHS','h_mm':200.,'b_mm':100.,'t_mm':6.,'effective_length_m':3.,'unbraced_length_m':3.,'tributary_width_m':1.,
    'soil_capacity_kpa':120.,'soil_source':'TEST explicit assumption','groundwater_known':True,'groundwater_depth_m':5.,'width_m':2.,'embedment_m':0.8,
}


def fixture(family_id, variant_id):
    family=get_scene_family(family_id);variant=get_scene_variant(family,variant_id)
    parameters={**EXPLICIT,**{p.key:p.default for p in variant.parameters}}
    if variant_id=='viewing-platform':parameters['slab_load_distribution']='tributary_45_degree'
    if family_id=='water-feature-pool':
        parameters['retained_soil_height_m']=0 if 'above' in variant_id else parameters['wall_height_m']*(0.5 if 'semi' in variant_id else 1)
    loads=[x.model_copy(update={'adopted_value':x.recommended_default if x.recommended_default is not None else 0.5,'confirmed':True},deep=True) for x in variant.load_package.items]
    nodes=[]
    for node in instantiate_scene_graph(family,variant_id).nodes:
        if not node.calculation_module:continue
        inputs={**parameters,**{target:parameters[source] for target,source in node.input_bindings.items() if source in parameters},'scene_parameters':parameters}
        if node.calculation_module in {'spread_footing','strip_footing'}:
            inputs.update(length_m=2.,width_m=2.,thickness_mm=500.)
        if node.calculation_module == 'steel_baseplate_anchor':
            inputs.update(plate_length_mm=360.,plate_width_mm=360.,plate_thickness_mm=20.,column_depth_mm=200.,column_width_mm=200.,concrete_bearing_capacity_mpa=10.,anchor_count=4,anchor_diameter_mm=20.,anchor_grade='5.8',anchor_spacing_mm=260.,anchor_edge_mm=50.,anchor_head_diameter_mm=50.,weld_throat_mm=6.,contact_stiffness_kn_m3=1e7,contact_model_source='TEST explicit elastic contact assumption',anchor_springs=[{'x_m':x,'y_m':y,'stiffness_kn_m':1e5} for x,y in [(-.13,-.13),(.13,-.13),(.13,.13),(-.13,.13)]])
        if node.calculation_module in {'concrete_column','concrete_beam'}: inputs.update(b_mm=300.,h_mm=400.)
        nodes.append(SceneNodeCalculation(node_id=node.id,calculation=CalculationRequest(module=node.calculation_module,mode='quick',inputs=inputs,confirmed_assumptions=True)))
    return family,variant,nodes,loads


VARIANTS=[(f.id,v.id) for f in SCENE_FAMILIES for v in f.variants if v.availability=='public']


@pytest.mark.parametrize('family_id,variant_id',VARIANTS)
def test_full_scene_fixture_has_no_typed_adapter_gaps(family_id,variant_id):
    family,variant,nodes,loads=fixture(family_id,variant_id)
    result=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
    messages=[x.message for x in result.node_results.values() if x.message and ('显式场景参数' in x.message or '专项输入不完整' in x.message)]
    assert messages==[]
    assert all(result.node_results[n.node_id].calculation_result is not None
               for n in nodes if n.calculation.module.value in MODELS)
    assert all(x.calculation_result.verification_status=='unverified' for x in result.node_results.values() if x.calculation_result)


def typed_for(family_id,variant_id,module):
    family,variant,nodes,loads=fixture(family_id,variant_id)
    node=next(x for x in nodes if x.calculation.module.value==module)
    return adapt_scene_requests(node.calculation,family_id,variant_id,node.node_id,loads),node,loads


def test_missing_inputs_list_names_instead_of_using_tool_defaults():
    with pytest.raises(CalculationInputError) as error:
        adapt_scene_requests(CalculationRequest(module='pool_structure',mode='quick'), 'water-feature-pool','rect-above','pool_structure',[])
    assert error.value.code=='scene_adapter_missing_inputs'
    assert 'inside_length_m' in error.value.details['missing_fields']
    assert 'wall_vertical_as_mm2_m' in error.value.details['missing_fields']


def test_sign_signed_wind_and_geometric_force_balance():
    requests,node,loads=typed_for('signage-billboard','double-post','planar_frame')
    for request in requests:
        typed=request.typed_inputs;result=calculate(request)
        applied_x=sum(x.force_x.value for x in typed.nodal_loads)
        applied_y=sum(x.force_y.value for x in typed.nodal_loads)
        assert sum(x.components['Vx'].value for x in result.reaction_envelopes)==pytest.approx(-applied_x,abs=1e-8)
        assert sum(x.components['Vy'].value for x in result.reaction_envelopes)==pytest.approx(-applied_y,abs=1e-8)
    assert min(sum(x.force_x.value for x in r.typed_inputs.nodal_loads) for r in requests)<0
    assert max(sum(x.force_x.value for x in r.typed_inputs.nodal_loads) for r in requests)>0
    changed=node.calculation.model_copy(update={'inputs':{**node.calculation.inputs,'panel_width_m':4.8}},deep=True)
    twice=adapt_scene_requests(changed,'signage-billboard','double-post',node.node_id,loads)
    assert sum(x.force_x.value for x in twice[0].typed_inputs.nodal_loads)==pytest.approx(2*sum(x.force_x.value for x in requests[0].typed_inputs.nodal_loads))


@pytest.mark.parametrize('family,variant,module,key',[
    ('pergola-pavilion','mono-pitch','continuous_beam','bay_spacing_m'),
    ('entrance-frame','unequal-columns','planar_frame','right_height_m'),
    ('boardwalk-platform','viewing-platform','two_way_slab','long_span_m'),
    ('water-feature-pool','rect-above','pool_structure','inside_length_m'),
    ('landscape-bridge','single-straight','bridge_steel_timber','span_length_m'),
    ('landscape-bridge','single-rc-shallow','bridge_rc','span_length_m'),
    ('landscape-wall-fence','concrete-straight','site_rc_wall','height_m'),
    ('landscape-wall-fence','steel-infill','steel_infill_wall','height_m'),
    ('landscape-wall-fence','plain-masonry','plain_masonry_wall','height_m'),
    ('retaining-facility','gravity','gravity_retaining_wall','retained_height_m'),
])
def test_each_primary_adapter_geometry_changes_computed_reactions(family,variant,module,key):
    requests,node,loads=typed_for(family,variant,module)
    base=calculate(requests[0])
    inputs=deepcopy(node.calculation.inputs);inputs[key]*=1.1
    changed=adapt_scene_requests(node.calculation.model_copy(update={'inputs':inputs},deep=True),family,variant,node.node_id,loads)
    result=calculate(changed[0])
    def signature(result):return [round(q.value,8) for e in result.reaction_envelopes for q in e.components.values()]
    assert signature(result)!=signature(base)


@pytest.mark.parametrize('family,variant,module',[
    ('pergola-pavilion','mono-pitch','continuous_beam'),
    ('signage-billboard','double-post','planar_frame'),
    ('boardwalk-platform','viewing-platform','two_way_slab'),
    ('landscape-bridge','single-straight','bridge_steel_timber'),
    ('landscape-bridge','single-rc-shallow','bridge_rc'),
    ('landscape-wall-fence','concrete-straight','site_rc_wall'),
    ('landscape-wall-fence','steel-infill','steel_infill_wall'),
    ('landscape-wall-fence','plain-masonry','plain_masonry_wall'),
])
def test_each_loaded_adapter_responds_to_scene_load_not_tool_default(family,variant,module):
    requests,node,loads=typed_for(family,variant,module)
    changed_loads=[x.model_copy(update={'adopted_value':2*x.adopted_value},deep=True) for x in loads]
    changed=adapt_scene_requests(node.calculation,family,variant,node.node_id,changed_loads)
    baseline=calculate(requests[0]);result=calculate(changed[0])
    assert [x.components for x in baseline.reaction_envelopes]!=[x.components for x in result.reaction_envelopes]


@pytest.mark.parametrize('variant',['mono-pitch','dual-pitch','multi-bay'])
def test_pitched_frame_integrates_vertical_load_in_global_coordinates(variant):
    from app.core.scene_typed_adapters import apply_vertical_line, include_member_self_weight
    requests,_,_=typed_for('pergola-pavilion',variant,'planar_frame')
    typed=apply_vertical_line(requests[0].typed_inputs,-7.)
    request=requests[0].model_copy(update={'typed_inputs':typed},deep=True)
    result=calculate(request)
    count=2 if variant=='multi-bay' else 1
    assert sum(e.components['Vy'].value for e in result.reaction_envelopes)==pytest.approx(7*4*count,abs=1e-7)
    assert sum(e.components['Vx'].value for e in result.reaction_envelopes)==pytest.approx(0,abs=1e-7)
    roof_diagrams=[d for d in result.diagrams if d.name.startswith('roof')]
    assert roof_diagrams
    for diagram in roof_diagrams:
        assert any(abs(point.value.value)>0.01 for point in diagram.points[1:-1])
    assert any(c.name.startswith('roof') and c.demand.unit=='mm' and c.demand.value>0 for c in result.checks)
    weighted=calculate(include_member_self_weight(request))
    assert sum(e.components['Vy'].value for e in weighted.reaction_envelopes)>7*4*count


def test_point_load_is_not_multiplied_by_span_as_if_it_were_a_line_load():
    requests,node,loads=typed_for('entrance-frame','multi-span','planar_frame')
    point=loads[0].model_copy(update={'unit':'kN','distribution':'point','adopted_value':10.},deep=True)
    with pytest.raises(CalculationInputError) as exc:
        adapt_scene_requests(node.calculation,'entrance-frame','multi-span',node.node_id,[point])
    assert f'load:{point.id}:physical_application_position' in exc.value.details['missing_fields']


def test_beam_and_slab_exact_total_load_balance():
    requests,_,_=typed_for('pergola-pavilion','mono-pitch','continuous_beam')
    for request in requests:
        result=calculate(request)
        assert sum(e.components['Vy'].value for e in result.reaction_envelopes)==pytest.approx(-sum(x.length.value*x.uniform_load_local_y.value for x in request.typed_inputs.spans))
    requests,_,_=typed_for('boardwalk-platform','viewing-platform','two_way_slab')
    for request in requests:
        result=calculate(request);typed=request.typed_inputs
        assert sum(e.components['Vy'].value for e in result.reaction_envelopes)==pytest.approx(typed.uniform_load.value*typed.short_span.value*typed.long_span.value)


def test_pool_water_mass_and_retaining_surcharge_balance():
    requests,node,loads=typed_for('water-feature-pool','rect-above','pool_structure')
    inputs={**node.calculation.inputs,'internal_water_depth_m':1.3}
    changed=adapt_scene_requests(node.calculation.model_copy(update={'inputs':inputs}), 'water-feature-pool','rect-above',node.node_id,loads)
    before=calculate(requests[0]);after=calculate(changed[0])
    def n(result):return next(e.components['N'].value for e in result.reaction_envelopes if e.combination_id=='full-sls-service')
    assert n(after)-n(before)==pytest.approx(0.1*6*3*10)
    requests,node,loads=typed_for('retaining-facility','gravity','gravity_retaining_wall')
    inputs={**node.calculation.inputs,'surcharge_kpa':15.}
    changed=adapt_scene_requests(node.calculation.model_copy(update={'inputs':inputs}), 'retaining-facility','gravity',node.node_id,loads)
    before=calculate(requests[0]);after=calculate(changed[0])
    assert after.reaction_envelopes[0].components['Vx'].value-before.reaction_envelopes[0].components['Vx'].value==pytest.approx((15-5)*2/3)


@pytest.mark.parametrize('module,variant,state',[('bridge_steel_timber','multi-span','sls-service'),('bridge_rc','multi-rc-shallow','SLS-standard')])
def test_bridge_crowd_increment_matches_integrated_deck_area(module,variant,state):
    requests,node,loads=typed_for('landscape-bridge',variant,module)
    changed_loads=[x.model_copy(update={'adopted_value':x.adopted_value+1.0},deep=True) if x.kind=='live' else x for x in loads]
    changed=adapt_scene_requests(node.calculation,'landscape-bridge',variant,node.node_id,changed_loads)
    before=calculate(requests[0]);after=calculate(changed[0])
    def total(result):return sum(e.components['N'].value for e in result.reaction_envelopes if e.combination_id==state)
    assert total(after)-total(before)==pytest.approx(2*6*2.5,abs=1e-7)


def test_pile_adapter_preserves_all_combinations_and_signed_six_components():
    from app.core.scene_graph import _apply_reaction
    family,variant,nodes,loads=fixture('landscape-bridge','single-rc-pile')
    result=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
    source=result.node_results['bridge_superstructure'].calculation_result
    left=result.node_results['support_left'].calculation_result
    assert left is not None
    assert {e.combination_id for e in source.reaction_envelopes}=={e.combination_id for e in left.reaction_envelopes}
    request=next(n for n in nodes if n.node_id=='support_left')
    adapted=adapt_scene_requests(request.calculation,family.id,variant.id,request.node_id,loads)[0]
    connection=next(c for c in instantiate_scene_graph(family,variant.id).connections if c.target_node_id=='support_left')
    for envelope in source.reaction_envelopes:
        if envelope.name!='S1':continue
        selected=source.model_copy(update={'reaction_envelopes':[envelope]},deep=True)
        mapped=_apply_reaction(adapted,connection,selected).typed_inputs
        for field,component in [('axial','N'),('shear_x','Vx'),('shear_y','Vy'),('moment_x','Mx'),('moment_y','My'),('torsion','T')]:
            assert getattr(mapped.effects,field).value==envelope.components[component].value


def test_platform_four_edges_and_four_corners_conserve_every_combination():
    from app.core.loads import FACTOR_SETS
    family,variant,nodes,loads=fixture('boardwalk-platform','viewing-platform')
    result=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
    deck=result.node_results['deck'].calculation_result
    assert len([n for n in result.node_results if n.startswith('platform_foundation_')])==4
    for packet in deck.reaction_envelopes:
        factor=next(f['self_weight'] for name,_,f in FACTOR_SETS if packet.combination_name.startswith(name))
        total=packet.components['Vy'].value
        edge_total=corner_total=0.
        for edge in ('south','north','west','east'):
            beam=result.node_results[f'edge_{edge}'].calculation_result
            reaction=sum(e.components['Vy'].value for e in beam.reaction_envelopes if e.combination_id==packet.combination_id)
            length=3. if edge in {'south','north'} else 4.5
            area=3*3/4 if edge in {'south','north'} else 3*4.5/2-3*3/4
            expected=total*area/(3*4.5)+length*.271*factor
            assert reaction==pytest.approx(expected,abs=1e-7)
            edge_total+=reaction
        for corner in ('south_west','south_east','north_west','north_east'):
            base=result.node_results[f'platform_base_{corner}'].calculation_result
            reaction=next(e.components['N'].value for e in base.reaction_envelopes if e.combination_id==packet.combination_id)
            corner_total+=reaction
            assert reaction==pytest.approx(edge_total/4,abs=1e-7)
        assert corner_total==pytest.approx(total+(2*3+2*4.5)*.271*factor,abs=1e-7)


def test_platform_requires_explicit_distribution_and_does_not_claim_fixed_edge_transfer():
    family,variant,nodes,loads=fixture('boardwalk-platform','viewing-platform')
    node=next(n for n in nodes if n.node_id=='deck')
    for updates in [{'slab_load_distribution':'待选择'},{'support_condition':'four_edges_fixed'}]:
        request=node.calculation.model_copy(update={'inputs':{**node.calculation.inputs,**updates}},deep=True)
        with pytest.raises(CalculationInputError):
            adapt_scene_requests(request,family.id,variant.id,node.node_id,loads)


def test_guided_grid_propagates_incomplete_stability_scope(monkeypatch):
    from tests.test_scene_space_frame import _profile
    import app.core.scene_graph as graph_module
    family,variant,_,loads=fixture('pergola-pavilion','guided-grid')
    monkeypatch.setattr(graph_module,'analyze_scene_space_frame',lambda *args,**kwargs:{
        'stability_scope':{'status':'incomplete','excluded_truss_member_ids':['brace']},
        'verification_status':'unverified'})
    result=execute_scene(family,variant.id,'quick',[],load_cases=loads,structural_profile=_profile('rhs-200x100x6'))
    assert result.workflow_status=='capability_unavailable'
    assert result.quick_outcome is None
    assert result.status=='incomplete'
    assert result.catalog_versions['space_frame_solver']=='steel-compass-space-frame-adapter-2.1-unverified'


def test_pile_cap_thickness_adds_self_weight_with_actual_source_combination_factors_once():
    from app.core.scene_graph import _apply_reaction
    from app.core.scene_typed_adapters import include_pile_cap_weight
    family,variant,nodes,loads=fixture('landscape-bridge','single-rc-pile')
    result=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
    source=result.node_results['bridge_superstructure'].calculation_result
    left=next(n for n in nodes if n.node_id=='support_left')
    connection=next(c for c in instantiate_scene_graph(family,variant.id).connections if c.target_node_id=='support_left')
    for combination in source.combinations:
        selected=source.model_copy(update={'reaction_envelopes':[e for e in source.reaction_envelopes if e.combination_id==combination.combination_id]},deep=True)
        prepared=[]
        for thickness in (500.,1000.):
            raw=left.calculation.model_copy(update={'inputs':{**left.calculation.inputs,'cap_thickness_mm':thickness}},deep=True)
            adapted=adapt_scene_requests(raw,family.id,variant.id,left.node_id,loads)[0]
            transferred=_apply_reaction(adapted,connection,selected)
            weighted=include_pile_cap_weight(transferred)
            assert include_pile_cap_weight(weighted)==weighted
            prepared.append(weighted)
        extra=3*3*.5*25*combination.factors['permanent']
        assert prepared[1].typed_inputs.effects.axial.value-prepared[0].typed_inputs.effects.axial.value==pytest.approx(extra)
        before=calculate(prepared[0]);after=calculate(prepared[1])
        assert sum(e.components['N'].value for e in after.reaction_envelopes)-sum(e.components['N'].value for e in before.reaction_envelopes)==pytest.approx(extra)
        wet=prepared[0].model_copy(update={'inputs':{**prepared[0].inputs,'cap_self_weight_applied':False,'cap_groundwater_condition':'known_water_table','cap_submerged_depth_m':.2,'cap_water_unit_weight_kn_m3':10.,'cap_buoyancy_factor_uls':1.35},'typed_inputs':transferred.typed_inputs.model_copy(update={'cap':prepared[0].typed_inputs.cap},deep=True)},deep=True)
        # Reuse the original unweighted effect, with a known submerged depth.
        wet.typed_inputs.effects=transferred.typed_inputs.effects
        weighted_wet=include_pile_cap_weight(wet)
        assert weighted_wet.inputs['cap_factored_buoyancy_kn']==pytest.approx(9*.2*10*(1 if combination.limit_state=='SLS' else 1.35))


@pytest.mark.parametrize('variant,count',[('mono-pitch',1),('dual-pitch',1),('multi-bay',2)])
def test_pergola_both_end_frames_receive_full_roof_dead_increment(variant,count):
    family,variant_obj,nodes,loads=fixture('pergola-pavilion',variant)
    baseline=execute_scene(family,variant,'quick',nodes,load_cases=loads)
    extra=[x.model_copy(update={'adopted_value':x.adopted_value+1,'override_reason':'independent +1kPa sensitivity'},deep=True) if x.kind=='dead' else x for x in loads]
    changed=execute_scene(family,variant,'quick',nodes,load_cases=extra)
    def total(result):
        return sum(e.components['N'].value for n in result.node_results.values()
                   if n.calculation_result and n.calculation_result.module.value=='steel_baseplate_anchor'
                   for e in n.calculation_result.reaction_envelopes if e.combination_id=='SLS-scene-1-5')
    assert total(changed)-total(baseline)==pytest.approx(4*3*count,abs=1e-7)
    assert 'rear_frame' in baseline.node_results


def test_platform_local_line_action_is_added_once_to_matching_upstream_case():
    family,variant,nodes,loads=fixture('boardwalk-platform','viewing-platform')
    baseline=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
    extra=loads[0].model_copy(update={'id':'custom-edge-line','value_type':'project_defined','source_reference':'independent explicit line load','application_target':'edge_south','distribution':'line','unit':'kN/m','adopted_value':10.,'recommended_default':None},deep=True)
    changed=execute_scene(family,variant.id,'quick',nodes,load_cases=[*loads,extra])
    case='SLS-scene-1-5'
    packets=changed.node_results['edge_south'].calculation_result.reaction_envelopes
    assert len([e for e in packets if e.combination_id==case])==2
    for corner in ('south_west','south_east','north_west','north_east'):
        def n(result):
            return next(e.components['N'].value for e in result.node_results[f'platform_base_{corner}'].calculation_result.reaction_envelopes if e.combination_id==case)
        assert n(changed)-n(baseline)==pytest.approx(15 if corner.startswith('south') else 0,abs=1e-7)


def test_sloped_member_axial_udl_recovers_internal_force_not_only_support_balance():
    from app.core.schemas import PlanarFrameInputs
    from app.core.scene_typed_adapters import apply_vertical_line,q
    import math
    typed=PlanarFrameInputs.model_validate({'module':'planar_frame','combination_id':'SLS-probe','combination_name':'SLS independent slope probe','limit_state':'SLS',
        'nodes':[{'id':'A','x':q(0,'m'),'y':q(0,'m')},{'id':'B','x':q(4,'m'),'y':q(2,'m')}],
        'members':[{'id':'beam','start':'A','end':'B','area':q(4000,'mm2'),'inertia':q(80e6,'mm4'),'elastic_modulus':q(206000,'MPa'),'axial_capacity':q(1000,'kN'),'shear_capacity':q(1000,'kN'),'moment_capacity':q(1000,'kN*m')}],
        'restraints':[{'node':'A','ux':True,'uy':True},{'node':'B','uy':True}], 'displacement_limit':q(100,'mm')})
    typed=apply_vertical_line(typed,-7)
    result=calculate(CalculationRequest(module='planar_frame',mode='quick',typed_inputs=typed))
    axial=next(c.demand.value for c in result.checks if '轴力需求' in c.name)
    assert axial==pytest.approx(14*2/math.sqrt(20),abs=1e-9)
    assert sum(e.components['Vy'].value for e in result.reaction_envelopes)==pytest.approx(28)
    assert max(abs(p.value.value) for d in result.diagrams for p in d.points)==pytest.approx(14)


if __name__=='__main__':
    rows=[]
    for family_id,variant_id in VARIANTS:
        family,variant,nodes,loads=fixture(family_id,variant_id)
        result=execute_scene(family,variant.id,'quick',nodes,load_cases=loads)
        rows.append({'family':family_id,'variant':variant_id,'workflow_status':result.workflow_status,'quick_outcome':result.quick_outcome,'nodes':[{'id':n.node_id,'status':n.workflow_status,'calculation_status':n.calculation_result.status if n.calculation_result else None,'has_calculation_result':n.calculation_result is not None,'message':n.message,'warning_codes':[w.code for w in n.calculation_result.warnings] if n.calculation_result else [],'verification_status':n.calculation_result.verification_status if n.calculation_result else n.verification_status} for n in result.node_results.values()]})
    path=Path('../docs/calculation-completion-20260926/scene-variant-matrix.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
