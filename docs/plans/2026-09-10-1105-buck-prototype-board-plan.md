# Plan 1 — finish the standalone buck prototype board

Created: 2026-09-10

## Assignment and completion

Turn the existing buck reference layout into a small, buildable bench board with a matching schematic, real power connectors, practical probe access, and verified assembly details. Finish when the release agent can export the frozen project without making electrical or mechanical decisions.

Read the [handoff index](2026-09-10-1105-buck-prototype-handoff-plan.md). Work in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`, branch `codex/buck-harness-experiment-plan`. Preserve the existing dirty checkout. You own `pcb/prototypes/buck-reva/` CAD files, local libraries, `source-manifest.json`, `verification/`, and its README. Other agents own its `procurement/`, `release/`, `export-release.sh`, and `docs/hardware/buck-reva/`; do not overwrite their work.

## Inputs and fixed decisions

- Electrical core: `elec/src/modules.ato::BuckConverter3V3` and `harness-lab/engineering/circuit-contract.json`.
- Layout baseline: `harness-lab/fixtures/buck-v2/buck-dev-a/witness.kicad_pcb`; copy its required library table, `fixture.pretty`, project rules and settings into the new project, resolving names rather than assuming witness sidecars already exist.
- Layout obligations: `harness-lab/fixtures/buck-v2/buck-v2-contract.json`. Preserve the nine-device electrical obligations, not synthetic terminal obligations.
- Exact components: `harness-lab/audits/buck-final-20260910/components/current-buck-bom.md`.
- Source-build evidence: `harness-lab/audits/buck-final-20260910/source-build/collection.json` and adjacent retained netlist/resolved component data.
- Start with 50 × 40 mm, two copper layers. Do not optimize several alternate layouts or change the regulator/passives merely to explore alternatives.

The retained Atopile build evidence used 0.2.69; `elec/ato.yaml` declares 0.2.68 and only a full-project default target. There is no existing standalone Atopile build target. Do not invent one as an assumed prerequisite or rebuild the whole toolchain just to draw this board.

## Step 1 — establish a standalone, traceable project

1. Read relevant project instructions and the schematic/layout/PCB skills before editing CAD. Record starting status and source hashes. Keep all existing benchmark inputs immutable.
2. Create `pcb/prototypes/buck-reva/buck-reva.kicad_sch`, `.kicad_pcb`, and `.kicad_pro`, with local `fp-lib-table`, `sym-lib-table` where needed, and resolved libraries. Do not change `pcb/temper.kicad_pcb`.
3. Build a legible one-page schematic for the nine-device core plus two connectors and test points. Use existing supported KiCad tools and symbols. Preserve core references U3, L2, C9–C13, R16, R17. Retain UUID/reference association when updating the copied board; prevent unintended replacement or duplicate footprints.
4. Keep Atopile authoritative for the core; record a source-to-schematic comparison in `verification/connectivity.md`. The standalone schematic is the manufacturing representation and authority for prototype-only I/O. Any core mismatch must be resolved explicitly; do not quietly allow two differing circuits.
5. Do not introduce another Python source of electrical truth. A small declarative manifest and exported netlist comparison are sufficient; reusable new implementation logic, if actually needed, follows the repository's Rust ownership rules.

Use this explicit core pin map as a review checklist, rechecking against current source before freezing:

| Net | Required core pins |
|---|---|
| VIN / +15V | C9.1, U3.3, U3.5 |
| GND | C9.2, U3.1, C11.2, C12.2, C13.2, R17.2 |
| SW | U3.2, C10.2, L2.1 |
| BOOT | U3.6, C10.1 |
| VOUT / +3V3 | L2.2, C11.1, C12.1, C13.1, R16.1 |
| FB | U3.4, R16.2, R17.1 |

EN must be tied to VIN: the module exposes enable separately, while the standalone intended circuit connects U3.5 to VIN. Record any deliberate alias translation, such as `gnd` to `GND`, instead of treating net names as proof of connectivity.

## Step 2 — make connector and probe decisions concrete

1. Remove the three synthetic fixture terminals from the new board. Their same-net pin pairs are not a usable conventional supply interface.
2. Select one exact, common DigiKey-listed two-position 5.08 mm vertical through-hole screw terminal, rated at least 3 A and 30 V, for both J1 and J2. Prefer a readily stocked established family with a manufacturer drawing. Confirm conductor range, wire-entry direction, screw access, drill size, pitch and pin numbering. A fixed screw terminal needs no separate mating plug; list one only if the chosen part actually requires it.
3. Wire J1.1 to VIN and J1.2 to GND; J2.1 to VOUT and J2.2 to GND. Use those assignments consistently in CAD, silk, documentation and later procurement. Orient terminals at accessible board edges; exact benchmark terminal coordinates are no longer constraints.
4. Add TP1 VIN and TP2 GND adjacent to C9, plus TP3 VOUT and TP4 GND adjacent to the output capacitors. Use bare probe pads unless removable hardware has a clear benefit. Document that bare pads have no purchasing line item.
5. Provide a compact SW probing location only where it does not lengthen the switching path or create a large copper stub; label optional access TP5 if added. Do not run SW to a cable/header. Probe FB at an existing accessible pad unless a small extra pad can be justified without disturbing the quiet feedback path.
6. Show `VIN 13.5–16.5V`, input/output polarity, `3V3`, connector designators, revision and testpoint names on readable silk. The build is isolated DC only; it contains no mains supply, MCU, 5 V rail, inverter or gate driver.

Send the selected connector MPN, verified pinout and probe map to the other two owners immediately. They can proceed without waiting for final routing.

## Step 3 — verify every land pattern and assembly constraint

Review exact manufacturer drawings and assembly recommendations, retaining source links or locally available evidence and the dimensions checked:

| Refs | Exact MPN | Land-pattern focus |
|---|---|---|
| U3 | LMR51430XDDCR | DDC SOT-23-6 numbering, pin 1, pads and solder access |
| L2 | SRP1265A-5R6M | Bourns SRP1265A pads and maximum body envelope; no generic smaller inductor footprint |
| C9 | CL32B106KBJZW6E | Samsung 1210 soft-termination land/paste guidance |
| C10, C13 | C0603C104K5RACTU | 0603 dimensions and clearance |
| C11, C12 | GRM32ER71E226KE15L | Murata 1210 land pattern and body clearance |
| R16 | RC0603FR-07100KL | 0603, 100 kΩ |
| R17 | RC0603FR-0722K1L | 0603, 22.1 kΩ |

Replace synthetic core footprints with verified library footprints where necessary while preserving pad positions/connectivity or rerouting deliberately. Verify silk, courtyard, fabrication layer, solder mask and paste independently of visual resemblance. Fill Manufacturer, MPN, Value, Footprint, Datasheet, DNP and assembly inclusion fields in the schematic.

Use resolved 3D models where available. If a model is unavailable, a documented manufacturer-dimension envelope and 2D clearance review can close mechanical inspection; a missing cosmetic STEP model alone must not trigger another research loop. Unverified pad geometry or body clearance cannot be waived this way.

## Step 4 — finish routing and mechanical details

1. Keep input-capacitor/U3 power and return paths compact; check the actual current loop, not just center-to-center distance. Keep bootstrap close to U3. Keep SW copper compact and away from FB.
2. Route the feedback divider from the regulated output with a quiet reference and appropriate separation from switching currents. Ensure uninterrupted useful ground return and sufficient copper for the 0.5 A budget and 1 A pulses.
3. Starting rules are 0.6 mm power traces, 0.3 mm signal traces, 0.2 mm clearance/edge clearance, 0.8 mm vias with 0.4 mm drills. These are fixture starting limits, not a substitute for checking current paths, fine-pitch pad escape and the chosen fabricator's capabilities. Document any necessary local rule rather than suppressing errors globally.
4. Retain the 50 × 40 mm outline unless a concrete assembly/access conflict requires adjustment. Provide clearance for terminal screwdrivers and wires and a stable way to support the board on an insulating bench fixture. Add mounting holes only if their positions and copper keepouts have been checked; do not sacrifice the power loop merely to add them.
5. Default fabrication proposal: two-layer FR-4, 1.6 mm thickness, 1 oz finished copper, solder mask both sides, lead-free HASL, top-side assembly. Verify suitability and manufacturer capability before freezing; write the actual selected specification into the project and drawing. Do not inherit the unrelated production-board copper-weight assumptions.

## Step 5 — verify the finished board and freeze it

Use one KiCad version, preferably the already qualified 10.0.6 runtime. Known CLI location is `/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli`; verify it exists and reports 10.0.6. If it is not mounted, recover the recorded runtime or document and validate an explicit version change. Never mix legacy 10.0.4 harness checks into a claimed 10.0.6 receipt.

1. Export the schematic netlist and verify all core pins plus J1/J2/TP pins. Compare PCB connectivity to that schematic, including no missing, duplicate or extra core components. Do not run the fixture's exact terminal census unchanged against the new design.
2. Run native ERC and native PCB DRC with resolved local libraries and project rules. Refill zones first. Require zero ERC errors, zero DRC errors and zero unrouted connections; review every warning and record a concrete disposition.
3. Inspect a rendered schematic, copper/mask/silk views and assembled view. Check connector orientation, polarity, closed outline, drill-to-pad fit, board edges and component clearance. Passing an automated report alone is insufficient.
4. Record the original locality metrics as supporting checks: input ≤8 mm, bootstrap ≤6 mm, output ≤14 mm, FB ≤10 mm, divider ≤6 mm, FB–SW ≥1 mm, ground return ≤4 mm. Review the actual routed loops even when these pass.
5. If a result appears inconsistent, check tool version, library resolution and rule loading before altering geometry. This small prototype has no legitimate production DRC debt to absorb into a ceiling. Repeat suspect checks for diagnosis, not a routine 120-run production-board measurement.
6. Write `verification/board-freeze.md`, raw ERC/DRC reports, netlist, reviewed renders, `verification/footprints.md`, `verification/connectivity.md`, and `source-manifest.json`. Record file hashes, tool version, source paths, source hashes, connector pinout, optional TP population and fabrication specification. A later source change invalidates the freeze.

## Acceptance and stop conditions

- [ ] All nine core references and exact MPNs match the approved design intent; EN is tied to VIN.
- [ ] J1 and J2 are real, verified components with conventional documented pinouts.
- [ ] Probe pads and adjacent grounds are accessible without hazardous improvised connections.
- [ ] Matching schematic/PCB connectivity, footprints, libraries, silk and mechanical clearance are reviewed.
- [ ] Native checks pass on the exact frozen files; warnings are explained without blanket suppression.
- [ ] The release and bring-up owners have the same frozen pinout and source manifest.

Stop for a circuit mismatch, unverifiable footprint, genuine rating conflict, unresolvable short/open, or inaccessible connector. Report the smallest concrete correction needed. Do not block prototype completion solely on combined capacitor derating, hot saturation data, model transient accuracy, or a missing cosmetic 3D model with otherwise verified dimensions.

Do not edit production PCB/DRC ceilings, benchmark fixtures, simulator parameters or the approval registry. Do not place orders or claim measured hardware performance.

## Ready-to-send agent prompt

> Use Luna to execute this board plan in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`. Read the handoff index and preserve existing WIP. You own only the standalone buck Rev A CAD, local libraries, source manifest and verification artifacts. Coordinate connector decisions early with the release and bring-up owners. Finish a reviewed, frozen board and matching schematic; do not reopen model qualification, modify the production board, order parts or fabricate. Return the freeze manifest, checks performed, remaining defects and exact handoff paths.
