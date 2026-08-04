---
title: Formal Board-Property Verification - Plan
type: feat
date: 2026-08-02
topic: formal-board-property-verification
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R26)
---

# Formal Board-Property Verification - Plan

## Goal Capsule

**Objective:** machine-check three board-level invariants with exact graph and geometry algorithms — every net connected, every component inside the outline, pours reaching their nets — so the off-board-component class is structurally impossible to commit.

**Product authority:** temper-placer and board maintainer (single-maintainer project).

**Open blockers:** none.

---

## Product Contract

### Summary

Board invariants stop being DRC-engine heuristics or review assertions. An exact checker runs over the parsed board model: connectivity via union-find over real copper, containment via exact polygon tests against the Edge.Cuts outline, pour reach via zone-to-net copper adjacency. The checks are formal and deterministic.

### Problem Frame

The tank capacitor was staged outside the board outline and committed; nothing checked component-in-outline as a hard invariant. Connectivity today is a kicad-cli DRC warning class (`track_dangling`, `via_dangling`) over the DRC engine's own model, and pour reach is asserted, not proven. The off-board-component class is an invariant violation that no heuristic catches until a human reads the board.

### Requirements

- R26. **Formal board-property verification** (Formal / Board / P2): board-level invariants (every net connected, every component inside the outline, pours reaching their nets) are machine-checked with exact graph algorithms rather than heuristics — the off-board-component class is structurally impossible to commit. (verbatim from origin)
  - Success signal: the three invariants are machine-checked by exact algorithms over the parsed board, and the off-board-component class fails the containment invariant on every run.

### Key Technical Decisions

- KTD1. **Invariants are computed from the parsed board model, independent of kicad-cli DRC** — `parse_kicad_pcb_v6`'s ParsedPCB carries tracks, vias, zones, and nets; exact algorithms run over the board's own geometry, not the DRC engine's heuristic output.
- KTD2. **Connectivity requires real copper per net** — a net is connected only through pads, tracks, and vias; a pad whose net has no copper path is a disconnect, mirroring `resync_pcb_netlist.py`'s ordinal-remap invariant.
- KTD3. **Containment is exact against the Edge.Cuts outline** — the same outline the fab uses; polygon-in-polygon with the board's margin convention, so a staged-outside component fails.
- KTD4. **One combined gate, one report, one CI step** — mirrors `run_all_preflight_checks` aggregation; each invariant is a section of the same report.

### Assumptions

