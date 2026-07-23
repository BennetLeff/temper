# Artifact Identity & Provenance: Making Silent Drift Impossible

**Date:** 2026-07-15
**Status:** Requirements agreed, ready for planning
**Scope tier:** Deep — feature (cross-cutting pipeline safety mechanism)

## Problem

Multiple bug classes share one root cause: **nothing machine-checks that an
artifact is what you think it is before a pipeline stage consumes it.**

| Bug class | Example | How it got through |
|-----------|---------|--------------------|
| Wrong board | 15 `pcb/*.kicad_pcb` files are the 33-component benchmark fixture, not the real ~100-component board. Months of placer/router work ran against it. | No check that PCB footprint refs match the netlist. |
| Stale schematics | `pcb/*.kicad_sch` drifted to 120 unconnected pins, 215 ERC violations, backwards IGBTs. | No sync from atopile → schematics; no check they match `default.net`. |
| Config–board mismatch | `configs/temper_deterministic_config.yaml` references refs (`U_GATE`, `C_BUS1`) that exist on the fixture but not the real design. | Config has no binding to a specific board/netlist. |
| Phantom constraints | PCL constraint types exist and are tested but never reach the solver; legacy loader runs instead. | No check that declared constraints reach the solver. |

The common fix: **every pipeline input declares what it was derived from, and
every stage verifies that before it runs — fail-closed, not advisory.**

## Why not the obvious approach

A first-draft proposal was a hand-maintained `artifacts.yaml` at repo root
(declaring `expected_components: 100`, `role: BENCHMARK_FIXTURE`, generators,
etc.) plus `scripts/preflight_identity.py` Python gates.

Rejected because it fights the actual goal (**little maintenance, no drift**):

1. **It's a new drift vector.** A hand-typed `expected_components: 100` is
   another assertion nothing derives — it drifts the moment the design
   changes. The manifest that's supposed to prevent drift can itself drift.
2. **Untyped.** YAML + Python dicts give no compile-time guarantees; the same
   class of "silently empty / downgraded to warning" failures the project
   already suffers from.
3. **High maintenance.** Every new artifact needs a hand-written stanza kept
   in sync by humans.

The project **already has the right mechanism**: the `temper-design-bundle`
Rust crate (`packages/temper-design-bundle/`) with typed `DesignBundle`,
`Provenance` (derived SHA-256 hashes via `sha2`), and hard-fail
`identity::validate()`. This brainstorm extends that crate rather than
building a parallel untyped Python system.

## Decision

**Extend `temper-design-bundle` so that identity and role are DERIVED and
verified in typed Rust. No `artifacts.yaml`. No hand-declared counts.**

### Agreed shape (user decisions)

| Decision | Choice |
|----------|--------|
| Mechanism | **Extend the Rust `temper-design-bundle` crate.** Not new Python, not untyped YAML. |
| Counts / hashes | **Derived, never declared.** Component/net counts are read from the files at bundle-construction time and compared; provenance hashes are computed. Nothing to hand-maintain, so nothing can drift. |
| Board inventory | **One board, generated.** The end state has a single production board derived from the SSOT — no fixture-vs-production distinction to declare, because there is only one kind of board. Delete the 14 confusing duplicates now. |
| Transitional fixture | **Keep exactly one, quarantined, with a sunset.** The placer/router were benchmarked against the 33-component fixture; keep a single clearly-quarantined copy (e.g. `pcb/benchmarks/`) only until they are re-benchmarked against the new correct board, then delete it too. |
| Sequencing | **Schematic generation is the enabling prerequisite.** The identity gate is only meaningful once the real production board exists, derived from generated schematics. Generate schematics → produce the one production board → re-benchmark placer/router against it → retire the fixture. |

## Delivery phases

Structured so the low-risk cleanup lands immediately and only the gate's full
payoff waits on the sibling schematic-generation effort. This is its **own
dependent plan**, not a fold-in to `2026-07-11-001` (see below).

- **Phase A — now, unblocked.** R2 (delete the 14 duplicate boards, quarantine
  one fixture with a sunset) and R4 (config–board binding). No dependency on
  schematic generation; immediate reduction of the drift surface.
