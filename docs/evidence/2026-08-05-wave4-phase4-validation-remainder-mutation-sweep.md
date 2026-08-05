# Wave 4 Phase 4 — validation remainder slice: anti-vacuity mutation sweep — 2026-08-05

<!-- provenance: base=e783f1d6f (TDD-RED commit), worktree rebuilt after mid-session deletion; this doc commits with the migration -->

**Base commit:** `e783f1d6f` (the TDD-RED commit: oracles + differential/PBT
suites for preflight / netlist_reconciliation / human_reference_extractor /
placement_roundtrip / prereg::schema). The Rust kernels and delegation
shims are working-tree changes committed together with this document.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. A differential never shown to fail is not
evidence.

The previous two attempts at this migration (which died mid-stream) had
not run any mutations. This sweep is that missing evidence.

## Method

For each mutant: apply a single behavior-changing edit to
`packages/temper-design-bundle/src/validation.rs` (or
`packages/temper-drc-rs/src/validation.rs` for M11), rebuild the touched
crate (`uv run --no-sync maturin develop --release`), run the affected
module's differential/PBT suite, record the result, restore the file from
a filesystem backup (both sources are uncommitted WIP — never
`git checkout`), and rebuild. Floats are compared via `float.hex()`;
finding/issue records via typed canonicalization keys.

## Results — 12 runs, 11 mutants, all caught

| # | Kernel mutated | Mutation | Suite | Result |
|---|---|---|---|---|
| M1 | `zones_overlap` | y-axis overlap predicate inverted (never overlaps) | preflight | **4 failed** |
| M2 | `preflight_unassigned` | fixed-refs exemption dropped | preflight | **4 failed** |
| M3 | `preflight_impossible` | CONSTRAINT_002 boundary `<=` → `<` | preflight | **SURVIVED first** → discriminating case added → **1 failed** |
| M4 | `parse_design_netlist` | duplicate refs never recorded (REUSE never fires) | netlist_reconciliation | **4 failed** |
| M5 | `reconcile` | NET-MISSING finding kind typo'd | netlist_reconciliation | **4 failed** |
| M6 | `canonical_angle` | `py_float_mod` → `f64::rem_euclid` (the −0.0/+0.0 case) | placement_roundtrip | **4 failed** |
| M7 | `angle_diff` | raw diff instead of shortest arc | placement_roundtrip | **4 failed** |
| M8 | `pad_key` | `__pad_N` fallback prefix changed | placement_roundtrip | **4 failed** |
| M9 | `check_footprint_geometry` | footprint-angle check inverted | placement_roundtrip | **4 failed** |
| M10 | `prereg_temporal_gate` | `created > battery` inverted to `<` | prereg | **4 failed** |
| M11 | `rdl_sum` | hypot length → manhattan length | human_reference | **4 failed** |

**One surviving mutant, closed by a discriminating case.** M3 (the
CONSTRAINT_002 `<=` boundary) initially survived: random hypothesis
floats never hit exact component-size == zone-size equality, and the
first discriminating attempt (a square 30×30 in a 30×30 zone) was masked
by the rotated-fit arm (`comp_h <= zone_w` still accepted it). The
sweep's rule from the Phase-4 DRC campaign applies: a surviving mutant is
closed by adding the missing discriminating case, not by ratcheting the
gate. The added case — `_comp("EXACT", 30.0, 5.0)` in zone `(0, 0, 30, 5)`,
which fits normal-only at exact equality — was verified against both arms:
15 passed with the correct `<=`, 1 failed under the mutated `<`, and the
case stays in `test_impossible_differential_hand_built`.

**No surviving mutants after the M3 closure.** Every mutation is caught
by at least one failing test, so the differentials are non-vacuous across
all six kernel surfaces (preflight ×3, netlist parse/reconcile, roundtrip
×4, prereg gate, rdl_sum).

## Two real defects the GREEN pass caught before this sweep

The differentials (run for the first time after the worktree rebuild)
caught two genuine pre-migration-behavior divergences in the salvaged
kernels, both fixed in this slice:

1. **`parse_design_netlist` duplicate-ref anchoring.** The first Rust
   transcription used `HashMap::insert`'s replace-and-return, which
   *chains* duplicate-ref pairs (`(ref, path2, path3)` after
   `(ref, path1, path2)`); the oracle anchors every pair at the
   FIRST-seen path (`(ref, path1, path2)`, `(ref, path1, path3)`) — its
   `ref_paths` map is written once, in the `else` branch. Caught by
   `test_parse_differential_random` on a three-occurrence ref; fixed in
   `validation.rs` (first-occurrence-only insert), pinned by mr3.
2. **`rdl_sum`'s `math.hypot`.** The first transcription dlsym'd the
   system libm `hypot` (the B1 hostmath precedent). It diverges from
   CPython's `math.hypot` by 1 ulp on non-correctly-rounded inputs
   (`math.hypot(0.1, 0.1)` is `0x1.21a1851ff630ap-3`, libm `hypot` is
   `…b-3`): CPython 3.12 inlines its own fdlibm-style hypot into
   `mathmodule.c` (bpo-33083), so no dlsym target reproduces it. The
   kernel now takes `math.hypot` as a per-segment callback — parity by
   construction, accumulation order still Rust. Verified: 11/11 human-
   reference tests pass; M11 (manhattan substitute) caught.

## Verbatim oracles

The pre-migration implementations are pinned verbatim at commit
`6290942be` as `_preflight_py_oracle.py` (608 lines),
`_netlist_reconciliation_py_oracle.py` (652),
`_human_reference_extractor_py_oracle.py` (503),
`_placement_roundtrip_py_oracle.py` (398),
`prereg/_schema_py_oracle.py` (203) under
`packages/temper-placer/tests/validation/`.
