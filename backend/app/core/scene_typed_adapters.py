"""Explicit scene -> typed contracts. No single-tool defaults are used here.

Dimensions come from the saved scene parameters, and specialist properties from
the node's saved inputs. A missing value is an input gap, never an assumed value.
"""
from __future__ import annotations

from math import isfinite, radians, tan, hypot
from itertools import product
from pydantic import ValidationError

from . import schemas as s
from .errors import CalculationInputError
from .loads import FACTOR_SETS
from .sections import steel_section
from .steel import steel_design_strength

MODELS = {
    'continuous_beam': s.ContinuousBeamInputs, 'planar_frame': s.PlanarFrameInputs,
    'two_way_slab': s.TwoWaySlabInputs, 'pool_structure': s.PoolStructureInputs,
    'pile_group_cap': s.PileGroupCapInputs, 'bridge_steel_timber': s.BridgeSteelTimberInputs,
    'bridge_rc': s.BridgeRCInputs, 'gravity_retaining_wall': s.GravityRetainingWallInputs,
    'site_rc_wall': s.SiteRCWallInputs, 'steel_infill_wall': s.SteelInfillWallInputs,
    'plain_masonry_wall': s.PlainMasonryWallInputs,
}

# Unit declarations are part of the scene input contract, not inferred values.
UNITS = {
    'm': 'inside_length inside_width wall_height base_projection retained_soil_height wall_horizontal_span full_internal_depth empty_external_head full_external_head span_length deck_width crossbeam_spacing deck_elevation retained_height base_width base_slab_thickness wall_bottom_thickness wall_top_thickness toe_projection water_depth_behind uplift_head_toe uplift_head_heel height length support_spacing maximum_post_spacing minimum_thickness_m maximum_height short_span long_span',
    'mm': 'wall_thickness base_thickness wall_bar_diameter base_bar_diameter wall_cover base_cover crack_width_limit thickness diameter_or_side length_x width_y column_x column_y cover bar_diameter girder_width girder_height slab_thickness slab_bar_diameter slab_bar_spacing girder_stirrup_spacing minimum_thickness deflection_limit displacement_limit',
    'MPa': 'concrete_fc concrete_ft rebar_fy rebar_es elastic_modulus bending_strength shear_strength yield_strength concrete_elastic_modulus concrete_compressive_strength concrete_tensile_strength rebar_yield_strength steel_elastic_modulus steel_yield_strength masonry_bending_strength masonry_shear_strength masonry_compression_strength',
    'kN/m3': 'concrete_unit_weight water_unit_weight soil_unit_weight wall_unit_weight unit_weight concrete_density masonry_unit_weight',
    'kPa': 'surcharge allowable_bearing crowd_load additional_dead_load soil_bearing_capacity material_compressive_design wind_pressure infill_dead_load',
    'mm2/m': 'wall_vertical_as wall_horizontal_as base_x_as base_y_as provided_rebar_x provided_rebar_y vertical_rebar horizontal_rebar',
    '1': 'minimum_reinforcement_ratio maximum_reinforcement_ratio antifloat_factor span_count longitudinal_girder_count deflection_limit_ratio damping_ratio girder_count slab_deflection_ratio girder_deflection_ratio cracked_stiffness_factor base_friction_coefficient sliding_safety_factor overturning_safety_factor opening_ratio effective_length_factor slenderness_limit',
    'deg': 'soil_friction_angle', 'kN': 'additional_ballast compression uplift horizontal axial_capacity shear_capacity',
    'kN/m': 'railing_dead_load_per_side wind_line_load railing_left railing_right post_self_weight',
    'mm2': 'area shear_area girder_bottom_area girder_top_area girder_stirrup_area post_area',
    'mm3': 'section_modulus post_section_modulus', 'mm4': 'inertia post_inertia',
    'Hz': 'walking_frequency minimum_vertical_frequency', 'N': 'pedestrian_dynamic_force',
    'm/s2': 'acceleration_limit', 'kN*m': 'moment_capacity',
    'kN*m/m': 'short_direction_moment_capacity long_direction_moment_capacity',
}
FIELD_UNITS = {name: unit for unit, names in UNITS.items() for name in names.split()}
SUFFIX = {'1': '', 'm':'_m','mm':'_mm','MPa':'_mpa','kN/m3':'_kn_m3','kPa':'_kpa','mm2/m':'_mm2_m','deg':'_deg','kN':'_kn','kN/m':'_kn_m','mm2':'_mm2','mm3':'_mm3','mm4':'_mm4','Hz':'_hz','N':'_n','m/s2':'_m_s2','kN*m':'_kn_m','kN*m/m':'_kn_m_m'}
ALIASES = {
    'full_internal_depth':'internal_water_depth_m', 'empty_external_head':'external_water_head_m',
    'full_external_head':'external_water_head_m', 'longitudinal_girder_count':'girder_count',
    'additional_dead_load':'dead_load_kpa', 'railing_dead_load_per_side':'railing_load_kn_m',
    'wind_line_load':'wind_load_kn_m', 'soil_bearing_capacity':'soil_bearing_kpa',
    'base_friction_coefficient':'base_friction', 'water_depth_behind':'water_depth_behind_m',
    'short_direction_moment_capacity':'short_moment_capacity_kn_m_m',
    'long_direction_moment_capacity':'long_moment_capacity_kn_m_m',
}