- **Phase B — after the production board exists.** R1 (derived ref-overlap
  identity check), R3 (fail-closed pipeline gate), R5 (provenance in outputs),
  R7 (CI), R8 (re-benchmark placer/router, retire last fixture). Gated on the
  2026-07-15 schematic-generation plan producing a real production board.

**Plan relationship:** land this as a standalone plan that declares
`2026-07-11-001` (Atopile+PCL+bundle boundary) as a **prerequisite**, not by
folding these requirements into it. That draft plan is unexecuted and scoped
tightly to the bundle boundary; this work adds materially different surface
area (deleting PCB files, CI enforcement, placer/router re-benchmarking) that
is easier to review and land as a separate unit.

## Existing state (verified 2026-07-15)

- `packages/temper-design-bundle/src/identity.rs` already validates internal
  consistency: schema versions, board **geometry** match, duplicate
  component/net IDs, net-class units, safety-rule reference resolution,
  net-mapping resolution against `NET_NAME_MAPPING.md`.
- `model.rs::Provenance` already carries derived `atopile_sha256`,
  `pcl_sha256`, `board_sha256`, `mapping_sha256`.
- **Gap 1:** no ref-designator overlap check between the actual `.kicad_pcb`
  footprints and the netlist components — the "33-vs-100 wrong board" bug.
- **Gap 2:** no concept of board **role** — the "developed against the
  fixture" bug.
- `docs/plans/2026-07-11-001-feat-atopile-pcl-rust-design-bundle-plan.md`
  (status: draft) covers the atopile→PCL→bundle boundary; this brainstorm
  adds the KiCad-board identity + role dimension on top.

## Requirements

### R1 — Derived board identity check (closes Gap 1)
Extend `identity::validate` (or add a sibling) to compare the KiCad board's
footprint ref-designators against the netlist component refs:
- Compute overlap ratio from the files; **do not** read an expected count
  from any manifest.
- Hard-fail (`DesignBundleError`, structured diagnostic) below a threshold,
  listing the disjoint refs on each side.
- Threshold is a construction parameter with a safe default, not a
  hand-declared per-board number (see Open Questions on bring-up).

### R2 — One board; retire the rest
- Delete the 14 confusing duplicate `pcb/*.kicad_pcb` files now.
- The generated production board (from R6) is the sole long-lived board.
- Keep exactly one quarantined fixture under a dedicated path (e.g.
  `pcb/benchmarks/`) with a documented sunset. Bundle construction infers
  from the path that this board can only build a fixture/dev bundle, never a
  production bundle. Once R8 (re-benchmark) lands, delete it — at which point
  the role concept itself disappears because only one board remains.

### R3 — Fail-closed pipeline gate
- Placement, routing, and validation stages refuse to start without a
  validated bundle for the board they are operating on.
- Running the production pipeline against a benchmarks-path board fails with
  a message explaining the role mismatch.
