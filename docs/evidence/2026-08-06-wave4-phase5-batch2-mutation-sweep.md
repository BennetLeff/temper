# Wave-4 Phase-5 batch-2 mutation sweep (2026-08-06)

<!-- provenance: commit=b3838f0c3431c1bbadd983d03913e5a22059bb06 dirty=true (sweep re-run at the review-fix commit; this doc's provenance line + results are the only working-tree delta — the sweep itself ran on a clean b3838f0c3 tree) -->

**What this is.** The anti-vacuity record for the deterministic leaf kernels
migrated in Wave-4 Phase-5 batch 2. A kernel is "honestly bounded" only if a
misimplementation of any of its branches is caught by the differential/PBT
suite; a mutation campaign proves each such misimplementation is. The
reproducible driver is `scripts/phase5_batch2_mutations.py`.

**Method** (driver-encoded): for each registered mutant, apply the Rust-source
edit, rebuild the owning crate (`maturin develop --release`), run the owning
differential + PBT suites, require at least one FAILURE (a kill), then revert
and verify the source is pristine (`git diff` clean) before the next mutant.
A pytest **exit code 1** (test failure) counts as the kill; exit 0 is a
SURVIVOR and any other exit code (2/3/4/5 — collection/infra failure) is an
ERROR, both recorded as errors. The campaign ends with a PRISTINE rebuild of
both touched crates and the full differential set green.

**Coverage of the sweep** — 26 mutants across the migrated kernels:

| # | Kernel / stage | Mutant |
|---|---|---|
| 1-2 | sequential_routing_dataclasses (DiffPairConfig) | default spacing 0.15→0.2; tolerance 0.5→0.6 |
| 3-4 | layer_assignment | Ground layer 1→2; plane inference drops layer 2 |
| 5-6 | power_plane | default plane layer 1→2; plane net not marked is_plane |
| 7-9 | component_assignment | footprint margin +1.0 dropped; reservation over-reserves +1.0; wirelength tie keeps last |
| 10-11 | fine_pitch_escape | layer-3 precedence dropped; min-pitch <3-pin threshold |
| 12-14 | validator slot-grid | fallback spacing 5→4; radius k ceil→floor (ceil-only zone); radius strict `<` |
| 15-17 | routing_metrics | avg rounding dropped; max(nets_total,1)→max(,0); fully-routed counter misrouted |
| 18-21 | DRC-check leaves | summary ascending sort; dedup rounding half-away; projection t unclamped; clamp x_max wrong margin |
| 22-26 | connectivity_validation | track-track layer guard inverted; pad-touch threshold 1e-4→2e-4; union attaches rb under ra; tracks counted as pad islands; dangling requires both ends open |

**Results** — kills=26/26, errors=0, survivors=0; pristine rebuild + full
differential set green (from /tmp/wt7-mutations-final.log, the review-fix
re-run at commit b3838f0c3). The original 25-mutant run and this re-run both
killed 25/25; the re-run adds the re-registered **validator radius k
ceil→floor** mutant (M13) — killed by `test_within_radius_ceil_only_zone`
(spacing 5, radius 8.5, slot (7.6, 0) sits in cell (2, 0) at distance
7.6 <= 8.5, reachable only through the ceil window `k = ceil(1.7) = 2`; a
floor window `k = 1` misses it). Earlier runs found real corpus gaps
(7 survivors + 1 infra error, then 2 survivors), each closed by a targeted
differential case: power-plane existing-net default layer, connectivity
union-orientation root ordering, and the component-assignment reservation
radius band. The M8/M23 mutants are now killed by those cases.

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

**Vacuity claims.** Two candidate mutants were proven observably vacuous (the
differential staying green is correct) and removed with in-driver notes:
layer_assignment empty-net-class (maps identically to "Signal") and the single
pad-component flag (sorted roots[1:] is empty). The slot-grid ceil/floor window
was ORIGINALLY dropped with a false vacuity claim — "a slot in a cell with
|index| > radius/spacing is at distance >= spacing*|index| > radius" — which
is wrong for round-to-nearest cells (the counterexample above: |cell_index| = 2
> radius/spacing = 1.7 while the slot is at distance 7.6 <= 8.5). The mutant
was re-registered and is live-killed by the ceil-only-zone differential case;
the ceil window (`k = ceil(radius/spacing)`) is the pinned, correct semantics.

<!-- provenance: worktree=<wt7-leaves>, branch=feat/wave4-phase4-deterministic-leaves2-rust -->
