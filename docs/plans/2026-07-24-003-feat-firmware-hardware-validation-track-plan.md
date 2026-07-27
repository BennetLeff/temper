---
title: "feat: Firmware + Hardware Validation Track — Bench-Trip Every Protection Plus Performance Plus EMC Precompliance"
type: feat
status: superseded
date: 2026-07-24
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
swept: 2026-07-25
swept_basis: "re-sequenced under STRATEGY v2 build order"
---

# feat: Firmware + Hardware Validation Track — Bench-Trip Every Protection Plus Performance Plus EMC Precompliance

## Goal Capsule

**Objective:** Once move 2 has delivered a digital file set that clears the
fab-ready verdict, move 3 powers the board on a bench and dynamically
validates the project's actual gates from `docs/STRATEGY.md`: every protection
gate (OCP, OVP, THM, UVL) trips at the rated threshold and within the rated
time, every performance gate that is measurable without regulatory-grade
infrastructure (EFF-01/02 efficiency vs a reference ferromagnetic pan,
PWR-01/02 power accuracy, PID-01..04 temperature control under the pan
thermal mass) is measured, and EMC precompliance
screens (conducted + radiated) catch gross CISPR Class B violations before
the certification lab. Move 3 delivers a structured **bench-evidence record**
per gate; full IEC 60335-1 compliance certification, the mechanical gates,
and formal EMC compliance measurements at an accredited lab are explicitly
deferred.

**Product authority:** Strategy-Level Move Set #3 in `docs/STRATEGY.md`,
added 2026-07-24. Move 3 is the dynamic validation arm — proof that the
hardware+lirmware actually do what `STRATEGY.md`'s gates require, given
move 2 already proved on paper they could.

**Open blockers:** Move 2 (`2026-07-24-002`) must ship the verdict layer;
move 3 consumes move 2's R7 firmware-traceability assertions as input.

---

## Problem Frame

Half of the active plan surface in this repo is firmware-adjacent: the
state-machine (`main/state_machine.c`), transition-table codegen
(`firmware/transition_table.yaml`), SIL fault-injection
(`2026-06-22-010-feat-sil-fault-injection-plan.md`), the UCC21550 latch-sensor
work (`2026-07-13-013`), P0 sensing/frontends/aux supply/grounding-isolation
fixes (`2026-07-15-003`–`2026-07-15-009`), programming-path gaps
(`2026-07-15-009`). All of it is active, all of it has reached unit-test
coverage on the host, and none of it has been connected to a "power this
board on a bench and trip each protection" exit criterion.

Meanwhile the existing `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`,
`docs/HV_SAFETY_TEST_PROCEDURE.md`, `docs/SAFETY_TEST_CHECKLIST.md`, and
`docs/SAFETY_TEST_LOG_TEMPLATE.md` define a workable test *procedure* for each
protection (current injection for OCP, Variac for OVP, blocked-fan for THM,
rail-injection for UVLO). They have never been executed because there was no
board to execute them against — and the procedure alone does not include
fault-injection tooling, performance-gate measurement, or EMC precompliance.
Move 3 closes that loop: turn the existing procedures into executed evidence
records, with test-mode firmware adding fault-injection paths that don't
require destructive external stimuli where the procedure is slow or risky.

The sequencing is the heart of the strategy: move 2's R7 traceability
assertion proves each protection has a firmware path on paper; move 3 proves
each protection's firmware path actually fires when the physical trigger
occurs. Without move 2, move 3 risks spending weeks debugging "the
protection never fired" only to discover the firmware never had the path
in the first place. Without move 3, move 2's static assertions are an
unverified paper trail.

---

## Requirements

### Phase 3a — protection trips (unlocks cert-lab track)

- **R1.** Move 3 dynamically validates every protection gate in `STRATEGY.md`
  by tripping it on a bench rig: OCP-01 (45–55A, <1µs), OCP-02 (55–65A,
  <5µs), OVP-01 (DC bus 390–410V), THM-01 (heatsink NTC 85°C shutdown),
  THM-02 (coil NTC 120°C shutdown), UVL-01 (gate-drive UVLO <12.0V), UVL-02
  (logic UVLO <2.9V). Each protection gate's bench-evidence record must
  contain BOTH an injection-confirmed-path entry AND a live-stimulus-
  confirmed-trip entry before the gate may report PASS — see R12. Trace:
  `@req(this-plan, R1)`.

