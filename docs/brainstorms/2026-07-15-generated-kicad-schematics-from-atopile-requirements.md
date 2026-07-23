# Generated KiCad Schematics from Atopile Netlist

**Date:** 2026-07-15
**Status:** Requirements agreed, ready for planning
**Scope tier:** Deep — feature (cross-cutting pipeline change)

## Problem

The repo maintains two parallel descriptions of the circuit:

1. `elec/src/*.ato` (atopile) → `ato build` → `elec/build/default.net` — the
   source of truth. Currently complete: 135 nets, 100 components, **zero**
   unconnected pins.
2. `pcb/*.kicad_sch` — 7 hierarchical sheets, hand-drawn by past sessions,
   with no pipeline step keeping them in sync.

The hand transcription has drifted badly. Current state: ~120 unconnected
pins in the exported schematic netlist, an entirely unwired gate driver
(hand-schematic `U1` / UCC21550), 215 ERC violations, plus the historical
bug list attributed to this gap in
`docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`
(short circuit, backwards IGBT, backwards bootstrap diode, swapped
comparator inputs, backwards mains rectifier diodes).

Manual repair is the failure mode, not the fix: every hand-placed wire is
another coordinate-precision transcription that nothing verifies.

## Decision

Make `pcb/*.kicad_sch` **derived output**, generated from
`elec/build/default.net`. Humans stop editing schematic files entirely.

### Agreed shape (user decisions)

| Decision | Choice |
|----------|--------|
| Connectivity representation | **Pure label-per-pin on all 7 sheets.** A net label placed exactly at each pin endpoint binds the pin to its net. No drawn wires anywhere — eliminates the wire-geometry bug class entirely. |
| Symbol placement | **Fully generated.** Deterministic grid layout, grouped by `.ato` module hierarchy. Existing hand layout is discarded. |
| Safety review surface | **Review `elec/src/*.ato` + the oracle report.** The third-source rule (independent datasheet/textbook check for safety-critical topology) from the 2026-07-14 solutions doc now applies during `.ato` review. The schematic is no longer a review artifact. |
| Sequencing | **Generator first** (fixes the live breakage), with the oracle check built into the generator as its mandatory self-verify step. A standalone CI gate can be added after. |
| First milestone | **All 7 sheets in one shot.** No single-sheet pilot. |

## Requirements

### R1 — Generator
A script (proposed home: `scripts/gen_schematics.py`, with a
`scripts/manifest.yaml` entry per repo convention) that:

- Reads `elec/build/default.net` (KiCad netlist format, atopile output)
- Emits all 7 `pcb/*.kicad_sch` sheets plus consistent sheet instances in
  `pcb/temper.kicad_sch`
- Assigns components to sheets using the netlist's `sheetpath` module
  hierarchy (e.g. `Top::hb.gate_hs.driver` → Half_Bridge sheet)
- Places symbols on a deterministic grid, grouped by `.ato` sub-module
- Emits exactly one net label per pin, positioned at the pin's absolute
  endpoint (computed from symbol origin + lib pin offset — library code,
  not hand math)
- Emits hierarchical labels / sheet pins consistent with net traversal
  across sheets
- Is deterministic: same `default.net` in → byte-identical sheets out
  (stable UUIDs derived from atopile `tstamps`)

### R2 — Built-in oracle (self-verify)
After generating, the script must:

- Run `kicad-cli sch export netlist` on the generated project
- Compare connectivity **partitions** (net names aside, the grouping of
  `(ref, pin)` into nets must be isomorphic) against `default.net`
- Exit non-zero with a precise diff (which pins are in the wrong group) on
  any mismatch — same post-solve-audit pattern mandated for CP-SAT
  constraints in `AGENTS.md`
- Also assert zero `unconnected-(...)` nets except pins atopile itself
  leaves unconnected, and no ERC errors of class `pin_not_connected` /
  `label_dangling` (advisory report for the rest)

