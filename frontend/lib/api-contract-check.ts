// Compile-time contract check: the hand-written request types in
// generated-api.ts must stay assignable to the types generated from the
// backend OpenAPI snapshot (lib/api-schema.ts). `tsc` fails here when the
// backend contract drifts. Type-only; nothing is emitted.

import type * as Api from "./generated-api";
import type * as Schema from "./api-schema";

type Assignable<T, U> = [T] extends [U] ? true : false;
type Assert<T extends true> = T;

export type ContractChecks = [
  Assert<Assignable<Api.ApiCalculationModule, Schema.CalculationModule>>,
  Assert<Assignable<Schema.CalculationModule, Api.ApiCalculationModule>>,
  Assert<Assignable<Api.ApiTypedValue, Schema.TypedInputValue>>,
  Assert<Assignable<Api.ApiContinuousBeamInputs, Schema.ContinuousBeamInputs>>,
  Assert<Assignable<Api.ApiPlanarFrameInputs, Schema.PlanarFrameInputs>>,
  Assert<Assignable<Api.ApiPlanarTrussInputs, Schema.PlanarTrussInputs>>,
  Assert<Assignable<Api.ApiTwoWaySlabInputs, Schema.TwoWaySlabInputs>>,
  Assert<Assignable<Api.ApiTimberConnectionInputs, Schema.TimberConnectionInputs>>,
  Assert<Assignable<Api.ApiWallAnchorInputs, Schema.WallAnchorInputs>>,
  Assert<Assignable<Api.ApiPoolStructureInputs, Schema.PoolStructureInputs>>,
  Assert<Assignable<Api.ApiPileGroupCapInputs, Schema.PileGroupCapInputs>>,
  Assert<Assignable<Api.ApiBridgeSteelTimberInputs, Schema.BridgeSteelTimberInputs>>,
  Assert<Assignable<Api.ApiBridgeRCInputs, Schema.BridgeRCInputs>>,
  Assert<Assignable<Api.ApiGravityRetainingWallInputs, Schema.GravityRetainingWallInputs>>,
  Assert<Assignable<Api.ApiSiteRCWallInputs, Schema.SiteRCWallInputs>>,
  Assert<Assignable<Api.ApiSteelInfillWallInputs, Schema.SteelInfillWallInputs>>,
  Assert<Assignable<Api.ApiPlainMasonryWallInputs, Schema.PlainMasonryWallInputs>>,
  Assert<Assignable<Api.ApiLoadCombinationsInputs, Schema.LoadCombinationsInputs>>,
  Assert<Assignable<Api.ApiWindSnowGuideInputs, Schema.WindSnowGuideInputs>>,
  Assert<Assignable<Api.ApiSoilWaterActionsInputs, Schema.SoilWaterActionsInputs>>,
];
