# Round 6 FEM coordination

- Board: native-17/section.kicad_pcb, SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- Intake: 2026-09-28, PR #1615 at `dac4f6e1b506b5146f1030f3d3416e1fa2076545`.
- Authority: [D1-FEM.md](../../validation-plan/D1-FEM.md), SHA-256 `aae75f1570d619f3cb796ac76b630d66a9b6ad1283d79c36223d33cd3eef2317`.
- Evidence class: execution/provenance record and model-based fixture diagnostics; no physical measurement.
- Status: **BLOCKED at solver qualification**. The [D1 FEM handback](../01-switching-parasitics/round6/d1-fem/README.md) records two Palace build failures and a failed Elmer iterative coax solve. No accepted board matrix exists. One additional Palace build with ARPACK enabled is awaiting owner approval.

## Scope and dependency order

D1-FEM supersedes the FastHenry extraction and previous six/eight-terminal discussion with four loop ports per leg. Palace is primary; Elmer is the documented fallback. The worker owns `01-switching-parasitics/round6/d1-fem/` in the isolated `codex/ps-r6-fem` checkout. The coordinator reviews the resulting fixtures, geometry and convergence evidence before accepting the matrix.

Only an accepted D1 matrix can feed the ROUND-5 D2 diagnosis/grid and C1/C2 timing/loss reruns. Model-only gate-resistor, snubber, split-drive and negative-bias comparisons follow that baseline. Production board, source and firmware edits remain outside this validation run. No bench work has been performed or manufacturing release approved.

## Downstream raw inputs verified

The coordinator rechecked the existing local evidence before preparing the dependent simulations. Commands below run from the repository root with `/Users/bennet/Miniforge3/bin/python3`:

```sh
python3 zapote/power-stage-120v/validation-results/round3-coordination/raw-evidence/verify.py zapote/power-stage-120v/validation-results
# 3327/3327 files verified; exit 0
python3 zapote/power-stage-120v/validation-results/round4-coordination/verify_raw.py zapote/power-stage-120v/validation-results
# 12027/12027 round-4 local files verified; exit 0
```

The first round-3 verifier invocation omitted its root argument and checked the repository root, reporting 0/3327. The corrected command above explicitly supplied the results root and passed; the first invocation was a path error, not missing evidence.

| Frozen manifest | SHA-256 |
| --- | --- |
| [Round 3](../round3-coordination/raw-evidence/manifest.json) | `dba4d00f74d577f72d3d5987e36a2363127e17a034253280c3c6dcb8d748665c` |
| [Round 4](../round4-coordination/raw-manifest.json) | `40ef4b2194c89dc841cef736fddac93f258cc23319b0128abbb5ff75724cccb5` |

These checks establish file identity, not model validity. Restore procedures and public release links remain in the [round-3 archive note](../round3-coordination/raw-evidence/README.md) and [round-4 archive note](../round4-coordination/raw-evidence/README.md).

## Extraction checks to resolve

- The worker's native pad audit found that a straight top-surface G–S bridge crosses the intervening D pad on all four TO-247 footprints. A routed or elevated closure must preserve the specified endpoints without contacting a third conductor. Preserve the straight-bridge failure as negative evidence and quantify the corrected closure's effect.
- Artificial bridges and capacitor port sheets carry field energy. Record their reference planes and sensitivity before combining the result with the existing package and assumed capacitor ESL models; do not label a closure-sensitive result as copper-only inductance.
- The heatsink is not selected. Its documented X span alone does not establish its full installed geometry. Any plate comparison must state its assumed position and dimensions; individual matrix entries are not automatically rigorous componentwise bounds.
- At the pinned Palace source, use open inactive current ports and `terminal-M.csv`. `terminal-Mm.csv` is a different current-difference representation. Check all keys against the actual built revision.

## Handoff rule

Keep the worker's raw geometry, meshes, solver logs and binary/source identities locally under ignored paths with hashes. The coordinator must independently review and integrate the handback before changing the master status. A completed worker task alone does not close D1 or authorize its dependent switching predictions.

## Notes for the dependent switching worker

Use the [instrumented round-4 D2 deck](../01-switching-parasitics/round4/d2-switching/scripts/extended_instrumented.cir) and its [diagnostic report](../01-switching-parasitics/round4/d2-switching/README.md), preserving the original scalar deck as a replay control. That report corrected the earlier interpretation: the 723.918 V peak occurred with negative die VGS, and the vendor channel probe includes avalanche current. The later off-gate peak is a different event. Save signed external drain, diode and internal model currents with time alignment; do not infer shoot-through from the channel probe alone.

The D1 port order and current directions must survive the SPICE conversion, including signs of mutual terms. Keep the physical capacitor branches separate and bind all results to the accepted matrix hash and exact deck/model hashes. A K=0 diagnostic removes magnetic coupling in this loop representation; document which entries were changed rather than claiming that every form of physical source impedance disappeared.

C1 must cover both legs at all six driver timing corners and the documented low-bus points. C2 must use the frozen 270-case A grid and report complete event coverage. The [round-4 C2 report](../01-switching-parasitics/round4/c2-losses/README.md) is a conditional reference-inductance subtotal: prior-cycle recovery, low-bus coverage, hot device loss and floating dead-time current reversal remain unresolved. Retain the existing input-identity, waveform-integrity and complete-case checks when extending these scripts. Neither a lower ZVS threshold nor a lower matched-subset subtotal alone establishes the requested total-loss verdict.

