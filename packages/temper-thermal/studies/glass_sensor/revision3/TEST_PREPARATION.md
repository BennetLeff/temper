# R3 coupon and inspection plan — NOT_RUN

Continue the [R2 preparation](../revision2/TEST_PREPARATION.md). The following is a proposed controlled engineering experiment; no apparatus, parts or measurements exist from this task.

## Coupons and fixed comparisons

| Code | Construction | Purpose |
|---|---|---|
| C0 | R2 Ø8×0.15 cap,0.05 catch gap, M222, original copper route | Preserve the physical baseline |
| C1 | Same,0.20 catch gap | Isolate the retention air-gap change |
| C2 | C1 plus cap-side hot anchor, same copper and developed length | Isolate anchor benefit and added mass |
| C3 | C1 with fourTFCC-003 constantan wires; qualified external reversed-current readout | Separate thermal benefit from electrical-offset penalties |

Within C1/C2, compare flat-ground and flat-lapped faces with measured free-state shape/roughness; include10 and25µm crown comparison coupons only if the fabricator accepts those drawings. No finish is credited with a2× contact coefficient before a measurement. Keep bonding, RTD, wire route, load and reference placement controlled. Record both flat and crowned shapes at cold/hot conditions. A cap flattened by the inspection fixture can falsely appear acceptable; inspect it after release and after hook welding/cure.

## Retention and anchor inspection

- Measure the three opposing catch gaps individually. Proposed nominal0.20 mm; sensitivity range0.15–0.25 mm is an analysis window, not an accepted production tolerance. Check clearance at cold/hot and under off-axis pan drag. Repeat after cycling.
- Inspect cap lift before capture, hook welds, ceramic arm condition and lead slack throughout that lift. No force limit is inferred from collision-free CAD. Define retention/dent loads with the intended cookware and handling requirements before qualification.
- Anchor coupon geometry is1.3×1.5×0.42 mm, with fourØ0.232 passages at0.28 pitch. Use intact PFA and actual selected wire. Section sacrificial coupons to inspect voids, wrap/contact, cracking and jacket condition. Verify electrical isolation after the intended temperature/wet exposure using reviewed limits for the complete appliance.
- The full weld/lead route remains to be formed. Demonstrate that native stubs, welds, hot anchor and free loops accommodate the extra0.20 mm cap lift and main/local travel without violating the existing≤10 mN parasitic-force target. The anchor must not bridge cap/island to carrier.

## Identify conductance without fitting everything at once

Characterize the hot-anchor and wire loss on a separate guarded coupon with known applied heat, measured cap/anchor/lead temperatures and a calibrated reference. Sweep actual route and ambient cooling; estimate conductance with uncertainty. Proposed anchor target≥0.003 W/K is demanding and must include PFA/interface resistance. Document heat added by reference sensors and the heater.

Then identify pan-to-cap conductance under independently measured force. Do not infer it from just a final RTD underread; support, wire and bond losses can compensate in a fit. Record pan/reference spatial gradients, cap temperature, island temperature and carrier temperature. Use the existing independent fit/holdout rules and calibrate shared nickel stub effects separately.

Suggested matrix: available depression0.10/0.25/0.60 mm with actual force measured; pan bowl−100/−25/0/+25/+100µm over the8 mm face; relative tilt0/0.1/0.25/0.5°; repeat placements, representative clean/oxidized/contaminated surfaces and declared cookware. Mechanical load is not proof of thermal contact. A fully specified production population and sample count still need product requirements.

Candidate thermal screen: effective pan-to-cap G≥0.13 W/K when anchor G≥0.003, other direct loss≤0.0002 and additional barrier loss≤0.0002 W/K, under the modeled temperature boundaries and h5–15 wire cooling. This is a conditional engineering target. Include parameter-identification uncertainty and holdout evidence before interpreting a pass; it is not an appliance accuracy certificate.

Report t90 to the sensor endpoint, t90 to the actual pan step, steady error, ramp error and slow tail. The preferred target package's simulated1.92°C thermal bias leaves essentially no allowance for RTD class, readout, reference uncertainty or spatial error inside a±2°C whole-system claim. A tighter thermal target or calibrated error budget is needed for that claim.

## Alloy-wire electrical comparison

For C3, measure signed voltage at both current polarities with a calibrated bipolar source/readout, verified current magnitude, settling and synchronized timing. Characterize offset while varying hot/cold junction mismatch and under the intended RF environment. Compare single-polarity, reversed and three-reading delta results. Do not assume a MAX31865 configuration already supplies current reversal. `electrical_offset_budget.csv` uses illustrative20/40/60µV/K coefficients, not a purchased-wire calibration curve. Qualify real junctions.

## Seals and contact detection stay coupled

Repeat the loss/force/anchor characterization after any membrane, jacket, optical window or feedthrough is installed. Keep the cartridge marked DRY until all passages are closed and the sealing design has evidence. Wetting the0.20 mm capture gap or anchor changes thermal behavior; the dry-gas model does not cover it. Preserve jam injection, real physical release timing, optical tilt/drift and the unavailable firmware backend until qualified. An improved temperature trace does not close those gates.