### Phase 3b — performance measurement

- **R2.** Move 3 dynamically measures every **performance gate that is
  measurable without regulatory-grade lab infrastructure**: EFF-01/02
  (efficiency at 1000W & 1800W), PWR-01/02 (power accuracy), PID-01..04
  (temperature accuracy, stability, overshoot, settling under the PID
  control loop). **EFF-01/02 are measured against a reference ferromagnetic
  pan** per the pan spec in `FUNCTIONAL_TEST_CRITERIA`, NOT a dummy
  inductive load — induction cookers couple into ferromagnetic cookware via
  an eddy-current resonant tank, and a dummy-resistor/dummy-inductor load
  is not field-representative (a board that hits 92% on a dummy may hit
  ~78% on a real pan as the resonant tank detunes). PID-01..04 use the
  same reference pan+thermal-mass setup. A dummy load is permitted only
  for protection-trip validation and PID control-loop validation, not
  for EFF-01/02 certification. If no reference ferromagnetic pan is
  available at ce-plan time, EFF-01/02 are declared `UNMEASURED` on the
  bench and deferred to the cert lab (move 4), NOT PASSed against a
  non-field-representative load. The bench rig is sized for this
  measurement, not just for protection trips. Trace: `@req(this-plan, R2)`.
### Phase 3c — EMC precompliance

- **R3.** Move 3 performs **EMC precompliance screening** for CISPR 14-1
  Class B (EMC-01/02/03): conducted-emission screening via a LISN on the
  AC input, radiated-emission screening via near-field H/E probes around the
  board and the cooktop coil. Precompliance is not formal compliance — its
  purpose is to catch gross violations early enough that silicon-trace
  fixes are still on the table, not to claim CISPR Class B cert.
  Trace: `@req(this-plan, R3)`.
- **R4.** Move 3 explicitly **does not own**:
  (a) full IEC 60335-1 compliance certification — that is an accredited
  lab activity downstream (owned by move 4);
  (b) MCH-01/02/03 mechanical gates (button force, knob torque, glass load)
  — owned by move 4 (Fabrication + Mechanical + Cert-Lab Handoff Track
  per `STRATEGY.md`);
  (c) formal CISPR Class B compliance measurements at an accredited lab —
  move 3 does precompliance only;
  (d) fabrication, procurement, supply-chain sourcing — owned by move 4;
  move 3 consumes a built board, it doesn't build one.
  Trace: `@req(this-plan, R4)`.

### Phase internal ordering — 3a before 3b/3c

3a (protection-trip validation only) ships first; **R12's unlock
(checkpoint) fires here**, opening the cert-lab track per move 4. 3b
(performance) and 3c (EMC precompliance) are sequenced after the unlock
and can run in parallel with early cert-lab engagement. The boundary
(phase 1 of the brainstorm) is unchanged — all three are still move 3
scope. The internal phase boundary prevents the safety evidence and the
lab-track unlock from being delayed by the performance/EMC scope.

### Test-mode firmware with fault-injection hooks

- **R5.** Move 3 engineers a **test-mode firmware build** as a
  compile-time-flagged variant of the production firmware that **never
  ships**, exposing controlled fault-injection paths:
  - adjustable OCP threshold + force-OCP-trigger-via-UART,
  - fake-NTC / temperature-sensor injection to trip THM-01/02 without
    heating the coil,
  - force-UVLO-signal firmware-side injection,
  - OV-trigger via adjustable bus-voltage reporting.
  The test mode reuses the production state machine — it adds hooks to
  inject trigger conditions, it does not fork the protection logic.
  **Reconciliation against prior `2026-06-22-010-feat-sil-fault-injection-plan.md`
  is required before engineering the test-mode build**: if that prior
  plan already delivers hooks R5/R6 require, R5/R6 consume it as a
  dependency (like move 1 consumes the forced-segment fail-closed
  dependency), not re-engineer; if it does not, the delta is scoped
  explicitly. Trace: `@req(this-plan, R5)`.
