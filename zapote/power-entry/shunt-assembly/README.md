# Shunt assembly heat-path study

Execution contract, 2026-09-16, base 5bd51b46f.

Extend the saved HCSM2818FT10L0 shunt experiment through its actual two-layer
copper, twelve adjacent plated vias, substrate and assumed solder contacts.
Gmsh generates the mesh; Elmer solves conduction; Rust owns extraction,
independent geometry checks, raw-result acceptance, replay and harness verdicts.
No layout change is justified by the earlier front-copper-only temperatures.

The manufacturer publishes the body/termination dimensions but no guaranteed
internal thermal resistance or transient thermal impedance. Therefore this
study injects heat at the two solder contacts and reports the remaining thermal
resistance budget to a 100 C surface target. It must never report resistor body
temperature, full assembly qualification, or a guaranteed thermal envelope.
A homogenized body with invented conductivity would not resolve that gap.

Model the native copper inside an explicitly cropped board region; preserve
native drill diameters and annular lands. Sweep imposed remote-board temperature,
terminal heat split, via plating and solder/material assumptions. Exposed local
faces are adiabatic: external cooling remains at crop faces, not an invented
ambient coefficient. Require three mesh sizes, source volume/material census,
exterior-only cooling ports, shared thermal interfaces, raw energy balance and
uniform boundary-temperature shift control. Reject changed native inputs, decks,
meshes, raw results or incomplete profiles. Retain all attempts.

No fabricated resistor thermal constants, no purchase, and no powered test.

## Corrected run results

[Run 15](run-15/report.json) completed all 19 solves and passed the pinned
numerical profile. All temperatures below are model results at solder contacts
or board material, not measured hardware or resistor-body temperatures.

| Scenario | Imposed crop temperature | Finest peak | Final refinement error estimate |
| --- | ---: | ---: | ---: |
| Equal terminal heat split | 60 °C | 105.789 °C | 0.195 K |
| Uniform hotter board | 80 °C | 125.789 °C | 0.195 K |
| All heat into terminal 1 | 60 °C | 134.662 °C | 0.286 K |
| All heat into terminal 2 | 60 °C | 148.501 °C | 0.430 K |
| Weaker joints/materials | 60 °C | 112.198 °C | 0.190 K |
| Wider crop | 60 °C | 106.166 °C | 0.137 K |

The worst total energy imbalance was 1.53e-8 W for a 2.2853 W source.
The direct/iterative nominal control differed by 3.49e-7 K. Widening the crop
changed the equal-split peak by 0.376 K, whereas the unknown terminal heat
division changed it by tens of kelvin. More mesh refinement therefore does
not resolve the dominant physical uncertainty.

Even the equal-split contact peak exceeds the selected 100 °C design target
with this prescribed 60 °C board boundary. There is no positive internal
resistor thermal-resistance budget to that target under these assumptions.
This does not establish a datasheet violation or actual overheating: the
100 °C condition accompanies the full 5 W rating, and the operating assembly's
cooling and internal resistor heat path remain uncharacterized. Do not resize
the PCB solely from these conditional temperatures.

## Verification and harness result

The final release-mode Rust workspace run passed **491 tests**, with zero
failures and one ignored test. This includes replay of the compressed 19-case
profile through the actual PFC/harness boundary, asserting numerical PASS
while assembly qualification stays INDETERMINATE. The mutation regressions
cover changed native geometry, the historical wrong core thickness, cells
crossing drilled voids, converted mesh identity, pre-solve input receipts,
command metadata, raw scalar/log mismatch, incomplete profiles, convergence
screen evasion and ambiguous compressed evidence.

The [seven-unit common run](../../validation/runs/shunt-assembly-20260916-final-01/summary.json)
completed with no FAIL units and no source change during execution. All seven
units remain INDETERMINATE for their recorded unresolved engineering or
qualification obligations. Each passed native ERC, DRC, unconnected and
schematic-parity checks using the actual recorded KiCad CLI **10.0.4**.
For power-entry, both shunt numerical rules pass; SHUNT_ASSEMBLY remains
INDETERMINATE. Buck and MCU are explicitly outside this maintained registry.

