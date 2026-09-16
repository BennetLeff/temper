# Shunt repair and electrical-model completion

Execution contract, 2026-09-16, starting at b7af4c912.

The approved work is shunt/copper thermal modeling, remaining current paths,
actual switching loops and startup/fault/loss-of-bias behavior. First resolve
an invalid model input: the authored WSL2726R0100FEA at 10 mΩ with two pads
is outside Vishay's published WSL2726 range and four-terminal package.
Source/native agreement did not detect this part-definition defect.

1. Retain exact manufacturer evidence and choose an available 10 mΩ shunt,
   preserving the controller's sense scaling. Bind MPN, resistance, package,
   land pattern and conditional power rating in Rust. Preserve the historical
   board as a failing regression; never rewrite historical source receipts.
2. Update authored source, compile with Atopile, refresh the saved working
   PCB/schematic and native receipts, and run construction/physical checks.
3. Model actual new shunt/copper geometry with explicit cooling and material
   uncertainty. Require energy balance, mesh convergence and sensitivities;
   a catalog wattage is not a temperature prediction or assembly qualification.
4. Resolve switching-loop and controller protection paths from source and
   manufacturer behavior. Keep missing external supervision and response-time
   bounds visible. Do not invent a safety deadline.
5. Run common harness and regression mutations; retain raw inputs/results and
   record remaining model or assembly limitations before committing/pushing.

Evidence belongs here and in a dated common-suite run. Historical GBU/GBJ
thermal results remain valid only for their original saved inputs. A changed
board is not allowed to inherit their acceptance by editing a hash.

No fabrication, purchase or powered measurement is part of this execution.

## Implemented repair

The working authoring source now uses GBJ2510-F and Stackpole
HCSM2818FT10L0 (10 mΩ, ±1%, two terminals). The historical GBU and GBJ
fixtures remain unchanged. Their unsupported WSL2726 shunt definition is now
an explicit `ERC.PFC.SHUNT_PART` failure, including in regression tests.

The replacement was compiled through Atopile, projected into native KiCad,
then applied to the routed GBJ candidate with its physical UUIDs preserved.
The land pattern uses two 3.5 × 5.3 mm rectangles, a 0.6 mm gap and a
7.15 × 4.95 mm body. The official KiCad Library Tools generator and parameters
are retained. Manufacturer documents, exact identities and source hashes are
in [sources/manifest.json](sources/manifest.json).

U12's left power trace is 5.3 mm wide and ends at (75.3, 132) mm, retaining
the sense-wire junction. A 6 mm trace ending there would short the new opposite
pad; shortening it first to 74.7 mm avoided that short but left a width-only
contact that the current graph could not resolve. The final edit repairs both
conditions. Its round cap stops at x = 77.95 mm; the opposite pad begins at
78.30 mm. Native DRC checks the resulting 0.35 mm clearance. The narrower trace
is subject to the same current screen as every other trace; no waiver was added.

Authoritative candidate: [candidate/section.kicad_pcb](candidate/section.kicad_pcb).
Use [units.json](units.json) to run the seven-unit suite with this working
candidate. The default maintained registry intentionally retains its historical
board; it does not silently acquire this candidate or its thermal evidence.

## What the thermal experiment establishes

[thermal-04/report.json](thermal-04/report.json) contains 15 actual Gmsh/Elmer
solves: five boundary/material/heat-split cases on three successively finer
meshes. Native front pads, local track rectangles and round ends are modeled
as separate copper domains. Independent Rust checks integrate mesh volumes,
check pad source volumes and cut areas, reject a bridged gap or internal clamp,
and require two connected domains with cooling boundaries. Both the Gmsh and
converted Elmer meshes are checked.

The heat source is 2.28528 W: 15 A RMS through 10 mΩ, with +1% resistance and
+75 ppm/K evaluated at 100 °C. It is a conditional input, not a temperature-
iterated worst-case bound. Heat balance, solver convergence and mesh convergence
are checked from raw output. Uniformly raising cut temperatures by 20 K raises
the result by 20 K; reducing copper conductivity from 350 to 250 W/(m·K)
scales the rise by 1.4, providing independent linear-equation checks.

