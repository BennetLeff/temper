# Wave-4 Phase-5 batch-2 mutation sweep (2026-08-06)

<!-- provenance: commit=054ca7a20 dirty=false -->

**What this is.** The anti-vacuity record for the deterministic leaf kernels
migrated in Wave-4 Phase-5 batch 2. A kernel is "honestly bounded" only if a
misimplementation of any of its branches is caught by the differential/PBT
suite; a mutation campaign proves each such misimplementation is. The
reproducible driver is `scripts/phase5_batch2_mutations.py`.

**Method** (driver-encoded): for each registered mutant, apply the Rust-source
edit, rebuild the owning crate (`maturin develop --release`), run the owning
differential + PBT suites, require at least one FAILURE (a kill), then revert
and verify the source is pristine (`git diff` clean) before the next mutant.
A rebuild/pytest infrastructure failure counts as ERROR and aborts the
campaign; a mutant that leaves the suites green is a SURVIVOR and also aborts.
The campaign ends with a PRISTINE rebuild of both touched crates and the full
differential set green.

**Coverage of the sweep** — 25 mutants across the migrated kernels:

| # | Kernel / stage | Mutant |
|---|---|---|
| 1-2 | sequential_routing_dataclasses (DiffPairConfig) | default spacing 0.15→0.2; tolerance 0.5→0.6 |
| 3-4 | layer_assignment | Ground layer 1→2; plane inference drops layer 2 |
| 5-6 | power_plane | default plane layer 1→2; plane net not marked is_plane |
| 7-9 | component_assignment | footprint margin +1.0 dropped; reservation over-reserves +1.0; wirelength tie keeps last |
| 10-11 | fine_pitch_escape | layer-3 precedence dropped; min-pitch <3-pin threshold |
| 12-13 | validator slot-grid | fallback spacing 5→4; radius strict `<` |
| 14-16 | routing_metrics | avg rounding dropped; max(nets_total,1)→max(,0); fully-routed counter misrouted |
| 17-20 | DRC-check leaves | summary ascending sort; dedup rounding half-away; projection t unclamped; clamp x_max wrong margin |
| 21-25 | connectivity_validation | track-track layer guard inverted; pad-touch threshold 1e-4→2e-4; union attaches rb under ra; tracks counted as pad islands; dangling requires both ends open |

**Results** — kills=25/25, errors=0, survivors=0; pristine rebuild + full
differential set green (from /tmp/wt7-mutations3.log, the final run). The
first two runs found real corpus gaps (7 survivors + 1 infra error, then 2
survivors), each closed by a targeted differential case: power-plane
existing-net default layer, connectivity union-orientation root ordering,
and the component-assignment reservation radius band. The M8/M23 mutants
are now killed by those cases.

**Infra notes.** Every mutant's `old` source string was verified to match the
current source before the campaign started (the layer_assignment empty-net-class
pattern had drifted through the #805 rebase and was re-pinned). The `1-1`/`0`
eq_op fold and the clippy `unwrap` removals landed as a cleanup commit BEFORE
the sweep, so no mutant is masked by a pre-existing lint failure. Two `<=`/`<`
boundary mutants (`<= 1e-4`, `dist <= radius`) were replaced by threshold
mutants on the same lines: an exact-boundary float input is unconstructible
through the pipeline (`point_to_rotated_rect_distance`'s output never lands on
1e-4; exhaustive search) and the assignment pipeline cannot be made to depend
on a slot at exactly the footprint radius. The strict-`<` semantics remain
pinned because both arms call the same single-source-of-truth function.

<!-- provenance: worktree=<wt7-leaves>, branch=feat/wave4-phase4-deterministic-leaves2-rust -->
