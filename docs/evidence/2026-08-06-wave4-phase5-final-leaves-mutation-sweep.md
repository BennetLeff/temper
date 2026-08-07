# Wave-4 Phase-5 final-leaves mutation sweep (2026-08-06)

<!-- provenance: commit=2b76533c8, worktree=<wt10-finalleaves>, branch=feat/wave4-phase5-final-leaves -->

**What this is.** The anti-vacuity record for the final deterministic leaf
kernels migrated in Wave-4 Phase-5 (the last unowned slice). A kernel is
"honestly bounded" only if a misimplementation of any of its branches is
caught by the differential suite; a mutation campaign proves each such
misimplementation is. The reproducible driver is
`scripts/phase5_final_leaves_mutations.py`.

**Method** (driver-encoded): for each registered mutant, apply the Rust-source
edit, rebuild the owning crate (`maturin develop --release`), run the owning
differential suite, require at least one FAILURE (a kill), then revert and
verify the source is pristine before the next mutant. A pytest **exit code 1**
counts as the kill; exit 0 is a SURVIVOR and any other exit code is an ERROR.
The campaign ends with a PRISTINE rebuild of both touched crates and the full
differential + PBT set green.

**Coverage of the sweep** — 14 mutants across the migrated kernels:

| # | Kernel / crate | Mutant |
|---|---|---|
| 1 | effective_ghost_pad_radius (design-bundle) | `math.hypot` (Dekker vector_norm) swapped for libm `(dx²+dy²).sqrt()` |
| 2 | effective_ghost_pad_radius | negative projections accumulate (`>` → `!= 0`) |
| 3 | effective_ghost_pad_radius | `max(0.0, ...)` clamp dropped |
| 4 | compute_wirelength | net-membership `any` → `all` |
| 5 | compute_wirelength | HPWL y-axis term dropped |
| 6 | find_critical_bottleneck_violations | severity reads the matched cell (the verbatim bug "corrected") |
| 7 | find_critical_bottleneck_violations | score-tie `>` → `>=` (last-wins) |
| 8 | find_critical_bottleneck_violations | grid index `floor` → `trunc` |
| 9 | point_in_polygon | top edge open (`y <= max` → `y < max`) |
| 10 | point_to_segment_distance | `pow(_, 0.5)` → `sqrt` (1-ulp class) |
| 11 | count_connected_layers (drc) | plane-layer auto-connect drops the `is_plane` gate |
| 12 | count_connected_layers | pin-sweep boundary `<=` → `<` |
| 13 | dedup_via_positions | boundary `<=` → `<` |
| 14 | dedup_via_positions | inner `break` removed (a position within tolerance of 2+ KEPT positions over-counts `duplicates`) |

**Results** — kills=14/14, errors=0, survivors=0; pristine rebuild + the full
differential/PBT set green after the final pass.

**Corpus gaps closed during the campaign.** Round 1 produced one survivor
(M12, the pin-sweep boundary): no differential case placed a pin at exactly
`dist == tol`. The `tol=0.1` boundary construction in
`test_count_trace_exactly_on_boundary` turned out NOT to land on the boundary
at all (`pow(1.0-1.1, 2)` = `0x1.47ae147ae1485p-7` > `0.1*0.1` =
`0x1.47ae147ae147cp-7`), so it only proved the two arms agreed. Both boundary
tests were reworked to the exact `tol=0.5`, `dy=0.5` construction
(`pow(0.5, 2.0) == 0.5*0.5 == 0.25` bit-exactly), and `test_count_pin_exactly_on_boundary`
now kills M12. Round 2 is 13/13.

The adversarial review then found a second, independent gap that the Round-2
corpus could NOT kill: the dedup inner `break` is load-bearing for the
`duplicates` COUNT, not just the boundary. A multi-match chain — one rejected
position within tolerance of two or more KEPT positions — fires the
`duplicates += 1` once per matching kept position when the `break` is removed
(divergence 2 vs 3 on `[(0,0),(0.03,0),(0.06,0),(0.05,0)]` at tol 0.05), while
the oracle counts once per REJECTED position. `test_dedup_multi_match_chain_counts_rejected_once`
closes the gap and now kills M14. Round 3 is 14/14.

**Vacuity notes.** The `d_len <= 0.0` early-out mutant (making it unreachable)
was dropped as observably vacuous: for coincident pins the division produces
NaN, `NaN > 0.0` is false, so `reduction` stays 0 and `max(0, base - 0) ==
base` — the result is identical. The `projection > 0.0` → `>= 0.0` mutant was
likewise dropped: a zero projection adds `0.0`, changing nothing observable;
M2 (`!= 0`) targets the same line and is live-killed.

**DRC-count / nondeterminism note.** No mutant depends on DRC count noise; all
kernel inputs in the differentials are constructed deterministically.