def saved_section_properties(specification, entry):
    dimensions=dict(entry.dimensions)
    properties=steel_section({'section_type':'H' if entry.family=='I' else entry.family,**dimensions})
    strength=steel_design_strength(specification.material_grade,max(float(dimensions.get('t_mm',0)),float(dimensions.get('tw_mm',0)),float(dimensions.get('tf_mm',0))))
    weak=specification.orientation=='weak_axis'
    prefix=specification.member_role+'_'
    return {prefix+'area_mm2':properties.area_mm2,
        prefix+'inertia_mm4':properties.iy_mm4 if weak else properties.ix_mm4,
        prefix+'elastic_modulus_mpa':206000,
        prefix+'axial_capacity_kn':properties.area_mm2*strength['fd']/1000,
        prefix+'shear_capacity_kn':properties.shear_area_mm2*strength['fv']/1000,
        prefix+'moment_capacity_kn_m':(properties.wy_mm3 if weak else properties.wx_mm3)*strength['fd']/1e6,
        prefix+'self_weight_kn_m':properties.self_weight_kn_m}


def q(value, unit):
    return {'value': float(value), 'unit': unit}


class Reader:
    def __init__(self, inputs):
        self.values = {**inputs.get('scene_parameters', {}), **inputs}
        self.missing = []

    def value(self, key, *, aliases=()):
        for candidate in (key, *aliases):
            if candidate in self.values and self.values[candidate] is not None:
                return self.values[candidate]
        self.missing.append(key)
        return 0.0

    def number(self, key, *, aliases=()):
        value = self.value(key, aliases=aliases)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            self.missing.append(key)
            return 0.0
        return float(value)

    def quantity(self, field, prefix=''):
        unit = FIELD_UNITS[field]
        key = f'{prefix}{field}{SUFFIX[unit]}'
        aliases = [f'{prefix}{field}']
        if field in ALIASES:
            aliases.append(f'{prefix}{ALIASES[field]}')
        return q(self.number(key, aliases=aliases), unit)

    def group(self, cls, prefix=''):
        return {field: self.quantity(field, prefix) for field, info in cls.model_fields.items()
                if info.is_required() and field in FIELD_UNITS}

    def finish(self, node_id):
        if self.missing:
            fields = sorted(set(self.missing))
            raise CalculationInputError('scene_adapter_missing_inputs',
                f'节点 {node_id} 缺少显式场景参数：' + '、'.join(fields),
                details={'node_id':node_id, 'missing_fields':fields})


def _combination(index=0):
    return {'combination_id':f'SCENE-{index + 1}', 'combination_name':f'场景作用组合 {index + 1}', 'limit_state':'ULS'}


