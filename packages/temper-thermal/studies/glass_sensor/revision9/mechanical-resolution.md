# R9 mechanical resolution

**The combined upward catch is now checked in CAD, and a separate bolted-bracket candidate addresses the missing positive attachment.** In unchanged R7, the upper capture fingers remain separate bodies without a modeled attachment that transfers their upward load into the carrier. The C9-BOLTED derivative supplies a defined screw/nut joint and nominal assembly geometry; neither version has qualified retention strength.

Status: nominal geometry and preparation only, 2026-10-04. Physical **NOT_RUN**. Canonical R7/R8 files remain unchanged. Applied the Temper mechanical-review and Python best-practices skills; Python additions are CadQuery inspection/export glue, not new physics.

## What the derived CAD closes

`mechanical/capture-checks.json` records seven sequential states for each of the three complete R7 assemblies, including all modeled native leads, four full extension routes, welds, covers and glass. Flexible seal envelopes are explicitly excluded from rigid collision claims. Six complete STEP assemblies represent the requested combined catch and the later downstream carrier stop; their actual reimported B-reps are validated and their catch contacts remeasured.

| Interface | Nominal engagement | Measured contact geometry |
| :-- | :-- | :-- |
| Cap hooks → island spider | Cap +0.20 mm relative to island | Three 0.240 mm² patches; 0.720 mm² total |
| Island flange → upper fingers | Island +0.10 mm relative to fixed carrier, after cap catch | Three approximately 0.594659 mm² patches; 1.783976 mm² total. Absolute cap lift is +0.30 mm |
| Carrier tabs → outer blade pads | Seated in all sampled states | Three 1.260 mm² patches |
| Outer blade pads → ceramic clamps | Seated in all sampled states | Three 1.260 mm² patches |
| Ceramic clamps → fixed housing underside | Carrier +0.40 mm after both preceding catches | Three 1.500 mm² patches; 4.500 mm² total. Absolute island/cap lifts become +0.50/+0.70 mm |

The last row identifies an **existing potential geometric carrier stop**: the outer clamps reach the housing flange underside at z = −5.30 mm. It was absent from the earlier documented load-path assessment. Its bearing strength, foil compression, clamp retention, housing attachment and hot-tolerance suitability remain unqualified. No operating travel or proof load follows from the 0.40 mm take-up.

Collision checks cover sampled axial states, not a continuous sweep or lateral/tilting escape. Positive intersections after deliberate 0.01 mm overtravel test that each catch can actually be detected. The full results retain all detected intended electrical overlaps and required join checks; numerical geometry agreement does not validate weld manufacture, lead forming, fatigue or sensor insulation.

## The upward path still breaks at a defined interface

`mechanical/attachment-checks.json` checks all nine upper-finger instances. Each finger has a **0.400 mm² bottom seating contact at z = −8.00 mm** on the carrier. That interface reacts downward seating. There is **no opposite upward-bearing capture surface** and no modeled fastener, interlock or qualified bond transferring upward finger load to the carrier. R7's kinematic grouping holds these bodies together by assumption.

Thus the chain is cap → hook/spider → island flange → upper finger → **undefined tension attachment** → carrier → blade pad/clamp → potential housing stop. The downstream stop cannot repair the upstream break. The cap's formed/welded hook attachment is also still a process/strength assumption even though its CAD is fused.

Do not solve this by simply fusing the finger solids in a release model. The inherited documentation identifies zirconia for the island but does not establish a qualified common carrier/finger grade or manufacturing route. A monolithic carrier with inward toes also blocks straightforward axial passage of the Ø8 mm island flange; an alternative insertion sequence and ceramic undercut process have not been demonstrated. No such candidate is promoted here.

The separate **C9-BOLTED** M222 control derivative now implements three independent 316L brackets with natural A4 M1.6 × 4 screw/nut reference envelopes at r = 7.10 mm. Modified carrier passages permit radial bracket installation after the island is present. Its three full-assembly states and reimported STEPs verify the new bearing interfaces; bracket/housing assembly samples and minimum fastener-access envelopes are also checked. See `mechanical/bolted-candidate.md` for exact geometry, primary fastener references and separate reproduction receipt.

The proposed positive attachment still needs carrier/bracket material and process definition, selected torque tooling, preload/locking development and hot structural analysis using actual product loads. Nominal threaded supplier envelopes do not model helical flanks or establish hot joint strength. No arbitrary force or cycle threshold was assigned. Changed thermal/EM paths, hot tolerances, unequal-hook loading, lateral escape, ceramic flaws and product-mount restraint require their own evidence; no R7 response number is transferred to C9-BOLTED.

## Two concrete open process specimens

`mechanical/P9-569-OPEN-100.step` and `mechanical/P9-569-OPEN-150.step` are distinct from the full R7 cartridges. Each reuses the existing D6 cap and adds only a centered 2.7 × 2.5 mm candidate bond pad and 2.3 × 2.1 × 0.25 mm bare alumina tile.

| Specimen | Nominal bond gap | Bond volume | Alumina volume | Cap/bond area | Bond/tile area |
| :-- | --: | --: | --: | --: | --: |
| P9-569-OPEN-100 | 0.100 mm | 0.6750 mm³ | 1.2075 mm³ | 6.75 mm² | 4.83 mm² |
| P9-569-OPEN-150 | 0.150 mm | 1.0125 mm³ | 1.2075 mm³ | 6.75 mm² | 4.83 mm² |

Both reimport as three valid solids with the intended gap/contact areas and no volumetric interference. They contain no RTD, wiring, covers, cartridge, seal or permanent spacer. External holding/gap-control tooling remains separate. Ceramabond 569 is a process candidate only; cured thermal properties are unknown, so these files do not support a named-material response prediction. See `process-decision.md` for manufacturer evidence and the conditional witness process. Nominal CAD thickness is not measured cured thickness.

## Reproduction and evidence identity

Run `sh mechanical/run.sh` from this directory, then `cd mechanical` and `shasum -a 256 -c artifacts.sha256`. The existing interpreter is `/private/tmp/temper-center-sensor-env/bin/python`, CadQuery 2.6.1. No installation, procurement, outreach or physical operation occurred. `mechanical/README.md` describes numerical thresholds and scope.

The capture, attachment and witness scripts independently retain these exact inherited pins; finalization rechecks them and the eight exported STEP digests before writing the receipt:

| Inherited source | SHA-256 |
| :-- | :-- |
| R7 `mechanical/build.py` | `1c9451a3af11f7025e4abd8d1f91d9c17d09c9c710d0de2b454e595dca6f2281` |
| R5 `mechanical/build.py` | `f4507ebc3f8c7bf82c19c5b38b9099dbd6c7af1d3190635577c72ec466c7feca` |
| R2 `mechanical/build.py` | `3057c0ede6adeeed338d0dc554b63100dfe5040e9bef562fb622199807f6499d` |
| R7 `mechanical/thermal_geometry.csv` | `72c6da410ee03d91aeee04386fba74b70ce14e504348abbb4515f3b8241a5343` |

The artifact receipt establishes reproducible source/output identity for this nominal study. It deliberately permits the explicit `OPEN_UPWARD_TENSION_JOINT` diagnostic; it is not a retention acceptance certificate. STEP timestamp changes can change file hashes on re-export without changing geometry.
