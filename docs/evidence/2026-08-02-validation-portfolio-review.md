# Validation Portfolio Review — 2026-08-02

Consolidated outcome of ce-doc-review runs (5 personas per document, non-interactive, executed in six parallel batches) over the 35 implementation-ready plans derived from `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md`.

## Verdict tally

23 KEEP · 5 TRIM · 7 MERGE · 0 DROP. Zero safe_auto fixes applied across the 35 docs (one factual correction landed in 029: `I-FAULT-EXITS` reworded to match the manifest's `EVENT_FAULT_RESET_PERSISTS` self-loop). All persona passes ran inline in one context per batch (nested dispatch depth-limited), so cross-persona agreement carries no independent-corroboration credit; cross-model peer passes were skipped (runner machinery unavailable to workers).

## Per-plan verdicts

| Plan | R-ID | Pri | Verdict | Core reason |
|---|---|---|---|---|
| 002 thermal oracle | R9 | P2 | KEEP | Measured bound on an existing fail-closed gate; sequence per-solve cadence behind cost characterization |
| 003 spice oracle | R10 | P2 | TRIM | Reference method undefined (circularity risk); measurement-first, defer corpus/register/gate |
| 004 proof register | R20 | P1 | KEEP | P1 anchor; specify the physics-gated detection rule (AST scan can't infer physics-dependency) |
| 005 BMC all encodings | R21 | P2 | TRIM | PCL half real; router-V6 restoration conditioned on undecided family survival; BMC object-under-test tautological |
| 006 mutation suite | R32 | P1 | KEEP | Systematizes R4; specify CI cost model, source-level mutation mechanism, 005 sequencing |
| 007 parameter injection | R33 | P2 | MERGE → 019 | Physics-scoped subset of the dead-parameter sweep; same perturb-and-observe harness |
| 008 full-board DRC oracle | R11 | P1 | KEEP | Flagship; bands must come from measured delta distribution, not kicad-only ceiling data |
| 009 round-trip oracle | R12 | P1 | KEEP | DoD contradicts deferred scope (center-offset divergence is current status quo); scope the PASS claim |
| 010 induction coverage | R22 | P2 | KEEP | Name the hosting workflow; gate must reject pending proofs; initial gap is 11 crates, not 4 |
| 011 transform algebra | R23 | P1 | KEEP | Cheapest cost/rigor; falsifier must anchor on asymmetric offsets (masking pairs can't discriminate) |
| 012 kernel mutation | R34 | P2 | KEEP | Add venv `.so` restore step (shared-mutable-state hazard); declare 011 dependency |
| 013 writer injection | R35 | P2 | MERGE → 012 | 4 of 5 mutants duplicate 009's static falsifiers; writer becomes a catalog inside the kernel harness |
| 014 human oracle | R13 | P2 | KEEP | Band population must be defined (extraction is deterministic; band ~0 makes gate vacuous-by-construction) |
| 015 lower-bound oracle | R14 | P3 | MERGE ↔ 017 | Identical dataclass change and same `solver_gap_bounds.json` collide |
| 016 post-solve audit | R24 | P1 | KEEP | Flagship; closes silent-constraint-drop seam; all claims verified against `audit.py` |
| 017 gap certificate | R25 | P3 | MERGE ↔ 015 | Certificate/_march/CI-gate layer is the distinct contribution; capture units duplicate 015 |
| 018 solution canaries | R36 | P2 | KEEP | Declare 014 dependency for symmetry metric; strict-inequality can fail on symmetric baselines |
| 019 dead-parameter | R37 | P1 | TRIM | Targets deprecated callerless `RunMetrics` surface with 4 phantom declared metrics; retarget to live surface |
| 020 fab-rule oracle | R15 | P2 | KEEP | Real but lowest value-density (thresholds over already-measured DRC classes); mask-opening parser gap |
| 021 netlist reconciliation | R16 | P1 | KEEP | Tank-cap claim false: C27 is placed (off-outline), so "missing" is unsatisfiable today; key by sheetpath |
| 022 formal board props | R26 | P2 | KEEP | Clean-board invariant contradiction; connectivity ignores zone copper; red-gate wiring decision needed |
| 023 DRC-ceiling contract | R27 | P1 | KEEP | Sample count lives in prose (not mechanical); trailer grammar redundant with `_march` |
| 024 board defect corpus | R38 | P1 | KEEP | Seeds are no-ops (defects already on committed board); seed from defect-free baselines with count deltas |
| 025 netlist mutation | R39 | P2 | MERGE → 021 | Renumber/reuse classes are 021's own U4 tests; dropped-net class needs an owner |
| 026 HIL oracle | R17 | P2 | TRIM | Corpus schema can't express ~14/23 events; QEMU weakest at its motivating bug class; spike-gate bring-up |
| 027 FW assumption contract | R18 | P1 | KEEP | Flagship; extractor would PASS on the off-board defect (no outline membership); key by sheetpath |
| 028 model check | R28 | P2 | KEEP | Exhaustive reachability over the manifest; name wildcard state set; derive sensor-fault events |
| 029 invariant proofs | R29 | P2 | MERGE → 028 | Parallel engine over the same manifest; I-NO-REENTRY needs 028's reachability computation |
| 030 transition mutation | R40 | P1 | KEEP | Codegen makes mutation cheap; scheduled-sweep fallback leaves CI on stale data — fix |
| 031 fault injection | R41 | P2 | KEEP | Cheap high-value; fault classes without manifest rows need a named expected-state source |
| 032 incident corpus | R19 | P1 | KEEP | Family's load-bearing seed; add seed-materialization step; own the shared runner |
| 033 gate non-vacuity | R30 | P1 | MERGE → 032 | Same runner, dir, verdict classes, sequential dependency — one mechanism at two granularities |
| 034 trigger closed-form | R31 | P2 | KEEP | 41 paths missing from manifest — ships red without population step; add workflows-dir override |
| 035 gate mutation | R42 | P1 | TRIM | Heaviest item on two P1 prerequisites; shrink to gates with fixtures (~24/51), drop to P2 |
| 036 trigger mutation | R43 | P2 | KEEP | Cheap live proof; fix cross-plan override gap with 034 |

## Merge map (35 → 29 artifacts)

| Absorbed | Surviving | Fold-in |
|---|---|---|
| 007 (R33) | 019 (R37) | Physics config fields as second declarative input surface; noise-floor discipline for threshold-less consumers |
| 013 (R35) | 012 (R34) | Writer-error catalog as a harness family; center-offset mutant excluded until the R22 fix |
| 015 (R14) | 017 (R25) | Capture unit + measured-threshold population into the certificate plan |
| 025 (R39) | 021 (R16) | Netlist-mutation corpus as the standing injection suite; net-level membership owned by 021 |
| 029 (R29) | 028 (R28) | Invariants module + proof record + power-active audit on 028's model builder |
| 033 (R30) | 032 (R19) | Per-gate canary contract as 032's coverage phase; single runner |

## Ground-truth corrections (verified against the tree)

- 024: defect seeds are no-ops — the tank cap is already off-board (`C27` at `(at 20.0 272.75)`), the C1 pad2↔R7 pad2 short is already present 120/120 (`shorting_items: 118`), creepage already at 75 violations. Seed from defect-free baselines and assert count deltas.
- 021/027: the tank cap IS in `pcb/temper.kicad_pcb` (line 1307, `(property "Sheetpath" "tank.c_tank3")`). The defect is placement off-outline, not file absence — refdes/value-lookup extractors pass it; outline membership is the missing mechanism.
- 009/013: the adapter writer's center-offset divergence (`_apply_placements_to_pcb` writes raw box-center) is current status quo, not a mutation — the round-trip oracle cannot pass on that path until the deferred R22 fix.
- 019: `RunMetrics` is a deprecated 8-field stub; `PlacementCompleteGate.required_metrics` declares 4 metrics that are not `RunMetrics` fields; `check_gate`/`check_all_gates` have no callers outside `validation_gates.py`.
- 005: `scripts/bmc_adoption_gate.py` exits 3 today (evaluators deleted in `772776115`); router-V6 family survival undecided; the atmostk induction lives in a solutions doc, not an encoder.
- 003: no field solver exists in-repo; the reference extraction must differ from the fast estimator or the differential measures noise.
- 034: 122 paths in path-filtered workflow lists vs 81 in `required-checks.json` (41 missing, incl. `firmware/**`, `.github/workflows/**`, `dashboard/**`, `benchmarks/**`).
- 012: `maturin develop --release` installs the mutated kernel into the shared venv — a restore step is required; "working tree clean" does not cover the venv.
- 011: R(−θ1)·R(−θ2) ≡ R(+θ1)·R(+θ2) whenever θ1+θ2 ∈ {0,180} mod 360 — 8 of 16 pairs including (90, 270) don't discriminate a sign flip.
- 023: sample count is embedded in `measured_via` prose; the provenance schema has no structured sample-count field.
- 026: the 7-column CSV cannot express ~14 of 23 events (buttons, timers, pan-status, self-test); the host probes live in `state_machine_stubs.c` and don't exist in the real ESP-IDF binary.
- 028/029: the test generator's `"*"` wildcards exclude INIT/IDLE (line 141) — "from every state" over-approximates unless deliberate.
- 031: `FAULT_IGBT_SHORT`/`FAULT_ADC_STUCK`/watchdog have no manifest rows; `EVENT_TIMER_EXPIRED` targets benign `STATE_COOLDOWN`.
- 010: 15 `Cargo.toml` under `packages/`, only 4 have `VERIFICATION.md` — 11 crates need classification.

## Fix-before-execution list (all KEEP/TRIM plans)

1. 008: derive tolerance bands from the two-engine delta distribution (U2 test 2 samples kicad-cli only).
2. 009: scope the adapter-path PASS claim to components without center offset; center-offset class asserts expected-FAIL pending the R22 fix. Same root in 012/013.
3. 014: define the band population (accepted solver placements, not the single human layout) or label bands "reviewed, not measured".
4. 019: pre-flight survey of the current gate set; retarget to live `cp_sat/gate.py` + invoked CI scripts; land behind a first-run remediation PR or warn-only initially.
5. 023: add a structured `sample_count` field to the provenance schema; make `_march` the single cause authority, drop the trailer-body grammar.
6. 024: seed each class from a defect-free starting point; scope the anti-vacuity gate set to gates green on the clean board.
7. 027: add outline-membership classification; key by sheetpath property per the cited handoff; state the landing contract (board fix same PR vs advisory).
8. 030: define the gate's behavior when the sweep is scheduled (fresh report per run, or sweep only mutated rows).
9. 031: class→expected-source mapping for fault classes without manifest rows.
10. 034: manifest population step (or scoped containment direction); `--workflows-dir` override for 036.
11. 036: coordinate the override into 034's U1.
12. 004/005/006: one shared surface inventory (004's register as single source) instead of four parallel scans; declare 005's restoration as a dependency.
13. 012: venv `.so` restore + content-hash assertion after each mutant.
14. 026: extend the corpus schema with non-sensor forcing channels; name the emulated-target injection mechanism; begin U3 with an A2 spike.
15. 010: name `python-tests.yml` as host; define gate semantics for pending proofs.
16. 022: define "clean board" (copy with the known off-board component corrected); include zone copper in connectivity; warn-gate with known-finding registry.
17. 018: declare the 014 dependency for the symmetry row; per-mutation "non-decreasing plus one strict move" instead of per-metric strictness.
18. 028: name the intended wildcard state set; derive the sensor-fault event set from the manifest.

## Portfolio-level recommendations

- **Known-finding registry / warn-gate convention** (020's KTD4 pattern, generalized): gates that legitimately fail on the unfixed board (021, 022, 024, 027) need a documented known-finding mode so they don't ship permanently red and recreate the advisory-gate culture this portfolio exists to end.
- **Sequencing spine:** 009 → 011 → 012 → 013-family for geometry; 005 restoration before 004/006; 032 before 033/035; 031 before 026 (same-file churn on `test_sil_fault_injection.c`); 021 before 025-family.
- **Advisory-gate reality:** every new CI gate remains advisory while branch protection on `main` is disabled (see `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md`); enabling protection is a prerequisite for the gates to bite.
- **Numbering collision:** a concurrent session created `docs/plans/2026-08-02-002-feat-sealed-compartment-plan.md`, colliding with 002 used by the thermal oracle plan. Both files coexist today; renumber one before committing.
- **Bloat bottom line:** no idea is DROP-level — every plan maps to a recorded incident or a real gap with live seed machinery. The portfolio's cost story improves from 35 to 29 artifacts via the merge map; the TRIM list is the remaining bloat risk if executed as written.

## Sources

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin portfolio (requirements-only).
- The 35 implementation-ready plans `docs/plans/2026-08-02-002…036-*.md`.
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` — board-defect ground truth.
- `docs/evidence/2026-07-30-placement-writer-rotation.md`, `docs/evidence/2026-07-30-drc-ceiling-remeasurement-cascade.md`, `docs/solutions/logic-errors/` — incident classes.