def _actions(loads, reader, target_node_id):
    """Keep mutually exclusive signs apart; apply declared factors once."""
    loads=[x for x in loads if x.kind in FACTOR_SETS[0][2]]
    for x in loads:
        if x.adopted_value is None:
            reader.missing.append(f'load:{x.id}')
    if not loads: return [(_combination(), [])]
    kinds = sorted({x.kind for x in loads})
    choices=[]
    for kind in kinds:
        directions=sorted({x.direction for x in loads if x.kind==kind})
        choices.append([[x for x in loads if x.kind==kind and x.direction==d] for d in directions])
    cases=[]
    for branch,selected in enumerate(product(*choices)):
        for index,(name,state,factors) in enumerate(FACTOR_SETS):
            cases.append(({'combination_id':f'{state}-scene-{branch+1}-{index+1}',
                'combination_name':name, 'limit_state':state},
                [(x,factors[x.kind]) for items in selected for x in items if x.application_target==target_node_id]))
    return cases


def apply_vertical_line(typed, line_value):
    """Global vertical load per projected horizontal metre on every roof member.

    Local transverse and axial UDLs reproduce the global
    vertical resultant even on mono/dual pitched and unequal-height rafters.
    """
    coordinates={x.id:(x.x.value,x.y.value) for x in typed.nodes}
    uniform=list(typed.uniform_loads)
    for member in typed.members:
        x0,y0=coordinates[member.start];x1,y1=coordinates[member.end]
        dx=x1-x0;dy=y1-y0;length=hypot(dx,dy)
        if abs(dx)<1e-12:continue
        c=dx/length;sn=dy/length
        global_line=line_value*abs(c)
        uniform.append(s.FrameUniformLoadInput(member=member.id,
            local_y=s.TypedInputValue(value=global_line*c,unit='kN/m'),
            local_x=s.TypedInputValue(value=global_line*sn,unit='kN/m')))
    return typed.model_copy(update={'uniform_loads':uniform},deep=True)


def include_member_self_weight(request):
    """Add receiving member weight once after transfer, with the same case factor."""
    typed=request.typed_inputs
    if isinstance(typed,s.PileGroupCapInputs):return include_pile_cap_weight(request)
    if not isinstance(typed,(s.ContinuousBeamInputs,s.PlanarFrameInputs,s.TwoWaySlabInputs)):return request
    r=Reader(request.inputs)
    factors=next((f for name,state,f in FACTOR_SETS if typed.combination_name.startswith(name)),None)
    factor=factors['self_weight'] if factors else (1. if typed.limit_state=='SLS' else 1.3)
    if isinstance(typed,s.ContinuousBeamInputs):
        weight=r.number('beam_self_weight_kn_m')*factor
        typed=typed.model_copy(update={'spans':[span.model_copy(update={'uniform_load_local_y':s.TypedInputValue(value=span.uniform_load_local_y.value-weight,unit='kN/m')}) for span in typed.spans]},deep=True)
    elif isinstance(typed,s.TwoWaySlabInputs):
        weight=r.number('concrete_unit_weight_kn_m3')*typed.thickness.value/1000*factor
        typed=typed.model_copy(update={'uniform_load':s.TypedInputValue(value=typed.uniform_load.value+weight,unit='kN/m2')},deep=True)
    else:
        points={x.id:(x.x.value,x.y.value) for x in typed.nodes}
        uniform=list(typed.uniform_loads);nodal=list(typed.nodal_loads)
        for member in typed.members:
            x0,y0=points[member.start];x1,y1=points[member.end];length=hypot(x1-x0,y1-y0)
            c=(x1-x0)/length;sn=(y1-y0)/length
            role='column' if abs(c)<1e-12 else 'beam'
            weight=r.number(role+'_self_weight_kn_m')*factor
            uniform.append(s.FrameUniformLoadInput(member=member.id,local_y=s.TypedInputValue(value=-weight*c,unit='kN/m'),local_x=s.TypedInputValue(value=-weight*sn,unit='kN/m')))
        typed=typed.model_copy(update={'uniform_loads':uniform,'nodal_loads':nodal},deep=True)
    r.finish('self_weight')
    return request.model_copy(update={'typed_inputs':typed},deep=True)


