---
title: "temper-drc Python→Rust migration — shim-then-delete, and the shared resolve_safety_category's new home"
date: "2026-08-03"
category: docs/solutions/architecture-patterns/
module: temper-drc-rs, temper_placer, CI
problem_type: architecture_pattern
component: safety_checks
severity: medium
symptoms:
  - "Packages referencing the old Python `temper-drc` package paths (e.g. `packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py`, `hv_lv_separation.py`, `creepage.py`) no longer resolve — the package was deleted from main"
  - "The shared `resolve_safety_category()` helper now lives in Rust and takes a different signature — `(comp: &Component, board: &BoardState) -> Option<&'static str>` instead of a bare net-class string"
  - "Old docs citing the Python paths drift (this repo's docs/solutions library had 2 such docs corrected in the 2026-08-03 refresh; AGENTS.md still cites the deleted path)"
---

# Problem

The DRC engine migrated to Rust, but doc and consumer anchors to the old
Python package paths survived the deletion and silently broke.

## Root cause

A two-phase migration left no single point where the old package's path
ceased to exist:

1. **Shim phase** — `3d9322b5d` (2026-06-30, "migrate temper-drc to
   Rust-backed shim"): `CheckRunner.run()` delegated to
   `temper_drc_rs.run_drc()`; the 15 check implementations became
   import-compatible stubs; CI switched to the Rust backend and DRC ceilings
   were re-calibrated in the same change.
2. **Delete phase** — the Python package's outright removal
   (`2122544d7`/`f438ca0e4`).

The port origin is U4 of
`docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md`. Consumers and
docs that kept referencing the Python paths lost their anchors — the deletion
commit itself did not sweep the repo for stale citations.

## Solution

### The current shape (verified 2026-08-03)

- Engine: `packages/temper-drc-rs` (Rust crate, pyo3 boundary
  `temper_drc_rs.run_drc()`).
- Safety checks: `packages/temper-drc-rs/src/rules/safety/` —
  `hv_lv_separation.rs` (ported from the Python `hv_lv_separation.py`, per its
  module docstring) and the creepage check.
- The shared category resolver lives at
  `packages/temper-drc-rs/src/rules/safety/hv_lv_separation.rs:25`:

  ```
  fn resolve_safety_category(comp: &Component, board: &BoardState) -> Option<&'static str>
  ```

  Resolution order (the contract every safety check relies on):

  1. **Declared first**: if
     `board.net_class_rules[comp.net_class].safety_category` is set (a field
     of the codegen SSOT model — see
     `netclass-rules-codegen-ssot-2026-08-03.md`), it wins.
  2. **Keyword fallback** for undeclared classes: HV_KEYWORDS =
     [hv, line, ac, neutral, mains]; LV_KEYWORDS = [lv, signal, 3v3, 5v, gnd,
     analog] (substring match on the lowercased net class).
  3. **AC is HV-side**: a declared `"AC"` safety_category maps to `"HV"` for
     separation purposes.

### The migration pattern: shim-then-delete

The two-phase move is the reusable lesson:

1. **Shim phase** — keep the Python API surface, delegate the engine to Rust.
   Every check implementation becomes an import-compatible stub; callers keep
   working; CI switches to the Rust backend and the DRC ceilings are
   re-calibrated in the same change.
2. **Delete phase** — once no live caller imports the Python package, remove
   it outright (git history preserves it). No `_archived/`, no compat shim
   left behind.

The hazard the pattern exists to prevent: doc/consumer anchors to the old
Python paths surviving the deletion. The 2026-08-03 refresh found and
corrected two such docs (`pydantic-dataclass-migration.md`,
`splr-to-rustsat-cadical-solver-migration-2026-06-29.md`); `AGENTS.md`'s
NetClassRules section still cites the deleted Python path and should be
repointed to the Rust module.

## Prevention

- When migrating a Python package to Rust in this repo, do shim-then-delete
  in two commits, and in the DELETE commit grep the whole repo (docs,
  AGENTS.md, solutions, plans) for the old package path — the refresh sweep
  found stale citations two months after the deletion.
- New safety checks read `resolve_safety_category` from the Rust module;
  never reintroduce a Python duplicate of the keyword tables.
- The keyword fallback is a drift risk: declared `safety_category` values
  (SSOT manifest) are authoritative — keyword classification is only for
  undeclared classes. Adding a net class to TEMPER_NET_ASSIGNMENTS /
  TEMPER_NET_CLASSES with a declared category removes it from the fallback
  surface.

## Evidence

- `3d9322b5d` (2026-06-30): "refactor(drc): migrate temper-drc to
  Rust-backed shim — Rewrite CheckRunner.run() to delegate to
  temper_drc_rs.run_drc(); Replace all 15 check implementations with
  import-compatible stubs"
- `hv_lv_separation.rs` module docstring: "Ported from:
  packages/temper-drc/src/temper_drc/checks/safety/hv_lv_separation.py …
  Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md"
- `hv_lv_separation.rs:25`: "fn resolve_safety_category(comp: &Component,
  board: &BoardState) -> Option<&'static str>" with "Prefer declared
  safety_category from the model" falling back to keyword matching
