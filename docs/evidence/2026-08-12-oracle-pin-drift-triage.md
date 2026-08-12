# Oracle pin drift triage: 3 drifted `_*_py_oracle.py` pins re-pinned (2026-08-12)

<!-- provenance: commit=f8e83c234664a9332ed80aa319bc464499ec7827 dirty=false -->

**Date:** 2026-08-12
**Branch:** `fix/oracle-drift-triage` (base `origin/main` @ `df0dc4d90`)
**Scope:** `scripts/oracle_hashes.json` (3 pins moved), the three drifted
oracle files (header pin-notes only where one was missing), this note.
No other files touched.

## What happened

`make regen-check` refused on the oracle-hash gate: 3 PINNED oracles had
drifted from their `scripts/oracle_hashes.json` pins. The registry records
verbatim pre-migration oracle bodies; a drift means the oracle bytes
changed without the keep-in-sync registry re-pin (the exact case the gate
exists to catch — recording it blind would launder the drift). The drift
grew 1 → 2 → 3 as concurrent sessions landed oracle-lock-step changes
without re-pinning. The cause for each was established before re-pinning,
below.

## Per-oracle triage

### 1. `packages/temper-placer/tests/core/_design_rules_py_oracle.py` — case (a), re-pinned

- **Cause commit:** `3231dc3db` "feat(drc): enforce HV↔HV functional
  creepage at the resonant-tank node (6.3mm, IEC 60335-1 Table 18)
  (#1084)", merged into `main` via `df0dc4d90` (a merge of two sibling
  lines: `4d8a5a187` had re-pinned the oracle for the #1061 netclass
  reconciliation *without* `HighVoltageTank`; the other side carried
  #1084's oracle update).
- **What changed:** the `HighVoltageTank` net class entry (923.7 V,
  6.3 mm creepage) and the `tank.c_tank1-p2` reclassification
  `HighVoltage` → `HighVoltageTank`, added to the oracle in lock-step with
  `temper_placer/core/design_rules.py`.
- **Verdict:** legitimate source change; oracle edit is **faithful** —
  the added entry is byte-identical to the live `design_rules.py` table
  (verified by diff). The #1084 PR forgot the registry re-pin.
- **Action:** added a `RE-PINNED 2026-08-12` header note naming the cause
  and commit, re-pinned the registry.
- **Pin:** `712f80397155...` → `d0f292ad4eef...`

### 2. `packages/temper-placer/tests/regression/_measure_closure_py_oracle.py` — case (a), re-pinned

- **Cause commit:** `8c43be740` "fix(gates): erc off-grid +
  drc-clearance-pct fail on absence-of-evidence (#1037)" (branch
  `fix/vacuous-safety-gates`).
- **What changed:** the oracle was updated to the POST-fix contract — a
  `result.drc_measured` truth-gate raising instead of reporting a
  fabricated 100.0 when DRC never ran, plus the zero-results truth-gate
  moved ahead of it. The oracle's own header already documents this as a
  deliberate re-pin ("RE-PINNED ... this file is re-pinned to the
  POST-fix contract so it stays the intended oracle rather than a pinned
  bug").
- **Verdict:** the author intended the re-pin and documented it in the
  oracle header but did not update `scripts/oracle_hashes.json`. The
  three-branch `compute_drc_clearance_pass_pct` formula is unchanged and
  still bit-identical to the Rust kernel
  (`packages/temper-design-bundle/src/measure_closure.rs`, verified).
- **Action:** re-pinned the registry; no oracle edit needed (header note
  already present).
- **Pin:** `938bba3770c5...` → `eb3a803df19a...`

### 3. `packages/temper-placer/tests/validation/_placement_roundtrip_py_oracle.py` — case (b), re-pinned

- **Cause commit:** `3ffa080a3` "fix(placer): stop dropping solved
  rotation-index-0 from write-back, causing pads outside board outline
  (#1074)".
- **What changed:** comment-only update to `_check_footprint`'s
  rotation-fallback comment, in lock-step with
  `placement_roundtrip.py`'s matching comment (the dense
  `to_rotations_dict` note). No semantics changed (`theta =
  rotations.get(ref, ...)` and all logic untouched — verified by diff).
- **Verdict:** faithful hand-edited comment; the pin was forgotten.
- **Action:** added a `RE-PINNED 2026-08-12` header note, re-pinned the
  registry.
- **Pin:** `893479e553ed...` → `ecaa2f1d8d09...`

## Unexplained drifts

None. All three drifts were attributable to a named commit with a
faithful, verified lock-step oracle edit.

## Verification

- `uv run --no-sync python scripts/check_oracle_hashes.py` → clean
  (0 drifted, 0 unregistered).
- `uv run python scripts/import_linter_gate.py` → passes.
- Differential suites for the re-pinned oracles: measure_closure and
  placement_roundtrip run fully green (67 passed total across all three
  files); design_rules' parity assertion passes (Rust and oracle
  bit-identical, 12 net classes incl. HighVoltageTank) with one
  pre-existing stale count literal failing — see the finding below.

## Unrelated pre-existing drifts (NOT touched, out of scope)

`make regen-check` also reported two non-oracle derived-artifact drifts on
the base commit: `gen_repo_state.py` (repo-state artifact) and
`gen_wasm_test_registry.py [temper-io-types]`
(`packages/temper-io-types/src/wasm_test_registry.rs`). These are separate
gates with separate generators, owned by other workstreams; this PR
deliberately does not touch them.

## Pre-existing differential staleness (NOT touched, out of scope)

`tests/core/test_design_rules_rust_differential.py:292`
(`test_create_temper_design_rules_identical`) asserts
`len(rust_dr.net_classes) == 11`. The live `design_rules.py` gained the
12th class (`HighVoltageTank`) in #1084, which did not touch this test
(last touched `daa3acbf1`, #587) — so this assertion fails on `main`
independently of this PR's re-pin. The differential's parity assertion
immediately above it (`_dr_fields(rust_dr) == _dr_fields(py_dr)`, which
canonicalizes `net_classes`) PASSES with 12 classes on both sides, so the
re-pinned oracle and the Rust `DesignRules` are bit-identical including
`HighVoltageTank`; only the stale count literal is wrong. Fix (for the
#1084 author or a follow-up): `== 11` → `== 12`. Left untouched per this
PR's file-ownership scope.
