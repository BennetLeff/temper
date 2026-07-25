---
title: "feat: Pivot to Fab-Ready Board — Single Digital Verdict Covering Board-Level Gates"
type: feat
status: superseded
date: 2026-07-24
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
swept: 2026-07-25
swept_basis: "verdict layer superseded by the provenance-tiered check corpus"
---

# feat: Pivot to Fab-Ready Board — Single Digital Verdict Covering Board-Level Gates

## Goal Capsule

**Objective:** Pivot the top-level planning horizon from CAD closure ("router
completes, DRC = 0") to a digital **fab-ready verdict**: the temper board's
file set — Gerbers, BOM, pick-and-place, routed board — must clear a single
verdict covering every board-level gate that feeds the safety envelope in
`docs/STRATEGY.md`. Move 2 wires existing `temper-drc-rs` rules into one
verdict layer, then fills every gate the verdict exposes as
UNIMPLEMENTED/UNMEASURED. The outer boundary is **strictly digital filing —
files out, not boards in**. Move 3 owns everything physical (procurement,
bench power-on, protection trips).

**Product authority:** Strategy-Level Move Set #2 in `docs/STRATEGY.md`, added
2026-07-24. Move 2 is enabled by move 1's recorded honest frontier; the pivot
is the explicit resumption of strategy work after the honesty tangent closes.

**Open blockers:** Move 1 must ship (`2026-07-24-001`); move 2 begins on the
recorded post-fail-closed frontier.

---

## Problem Frame

The placer/router subtree has measured itself against one target — CAD
closure (router completion + DRC = 0) — for close to a month. That target is a
means, not an end. `docs/STRATEGY.md` defines the project's actual gates —
efficiency, power accuracy, PID, OCP <1µs, OVP, UVLO, thermal, EMC CISPR
14-1 Class B, mechanical. Fabrication sign-off gates on a CM-submit-readiness
verdict covering the static digital prerequisites of those gates, *not* on a
"24/X routed" headline.

The router-hygiene tangent closed the wrong gap. Even after move 1 ships
forced-segment fail-closed + records the honest frontier, the project has no
single verdict that says "this file set is OK to submit to a CM." The
infrastructure is mostly already built: `temper-drc-rs` ships rules for
safety/isolation, clearance, courtyard, trace clearance, via spacing, zone
containment, component overlap, EMC, ERC, routing (incl. `isolation_slot.rs`,
`isolation_barrier.rs`), and there is a comprehensive
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` with IEC 60335-1 creepage/clearance
requirements. The missing thing is the *verdict layer* that runs all gates
against the temper file set, reports per-gate status, surfaces what's
UNIMPLEMENTED/UNMEASURED, and gets the file set to a single PASS.

Compounding the pre-move-1 wrongness: the fabricated "24/24 routed" figure was
the piantor benchmark board, not the temper board. The same kind of
stale-figure-in-the-wrong-context gap that move 1 corrected at the router
level, move 2 must prevent at the fabrication level by surfacing per-gate
verdicts explicitly — there is no single aggregate number to go stale with a
verdict layer that reports each gate by name.

---

## Requirements

### Verdict layer — wire existing gates, surface gaps

- **R1.** A single fab-ready verdict command runs every board-level gate the
  project recognizes — DRC, ERC, safety/isolation (creepage + clearance +
  isolation-slot integrity per `HIGH_VOLTAGE_CLEARANCE_SPEC`), placement
  rules, routing rules, **connectivity-coverage** (the per-gate verdict that
  verifies the hard-safety-net set routed by move 1's halt), and BOM-vs-
  schematic reconciliation — against `pcb/temper.kicad_pcb` (and the routed
  output + BOM + placement files), and emits a per-gate
  PASS/FAIL/UNIMPLEMENTED/UNMEASURED verdict plus a single aggregate VERDICT
  (PASS only if every gate is PASS). **EMC is reported as `UNMEASURED` at
  this layer** — see R9's deferral. Trace: `@req(this-plan, R1)`.
- **R2.** The verdict reuses existing `temper-drc-rs` rule implementations for
  the **geometric gates** (DRC, clearance, courtyard, trace_clearance,
  via_spacing, zone_containment, component_overlap, EMC, ERC,
  routing/isolation_slot, routing/isolation_barrier, safety/isolation) — no
  new gate logic is written where an existing rule already covers the spec.
  **Net-new rule work is limited to non-geometric gates**: BOM-vs-schematic
  reconciliation and protection-circuit value-vs-spec validation (R5/R6),
  both of which require a BOM/schematic ingestion path temper-drc-rs does
  not currently have. Trace: `@req(this-plan, R2)`.
- **R3.** The first action of move 2 is a **gap inventory**: run the verdict
  against the current temper file set and catalog which gates are PASS,
  which are FAIL (with a fix), and which surface as UNIMPLEMENTED or
  UNMEASURED. The inventory is the input to the gate-fill phase. Trace:
  `@req(this-plan, R3)`.
- **R4.** Gates that surface as UNMEASURED (the existing `temper-drc-rs` rule
  exists but is not wired into the verdict) are wired in first; gates that
  surface as UNIMPLEMENTED (no rule exists for a gate `HIGH_VOLTAGE_CLEARANCE_SPEC`
  or `STRATEGY.md` demands) are implemented next, **capped**: if the gap
  inventory surfaces more than a small bound (proposed: 3 UNIMPLEMENTED
  geometric gates, plus the net-new BOM/schematic reconciliation + value-vs
  -spec set already scoped in R5/R6), the excess is scoped as a separate
  DRC-engine-completeness track at ce-plan time, not absorbed silently into
  move 2. Both follow the fail-closed `UNMEASURED` discipline per
  `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`.
  Trace: `@req(this-plan, R4)`.

### Static protection-circuit interlock (no power)

- **R5.** The verdict enforces a **static protection-circuit interlock** for
  every protection gate in `STRATEGY.md`: OCP-01/02, OVP-01, THM-01/02,
  UVL-01/02. Static, no-power checks only — the verdict never claims a
  protection actually trips at the rated current/voltage/temperature (that is
  move 3). The static checks cover: protection components present on BOM and
  placed per spec (sense resistor for OCP, zener/divider for OVP, NTC
  thermistor placement in the THM-01/02 heatsink/coil zones, gate-drive UVLO
  chip on BOM), creepage/clearance on the protection side of the isolation
  barrier, **and the full latch-loop netlist topology end-to-end**: for each
  protection gate the verdict asserts a connected net path from sense element
  → comparator → latch SET/RESET → driver DIS/EN → IGBT gate exists in the
  parsed schematic netlist, and asserts no parallel power path bypasses the
  latch. (A verdict that PASSes presence + value but misses a disconnected
  latch output gives a false sense of fab-readiness; the netlist-topology
  check is distinct from presence/value and is required for R5 PASS.)
  Trace: `@req(this-plan, R5)`.
- **R6.** Protection-circuit **values** against the gate spec — sense
  resistor value plausibly landing in the 45–55A primary / 55–65A secondary
  windows for OCP-01/02, OVP divider plausibly tripping at 390–410V, NTC
  thermistor B-value plausibly readable at 85 °C / 120 °C thresholds. **A
  mis-rated component is a verdict FAIL, not a record-only note.**
  Implementation-of-R6 is **deferred to the gate-fill phase**: it requires a
  net-new BOM/schematic-side ingestion path (KiCad BOM CSV parsing or atopile
  /ato export consumption from `elec/`) that temper-drc-rs does not currently
  have; the inventory (R3) determines whether presence-only (R5) is
  insufficient, after which R6 is implemented as a separately-scoped value-vs
  -spec rule set. R6 is NOT promiscuously added to the verdict layer's
  geometric reuse. Trace: `@req(this-plan, R6)`.

### Firmware state-machine traceability as a move-2 fab-ready assertion

- **R7.** The verdict enforces **firmware-state-machine traceability** as a
  static fab-ready assertion: every protection gate (OCP-01/02, OVP-01,
  THM-01/02, UVL-01/02, plus EFF-01/02 where it's statically checkable) has
  at least one `@req(<plan-id>, <req-id>)` annotation in
  `firmware/main/state_machine.c`, its transition-table codegen
  (`firmware/main/transition_table.h` from `firmware/transition_table.yaml`),
  or a state-machine unit test — using the existing traceability contract
  documented in `docs/TRACEABILITY.md` and gated by the existing
  `test_traceability_gate.py`. A protection gate that powers-on trips a firmware
  path the gate has no record of is a verdict FAIL. Trace: `@req(this-plan, R7)`.
  - **R7a. (firmware opt-in — required pre-work)** Add a `TRACEABILITY`
    sentinel to `firmware/main/` and `firmware/test/` (currently absent —
    the only opted-in directory is `packages/temper-placer/tests/router_v6/`).
    Without this sentinel, R7's verdict FAILs on a tooling-absence dressed as
    a safety-absence. Trace: `@req(this-plan, R7a)`.
  - **R7b. (annotation authoring — required firmware work scoped to move 2)**
    Author `@req` annotations on every protection-trigger transition in
    `state_machine.c` and `transition_table.h` mapping to the `STRATEGY.md`
    gate IDs (`OCP-01`, `OCP-02`, `OVP-01`, `THM-01`, `THM-02`, `UVL-01`,
    `UVL-02`). Zero `@req` annotations currently exist in `firmware/`. This
    is in-scope firmware work for move 2 because move 2's verdict cannot
    reach R7 PASS without it, and move 3's R11 is explicitly forbidden from
    re-deriving firmware-path existence. Trace: `@req(this-plan, R7b)`.
  - **R7c. (firmware transition-table additions — required firmware precursor
    work scoped to a move-2.5 transition-table-addition track)** The
    production firmware state-machine currently has **no firmware path for
    OVP-01, UVL-01, or UVL-02** (`firmware/main/state_machine.h:89-112`
    EVENT_LIST lacks `EVENT_OVER_VOLTAGE`, `EVENT_UVLO_GATE_DRIVE`,
    `EVENT_UVLO_LOGIC`; `firmware/transition_table.yaml` has no
    corresponding transitions), and **THM is a single generic
    `EVENT_OVER_TEMP` with no heatsink-vs-coil distinction** (THM-01 at
    85 °C heatsink and THM-02 at 120 °C coil cannot be separated in the
    transition table today). Move 2's R7 verdict FAULTs on these gates
    not because the gates are unsafe but because the firmware has not yet
    declared the trips. **This is owned by a move-2.5 firmware transition-
    table-addition track** (split out from move 2's verdict work because it
    is firmware engineering, not DRC-rule work; move 2 depends on move 2.5
    for R7 PASS, move 3 depends on it for R1 bench-trip on OVP/UVLO/THM-02):
    add `EVENT_OVER_VOLTAGE`, `EVENT_UVLO_GATE_DRIVE`, `EVENT_UVLO_LOGIC`;
    split `EVENT_OVER_TEMP` into `EVENT_OVER_TEMP_HEATSINK` and
    `EVENT_OVER_TEMP_COIL`; add the corresponding rows in
    `firmware/transition_table.yaml` and FAULT_LIST entries; author the
    `@req` annotations per R7b. Trace: `@req(this-plan, R7c)`.
- **R8.** R7's firmware-traceability assertion is specifically the static
  armor that move 3's *dynamic* bench-trip validation then exercises — the
  two are sequenced: R7 proves the firmware path exists on paper; move 3
  proves the firmware path actually fires when the protection triggers.
  Move 2 never claims dynamic trip behavior; move 3 never re-derives
  firmware-path existence from scratch (it consumes R7's static
  assertions as input). Trace: `@req(this-plan, R8)`.

### EMC deferral and performance static prerequisites

- **R9.** EMC-01/02/03 are reported as **`UNMEASURED`** by move 2's verdict.
  EMC static layout prerequisites (return-path integrity, decoupling-cap
  placement per spec, switch-node copper area) are **not** part of the
  verdict layer — each has no stated threshold in `STRATEGY.md` move 2's
  enumerated scope and not enumerated in `STRATEGY.md`'s move-2 gate list.
  They are owned by a separately-scoped future **EMC static-prerequisite
  track** (opened when move 3c precompliance runs, against concrete
  thresholds), not by move 2's verdict work. Move 2 explicitly does not
  bundle EMC layout-rule-writing into its scope — that would be the
  shape of leaf-dancing this move-set is trying to escape. Trace:
  `@req(this-plan, R9)`.
- **R10.** For EFF-01/02 (efficiency >90%/92%) and PWR-01/02 the verdict
  enforces only the **static digital prerequisites**: the power stage is
  fully present in the file set (IGBTs, gate drivers, inductor, sense
  components on BOM + placed), no obvious topology error (parallel MOSFET
  paths, missing gate resistors). Dynamic efficiency measurement is move 3+.
  Trace: `@req(this-plan, R10)`.
- **R11.** Mechanical gates (MCH-01/02/03 — button force, knob torque, glass
  load) are **out of move 2's scope entirely** — they have no static digital
  prerequisite beyond footprint/symbol presence, which is folded into the
  base BOM-vs-schematic reconciliation. They are owned by the physical
  lab/fabrication track, not by any digital verdict. Trace: `@req(this-plan, R11)`.

### Dependency on move 1 + floor-failure handling

- **R12.** Move 2 begins only after move 1 (`2026-07-24-001`) ships — the
  verdict needs the honest post-fail-closed routed-board geometry to check
  creepage/clearance/EMC against. Move 2 plans against the recorded frontier;
  no separate "what if move 1 stalls" arm is maintained inside move 2.
  Trace: `@req(this-plan, R12)`.
- **R13.** Move 2 begins only after move 1 ships. If move 1's per-gate
  floor condition (R4) fails — any hard-safety net still unrouted after move
  1's halt decision — move 2's verdict runs against the known-incomplete file
  set and is expected to FAIL on the **connectivity-coverage gate**; that
  FAIL is itself the recovery trigger. The recovery work is owned by a
  **separate routing-recovery track** scoped at the time the FAIL fires,
  with its own halt discipline and a floor-of-floors below which a board
  re-spin is escalated rather than further router-algorithm work — this
  is NOT pre-named or pre-scoped inside move 2's requirements-only artifact.
  Move 2 explicitly disclaims router/placer algorithm work; routing-recovery
  is a sibling track, not a sub-arm of move 2. Trace: `@req(this-plan, R13)`.

---

## Acceptance Examples

- **AE1 — Covers R1, R2, R3.** Given the verdict command runs on
  `pcb/temper.kicad_pcb`, the output is a per-gate list (DRC: 381 FAIL,
  ERC: UNMEASURED, isolation/creepage: PASS, OCP-component-presence: PASS,
  THM-thermistor-placement: FAIL, firmware-traceability for THM-01/02: FAIL,
  etc.) plus a single aggregate VERDICT: FAIL. The gap inventory is the
  catalog of which gates drove the FAIL.
- **AE2 — Covers R4, R5, R6.** Given the gap inventory surfaces the THM
  thermistor placement gate as UNIMPLEMENTED, the gate-fill phase adds a
  `temper-drc-rs` rule that checks NTC thermistor placement against the
  heatsink (85°C) and coil (120°C) zones the spec identifies, on the next
  verdict run that gate is no longer UNIMPLEMENTED — it is PASS (or FAIL
  with a real misplacement flagged).
- **AE3 — Covers R7, R8.** Given the firmware state-machine has a transition
  for `OVERCURRENT → FAULT` but no `@req(OCP-gate-plan, OCP-01)` annotation
  on it, the firmware-traceability assertion in the verdict FAILs and
  move 2 owns the in-scope fix (adding the annotation with the correct
  plan-id/req-id). Move 3 then takes the annotation's existence as given
  and exercises the dynamic trip.
- **AE4 — Covers R9.** Given the ground pour is discontinuous (return path
  broken under the IGBT switch node), the verdict FAILs the EMC static
  prerequisite on return-path integrity even though no CISPR measurement has
  been performed — the verdict reports the digital-signature defect; the
  emitter-level CISPR measurement is move 3+.
- **AE5 — Covers R10, R11.** Given the BOM is missing the gate resistor on
  the low IGBT, the verdict FAILs the EFF static prerequisite (incomplete
  power stage). Mechanical gates (MCH-01/02/03) are not part of the verdict
  output — they have no digital signature at move 2's level.
- **AE6 — Covers R12, R13.** Given move 1 ships cleanly at 68/95 completion,
  move 2's verdict runs against the resulting routed board and the verdict
  reflects the (honestly incomplete) geometry — the DRC and creepage gates
  run against the real copper, not a fabricated-completion substitute.
  Given move 1's floor fails (55/95) instead, a separate routing-recovery
  planning track opens; move 2's own scope is unchanged.

---

## Success Criteria

- A single command emits a per-gate fab-ready verdict covering DRC, ERC,
  safety/isolation, EMC static prereqs, performance static prereqs,
  protection-circuit static interlock, and firmware-state-machine
  traceability for every protection gate in `STRATEGY.md`.
- The verdict distinguishes PASS / FAIL / UNIMPLEMENTED / UNMEASURED per
  gate; the aggregate VERDICT is PASS only when every gate is PASS.
- Every gate `STRATEGY.md` and `HIGH_VOLTAGE_CLEARANCE_SPEC` require has a
  rule implemented in `temper-drc-rs` and wired into the verdict (no
  UNIMPLEMENTED remaining).
- No gate is left silently UNMEASURED — fail-closed per the project's
  two-tier acceptance-gate discipline.
- The file set (Gerbers + BOM + PnP + routed board + spec) clears the
  verdict OR an explicit, named FAIL list blocks submission.
- Firmware-state-machine traceability is a verdict gate; move 3 can consume
  it as a pre-proven static assertion.
- Mechanical gates are explicitly out of scope and not part of the
  verdict's output.

---

## Key Decisions

- **Outer boundary = files out, not boards in — and the verdict PASS is a
  precondition, not a product milestone.** Move 2 delivers a digital file
  set that clears a verdict; no board exists, no protection has tripped,
  no performance has been measured. The verdict PASS is a precondition for
  fabrication (move 4), not the "fab-ready" milestone a team might
  otherwise celebrate as a product step — to prevent it from becoming the
  next "24/24 routed" intermediate number that drains urgency from moves
  3 and 4. Procurement, bench power-on, and protection trips are move 3
  and move 4. The line is "I could click Submit on a CM order and trust
  the files," not "the product is fab-ready."
- **Wire existing geometric gates AND fill the gaps the wiring surfaces —
  with a cap.** The verdict layer is cheap for **geometric** gates (DRC,
  creepage, isolation-slot, courtyard, etc.) and surfaces the gap
  inventory for free; the gate-fill phase uses that inventory as its
  backlog, capped per R4 (excess UNIMPLEMENTED gates are scoped as a
  separate DRC-engine-completeness track, not absorbed silently into move
  2). The BOM/schematic/component-value gates (R5/R6) are NOT free —
  they require a net-new BOM/schematic ingestion path. This matches the
  AGENTS.md fail-closed/UNMEASURED discipline while bounding the
  leaf-dancing risk at gate-fill.
- **Static protection interlock covers presence + latch-loop topology + (via
  move 2.5) firmware-traceability.** Move 2 proves on paper that every
  protection gate has (a) its sense/comparator/latch/driver components on
  BOM + placed, (b) the latch-loop netlist topology wired end-to-end with
  no parallel power bypass, and (c) its firmware path declared (`@req`
  annotations gated by the existing traceability gate — R7a–R7c). Move 3
  proves the path fires when the protection physically triggers. The
  three are sequenced; move 3 consumes R7's static assertions as input,
  never re-derives them from scratch.
- **Mechanical gates (MCH-01/02/03) and board fabrication are explicitly
  out of move 2's scope.** No static digital signature makes mechanical
  meaningfully a move-2 gate; fabrication needs move 2's file set but
  is not consumed by it. Both are owned by move 4 (Fabrication +
  Mechanical + Cert-Lab Handoff Track per `STRATEGY.md`)', not orphaned.
- **EMC layout prerequisites are NOT bundled into move 2's verdict.**
  Each has no stated threshold in `STRATEGY.md`'s move-2 enumerated
  scope; bundling them now would be the same shape of leaf-dancing the
  move-set is trying to escape. EMC is `UNMEASURED` in the verdict; a
  separately-scoped future EMC track owns layout prerequisites with
  concrete thresholds when move 3c precompliance runs.
- **Move 2 plans against move 1 succeeding cleanly; floor-failure is
  scoped at FAIL-time, not pre-named.** Move 2 begins after move 1 ships;
  if move 1's per-gate floor condition trips, move 2's verdict FAIL on
  connectivity-coverage is the recovery trigger, and the routing-recovery
  track is scoped at that time with its own halt discipline — not
  pre-named or pre-scoped inside this requirements-only artifact.
  Pre-specifying a fourth brainstorm for a contingency that may not
  materialize is the planning-surface expansion the user wanted to avoid.
- **Per-gate verdict, no single headline number.** Move 1 taught the
  project that a single "24/24"-style number invites stale-figure-in-
  wrong-context drift. The verdict layer reports every gate by name with
  its status; there is no aggregate that can substitute for the per-gate
  view.

---

## Scope Boundaries

**In scope:**
- The verdict layer command and per-gate output (R1).
- Wiring every existing `temper-drc-rs` geometric rule into the verdict
  (R2 — geometric gates only).
- The gap inventory as the first action of move 2 (R3, R4).
- Implementing `temper-drc-rs` rules for any geometric gate currently
  UNIMPLEMENTED (R4), capped per the bounded-gate-fill rule.
- Static protection-circuit interlock: presence + latch-loop topology
  end-to-end (R5).
- Protection-circuit value-vs-spec validation (R6) — net-new BOM/schematic
  ingestion path, deferred to gate-fill phase when R3's inventory
  confirms presence-only is insufficient.
- Firmware-state-machine traceability as a verdict gate (R7, R8) — uses
  the existing `test_traceability_gate.py` per `docs/TRACEABILITY.md`.
- Firmware opt-in + `@req` annotation authoring (R7a, R7b) — in-scope
  firmware work for move 2.
- Power-stage completeness for EFF/PWR static prerequisites (R10).

**Out of scope:**
- EMC layout prerequisites (R9 — explicitly deferred to a separately-
  scoped EMC track).
- Firmware transition-table additions for OVP/UVLO/THM-split (R7c — owned
  by the move 2.5 firmware transition-table-addition track).
- Physical procurement, board fabrication, bench power-on, dynamic
  protection trips — all move 3 and move 4.
- Emitter-level CISPR Class B measurement — move 3c+/lab activity.
- Dynamic efficiency measurement — move 3b+.
- Mechanical gate validation (MCH-01/02/03) — move 4.
- Full IEC 60335-1 compliance certification — separate lab activity (move
  4 cert-lab handoff).
- Router/placer algorithm improvements; routing-recovery — sibling track
  scoped at floor-FAIL time, not inside move 2.
- Re-design of `HIGH_VOLTAGE_CLEARANCE_SPEC` or `PCB_SPECIFICATION` — move 2
  implements against them as authoritative; spec changes are their own work.
- Re-implementing gates the existing `temper-drc-rs` already covers — R2
  explicitly forbids this.

**Deferred:**
- EMC static prerequisites, dynamic EMC, dynamic efficiency, mechanical,
  full compliance certification — all to move 3c + move 4 + the lab track.

---

## Dependencies / Assumptions

- Depends on move 1 (`2026-07-24-001`) shipping — the verdict runs against
  the honest post-fail-closed routed-board geometry.
- Depends on the move 2.5 firmware transition-table-addition track (R7c)
  shipping its firmware-side additions before R7 verdict can PASS on
  OVP-01/UVL-01/UVL-02 and the heatsink-vs-coil split of THM-01/THM-02;
  move 3's R1 bench-trip on those same protections also depends on it.
- Assumes `temper-drc-rs`'s current **geometric** rule surface (safety/
  isolation, clearance, courtyard, trace_clearance, via_spacing,
  zone_containment, component_overlap, EMC, ERC, routing/isolation_slot,
  routing/isolation_barrier, oracle, placement) reuses correctly when
  wired into the verdict, without per-rule rewrites. **Non-geometric**
  coverage (BOM/schematic reconciliation, protection-circuit value-vs-spec)
  is net-new and requires an ingestion path KiCad-BOM-CSV-or-atopile/ato-
  via-`elec/`-export that temper-drc-rs does not currently have.
- Assumes `HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `PCB_SPECIFICATION.md`,
  `NET_CLASS_SPECIFICATION.md`, `VIA_SPECIFICATION.md` are authoritative
  for gate definitions; move 2 does not re-spec.
- Assumes `firmware/main/` and `firmware/test/` can opt into the
  TRACEABILITY system via sentinel file (R7a) without breaking existing
  gates — the only currently opted-in directory is
  `packages/temper-placer/tests/router_v6/`.
- The "enough nets routed for fab-ready" criterion is owned by move 2's
  own gate set specifically the **connectivity-coverage gate** plus the
  creepage/clearance surfaces — not the absolute A*-routable completion
  percentage (per the per-gate discipline move 1's R4 also adopts).

---

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] The exact output format of the verdict — a single
  machine-readable JSON plus a human-readable summary, or a single combined
  report; the verdict command's CLI shape and exit-code semantics (0 = PASS,
  non-zero = FAIL with a real distinction between FAIL-because-violation
  and FAIL-because-UNMEASURED).