### R3 — Ref designators
Atopile's refs win (e.g. atopile `U1` = fuse). Hand-schematic refs are
discarded with the rest of the hand drawing. Any downstream artifact that
referenced old hand refs must be checked in planning (see Open Questions).

### R4 — Pipeline integration
- `make netlist` (or a new `make schematics`) runs the generator after
  `ato build`
- Generated `.kicad_sch` files stay committed; CI regenerates and
  `git diff --exit-code`s, following the existing `config.h` /
  `transition_table.h` regen-and-diff convention
- A header comment in each generated sheet marks it `GENERATED — do not
  hand-edit; edit elec/src/*.ato and run make schematics`

### R5 — Documentation
- Update `AGENTS.md` with the regen workflow (same format as the config.h
  section)
- Record the decision + rationale as a solutions doc update or successor to
  the 2026-07-14 workflow-issues doc (schematic is now derived; review
  lives in `.ato`)

## Success criteria

1. `kicad-cli sch export netlist` on generated sheets → connectivity
   partition identical to `elec/build/default.net` (oracle passes)
2. Zero unexpected `unconnected-(...)` nets (baseline today: ~120)
3. Regenerating twice with no `.ato` change produces zero git diff
4. A deliberate `.ato` connectivity change flows through
   `ato build` → generator → exported netlist with no hand edits
5. CI fails if committed sheets drift from regenerated output

## Scope boundaries

**Deferred for later:**
- Standalone CI oracle gate as a separate check (generator `--check` mode
  covers it initially)
- Generated visual wire routing for readability (revisit only if `.ato`
  review proves insufficient in practice)
- `ato view` / atopile KiCad plugin integration (usability unverified)
- Auto-generating the PCB from the netlist (existing `make route` flow
  unchanged for now)

**Outside scope:**
- Fixing bugs in `elec/src/*.ato` itself (source review is a separate,
  ongoing discipline — the 2026-07-14 doc's third-source rule)
- Footprint generation (`make footprints` placeholder unchanged)

## Known unknowns / open questions for planning

1. **Symbol source (main technical risk).** `default.net` carries
   footprints but no schematic symbols. The generator needs a symbol
   definition per component. Candidate sources, to evaluate in planning:
   harvest the embedded `lib_symbols` from the current hand-drawn sheets
   into a checked-in library keyed by part; synthesize plain box symbols
   from the netlist's pin lists; or a hybrid (harvest where available,
   synthesize otherwise). Synthesis is the only option that keeps the
   generator total over new `.ato` components.
2. **PCB linkage.** `pcb/temper.kicad_pcb` (and `temper_placed.kicad_pcb`)
   reference the old hand refs/UUIDs. Regeneration changes both. Planning
   must decide how the board re-syncs (netlist import keyed on new refs vs.
   re-annotation map). Unverified assumption: the board's footprint set is
   close enough to `default.net`'s to re-link mechanically.
3. **Power symbols / global nets.** How GND/+15V/+3.3V render on generated
   sheets (global labels vs power symbols) — cosmetic, but affects ERC
   noise.
4. **Pins atopile intentionally leaves unconnected** (e.g. NC pins) need
   `no_connect` markers to keep ERC clean.
5. **Dirty working tree.** `pcb/half_bridge.kicad_sch`,
   `power_input.kicad_sch`, `power_management.kicad_sch`,
   `sensing.kicad_sch` have uncommitted hand edits from the interrupted
   repair session. These become moot once generation lands; decide in
   planning whether to commit, stash, or discard them before the first
   generated commit.

## Evidence

- `elec/build/default.net`: 135 nets, 100 comps, 0 unconnected (verified 2026-07-15)
- Exported hand-schematic netlist: 120 `unconnected-(...)` nets, 215 ERC violations (verified 2026-07-15)
- Ref divergence: atopile `U1` = fuse (`power_in.fuse`); hand-schematic `U1` = UCC21550 gate driver (verified 2026-07-15)
- Pipeline gap + bug history: `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`
- Tooling available: `kiutils` importable (`kiutils.schematic.Schematic`), `kicad-cli` on PATH, `ato` at `~/.local/bin/ato`