`cargo clippy --workspace --all-targets --release --offline --locked`,
`make regen`, `make regen-check`, and the import-boundary gate completed
successfully. Clippy still reports existing warnings; this is not a claim of
a warning-free workspace. [Execution logs](execution-logs/) retain the actual
commands' output, including earlier failed attempts. Raw solver whitespace
is preserved because changing it would invalidate the retained byte hashes.
Source/document whitespace checks pass; unedited raw solver outputs contain
their original trailing spaces.

The [review closure](../../../docs/reviews/shunt-assembly-20260916/closure.md)
records the post-review receipt fix and integration-test result. The board
bytes are unchanged. No fabrication, powered test or full-cooker acceptance
is implied by this numerical closeout.

## Model and acceptance contract

The reviewed board is SHA-256
`b1e06afbf0e9a8b41a3bbbbd046abeb5495e9b42f3fc07e1b312095bc7e97583`.
Extraction rejects another board until its outline/cutouts are reviewed; pad
coordinates alone do not establish a continuous substrate. The native snapshot
also passes the existing Rust board/component/trace/via binding check.

The normal crop is x=68–87, y=128–136 mm. A wider x=67–88 mm crop checks
sensitivity to the imposed cooling boundary. The 1.6 mm finished stack contains
two 70 µm copper layers, 1.44 mm substrate and two 10 µm solder-mask layers.
The conduction solid is 1.58 mm: its outer adiabatic mask skins are omitted,
not reassigned to FR4. All intersecting native traces,
filled back copper, twelve 0.8 mm finished via holes and 1.4 mm lands are
included. Assumptions are 25 µm plating, 0.15 mm solder, copper 350 W/(m K),
solder 50 W/(m K), and substrate 0.25 W/(m K). The weaker-joint case uses
15 µm plating, 0.25 mm solder, 25 W/(m K) solder and 0.18 W/(m K) substrate.
These are sensitivity inputs, not manufacturer-certified bounds.

The source is 2.2852828125 W, from 15 A RMS, 10 mΩ, +1% resistance tolerance
and +75 ppm/K over 75 K. It is a conditional loss at the selected 100 °C
resistance point, not a temperature-iterated worst-case loss. Heat enters the
two 2.9 × 4.95 mm solder-top faces: equal split, all into terminal 1, or all
into terminal 2. The extreme splits expose an unknown; they are not predictions
of the actual resistor's internal heat division.

Four crop faces are held at 60 °C, or 80 °C for the uniform-shift control.
All other exposed surfaces are adiabatic. A prescribed board temperature is
not ambient air temperature and does not establish a realizable cooling system.
The model excludes resistor internals, copper Joule heating, neighboring heat
sources, enclosure airflow and transients.

Required checks include:

- Independent cell-material membership, native material volumes, complete
  exterior cooling faces, heat-source face areas, shared interfaces and solid
  connectivity. Convex-hull projection excludes cells crossing drilled voids;
  a separate whole-cell guard rejects copper bridging the terminal gap.
- Gmsh and Elmer mesh topology/material/port equality, allowing element order
  changes and at most 1 pm coordinate rounding. The solver's node/element
  census must match the mesh header and actual mesh files.
- Raw heat input and output agreement within 1e-7 W; solver completion and
  convergence; a +20 K boundary shift must shift the peak by +20 K within
  1e-5 K. A direct-solver control must agree with the nominal iterative solve
  within 1e-5 K.
- Three meshes per physical scenario. Node counts must increase. The
  first-order remaining-error estimate
  `abs(Tfine - Tcoarse) * hfine / (hcoarse - hfine)` must be below 1 K for the
  first interval and 0.5 K for the final interval. This is a convergence
  screening estimate, not a formal discretization-error bound.