- [Affects R3][Needs research] The initial gap inventory's outcome —
  specifically, which gates surface as UNIMPLEMENTED vs UNMEASURED. Move 2's
  gate-fill backlog is unknown until the first verdict run completes.
- [Affects R5, R6][Technical] How `temper-drc-rs` checks protection
  component *values* (sense resistor resistance, NTC thermistor B-value)
  — does it read BOM fields directly, or parse component attributes from the
  schematic, or both via the ato/atopile path that exists in `elec/`?
- [Affects R9][Needs research] Whether the existing `temper-drc-rs` EMC
  rules already cover return-path integrity and decoupling-cap placement —
  note: even if rules exist, the layout-prerequisite thresholds are
  deliberately out-of-scope for move 2 per R9; this OQ is informational.
- [Affects R7][Technical] Whether the traceability gate
  (`test_traceability_gate.py` / `scripts/check_traceability.py`) already supports "every STRATEGY.md protection gate
  has at least one annotation" as a query, or whether move 2 needs a small
  extension to inject STRATEGY.md gate IDs alongside plan @req IDs.
- [Affects R13][Needs research] The exact threshold at which a separate
  routing-recovery planning track gets triggered — move 1's per-gate floor
  (any hard-safety net unrouted) is the router-level trigger, and at the
  move-2/verdict level the same per-gate discipline applies via the
  verdict's connectivity-coverage gate. Whether move 2's
  connectivity-coverage threshold is exactly the same hard-safety
  enumeration or independently defined is a planning decision.