- R26 names no seed; the plan anchors on `io/kicad_parser.py` (parse_kicad_pcb_v6) and `core/graph.py` (NetlistGraph).
- "Every net connected" is scoped to nets with two or more pads; single-pad nets and mechanical refs are reported as INFO, never as violations.
- "Pours reaching their nets" is checked at the declared-net level (zone net name versus copper touching that net's pads), not thermal-relief detail.

---

## Implementation Units

### U1. Copper-connectivity invariant

**Goal:** an exact connectivity check — build the copper graph per net from pads, tracks, and vias; every multi-pad net must be one connected component.

**Requirements:** R26.

**Dependencies:** none.

**Files:** `packages/temper-placer/src/temper_placer/validation/board_properties.py` (new), `packages/temper-placer/tests/validation/test_board_properties_connectivity.py` (new).

**Approach:** From ParsedPCB, collect per-net copper items (pads with their net, track segments, vias) and run union-find over geometric endpoints. A net with multiple pads in different components is reported disconnected. A copper stub attached to no pad of its net is reported as floating copper.

**Patterns to follow:** `core/graph.py`'s NetlistGraph; the copper-item net remapping in `scripts/resync_pcb_netlist.py`.

**Test scenarios:**
1. A synthetic board with two pads of one net joined by a track reports the net connected.
2. The same two pads with the track removed reports the net disconnected, naming both pads.
3. A track whose net has no pads reports floating copper.
4. A via joining two layers keeps a net connected across layers.
5. The connected-net verdict on `pcb/temper.kicad_pcb` is identical across two runs.

**Verification:** the connectivity invariant passes on the current board and fails on each synthetic disconnect.

### U2. Outline-containment invariant

**Goal:** an exact containment check — every footprint's placed bounds lie inside the Edge.Cuts outline polygon; a component outside the outline fails.

**Requirements:** R26.

**Dependencies:** none.

**Files:** `packages/temper-placer/src/temper_placer/validation/board_properties.py`, `packages/temper-placer/tests/validation/test_board_properties_containment.py` (new).

**Approach:** Extract the Edge.Cuts outline polygon. Extract each footprint's placed bounds (position, rotation, size). Test polygon containment exactly. A footprint fully outside, or straddling, the outline fails, naming the ref and the offending geometry. Apply the board margin convention as a configurable inset.

**Patterns to follow:** footprint position extraction in `io/kicad_parser.py`; the geometry-test style in `tests/core/test_pad_geometry.py`.

**Test scenarios:**
1. A synthetic footprint fully inside the outline passes.
2. A synthetic footprint fully outside the outline fails, naming the ref.
3. A footprint straddling the outline edge fails.
4. A footprint inside the outline but inside the margin inset fails when the margin applies.
5. The current board's off-board component (`tank.c_tank3` / board `C27`, staged outside the outline) fails containment.

**Verification:** the containment invariant reports the off-board class on the current board and passes for in-outline components.

### U3. Pour-reach invariant

**Goal:** an exact check that every zone declared on a net has copper reaching that net's pads — a pour assigned to a net it never touches fails.

**Requirements:** R26.

**Dependencies:** U1.

**Files:** `packages/temper-placer/src/temper_placer/validation/board_properties.py`, `packages/temper-placer/tests/validation/test_board_properties_pours.py` (new).

**Approach:** For each zone, resolve its declared net (zone net name and ordinal must agree, per `resync_pcb_netlist.py`'s invariant). Check that the zone's filled copper region is geometrically adjacent to, or covers, at least one pad of that net. A zone that touches no pad of its declared net fails.

**Patterns to follow:** the zone netName-versus-ordinal consistency check in `resync_pcb_netlist.py`; zone handling in `validation/drc_oracle.py`.

**Test scenarios:**
1. A zone declared on net A covering a pad of net A passes.
2. The same zone with its declared net changed to net B (no net-B pad under it) fails, naming the zone and both nets.
3. A zone whose net name and net ordinal disagree fails closed as inconsistent.
4. Every zone on `pcb/temper.kicad_pcb` resolves its declared net consistently.

**Verification:** the pour-reach invariant passes on the current board and fails on each synthetic pour defect.

### U4. Combined gate and bite proof

**Goal:** one gate runs all three invariants over `pcb/temper.kicad_pcb`, reports per-invariant results, and is proven to bite on each invariant's defect class.

**Requirements:** R26.

**Dependencies:** U1, U2, U3.

**Files:** `scripts/check_board_properties.py` (new), `scripts/manifest.yaml` (entry), `packages/temper-placer/tests/validation/test_board_properties_gate.py` (new).

**Approach:** Add a check script aggregating the three invariants with fail-closed exit codes and a per-invariant report. Wire it into the board gates workflow. Add probe tests that inject each defect class into a board copy (component moved off-board, net copper broken, zone re-netted) and assert the gate fails on the owning invariant; the clean board must pass (anti-vacuity).

**Patterns to follow:** the CLI and exit-code shape of `scripts/check_drc_ceiling_approval.py`; the anti-vacuity discipline of `scripts/check_vacuous_gates.py`; the `scripts/manifest.yaml` convention.

**Test scenarios:**
1. A board copy with one component moved outside the outline fails the containment invariant.
2. A board copy with one net's copper removed fails the connectivity invariant.
3. A board copy with one zone re-netted fails the pour-reach invariant.
4. The clean committed board passes all three invariants.
5. An unparseable board file fails closed with a GATE ERROR.

**Verification:** the gate passes on the clean board, fails on each injected defect class, and the script has a `scripts/manifest.yaml` entry. The off-board-component class is reported on the current board as the documented known finding.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/validation/test_board_properties_connectivity.py packages/temper-placer/tests/validation/test_board_properties_containment.py packages/temper-placer/tests/validation/test_board_properties_pours.py packages/temper-placer/tests/validation/test_board_properties_gate.py` passes.
- `uv run --no-sync python scripts/check_board_properties.py` runs all three invariants over `pcb/temper.kicad_pcb` and reports per-invariant verdicts.
- `uv run python scripts/import_linter_gate.py` passes.
- No new zero-coverage public functions in `temper_placer/` (invariant code is exercised by tests).

---

## Definition of Done

- Connectivity, containment, and pour-reach are machine-checked by exact algorithms over the parsed board.
- The off-board-component class (`tank.c_tank3` / board `C27`) fails containment on the current board, documented.
- Each invariant is proven to bite via injected defect probes; the clean board passes (anti-vacuity).
- New scripts have `scripts/manifest.yaml` entries.
- Dead-end or experimental code from implementation is removed from the diff.

---

## Scope Boundaries

- The invariants report; they do not repair. A failing board requires a placement or schematic change.
- DRC stays the authority for electrical rules; the invariants cover the three board-level properties only.

### Deferred to Follow-Up Work

- The board-defect mutation corpus (R38) consumes these invariants as owning gates for its off-board and pour classes.
- Additional invariants (routing symmetry, thermal adjacency) — future candidates for the same checker.
- Hardening the gate to merge-blocking — pending bite-proven history.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R26)
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` (off-board tank cap)
- `packages/temper-placer/src/temper_placer/io/kicad_parser.py` (parse_kicad_pcb_v6)
- `packages/temper-placer/src/temper_placer/core/graph.py` (NetlistGraph)
- `scripts/resync_pcb_netlist.py` (copper and zone net consistency invariants)