| Case, finest mesh | Peak modeled local copper |
|---|---:|
| 80 °C cuts, equal terminal heat | 122.68 °C |
| 80 °C cuts, all heat into terminal 1 | 162.74 °C |
| 80 °C cuts, all heat into terminal 2 | 165.37 °C |
| 100 °C cuts, equal terminal heat | 142.68 °C |
| 80 °C cuts, weaker copper conductivity | 139.76 °C |

These are **not predictions of resistor body temperature or evidence that the
real board overheats**. The model omits body/solder conduction, vias, back copper,
FR4, convection and copper Joule heat. Parallel heat paths may cool the actual
assembly; other losses may heat it. The imposed cut temperatures need a board/
assembly cooling model. The 5 W catalog rating requires specified copper and
surface temperature conditions, which this model does not establish.
`THERMAL.PFC.SHUNT_ASSEMBLY` therefore remains INDETERMINATE.

Replay binds the exact saved board, source-bound 15 A waveform, geometry, decks,
backend/module digests, meshes, raw logs and measurements. Edited summaries,
changed decks even with updated checksums, missing heat materials, incorrect
boundaries, nonconverged solves and unbalanced heat are regression failures.
The first empty-region mesher attempt and subsequent historical runs are kept
as development evidence; they cannot be substituted for this final run.

## Controller and switching-loop coverage

The common runner executes the source-bound UCC28180 threshold cases. UVLO,
standby, high OVP/reset, open current sense, soft current limit and peak current
limit distinguish guaranteed threshold crossings from tolerance bands.
The ICOMP table/prose unit conflict remains INDETERMINATE. No guaranteed
shutdown propagation time or gate-voltage behavior at zero bias is invented.
Controller inhibition does not disconnect mains or discharge the DC bus.

Named boost-commutation, gate-drive and on-state input loops are checked against
source pin identities and native conductor paths. Bridge polarity is resolved
from its exact MPN. Returned edge IDs are connectivity witnesses, not extracted
high-frequency current paths. Loop geometry and parasitic inductance remain
explicit mandatory INDETERMINATE checks; a whole-net bounding box cannot satisfy
them.

## Remaining physical obligations

1. Resolve shunt body/terminal thermal parameters and actual board cooling,
   including vias and back copper; then evaluate resistor surface temperature
   and transient/pulse capability under the operating envelope.
2. Extract high-frequency return paths and parasitics for the named loops.
3. Supply the external bias, permit/precharge, disconnect and discharge contracts;
   validate their startup and fault timing with the power stage.
4. Complete inductor, switch, diode, capacitor and remaining pad/via loss/rating
   corners before calling the power-entry assembly qualified.

The new checks make these omissions visible. Numerical PASS, source agreement
and native DRC PASS are each narrower than hardware qualification.

## Final validation, 2026-09-16

[Final receipt](evidence/final-validation.json) binds the board and source hashes.
The [seven-unit run](../../validation/runs/shunt-20260916-final-02/summary.json)
has zero native ERC/DRC/unconnected/parity findings and zero Rust failures.
Every overall unit verdict remains INDETERMINATE because physical/integration
obligations are not waived. The workspace tests report 473 passed, zero failed,
one ignored. Clippy reports only the 15 previously present warnings; import
boundaries and generated-artifact consistency checks pass.

The bridge evidence was regenerated from this exact candidate: 96 local solves
under [bridge-thermal-02](bridge-thermal-02/assessment.json), with nominal mesh
deltas 0.04383/0.02454 K and wider-domain delta 0.01685 K. No historical bridge
result was made current by changing its input hash. Required raw meshes, scalar
measurements, decks, logs and tool receipts are retained; gzip archives preserve
their original-byte hashes. Optional nodal restart fields are retained locally
at the location and digests recorded in `bridge-thermal-02/field-archive.json`;
they are not inputs to the acceptance replay.

`shunt-20260916-final` is a rejected attempt: archiving those optional restart
fields overlapped its input read, and the integrity guard refused the run.
`shunt-20260916-final-02` is the completed immutable-input rerun. Earlier failed
geometry, copper and model attempts are retained with their actual outcomes.

[Code-review receipt](../../../docs/reviews/shunt-20260916/run-20260916-shunt/review.json)
reports no actionable findings. Its coverage limitations are retained. No
hardware was powered, no purchase was placed and no fabrication order was made.
