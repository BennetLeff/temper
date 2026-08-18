# `compile_fail` doctests proved less than they claimed — trybuild enforcement

**Date:** 2026-08-18
**Branch:** `fix/trybuild-compile-fail-enforcement`
**Board:** `pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f...` — **unmodified** (verified before and after).
**Toolchain:** rustc 1.97.1 (8bab26f4f 2026-07-14), cargo 1.97.1.

## Summary

The project's safety-critical invariants are enforced by Rust type-system
guards. Each was documented with a `` ```compile_fail `` doctest and cited as
proof the invariant holds. Those doctests assert exactly one thing — *the
snippet does not compile* — and never **why**. Measured here, that gap is
exploitable in both directions, and two guards that were cited as having
doctests had none at all.

The invariants themselves all hold. What was missing was proof. This change
supplies it with `trybuild` (full rustc stderr diffed against checked-in
`.stderr` expectations) plus a second layer that pins the error *code*
independently of the message text.

## 1. What was actually there

Seven `compile_fail` doctests, in three crates. **Every one was a bare
`` ```compile_fail `` with no error-code annotation at all** — so even the weak
form of the check rustdoc offers was not being requested.

| # | Guard | File |
|---|---|---|
| 1 | `WorldPosition` struct literal | `packages/temper-geometry/src/world_position.rs:42` |
| 2 | `WorldPosition` `From<(f64,f64)>` | `packages/temper-geometry/src/world_position.rs:50` |
| 3 | `Layer` struct literal | `packages/temper-geometry/src/layer_identity.rs:180` |
| 4 | `RotationQuadrant` `Div` | `packages/temper-geometry/src/rotation_quadrant.rs:66` |
| 5 | `NetRouteResult::Connected` | `packages/temper-geometry/src/net_route_result.rs:116` |
| 6 | `PadOccurrence` `From<&str>` | `packages/temper-design-bundle/src/pad_occurrence.rs:69` |
| 7 | `Via` private fields | `packages/temper-orchestration/src/pipeline_route.rs:124` |

### Guards cited in the brief that had NO doctest

* **`ClearanceHalo`** — `packages/temper-geometry/src/clearance_halo.rs`. Its
  private `polygon` field and its `ConservativeSuperset` ZST marker are real
  and correct, but nothing tested them. Two cases added.
* **`DrcCount`** — `packages/temper-drc-rs/src/drc_count.rs`. Private
  `count`/`is_capped` are real and correct; nothing tested them. One case added.
* **`Via::new`'s annular clamp** — a **runtime** clamp, not a type-system
  guard. No snippet fails to compile when it is removed, so it cannot have a
  `compile_fail` test. It is covered by the runtime test
  `via_new_enforces_annular_floor_on_the_exact_regressed_pair`, which is
  non-vacuous (see §4).

## 2. The two vacuity holes, measured

Both reproduced against `cargo test --doc --no-default-features` on
`temper-geometry`, on the real `world_position.rs` guard (actual error E0451):