- **R5a. (timing-path hook constraint — required)** Injection hooks for
  timing-critical protections (OCP-01 <1µs, OCP-02 <5µs) must be
  architecturally **off the trip hot path**: hooks write to a register or
  memory the comparator or ISR reads, not to a function call or branch in
  the trip service routine. A test-build's measured OCP trip time is a
  lower bound on production's trip time only if the hooks are provably off
  the measuring hot path. The bench-evidence record for OCP-01/02 must
  state which build the timing was measured on; the <1µs/<5µs numbers
  that anchor R1's PASS are measured on a **production build with external
  current injection** (the live-stimulus variant per R6), NOT on a
  test-mode build's UART-injected path. The test-build measurement
  supports the firmware-path-fires claim, not the timing claim. Trace:
  `@req(this-plan, R5a)`.
- **R6.** Fault-injection hooks cover the cases the existing
  `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` flags as slow or destructive:
  thermal-rise-protected-against by NTC injection; UVLO-without-pulling-the-rail
  via firmware-side signal injection; OCP-without-frying-the-IGBT via current
  injection into the CT burden. The existing procedures' "live" variants
  (Variac overload, blocked-fan thermal rise, pan-without-liquid) are
  **required PASS evidence per gate per R12 — not optional scout
  evidence**; they are sequenced after injection confirms the path fires
  but a gate may not report PASS on injection-only evidence. Trace:
  `@req(this-plan, R6)`.
- **R7.** The test-mode firmware build is **gated against ever becoming a
  release artifact via a defense-in-depth stack**, not a single CI rule.
  For a mains-connected (120–240V AC / 340V DC / ~1.8kW) consumer device
  in which `STRATEGY.md`'s invariant is "software cannot override hardware
  protection," the test-mode build's fault-injection paths are by design a
  software override of every hardware-latched protection (OCP/OVP/THM/
  UVL). A single CI rule prevents it shipping; defense-in-depth requires:
  (a) hooks are compiled under `#ifdef CONFIG_TEMPER_TEST_MODE` only and
  the hook code is absent from the binary entirely when the flag is unset
  (not a runtime flag);
  (b) `firmware/sdkconfig.defaults` does not define `CONFIG_TEMPER_TEST_MODE`;
  (c) a build-time CMakeLists assertion fails the production target if
  `CONFIG_TEMPER_TEST_MODE` is defined;
  (d) a post-build symbol scan (`nm` / `idf.py size` or a custom
  equivalent) verifies no test-mode symbols are present in the production
  `.elf` and is a hard CI gate;
  (e) the CI check runs on the built artifact, not on the source flag, so
  direct git-push or a config drift cannot bypass it.
  Production binaries never contain the fault-injection hooks. Trace:
  `@req(this-plan, R7)`.

### Bench-evidence record — deliverable, not format

- **R8.** The artifact move 3 delivers is a **structured bench-evidence
  record per gate** — measured values, instrumented scope-capture / spectrum
  / efficiency-data file paths, and pass/fail against `STRATEGY.md`
  threshold for each gate ID. The record IS the deliverable; its schema
  (YAML / JSON / extension of the existing `SAFETY_TEST_LOG_TEMPLATE.md` / a
  new per-gate evidence file format) is deferred to ce-plan according to
  the user-chosen decision. The brainstorm fixes the deliverable as
  "structured evidence per gate, citable per STRATEGY.md gate ID", not the
  format. **Non-deferrable integrity properties (required regardless of
  schema)**: each capture file path must be accompanied by (i) a content
  hash (sha256) of the capture recorded at capture time, (ii) the
  instrument model + serial number + calibration-due date, (iii) the rig
  configuration (Variac setting, load/pan type and thermal mass, probe
  type and position) sufficient for a third party to reproduce the
  measurement, and (iv) a capture timestamp. The record itself is
  append-only or git-committed at capture time so post-hoc edits are
  visible. A gate's PASS is only as credible as its evidence chain;
  deferring integrity properties with the schema would defer the safety
  claim's foundation. Trace: `@req(this-plan, R8)`.
- **R9.** Together with move 2's static per-gate verdict, move 3's
  bench-evidence record forms the **IEC 60335-1 submission evidence trail**
  the certification lab consumes later — static coverage (move 2's gate
  verdict + firmware-traceability assertion) plus dynamic coverage (move 3's
  bench-evidence record). Move 3's record must therefore be **citable per
  STRATEGY.md gate ID** so the cert lab can cross-reference static and
  dynamic coverage per gate. Trace: `@req(this-plan, R9)`.
