# Native19 orientation correction — required before cooker fabrication

The inherited baseline is **REFLECTED_BASELINE_NOT_MANUFACTURING_GEOMETRY**. The corrected candidate now imports actual native19 with a proper Rz180 transform and replaces affected cooling, retention, catch and sense-harness geometry. Historical files remain unchanged. The actual final STEP must pass `check_power_orientation.py`, including a historical-mirror negative control, and all matching installation receipts before this correction is considered digitally closed. Physical and electrical qualification remain separate.

## Evidence and independently observed coordinates

`round2/cooling/build_revision.py:97` uses `shape.mirror("XZ").translate((x,y,z))`. Its linear determinant is −1. A manufactured populated board cannot be installed by reflection. All proper rigid rotations have determinant +1.

The source `temper-power-native19-candidate.step`, SHA256 `b4b9edb5ad9c4b0aa4e1b69158abb6be8b9ce203b561c1d34a58e88812a8fa4c`, uses X = native KiCad X, Y = negative native KiCad Y, and component side +Z. `orientation-native-oracle.json` records live pcbnew points from native19 SHA256 `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`; `orientation-source-bounds.json` records independently read STEP shapes.

J8 footprint center is native (13,30.5) on F.Cu; its exact STEP body bounds are X9.5…16.5, Y−34…−27, centered (13,−30.5). J10 is the asymmetric second anchor: native (47,30.5), STEP center (47,−30.5). C5 native four pins span X13…50.5 and Y43.95…64.25; its body spans X10.75…52.75, Y−70.6…−37.6, Z1.613…49.613. BR1 is front-side native (16.3,4.6), with STEP body X13.65…43.95, Y−7…−2.2, Z1.613…21.913. Substrate Z0…1.493 and positive component body establish the top side. Native XY→STEP XY is a coordinate-system conversion; applying an additional mirror to an already exported solid is not a physical rotation.

## Proper rigid placement experiments

`probe_power_orientation.py` imports the native STEP directly, retains all 419 non-power-board named parts of the protection assembly, and performs exact Boolean intersections. It does not remove obstructing parts to obtain a pass. See `power-orientation-probe.json` for complete sets and hashes.

| Placement | Native pad mapping, mm | Result |
|---|---|---|
| Identity, component side up | X = native X−110.5; Y = 322−native Y; Z = STEP Z+30.387 | Five intersections with catch wire/lug/boot parts; heat-source edge moves to Y315…320.485, over 153 mm behind the current sink face at Y161.9. Reject for existing cooling architecture. |
| Rz180°, component side up | X = 129.5−native X; Y = 162+native Y; Z = STEP Z+30.387 | Five intersections: PS2/R80 top capture19.2 mm³, C23/J8 boot25.5585, C6/HV_RET wire328.3355, C6/J10 lug159.9937, C6/J10 boot642.8225 mm³. Cooling contact positions and catch endpoints are wrong. Preferred basis for a new ECO, **not fit**. |

`r4-rigid-power-orientation-PROBE-NOT-FIT.step` is the true-handed Rz180 experiment with all conflicting retained parts still visible. Its 664 solids are valid; validity does not mean installability.

Rz180 keeps the board rectangle X−110.5…129.5, Y162…322 and top datum unchanged. This limits main-housing disruption and preserves the front cooling edge. Required geometry corrections follow.

## Implemented candidate correction

- The cooling owner retained the200mm sink and translated it+36mm inX to−76…124. Fans become−101…−76 and124…149; both front duct transitions, the cradle and custom contact pieces were rebuilt. Corrected BR1 body endsX115.85, leaving8.15mm nominal sink-end margin. The matched cooling source/receipt is under `round5/orientation-cooling`; its pressure clamps, dedicatedPE connection and service sequence are part of the candidate.
- Corrected shim X ranges are Q2−32.5…−20.5; Q3−14.5…−2.5; Q5 25.5…37.5; Q6 7.5…19.5; BR1 88.7…112.7. Native model contacts and livepcbnew edge windows were screened independently. These remain generic package models; actual films, shim thicknesses, ceramic edges, forces and hot growth require measurement.
- Bespoke edge-retention pieces followXnew=19−Xold; the formerR80 capture is now on the left, away fromPS2. This is newly fabricated custom mechanical geometry, not reflection of a PCB or vendor fan. The historical rail names remain identifiers: `CARRIER_RAIL_-122p5` now denotes the world-right rail. Assemblers select it by actual bounds.
- The new floor restores only8 obsolete cooling holes, cuts12 new cooling holes, and preserves all unrelated floor features. The8 sensor/OUT support holes and4 sense-guide holes are added afterward. An old floor with shifted overlapping holes is not the candidate fabrication drawing.
- J8/J10 move to(116.5,192.5)/(82.5,192.5). Right-side catch routing, a bolted saddle and explicit CC1 return termination reservations replace the obsolete left-side paths. See `rigid-power-installation.json` and `installation-ECO.md` for actual curves, screws and connection limits. Installed full-loop inductance is not claimed extracted from these new paths.
- Corrected native sense endpoints are C5.1BUS_P=(116.5,205.95,30.387); C5.3HV_RET=(79,205.95,30.387); C21.1RES_A=(−104.75,259,30.387); C21.2SW_B=(−62.25,259,30.387). BUS runs through the right duct; TANK through the left. New R32 tubes, penetrations, grommets and blocks are generated against the corrected assembly.

The proper-handed probe remains intentionally NOT-FIT evidence of the old interface conflicts. The final corrected STEP is `r4-supported-routed-candidate.step`; never interchange these two exports. The actual-solid chirality check, source hashes, cooling contact checks, all material/service groups, thread-contact classifications and tolerance records must refer to the same final revision. These establish digital installation geometry, not powered behavior or manufacturing release.