- Failures are never downgraded to warnings or empty outputs (consistent with
  the crate's existing `R5 — Hard-fail consistency checks`).

### R4 — Config–board binding
- The placement config's target board is verified against the board actually
  being operated on. Prefer deriving the binding (config lives beside its
  board, or references it by derived identity) over a hand-typed
  `bound_to:` field, to avoid re-introducing a drift vector. Exact mechanism
  is a planning decision.

### R5 — Provenance surfaced in outputs
- Pipeline-written PCBs carry a provenance block (input board + netlist +
  config SHA-256, timestamp) as KiCad comments, computed at write time.
- Generated schematics (from the 2026-07-15 schematic-generation brainstorm)
  carry a provenance header including the source-netlist SHA-256, following
  the existing `config.h` / `transition_table.h` regen-and-diff convention.

### R6 — Prerequisite: schematic generation
- Implement the 2026-07-15 generated-schematics work first (separate plan):
  `elec/build/default.net` → generated `pcb/*.kicad_sch` → a real production
  board. Without it there is no correct production board for the identity
  gate to validate, and the other pieces (config binding, provenance chain)
  cannot be exercised end-to-end.

### R7 — CI enforcement
- CI constructs the production bundle on every push; construction failure
  fails the build.
- CI regenerates schematics and DRU and `git diff --exit-code`s (existing
  pattern extended with source SHA-256 in headers).
- Placer/router test jobs that consume a `.kicad_pcb` run the bundle/identity
  construction first.

### R8 — Re-benchmark placer/router against the correct board
- Once the generated production board exists, re-run and re-baseline the
  placer and router against it (new benchmark numbers reflect the real
  ~100-component design, not the 33-component fixture).
- After re-benchmarking, delete the last quarantined fixture (R2); committed
  `.kicad_pcb` inventory becomes exactly one board.

## Success criteria

1. Constructing a production bundle against a benchmarks-path board (or a
   board with <threshold ref overlap) hard-fails with a diagnostic naming the
   disjoint refs. `make route` against the current fixture fails closed.
2. Constructing a bundle against the real production board (once schematics
   generate one) succeeds.
3. No component/net counts are hand-written anywhere in the repo; changing the
   design changes the derived checks automatically with no manifest edit.
4. A config pointed at the wrong board fails bundle construction.
5. Pipeline-written PCBs and generated schematics carry verifiable provenance
   hashes traceable back to `default.net`.
6. Placer/router are re-baselined against the generated board; committed
   `.kicad_pcb` inventory shrinks to one board (the fixture retired).

## Scope boundaries

**In scope:** ref-designator identity check, one-board inventory (delete the
duplicates), a single sunset-tracked quarantined fixture, fail-closed
pipeline gate, config-board binding, provenance in outputs, re-benchmarking
the placer/router, CI enforcement — all built on `temper-design-bundle`.

**Deferred:**
- Deny-by-default on *undeclared* boards (directory convention largely
  obviates it; revisit if stray boards reappear).
- Automating KiCad "Update PCB from Schematic" (no CLI equivalent; manual
  step after schematics exist).

**Outside scope (separate initiatives):**
- Schematic generation itself — 2026-07-15 brainstorm / its own plan (this
  work depends on it but does not subsume it).
- PCL SSOT migration and the phantom-constraint fix — tracked via the
  design-bundle plan's constraint path.
- Fixing bugs inside `elec/src/*.ato` (source review discipline).

## Open questions for planning

1. **Which boards are truly disposable.** Confirm all 14 non-kept
   `pcb/*.kicad_pcb` can be deleted (any referenced by tests, `Makefile`,
   configs, scripts, or docs must be repointed first). Pick the single
   fixture to quarantine and the path for it.
2. **Ref-overlap threshold during bring-up.** With only one real board, the
   check is mostly binary (matches netlist or not), but a partially-populated
   board during bring-up may share <100% of refs. Fixed safe default vs a
   derived/bring-up mode? Avoid a per-board hand-typed number.
3. **Config-board binding mechanism.** Co-location vs derived reference vs a
   minimal typed link — pick the lowest-drift option in planning.
4. **Relationship to the draft design-bundle plan.** *Resolved:* land as a
   standalone dependent plan declaring `2026-07-11-001` as a prerequisite —
   not folded in. Planning still needs to confirm the exact prerequisite
   surface (which bundle types/importers must exist before Phase B).
5. **Production board provenance.** KiCad "Update PCB from Schematic" is a
   manual GUI step with no CLI; how is that board's derivation from generated
   schematics recorded and re-verified?
6. **Placer/router benchmark baseline.** Where the new baseline numbers live
   and what regression tolerance applies once re-run against the real board.

## Evidence

- Existing crate: `packages/temper-design-bundle/src/{identity,model,serialize}.rs`;
  `Provenance` already derives 4 SHA-256 hashes (verified 2026-07-15).
- `identity.rs` checks geometry + reference resolution but not PCB↔netlist ref
  overlap and has no role concept (verified 2026-07-15).
- 15 `pcb/*.kicad_pcb` files present; fixture is ~33 components vs design ~100
  (`elec/build/default.net`: 135 nets, 100 comps).
- Draft plan `docs/plans/2026-07-11-001-feat-atopile-pcl-rust-design-bundle-plan.md`.
- Prerequisite brainstorm `docs/brainstorms/2026-07-15-generated-kicad-schematics-from-atopile-requirements.md`.
- Root-cause context `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`.