- **R10.** Existing infrastructure — `docs/SAFETY_TEST_LOG_TEMPLATE.md`,
  `docs/SAFETY_TEST_CHECKLIST.md`, `docs/SAFETY_TEST_PROCEDURE.md`,
  `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`, `docs/HV_SAFETY_TEST_PROCEDURE.md`,
  `docs/FUNCTIONAL_TEST_CRITERIA.md`, `docs/FUNCTIONAL_TEST_PROCEDURE.md` — is
  the **procedure authority**, consumed as input. Move 3 does not re-author
  the procedures; it executes them and records evidence against them.
  Trace: `@req(this-plan, R10)`.

### Sequencing and dependencies

- **R11.** Move 3 begins after move 2 ships. Move 3 consumes move 2's R7
  firmware-state-machine traceability assertion as **input** — every
  protection-trigger transition R7 proves on paper is the transition move 3
  exercises dynamically. Move 3 never re-derives firmware-path existence
  from scratch; if move 3's bench trip fires no firmware transition, that
  gap is reported as "R7 assertion contradicted by bench evidence,"
  not debugged by re-walking the firmware. Trace: `@req(this-plan, R11)`.
- **R12.** Move 3 (specifically phase 3a) is the gateway to the deferred
  tracks: once the protection-gate bench-evidence records show PASS for
  every protection gate, the project unlocks move 4 (Fabrication +
  Mechanical + Cert-Lab Handoff Track) — formal IEC 60335-1, formal CISPR
  Class B measurements, MCH-01/02/03 mechanical-gate validation, all as
  separately-scoped work owned by move 4. Move 3 does not own move 4; it
  owns the gate that unlocks it. **A protection gate may report PASS only
  when its bench-evidence record contains BOTH an injection-confirmed-path
  entry AND a live-stimulus-confirmed-trip entry (per R6); injection-only
  PASS reports `INJECTION-PASS, LIVE-PENDING` and does NOT unlock R12.**
  Live-stimulus per gate:
  - OCP-01/02: real overcurrent via Variac+load at the rated primary/secondary
    current;
  - THM-01: blocked-fan thermal rise to 85 °C;
  - THM-02: hot-pan / coil-driven thermal rise to 120 °C;
  - UVL-01/02: rail pull-down to the rated UVLO voltage (gate-drive 12 V
    side; logic 2.9 V side);
  - OVP-01: Variac-driven bus rise to 400 V.
  "Slow" or "destructive" live tests may be deferred per-test, but a
  deferred live test blocks that gate's PASS and therefore blocks R12 —
  they are not optional scout evidence; they are PASS evidence. Trace:
  `@req(this-plan, R12)`.

---

## Acceptance Examples

