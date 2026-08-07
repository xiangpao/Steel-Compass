# Geotechnical infrastructure verification evidence

Evidence date: 2026-08-04

## Decision

`gravity_retaining`, `pool_structure`, and `pile_group` remain `unverified`.
Independent closed-form scripts now cross-check representative actions,
equilibrium, capacities, and 0.99/1.01 decision boundaries, but that numerical
agreement is only one release gate. Exact clause review, complete applicability
review, and a named human reviewer/date are still absent.

## Mapping checklist

| Module | Candidate standards | Independently recomputed | Still missing |
|---|---|---|---|
| gravity retaining wall | GB 50007-2011; GB 55003-2021; material standard TBD | Rankine soil/water actions, self-weight, uplift, sliding/base equilibrium, compression screening | exact clauses, material-specific design, drainage and groundwater review, global stability and settlement |
| rectangular pool | GB/T 50010-2010 (2024 amendment); GB 55008-2021; GB 55003-2021; GB 50007-2011 | empty/full pressure resultants, vertical balance, uplift, simplified two-way base demand, RC strip capacities | crack-width validation, two-way slab method validation, watertight detailing, nonlinear contact |
| rigid pile group and cap | JGJ 94-2008; GB 50007-2011; GB 55003-2021; GB/T 50010-2010 (2024 amendment) | six-component rigid-cap allocation for centred orthogonal layouts, pile capacity thresholds, cap punching/shear/flexure | group-soil interaction, settlement, lateral interaction, pile structural design, deep-cap and anchorage checks |

All standard references above are candidate topic mappings, not signed clause
mappings. They must not be presented as completed normative verification.

## Applicability and boundaries

- Gravity wall: straight wall per metre, level single-layer fill and static
  water. No seismic action, passive-resistance credit, global stability,
  settlement, or material-specific detailing.
- Pool: rectangular RC geometry, one soil layer and static water levels. Wall
  strips and base-slab distribution are simplified; irregular geometry,
  temperature, seismic action, joints and watertight details are excluded.
- Pile group: rigid centred cap with geotechnical capacities supplied by the
  investigation. The software does not derive pile capacity from soil data and
  does not check settlement, pile-soil nonlinear response, pile reinforcement,
  seismic action, or deep-cap strut-and-tie behaviour.

## Promotion gate

Promotion to `independently_verified` requires all candidate mappings to be
replaced by exact reviewed clauses, all remaining gaps to be closed or made a
validated non-applicable boundary, and a named reviewer with review date.
Until then, professional results must remain `incomplete`; numerical screening
may be shown only with the current bounded scope.