- Canonical generated decks, exact native input and backend hashes, all raw
  mesh/scalar/log and invocation receipts, plus summary-to-raw equality.
  `solver-inputs.json` hashes the decks and both meshes immediately before
  ElmerSolver and is checked afterward and at replay.
  Reuse requires current native/backend identity and revalidation of each case.
  Original invocation working directories are retained, not rewritten to imply
  a new solve. Absolute executable paths are required before starting a run.

Nominal, hot-board, weak-joints and wider-domain use 100/50/40 µm local mesh
sizes. Terminal 1 uses the same sequence. Terminal 2 needs 100/50/35 µm:
its 50→40 µm estimate was 0.536 K and failed the unchanged 0.5 K requirement.
The 25 µm attempt produced a 381 MB mesh and hit the former 128 MiB input cap.
The bounded reader now permits 256 MiB for the targeted 35 µm refinement;
the rejected 25 µm attempt remains retained. Geometry is refined locally near
the contacts, with the surrounding mesh limit four times the local value.

## Applicability and remaining work

The reported maximum is a **solder-contact/board temperature**, not resistor
body temperature. The datasheet's 100 °C condition belongs to the full 5 W
rating with approximately 500 mm² copper. It is a useful conservative design
target here, not a universal absolute-temperature limit at 2.3 W.

The fixed native geometry is checked with sampled material predicates and
independent integral/interface checks. Drilled voids and the terminal gap have
whole-cell checks; arbitrary concave copper boundaries do not yet have a
general exact Boolean containment proof. The model must not be transferred
to another board by copying its temperatures or weakening the applicability
guard. Hashes detect stale/edited retained artifacts; they are not signed
attestations against a producer rewriting the entire evidence tree.

Next physical evidence needed is the resistor's internal thermal path or a
controlled assembly measurement, and a full-board cooling/neighbor-loss
budget. Keep assembly qualification INDETERMINATE. No PCB change follows
solely from exceeding the selected 100 °C target under assumed crop cooling.
After that, continue power-stage component loss/rating corners, actual
switching-loop parasitics and startup/shutdown/bias timing. Auxiliary power
remains the next standalone unit after the power-entry interface handoff.

The review also found that older front-copper-only `shunt_local` replay did not
bind invocation metadata. Both paths now share command-contract validation.
The local certificate is version 3 and includes all 45 existing command
receipts; its original v2 report is preserved as
`../shunt-repair/thermal-04/report-before-command-binding.json`. This is a
revalidation of retained solves, not a claim of new FEM execution. A mutation
test rejects changed arguments even after recomputing artifact hashes.

## Rejected attempts and learned safeguards

Runs 01–14 are historical, rejected or superseded attempts. They must not be
used as current acceptance evidence. Besides meshing/resource/convergence
failures, all used the finished 1.6 mm dimension as the copper/core solid,
incorrectly assigning the 20 µm mask thickness to FR4. Run 15 regenerates all
cases from parsed layer thicknesses. A regression rejects the historical mesh;
this is a model correction, not a board change or a tolerance adjustment.

Thin via barrels need curved-surface resolution even when the surrounding
board mesh is coarse. OpenCASCADE physical-volume selection needs a tolerance
large enough to classify copper correctly, with an independent material census
to catch mistakes. Energy balance alone did not catch either geometry issue.
BiCGStab/ILU1 failed the weaker-joint geometry; ILU2 resolved that probe while
preserving the convergence and energy requirements. The pinned final profile
uses ILU2 for that case and ILU1 otherwise, plus a direct nominal control.

Archives preserve original decoded bytes and SHA-256 digests; `.gz` and raw
copies at the same logical path are rejected as ambiguous. Read/replay works
on either one representation. Failed attempts remain available for diagnosis.
The oversized rejected run-10/nominal-25 mesh archive is stored as numbered
`local.msh.gz.part-*` files; concatenate them in filename order to reconstruct
the gzip stream, then verify the hashes in `local.msh.gz.parts.json` and
`archive-01.json`. That historical case is not an accepted replay fixture.