- [Affects the move-set as a whole][Strategic] **Do-less baseline: order
  the board now against the current file set and fill verdict gates
  against the returned artifact, rather than building the verdict layer
  before the board exists.** The gate-first ordering was assumed during
  the brainstorm, not explicitly justified against this alternative. The
  adversarial reviewer (H7) flagged this as a structural misrepresentation:
  the move-set may re-create leaf-dancing at one level up (gates on gates
  on gates whose PASS conditions are themselves the deliverables) where
  the user's complaint was the project keeps building gate infrastructure
  instead of hardware. Revisit if gate-first work exceeds ~4 weeks. This
  is recorded as an Outstanding Question per the doc-review disposition,
  not a settled decision — ce-plan inherits it as live input.

---

## Sources & References

- Strategy entry point: `docs/STRATEGY.md` Current Board Closure State +
  Strategy-Level Move Set (added 2026-07-24).
- Move 1 dependency: `docs/plans/2026-07-24-001-feat-close-honesty-tangent-pivot-to-fab-ready-plan.md`.
- DRC engine surface: `packages/temper-drc-rs/src/rules/{drc,emc,erc,oracle,placement,routing,safety}`.
- Gate specs (authoritative): `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`,
  `docs/specs/PCB_SPECIFICATION.md`, `docs/specs/NET_CLASS_SPECIFICATION.md`,
  `docs/specs/VIA_SPECIFICATION.md`.
- Firmware-traceability contract: `docs/TRACEABILITY.md`
  + existing `test_traceability_gate.py`.
- Firmware transition-table codegen: `firmware/transition_table.yaml`
  → `firmware/tools/gen_transition_table.py`
  → `firmware/main/transition_table.h`, plus the regenerated test at
  `firmware/test/test_transition_table_generated.c`.
- Fail-closed / two-tier-gate institutional discipline:
  `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`.
- Stale-figure provenance: AGENTS.md's `24/24`-vs-temper-recording language
  in `STRATEGY.md` Current Board Closure State (move 1 corrected the router
  level; move 2 prevents its analog at the fabrication level via per-gate
  verdicts).