def include_pile_cap_weight(request):
    if request.inputs.get('cap_self_weight_applied'):return request
    typed=request.typed_inputs;r=Reader(request.inputs)
    packets=request.inputs.get('upstream_reaction_envelopes',[])
    packet=next((x for x in packets if x.get('combination_id')==typed.combination_id),{})
    factors=packet.get('action_factors',{})
    permanent_factor=factors.get('permanent',factors.get('dead',factors.get('self_weight')))
    if permanent_factor is None:
        r.missing.append('upstream_combination_permanent_factor')
        permanent_factor=0.
    unit_weight=r.number('cap_concrete_unit_weight_kn_m3')
    condition=r.value('cap_groundwater_condition')
    source=r.value('cap_groundwater_source')
    if not isinstance(source,str) or not source.strip():r.missing.append('cap_groundwater_source')
    submerged=0.;water=0.;buoyancy_factor=0.
    thickness=typed.cap.thickness.value/1000
    if condition=='known_water_table':
        submerged=r.number('cap_submerged_depth_m');water=r.number('cap_water_unit_weight_kn_m3')
        if not 0<=submerged<=thickness:r.missing.append('cap_submerged_depth_m (0..cap thickness)')
        if 'uplift' in factors:buoyancy_factor=factors['uplift']
        elif typed.limit_state=='SLS':buoyancy_factor=1.
        else:buoyancy_factor=r.number('cap_buoyancy_factor_uls')
    elif condition!='no_influence':r.missing.append('cap_groundwater_condition (no_influence or known_water_table)')
    if unit_weight<=0:r.missing.append('cap_concrete_unit_weight_kn_m3 (>0)')
    r.finish('pile_cap_self_weight')
    area=typed.cap.length_x.value*typed.cap.width_y.value/1e6
    dead=area*thickness*unit_weight*permanent_factor
    buoyancy=area*submerged*water*buoyancy_factor
    typed=typed.model_copy(update={'effects':typed.effects.model_copy(update={'axial':s.TypedInputValue(value=typed.effects.axial.value+dead-buoyancy,unit='kN')},deep=True)},deep=True)
    return request.model_copy(update={'typed_inputs':typed,'inputs':{**request.inputs,
        'cap_self_weight_applied':True,'cap_factored_self_weight_kn':dead,'cap_factored_buoyancy_kn':buoyancy}},deep=True)


def _load_totals(case, reader, width=None, horizontal_width=None):
    vertical = horizontal = moment = 0.0
    for item, factor in case:
        value = float(item.adopted_value or 0) * factor
        if item.unit in {'kPa','kN/m2'}:
            adopted_width=horizontal_width if item.direction in {'x_positive','x_negative'} and horizontal_width is not None else width
            if adopted_width is None:
                reader.missing.append('tributary_width_m')
                continue
            value *= adopted_width
        elif item.unit in {'kN','kN.m','kN·m'}:
            # Scene graph targets identify a calculation node, not a physical
            # member location. Never reinterpret a point action as a UDL.
            reader.missing.append(f'load:{item.id}:physical_application_position')
            continue
        elif item.unit != 'kN/m':
            reader.missing.append(f'unsupported_load_unit:{item.id}:{item.unit}')
            continue
        if item.unit in {'kN.m','kN·m'}:
            moment += value
        elif item.direction == 'gravity': vertical -= value
        elif item.direction == 'uplift': vertical += value
        elif item.direction in {'x_positive','x_negative'}:
            horizontal += value * (-1 if item.direction == 'x_negative' else 1)
        else: reader.missing.append(f'unsupported_load_direction:{item.id}:{item.direction}')
    return vertical, horizontal, moment