- **AE1 — Covers R1, R5, R5a, R6, R7.** Given the test-mode firmware is
  flashed to a bench-mounted temper board, when an engineer sends the
  force-OCP UART command with the threshold set to 50A primary, the OCP
  fault latch engages and gate-driver DIS goes HIGH — proof the firmware
  path fires via injection. The OCP-01 <1µs trip-time PASS evidence is
  recorded against a **production build with external current injection**
  (R5a's live-stimulus variant), not on the test-mode build's UART-injected
  path (hooks are off the trip hot path per R5a). The bench-evidence
  record cites OCP-01 with both entries: injection-confirmed-path + the
  production-build live-overcurrent <1µs scope capture. The test-mode
  build's defense-in-depth stack per R7 prevents a production binary
  from carrying the hooks at all four layers (compile-time #ifdef,
  sdkconfig.defaults, build-time CMake assertion, post-build symbol scan).
- **AE2 — Covers R2.** Given the bench rig with a reference ferromagnetic
  pan per `FUNCTIONAL_TEST_CRITERIA`, when the board runs at 1800W input,
  the bench-evidence record cites EFF-02 with measured input power, measured
  output power at the pan, the computed efficiency, and PASS/FAIL against
  >92% threshold. PID-01..04 are measured against the same pan+thermal-mass
  setup with the production PID control loop engaged.
- **AE3 — Covers R3.** Given the LISN is connected on the AC input and the
  near-field probes are placed near the cooktop coil, when the board runs
  at full power, the bench-evidence record cites EMC-01/02/03 with the
  conducted-emission and radiated-emission spectrum-plot file paths and a
  precompliance PASS/MARGINAL/FAIL annotation against the CISPR Class B
  limits — flagged as precompliance, not formal compliance.
- **AE4 — Covers R8, R9, R11.** Given move 2's verdict exists and R7
  asserted that THM-01 has a transition-table `OVERTEMP_HEATSINK → FAULT` with
  the appropriate `@req` tag, move 3's bench trip injects the NTC-fake value
  to force the OVERTEMP_HEATSINK condition, the firmware path fires
  (matching R7's asserted path, not re-derived from scratch), the
  bench-evidence record cites THM-01 with the trip confirmation and
  per-gate ID cross-reference to R7's static assertion. Together the two
  records form the per-gate IEC submission trail.
- **AE5 — Covers R4.** Move 3's outputs explicitly do not cover MCH-01/02/03
  (no bench-evidence record exists for button force / knob torque / glass
  load), do not claim IEC 60335-1 compliance, and do not claim CISPR Class B
  formal compliance — only precompliance screening.
- **AE6 — Covers R12.** Given all protection-gate bench-evidence records
  show PASS, the certification lab track is unlocked as a separately-scoped
  track — move 3 does not begin certification work; it ends with the
  evidence record whose PASS status unlocks the certification track.

---

## Success Criteria

- Every protection gate in `STRATEGY.md` (OCP-01/02, OVP-01, THM-01/02,
  UVL-01/02) has a bench-evidence record with a measured trip confirmation
  against its rated threshold and time.
- Every performance gate measurable on a bench rig without regulatory-
  grade infrastructure (EFF-01/02, PWR-01/02, PID-01..04) has a bench-
  evidence record with measured values vs `STRATEGY.md` thresholds.
- EMC precompliance records exist for EMC-01/02/03 with spectrum-plot
  file paths, flagged as precompliance, with the bench evidence available
  to a future certification lab.
- A test-mode firmware build with fault-injection hooks exists and is
  provably excluded from production builds via a CI/build-system gate.
- Bench-evidence records are citable per STRATEGY.md gate ID, cross-
  referencing move 2's R7 firmware-traceability assertion per gate.
- Every protection bench-evidence record contains BOTH an
  injection-confirmed-path entry AND a live-stimulus-confirmed-trip
  entry (R12), with capture files hash-pinned, instrument-identified,
  rig-config-bound, and timestamped per R8's integrity properties.
- Mechanical gates, full IEC 60335-1 cert, formal CISPR Class B, and
  fabrication are explicitly out of scope and not part of move 3's
  bench-evidence output.

---

## Key Decisions

- **Outer boundary: protection + performance + EMC precompliance, with
  internal phase ordering (3a → 3b/3c).** Move 3 owns every dynamic gate
  `STRATEGY.md` lists that is measurable without regulatory-grade
  infrastructure; phase 3a (protection) ships first and unlocks the
  cert-lab track per R12; phase 3b (performance) and 3c (EMC
  precompliance) follow and can run in parallel with early cert-lab
  engagement. Move 4 owns fabrication + mechanical + the cert-lab handoff
  that 3a's unlock opens.
- **Test-mode firmware with fault-injection hooks; never ships via
  defense-in-depth.** Production-firmware-only with external stimuli
  (Variac, blocked fan, hot pan) is slow and some methods are destructive;
  a compile-time-flagged test build that reuses the production state
  machine and adds injection paths decelerates thermal tests and avoids
  hardware destruction. The "never ships" constraint is a five-layer
  defense-in-depth stack (R7), not a single CI rule — for a mains-
  connected consumer device whose `STRATEGY.md` invariant is "software
  cannot override hardware protection," shipping the test-mode build with
  its fault-injection hooks compiled in is a fire/electrocution risk.
  Single-layer enforcement is insufficient.
- **Live external-stimulus tests are PASS evidence, not scout evidence.**
  Each protection gate's bench-evidence record contains BOTH an injection
  -confirmed-path entry AND a live-stimulus-confirmed-trip entry before
  it can report PASS (R12). Injection covers slow/destructive cases
  faster and safer; the live tests prove the protection actually trips
  in real-world physics. A deferred live test blocks the gate's PASS and
  therefore blocks R12's cert-lab unlock — they are not optional. The
  OCP-01/02 timing PASS further requires measurement on a production
  build with external current injection (R5a), since test-build hooks
  on the trip hot path would alter the <1µs/<5µs timing.
- **EFF-01/02 measured against a reference ferromagnetic pan, not a
  dummy inductive load.** A dummy-resistor/dummy-inductor load is not
  field-representative for an induction cooker; a board that clears
  EFF-02 on a dummy may miss it on a real pan. If no reference pan is
  available, EFF-01/02 are declared UNMEASURED on the bench and deferred
  to the cert lab (move 4), not falsely PASSed against a non-
  field-representative load.
- **Bench-evidence record — what's delivered, format deferred; integrity
  properties non-deferrable.** Move 3 asserts the deliverable is a
  structured per-gate record with measured values + instrumented file-
  paths + threshold comparison, cross-referenced to move 2's static per-
  gate assertion; the schema is deferred to ce-plan. The integrity
  properties (content hash, instrument model+serial+cal-due, rig-config-
  bound, timestamp, append-only) are non-deferrable — R9 already commits
  the record to be IEC submission evidence and a YAML-of-file-paths is
  not tamper-evident enough to anchor a safety claim.
- **Move 3 consumes move 2's R7 traceability, never re-derives it.** The
  sequencing doubles defense: static proof the firmware path exists on
  paper (move 2 R7), dynamic proof the firmware path fires on the bench
  (move 3). A bench-trip contradiction is reported against R7's assertion,
  not debugged by re-walking the firmware — that's the discipline that
  keeps the two tracks sequenced, not parallel.
- **Move 3 unlocks move 4; it doesn't execute it.** When every protection
  bench record is PASS for 3a, move 4 (Fabrication + Mechanical + Cert-
  Lab Handoff Track) is separately scoped work — it owns fabrication,
  mechanical-gate validation, and the accredited-lab handoff; move 3 does
  not begin that work internally.

---

## Scope Boundaries

**In scope:**
- Dynamic protection-trip validation on a bench rig (R1, R5, R5a, R6).
- Dynamic measurement of bench-measurable performance gates (R2).
- EMC precompliance screening (R3).
- Test-mode firmware build with fault-injection hooks + defense-in-depth
  never-ships stack (R5, R7, R5a).
- Bench-evidence record per gate with non-deferrable integrity properties
  (R8, R9).
- Consuming existing test procedures as authoritative inputs (R10).
- Live-stimulus PASS evidence per protection gate (R12 — required, not
  scout).
- The unlock of move 4 at phase 3a PASS (R12).

**Out of scope:**
- Full IEC 60335-1 compliance certification — accredited lab, downstream.
- Formal CISPR 14-1 Class B compliance measurements at an accredited lab
  — move 3 does precompliance only.
- Mechanical gate validation (MCH-01/02/03) — physical/lab track.
- Board fabrication, procurement, supply-chain sourcing — move 3 consumes
  a built board.
- Re-forking the production state machine — test-mode firmware reuses it.
- Re-authoring the test procedures — existing procedure docs authoritative.

**Deferred (not owned):**
- Accredited-lab certification, formal EMC compliance, mechanical, full
  compliance certification — Lab track, unlocked by R12 after move 3 PASS.

---

## Dependencies / Assumptions

- Depends on move 2 (`2026-07-24-002`) shipping: the digital file set and
  the R7 firmware-traceability assertion are inputs.
- Depends on a built and powered-up temper board existing — fabrication
  is assumed as a precondition (and may itself require its own
  prior-track planning; if it doesn't, move 3's first blocker is "no board
  exists" and that surfaces immediately, not late).
- Assumes the existing firmware state-machine covers the protection-trigger
  transitions move 3 exercises (R7 of move 2 asserts this on paper; move 3
  proves it on the bench).
- Assumes the existing
  `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` / `HV_SAFETY_TEST_PROCEDURE.md`
  / `FUNCTIONAL_TEST_CRITERIA.md` / `FUNCTIONAL_TEST_PROCEDURE.md` are
  current enough to execute against; if any procedure drifts from the
  shipped file set, a procedure-update is in-scope for move 3 as a small
  in-flight fix.
- Assumes the test-mode firmware can be built without forking the
  production state machine — the compile-time flag adds hooks, it doesn't
  branch the protection logic.
- Assumes a basic bench rig (Variac, current source, NTC thermistor
  conditioning, oscilloscope, LISN, near-field probes, **reference
  ferromagnetic pan** per `FUNCTIONAL_TEST_CRITERIA`) is available to the
  project — the rig itself is a project artifact but not a build-from-
  scratch deliverable; ce-plan should decide whether "rig + setup
  procurement + reference pan sourcing" is part of move 3 or a separate
  precondition.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R5][Needs research] The exact set of fault-injection hooks
  needed: a fixed list of hooks must be enumerated before the test-mode
  firmware can be built. The hook list per protection is likely derivable
  from the existing FUNCTIONAL_SAFETY_TEST_PROCEDURE. **Also:**
  reconciliation against `2026-06-22-010-feat-sil-fault-injection-plan.md`
  (active SIL fault-injection plan) — does it deliver the hooks R5/R6
  require, or is the delta separately scoped?
- [Affects R8][Format-deferred] The schema of the bench-evidence record —
  YAML/JSON structure, extension of SAFETY_TEST_LOG_TEMPLATE, or a new
  per-gate evidence file format. User-deferred; ce-plan decides based on
  what an IEC cert lab will consume (may require short external research).
  **Note:** integrity properties (R8 sub-requirement) are non-deferrable;
  only the schema's structural shape is deferred.
- [Affects R2][Technical] Whether the bench rig can drive a real
  ferromagnetic pan (the field-representative load) at 1.8kW and stay
  within reasonable Variac/source limits; rig sizing is a planning
  decision. If a reference pan is not available, EFF-01/02 defer to the
  cert lab per R2.
- [Affects R12][Needs research] Whether the unlock to move 4
  (Fabrication + Mechanical + Cert-Lab Handoff) is gated only on
  protection-PASS or also on EMC precompliance MARGINAL — i.e. does a
  precompliance FAIL block the lab handoff or feed it as a known issue.
- [Affects R11][Technical] What happens when a bench trip contradicts
  move 2's R7 assertion — the discipline (report against the assertion,
  not debug from scratch) is stated; the precise escalation path back to
  move 2 (does move 2 reopen? does a fix-live-traceability plan start?)
  is a planning decision.

---

## Sources & References

- Strategy entry point: `docs/STRATEGY.md` Current Board Closure State +
  Strategy-Level Move Set (added 2026-07-24).
- Move 2 dependency: `docs/plans/2026-07-24-002-feat-pivot-to-fab-ready-board-verdict-plan.md`
  (R7 firmware-traceability assertion is move 3's input).
- Existing test procedures (authoritative inputs): `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`,
  `docs/HV_SAFETY_TEST_PROCEDURE.md`, `docs/FUNCTIONAL_TEST_PROCEDURE.md`,
  `docs/FUNCTIONAL_TEST_CRITERIA.md`, `docs/SAFETY_TEST_CHECKLIST.md`,
  `docs/SAFETY_TEST_LOG_TEMPLATE.md`.
- Firmware surface: `firmware/main/state_machine.c`,
  `firmware/transition_table.yaml` → `firmware/main/transition_table.h`,
  `firmware/test/` (existing transition-table tests),
  `firmware/tools/gen_transition_table.py`.
- Related active firmware plans: `2026-06-22-010-feat-sil-fault-injection-plan.md`,
  `2026-06-22-010-feat-transition-table-firmware-plan.md`,
  `2026-06-22-010-feat-runaway-boundary-interlock-plan.md`,
  `2026-07-13-013-feat-ucc21550-latch-sensors-supply-plan.md`,
  `2026-07-15-003`–`2026-07-15-009` (P0 fixes),
  `2026-07-15-009-fix-programming-path-gaps.md`.
- Fail-closed / two-tier-gate institutional discipline:
  `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`.
- AGENTS.md R22 bug-triage rule (still operative; bench-trip-surfacable
  bugs follow it).