# Native copper/current evidence — 2026-10-02

Scope: filled-copper reconstruction and conditional DC current distribution for
native-17. Production PCB SHA-256 remains
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
KiCad 10.0.4 supplied live geometry. [Source hashes](source-sha256.json) identify
Rust, extractor, profile basis, fixture, Make/CLI and PCB bytes. Reports truthfully
record a dirty pre-commit tree and include the actual evaluator/extractor hashes.

## Native result

[Compact report](native17-summary.json) (full report and its SHA-256 are retained
in the native current archive): 35/35 filled-copper paths, 23/35 centreline
paths, all 395 track/pad entries, 1,786 metric rows including 28 conditional
R/loss measurements. Twelve centreline limitations remain separately labelled;
there are no full-copper reconstruction gaps for this profile.

All 14 declared current/plating cases complete at both mesh sizes. The maximum
relative R change is 1.62%; the minimum is 0.24%. Numerical residuals and energy
balances are in each case, along with layer samples and individual barrel
currents/locations. Largest refined case: 80,598 active nodes, 125,068 total
triangles. This is conditional numerical completion, not board acceptance.
See [CURRENT.md](../CURRENT.md) for boundary assumptions, results and exclusions.

The final live report took **8.028 s** including extraction and persistence.
The [release benchmark](benchmark.txt) measured **1,274.82 ms/report** for full
geometry over 25 iterations, and **5,209.10 ms/current profile** over 3 iterations,
excluding extraction and JSON parsing. These are host observations, not timing
guarantees. Geometry takes longer than the previous track-only report because it
now triangulates and traverses filled copper.

## Independent checks and actual edits

[Native layout proof](native-layout-proof.tar.gz) retains the scratch board,
raw snapshots, reports and KiCad connectivity oracle output. KiCad confirms all
35 endpoint connections, plus every object transition on C16's track return.
The existing trace-width mutation still changes track R and pad-entry feedback.

[Native current proof](native-current-proof.tar.gz) retains three full native
runs and the scratch PCB files:

1. Unmodified production board: every current case solves.
2. All copper thicknesses halved, with general finished thickness corrected:
   coil-feed resistance doubles to the test tolerance, through CLI comparison.
3. Coil-feed tracks/vias/zones removed: the case reports disconnected copper,
   exits 2, and its R/loss comparison has null after/change values. It does not
   report zero resistance or conceal missing data as an improvement.

The tests check that the production PCB's bytes remain unchanged.

[Workspace tests](workspace-tests.txt): **407 passed, 0 failed, 2 ignored**, run
with `PROPTEST_CASES=2048`. The two ignored native tests were then run explicitly
in the [3-test CLI suite](live-tests.txt), all passing. [Focused native tests](native-tests.txt)
provide another finalized-model receipt before the last one-nanometre-gap test;
that last test is covered by the full workspace receipt.

Numerical tests use independent uniform-strip, parallel/series circuit, and
logarithmic annular-sheet solutions. The annular case verifies refinement toward
a non-linear exact field. Property tests vary conductor dimensions, current and
subdivision; other cases cover holes, separate islands, a 1 nm gap, floating
copper and invalid dimensions/material inputs. Live tests cross the actual
Make/CLI/pcbnew/Rust/report boundary; captured-fixture replay also runs by default.
These do not independently validate all physical approximations on native-17.

## Failures caught during development

[jacobi-cg-incomplete.json.gz](jacobi-cg-incomplete.json.gz) records the first
iterative implementation: most native power-net cases exhausted the iteration
budget. The small analytical tests alone had not exposed this. The final code
uses sparse Cholesky plus stable current evaluation and iterative refinement.

[coarse-mesh-incomplete.json.gz](coarse-mesh-incomplete.json.gz) records the
2/0.5 mm² study. The HV return and B-leg return missed the unchanged 3% resistance
refinement criterion. The final profile tightens both meshes to 0.5/0.125 mm².
These historical reports have their own evaluator identities; they are not valid
baselines for the final evaluator.

## Repository validation

- [Clippy](clippy.txt) completed for DRC/harness and all targets. Seventeen existing
  warnings were outside the changed code; [structured diagnostics](clippy.jsonl.gz)
  retain their exact locations. Changed Rust passes rustfmt; extractor passes Ruff.
- [Import boundaries](import-boundary.txt): 0 new violations.
- [Regeneration](regen.txt) and [regen-check](regen-check.txt): all derived artifacts consistent.
- [Five-unit run](unit-run.tar.gz), [summary](unit-summary.json): all five units
  indeterminate, none failed; missing acceptance inputs remain explicit. Make
  returns nonzero for this incomplete-evidence status. This is separate from
  numerical completion of the native-17 current profile.
- [Implementing-context review](../../../docs/reviews/2026-10-02-native-current/review.md):
  sequential review under the user's tool mapping; no independent reviewer claim.

Commands used the bundled KiCad Python/CLI listed in CURRENT.md/NATIVE.md,
`cargo test --release --locked --offline --workspace`, the explicit
`layout_native_cli -- --include-ignored --nocapture` selection, and
`cargo bench --locked --offline -p zapote-drc --bench layout_quality` from the
Zapote workspace. Archives preserve the command, raw extractor output and report
for each native run.