def _beam(reader, family, variant, node_id, case):
    # Roof members run longitudinally between frame planes; platform beams
    # follow their own slab dimensions, never a hidden roof-grid dimension.
    length = reader.number('short_span_m' if node_id in {'edge_south','edge_north'} else 'long_span_m') if family=='boardwalk-platform' else reader.number('bay_spacing_m')
    width = reader.number('roof_member_tributary_width_m') if family=='pergola-pavilion' else 1.
    props = {f:reader.quantity(f, 'beam_') for f in ('elastic_modulus','inertia','moment_capacity','shear_capacity')}
    vertical, horizontal, moment = _load_totals(case, reader, width)
    if horizontal or moment: reader.missing.append('roof_member_horizontal_or_moment_load_model')
    if family=='boardwalk-platform':
        a=reader.number('short_span_m')
        breakpoints=sorted({0.,a/2,length-a/2,length})
        positions=[breakpoints[0]]
        for left,right in zip(breakpoints,breakpoints[1:]):
            positions += [left+(right-left)*i/8 for i in range(1,9)]
        nodes=[f'E{i}' for i in range(len(positions))]
        return {'nodes':nodes,'spans':[{'id':f'edge_segment{i}','start':nodes[i],'end':nodes[i+1],
            'length':q(right-left,'m'),**props,'uniform_load_local_y':q(vertical,'kN/m')}
            for i,(left,right) in enumerate(zip(positions,positions[1:]))],
            'supports':[{'node':nodes[0],'vertical':True},{'node':nodes[-1],'vertical':True}],
            'deflection_limit':reader.quantity('deflection_limit')}
    return {'nodes':['B0','B1'], 'spans':[{'id':'roof_member','start':'B0','end':'B1','length':q(length,'m'),
        **props,'uniform_load_local_y':q(vertical,'kN/m')}],
        'supports':[{'node':'B0','vertical':True}, {'node':'B1','vertical':True}],
        'deflection_limit':reader.quantity('deflection_limit')}


def _frame(reader, family, variant, case):
    signage = family == 'signage-billboard'
    count = 2 if variant in {'multi-span','multi-bay'} else 1
    if count == 2 and reader.number('bay_count') != 2:
        reader.missing.append('bay_count (this graph requires exactly 2 bays)')
    span = reader.number('post_spacing_m' if signage and variant == 'double-post' else 'span_m') if variant != 'ground-mounted' else 0
    height = reader.number('post_height_m' if signage else 'height_m')
    restraint=reader.value('base_restraint')
    if restraint not in {'fixed','pinned'}:reader.missing.append('base_restraint (fixed or pinned)')
    right_height = reader.number('right_height_m') if variant in {'unequal-columns','multi-bay'} else height
    if variant == 'mono-pitch': right_height = height + span * tan(radians(reader.number('roof_slope_deg')))
    positions = [(i*span, height+(right_height-height)*i/count) for i in range(count+1)]
    if variant == 'ground-mounted': positions = [(0,height)]
    nodes=[]; members=[]; restraints=[]
    def member(mid,start,end,role):
        properties={f:reader.quantity(f, role+'_') for f in ('area','inertia','elastic_modulus','axial_capacity','shear_capacity','moment_capacity')}
        members.append({'id':mid,'start':start,'end':end,**properties})
    for i,(x,y) in enumerate(positions):
        nodes += [{'id':f'base{i}','x':q(x,'m'),'y':q(0,'m')},{'id':f'top{i}','x':q(x,'m'),'y':q(y,'m')}]
        member(f'column{i}',f'base{i}',f'top{i}','column')
        restraints.append({'node':f'base{i}','ux':True,'uy':True,'rz':restraint=='fixed'})
    if variant == 'dual-pitch':
        nodes.append({'id':'ridge','x':q(span/2,'m'),'y':q(height+span/2*tan(radians(reader.number('roof_slope_deg'))),'m')})
        member('roof0','top0','ridge','beam'); member('roof1','ridge','top1','beam')
    else:
        for i in range(len(positions)-1): member(f'roof{i}',f'top{i}',f'top{i+1}','beam')
    width = reader.number('panel_width_m')*reader.number('panel_height_m') if signage else reader.number('roof_width_m')
    exposed_height=reader.number('frame_wind_exposed_height_m') if not signage and any(item.direction in {'x_positive','x_negative'} for item,_ in case) else None
    vertical,horizontal,moment=_load_totals(case,reader,width,exposed_height)
    # Area actions on signs are total forces; frame roof line actions are
    # integrated over projected span and distributed as equivalent nodal forces.
    total_scale = 1 if signage else span*count
    eccentricity = reader.number('eccentricity_m') if variant == 'eccentric-lintel' else 0
    total_vertical=vertical*total_scale; total_horizontal=horizontal*total_scale
    loads=[]
    for i in range(len(positions)):
        share = 1/len(positions) if signage else (0.5 if i in {0,count} else 1)/count
        loads.append({'node':f'top{i}','force_x':q(total_horizontal*share,'kN'),
            'force_y':q(total_vertical*share if signage else 0,'kN'),'moment_z':q((moment+total_vertical*eccentricity)*share,'kN*m')})
    data={'nodes':nodes,'members':members,'restraints':restraints,'nodal_loads':loads,
            'displacement_limit':reader.quantity('displacement_limit')}
    if not signage and not reader.missing:
        typed=s.PlanarFrameInputs.model_validate({'module':'planar_frame',**_combination(),**data})
        data=apply_vertical_line(typed,vertical).model_dump(exclude={'module','combination_id','combination_name','limit_state'})
    return data