## Solver build outcome

Palace source was pinned at `ca04eddeaa1d8f5345b8a51b5ce5cc578da3a8c7`. Configuration needed an explicit Homebrew OpenBLAS path and network access for dependency downloads. The first actual build failed while linking MFEM's `ex1` self-test: the link command omitted OpenBLAS. The second enabled MFEM LAPACK support and passed the MFEM self-tests, then Palace configuration rejected the reduced-feature selection with both SLEPc and ARPACK disabled. These are recorded configuration/link failures, not evidence that Palace cannot run on this machine. No Palace executable was qualified.

Following D1-FEM's two-attempt rule, the worker switched to Elmer release 26.2.1 at `a19504ac53ec222e3355e182b08f2ff280c2203a`. Its isolated build and install succeeded, and three selected upstream magnetodynamics CTests passed. A subsequent HYPRE-enabled build also succeeded. These build results are not extraction-method acceptance receipts.

The legacy D2 deck has `CLOC=0.4u`; D1-FEM explicitly requests two physical 100 nF branches per leg. Preserve 0.4 µF only for the faithful historical control. Record the changed capacitance and branch topology alongside the matrix replacement in the new baseline, so a waveform difference is not attributed solely to inductance. Keep the original recorded comparison separate from any fresh revised-topology replay.

## Fixture qualification outcome

The corrected radial coax load and a direct tree-gauge solve give 13.745242 nH on the 0.25 mm mesh versus 13.862944 nH analytic (0.849% low at nominal 1 A). The nodal source approximation is not exactly current-conserving: sampled circular cuts differ by about 1.14%. An area-average normalization gives about 1.50% low, but that average is not a uniquely conserved branch current. Both definitions and source discretization must remain explicit. Doubling current quadrupled energy and reversing it preserved energy at the tested 0.35 mm mesh. Plate, mutual and board qualification remain pending.

The first HYPRE/AMS solve on the fixed 0.35 mm coax mesh returned 1.777093 nJ versus the direct solve’s 6.839985 nJ. The source-documented singular-matrix option, with unchanged physics and tolerance, returned 10,256.04 nJ and a final printed relative residual of 9.723099 against 1e-9. Both runs exited zero and printed `ALL DONE`; both are rejected. The worker stopped before plate, mutual or board solves. Final numerical values and source-bound logs are in the [fixture report](../01-switching-parasitics/round6/d1-fem/README.md).

## Resume decision

The next concrete build correction is to enable Palace’s required ARPACK backend while retaining the successful MFEM LAPACK/OpenBLAS configuration. This can reuse the existing dependencies under `/tmp/ps-r6-fem-build1`. The inner Palace cache selected Homebrew’s `libmfem.dylib` despite the isolated `MFEM_DIR`; a retry must explicitly bind and inspect the MFEM library and include path. It would exceed D1-FEM §4’s two-attempt limit, so owner approval is pending; no third build has run. Preserve all build trees. Approval of this build would not qualify the solver: all three analytic fixtures, current-port normalization and the board sensitivity checks would still be required.

## Coordinator validation

The frozen worker handback was copied into the coordinator checkout at `/Users/bennet/.codex/worktrees/ps-r4-integration/temper`. Its original remains under `/Users/bennet/Desktop/temper/worktrees/ps-r6-fem`. Both hold the ignored `round6/d1-fem/raw/` files. No raw evidence was published or staged.

- The 98-file raw manifest passed independently after copying. Manifest SHA-256: `2eb6bc4bef8beaad140c3716d74a27687d2b4fbcbd1d6e6133979b9532a2549b`.
- All eight recorded installed runtime/library hashes and both recorded Elmer source-file hashes match the actual local files.
- The current verifier exactly reproduces the saved direct and AMS receipts. Its six captured-log mutations pass, including terminal NaN values after earlier valid values.
- Independent binary-to-ASCII conversion of the 66,006-tetrahedron coax mesh preserves oriented connectivity after node-ID mapping; maximum coordinate difference is `7.105427357601002e-15` mm.
- Ruff, Python syntax and JSON checks pass. The import-boundary gate reports five contracts kept and zero broken. `make regen` and `make regen-check` pass without changing derived files. All three shell recipe blocks pass syntax checks; the fresh full FEM rerun was not repeated during integration.
- The code-simplification skill’s reuse, quality and efficiency rubrics were applied to the nine helper scripts. No behavior-preserving restructuring was justified; fixture-specific scripts retain their explicit checks. Correctness fixes were handled separately: reject stale STEP output, inspect the written mesh conversion, and reject terminal nonfinite solver values.

No additional operational monitoring is required: this packet contains local validation tools and evidence, with no production design or firmware change. It does not authorize manufacturing or close electrical acceptance gates.

The [completed code-review receipt](review/review.json) has no open findings. A separate Sol reviewer applied seven lenses sequentially, as required by repository instructions; there was no external peer review. Its one finding—the fresh solve recipe checking a retained log—was corrected and re-reviewed. This verdict covers the blocked handback only, not electrical or manufacturing acceptance.