| Negative control | Result |
|---|---|
| Annotate the guard `` ```compile_fail,E0433 `` — a flatly wrong code | **passed green** (5/5 ok) |
| Replace the body's `WorldPosition` with `WrldPositionTYPO`, deleting all contact with the guard | **passed green** (5/5 ok) |

So on stable rustdoc the annotation is decorative, and a doctest that fails for
a typo is indistinguishable from one that fails for the invariant.

## 3. The mechanism

`trybuild` 1.0.120, added as a dev-dependency to the four affected crates.
Each guard gets a case under `packages/<crate>/tests/compile_fail/` with a
generated `.stderr` expectation; the runner is `tests/compile_fail.rs`.

The `compile_fail` doctests are **kept** — they are the rendered documentation
next to the type they protect, and `cargo test --doc` still runs them
unchanged. trybuild is the enforcement, not a replacement.

### Second layer: `each_guard_expectation_still_pins_its_intended_error_code`

trybuild's stderr diff is message-text-sensitive, and CI runs `ubuntu-latest`'s
stock toolchain with **no `rust-toolchain.toml` pin** in this repo. So the
`.stderr` files will eventually go red for cosmetic rustc rewording, and the
fix will be `TRYBUILD=overwrite`.

**That regeneration is the real hazard**, and it is not hypothetical — it is
demonstrated in §5. Run blindly it absorbs a guard that has started failing for
a different reason, restoring exactly the vacuity this work removes, while
leaving CI green. Each crate's test file therefore carries a hand-written table
mapping case → required error code, asserted directly against the `.stderr`
files, plus a count check so a new case cannot be added without pinning its
code. Error codes are far more stable than message text, so this layer should
survive toolchain upgrades that legitimately churn the expectations.

## 4. Anti-vacuity results

Every guard, both experiments. **A** = remove the guard from the source, the
test must fail. **B** = corrupt the expectation's error code, the test must
fail.

| Guard | Crate | Real code | A: guard removed | B: wrong code |
|---|---|---|---|---|
| `WorldPosition` (struct literal) | geometry | E0451 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `WorldPosition` (`From<(f64,f64)>`) | geometry | E0277 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `Layer` (struct literal) | geometry | E0451 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `RotationQuadrant` (no `Div`) | geometry | E0369 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `NetRouteResult::Connected` | geometry | E0451 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `ClearanceHalo` (private polygon) | geometry | E0616 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `ConservativeSuperset` (ZST marker) | geometry | E0451 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `PadOccurrence` (no `From<&str>`) | design-bundle | E0277 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `Via` (private fields) | orchestration | E0616 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `DrcCount` (capped/count coherence) | drc-rs | E0451 | **FAIL** (case compiles) | **FAIL** (mismatch) |
| `Via::new` annular clamp *(runtime)* | orchestration | n/a | **FAIL** — `ring 0.2 below the 0.254mm fab floor` | n/a (not a compile-time guard) |

All 10 compile-time guards demonstrate both directions. The runtime clamp
demonstrates the applicable direction.

A partial weakening is caught too: making only `VerifiedRoute::pad_ids` public
(leaving the other two private) changed the case from
`error[E0451]: fields pad_ids, segment_ids and via_ids are private` to a
two-field message and trybuild reported `mismatch`. Making all three public
made the case compile, reported as `error`.

## 5. The second layer is itself non-vacuous

Simulating the exact dangerous workflow — a guard changes shape, someone runs
`TRYBUILD=overwrite` without reading the diff:

1. Renamed `ClearanceHalo`'s private `polygon` field to `poly_verified` and
   made it public. The guard is now **gone**, but the case still fails to
   compile — `halo.polygon` now resolves to the *method* `polygon()`, giving
   **E0615** instead of E0616.
2. `TRYBUILD=overwrite` regenerated the expectation to E0615.
3. Result:

```
test tests/compile_fail/clearance_halo_private_polygon.rs ... ok        <-- trybuild FOOLED
test each_guard_expectation_still_pins_its_intended_error_code ... FAILED
```

> `clearance_halo_private_polygon: expected error[E0616] (guard: ClearanceHalo.polygon private
> -- no unverified halo substitution) but the checked-in expectation contains
> ["error[E0615]: attempted to take value of method polygon on type &ClearanceHalo"].
> A changed error code means the guard changed shape -- read the guard, do NOT edit
> the table to match.`

trybuild alone reported the case green. Only the error-code table caught it.
This is why both layers exist.

## 6. CI wiring

New step **"Type-system guard enforcement (trybuild compile_fail)"** in the
`rust-checks` job of `.github/workflows/python-tests.yml`, immediately after the
existing doctest step. That job's context — *"Rust Checks (cargo check +
clippy)"* — is a required check, so this is gated on the PR path rather than
merely present. It runs `--no-default-features`, matching the doctest step, to
keep pyo3's `extension-module` out of the link.

Native-only by construction: trybuild shells out to cargo and needs a host
toolchain, so it cannot run on the wasm tier — the same structural limit the
doctests it backs already have.

## 7. Verification

| Check | Result |
|---|---|
| `cargo test --test compile_fail --no-default-features` x4 crates | 2 passed per crate, 0 failed (10 cases + 4 code-table tests) |
| `cargo test --doc --no-default-features` x4 crates (pre-existing step) | unchanged: geometry 2+5, design-bundle 1+1, orchestration 1, drc-rs 1 — all ok |
| `cargo clippy --all-features --all-targets -- -D warnings` x4 crates (CI-exact) | clean |
| `pcb/temper.kicad_pcb` sha256 | `26981fea2dbc425f...` before **and** after |
| Workflow YAML parses; step present in `rust-checks` | ok (13 steps) |

No guard was weakened. No clearance, creepage, copper-weight or DRU threshold
was touched. No `_*_py_oracle.py` was touched. No `git stash` was used.

## 8. Separate finding — misattached `Via` doc comment

`packages/temper-orchestration/src/pipeline_route.rs`: the doc comment block
beginning *"A via ready for KiCad sexpr emission"* (line ~112), **including its
`compile_fail` doctest**, is separated from `pub struct Via` (line 160) by the
`MIN_ANNULAR_RING_MM` and `ANNULAR_RING_TARGET_MM` constant definitions. The
whole block therefore attaches to `MIN_ANNULAR_RING_MM`, not to `Via` — visible
in the doctest's own name:

```
test src/pipeline_route.rs - pipeline_route::MIN_ANNULAR_RING_MM (line 124) - compile fail ... ok
```

`pub struct Via` has no doc comment at all, and rustdoc renders the via
documentation on the constant. This does not affect whether the doctest runs,
and the trybuild case covers the guard regardless. **Not fixed here** — it is a
documentation-placement defect in a file adjacent to another agent's ownership
area, reported for its owner rather than edited.