def adapt_scene_requests(calculation, family_id, variant_id, node_id, loads):
    """Return one request per coherent case, leaving pre-existing typed input intact."""
    module=calculation.module.value
    if module not in MODELS or calculation.typed_inputs is not None:
        return [calculation]
    r=Reader(calculation.inputs)
    targets=[x for x in loads if x.application_target == node_id]
    if family_id=='boardwalk-platform' and variant_id=='viewing-platform':
        if r.value('slab_load_distribution') not in {'tributary_45_degree','45°几何分担法'}:r.missing.append('slab_load_distribution (tributary_45_degree)')
        if module=='two_way_slab' and r.value('support_condition')!='four_edges_simply_supported':
            r.missing.append('support_condition (this edge-beam graph requires four_edges_simply_supported)')
        if module=='continuous_beam':
            calculation=calculation.model_copy(update={'inputs':{**calculation.inputs,'slab_edge_id':node_id}},deep=True)
    if module in {'bridge_steel_timber','bridge_rc'}:
        for kind,key in [('dead','dead_load_kpa'),('live','crowd_load_kpa'),('wind','wind_load_kpa')]:
            selected=[x for x in targets if x.kind==kind]
            if selected:
                if any(x.unit not in {'kPa','kN/m2'} for x in selected):r.missing.append(f'{kind}_area_load_unit')
                r.values[key]=sum(float(x.adopted_value or 0) for x in selected)
        if module=='bridge_steel_timber':
            r.values['wind_load_kn_m']=r.number('wind_load_kpa')*r.number('wind_height_m')
    if module=='planar_frame' and family_id=='pergola-pavilion':
        # One roof member reaction divided by its explicit tributary spacing.
        # This parameter belongs to the receiving node, not roof_members.
        spacing=r.number('roof_member_tributary_width_m')
        calculation=calculation.model_copy(update={'inputs':{**calculation.inputs,'reaction_conversion_spacing_m':spacing}},deep=True)
    cases=_actions(loads,r,node_id) if module in {'continuous_beam','planar_frame','two_way_slab'} else [(_combination(),[])]
    results=[]
    for i,(metadata,case) in enumerate(cases):
        data={'module':module}
        if module in {'continuous_beam','planar_frame','two_way_slab','pile_group_cap','gravity_retaining_wall'}: data.update(metadata)
        if module == 'continuous_beam': data.update(_beam(r,family_id,variant_id,node_id,case))
        elif module == 'planar_frame': data.update(_frame(r,family_id,variant_id,case))
        elif module == 'two_way_slab':
            data.update(r.group(s.TwoWaySlabInputs))
            data['thickness']=q(r.number('slab_thickness_mm'),'mm')
            r.missing=[x for x in r.missing if x!='thickness_mm']
            data['support_condition']=r.value('support_condition')
            data['poisson_ratio']=r.number('poisson_ratio')
            vertical,horizontal,moment=_load_totals(case,r,1)
            if horizontal or moment:r.missing.append('slab_horizontal_or_moment_load_model')
            data['uniform_load']=q(-vertical,'kN/m2')
        elif module == 'pool_structure':
            data.update(geometry=r.group(s.PoolGeometryInputs),materials=r.group(s.PoolMaterialInputs),
                reinforcement=r.group(s.PoolReinforcementInputs),water_levels=r.group(s.PoolWaterLevelInputs),
                additional_ballast=r.quantity('additional_ballast'),antifloat_factor=r.quantity('antifloat_factor'))
            data['water_levels']['full_external_head']=r.quantity('full_external_head')
            # Retained height is explicit; above/buried variants cannot silently
            # use another variant's soil geometry.
            retained=data['geometry']['retained_soil_height']['value']
            wall=data['geometry']['wall_height']['value']
            if ('above' in variant_id and retained != 0) or ('semi-buried' in variant_id and not 0<retained<wall) or ('rect-buried' in variant_id and retained != wall):
                r.missing.append('retained_soil_height_m (incompatible with variant)')
        elif module == 'bridge_steel_timber':
            count=2 if variant_id.startswith('multi') else 1
            geometry=r.group(s.BridgeGeometryInputs); geometry['span_count']=q(count,'1')
            r.missing=[x for x in r.missing if x != 'span_count']
            data.update(geometry=geometry,actions=r.group(s.BridgeActionInputs),
                timber_deck=r.group(s.TimberDeckInputs,'timber_'),
                crossbeam_section=r.group(s.SteelBridgeSectionInputs,'crossbeam_'),
                longitudinal_section=r.group(s.SteelBridgeSectionInputs,'longitudinal_'),
                comfort=r.group(s.BridgeComfortInputs),foundation_types=['pile' if 'pile' in variant_id else 'shallow']*(count+1))
        elif module == 'bridge_rc':
            count=2 if variant_id.startswith('multi') else 1
            geometry=r.group(s.RCBridgeGeometryInputs);geometry['span_count']=q(count,'1')
            r.missing=[x for x in r.missing if x != 'span_count']
            data.update(geometry=geometry,material=r.group(s.RCBridgeMaterialInputs),reinforcement=r.group(s.RCBridgeReinforcementInputs),
                service_limits=r.group(s.RCBridgeServiceLimitInputs),
                loads={'spans':[{'additional_dead':q(r.number('dead_load_kpa'),'kPa'),'crowd':q(r.number('crowd_load_kpa'),'kPa')} for _ in range(count)],
                    'railing_left':r.quantity('railing_left'),'railing_right':r.quantity('railing_right'),
                    'wind_pressure':q(r.number('wind_load_kpa',aliases=('wind_pressure_kpa',)),'kPa'),
                    'wind_exposed_height':q(r.number('wind_height_m'),'m')},
                supports=[{'id':f'S{j+1}','node_index':q(j,'1'),'foundation_type':'pile' if 'pile' in variant_id else 'shallow'} for j in range(count+1)])
        elif module == 'pile_group_cap':
            sx=r.number('pile_spacing_x_mm');sy=r.number('pile_spacing_y_mm')
            data.update(piles=[{'id':f'P{j+1}','x':q(x*sx/2,'mm'),'y':q(y*sy/2,'mm'),
                'diameter_or_side':q(r.number('pile_size_mm'),'mm'),'pile_type':r.value('pile_type')}
                for j,(x,y) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)])],
                capacities={**{f:q(r.number(f'{f}_capacity_kn'),'kN') for f in ('compression','uplift','horizontal')},'source':r.value('capacity_source')},
                cap=r.group(s.PileCapGeometryInputs,'cap_'),material=r.group(s.PileCapMaterialInputs,'cap_'),
                effects={f:q(0,'kN' if f in {'axial','shear_x','shear_y'} else 'kN*m') for f in s.SixComponentEffectInputs.model_fields})
            # These zeros are placeholders only. execute_scene requires upstream
            # vectors and replaces every component before invoking the solver.
        elif module == 'gravity_retaining_wall': data.update(r.group(s.GravityRetainingWallInputs))
        else:
            data.update(r.group(MODELS[module]))
            dead=sum(float(x.adopted_value or 0) for x in targets if x.kind in {'dead','self_weight'})
            winds=[x for x in targets if x.kind=='wind']
            if not winds:r.missing.append('scene_wind_load_cases')
            data['load_cases']=[{**_combination(j),'wind_pressure':q(float(x.adopted_value or 0)*(-1 if x.direction=='x_negative' else 1),'kPa'),
                'additional_dead_load':q(dead,'kPa')} for j,x in enumerate(winds)]
        r.finish(node_id)
        try: typed=MODELS[module].model_validate(data)
        except ValidationError as exc:
            raise CalculationInputError('scene_adapter_missing_inputs',f'节点 {node_id} 的专项输入不完整。',details={'node_id':node_id,'missing_fields':['.'.join(map(str,e['loc'])) for e in exc.errors()]}) from exc
        results.append(calculation.model_copy(update={'typed_inputs':typed,'inputs':{**calculation.inputs,'scene_adapter_generated':True}},deep=True))
    return results


def specialist_field_contracts():
    """Fields displayed blank by the scene UI; also usable by API clients."""
    groups={
        'pool_structure':[(s.PoolGeometryInputs,''),(s.PoolMaterialInputs,''),(s.PoolReinforcementInputs,''),(s.PoolWaterLevelInputs,'')],
        'bridge_steel_timber':[(s.BridgeGeometryInputs,''),(s.BridgeActionInputs,''),(s.TimberDeckInputs,'timber_'),(s.SteelBridgeSectionInputs,'crossbeam_'),(s.SteelBridgeSectionInputs,'longitudinal_'),(s.BridgeComfortInputs,'')],
        'bridge_rc':[(s.RCBridgeGeometryInputs,''),(s.RCBridgeMaterialInputs,''),(s.RCBridgeReinforcementInputs,''),(s.RCBridgeServiceLimitInputs,'')],
        'pile_group_cap':[(s.PileCapGeometryInputs,'cap_'),(s.PileCapMaterialInputs,'cap_')],
        'gravity_retaining_wall':[(s.GravityRetainingWallInputs,'')],
        'site_rc_wall':[(s.SiteRCWallInputs,'')], 'steel_infill_wall':[(s.SteelInfillWallInputs,'')],
        'plain_masonry_wall':[(s.PlainMasonryWallInputs,'')], 'two_way_slab':[(s.TwoWaySlabInputs,'')],
        'continuous_beam':[], 'planar_frame':[],
    }
    extra={
        'pool_structure':{'additional_ballast_kn':'kN','antifloat_factor':'1','external_water_head_m':'m'},
        'bridge_steel_timber':{'wind_height_m':'m'},
        'bridge_rc':{'railing_left_kn_m':'kN/m','railing_right_kn_m':'kN/m','wind_height_m':'m'},
        'pile_group_cap':{**{x:'mm' for x in ['pile_spacing_x_mm','pile_spacing_y_mm','pile_size_mm']},**{x+'_capacity_kn':'kN' for x in ['compression','uplift','horizontal']},'pile_type':'text','capacity_source':'text',
            'cap_concrete_unit_weight_kn_m3':'kN/m3','cap_groundwater_condition':'text','cap_groundwater_source':'text','cap_submerged_depth_m':'m','cap_water_unit_weight_kn_m3':'kN/m3','cap_buoyancy_factor_uls':'1'},
        'continuous_beam':{'roof_member_tributary_width_m':'m','deflection_limit_mm':'mm','slab_load_distribution':'text'},
        'planar_frame':{'roof_member_tributary_width_m':'m','post_height_m':'m','displacement_limit_mm':'mm','base_restraint':'text','frame_wind_exposed_height_m':'m'},
        'two_way_slab':{'support_condition':'text','concrete_unit_weight_kn_m3':'kN/m3','poisson_ratio':'1','slab_load_distribution':'text'},
    }
    contracts={}
    for module,pairs in groups.items():
        fields={}
        for cls,prefix in pairs:
            for field,info in cls.model_fields.items():
                if info.is_required() and field in FIELD_UNITS:
                    unit=FIELD_UNITS[field];key=prefix+ALIASES.get(field,field+SUFFIX[unit])
                    fields[key]=unit
        fields.update(extra.get(module,{}))
        fields.pop('span_count',None)
        if module=='two_way_slab':fields.pop('thickness_mm',None)
        if module in {'bridge_steel_timber','bridge_rc'}:
            for key in ['dead_load_kpa','crowd_load_kpa','wind_load_kn_m']:fields.pop(key,None)
        contracts[module]=fields
    return contracts
