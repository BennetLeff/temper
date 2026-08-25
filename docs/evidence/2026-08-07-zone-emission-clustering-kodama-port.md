<!-- provenance: commit=c10523bbb74ba6250d88af7bed417da6c7aec6c8 (this migration's base commit; merges worktree-agent-a0c9bd1a1df109a4d [scipy re-triage] and worktree-agent-a4aa64a380b629dcd [zone-emission clustering defect fix]), dirty=true (this doc's own change in progress) -->

# `zone_emission.py` clustering: consumer-contract spike, `kodama` differential, and port (2026-08-07)

**Task**: `docs/evidence/2026-08-07-scipy-keeps-re-triage.md` re-triaged
`zone_emission.py`'s `_cluster_positions` (`scipy.cluster.hierarchy.linkage`/
`fcluster`/`scipy.spatial.distance.pdist`, Ward hierarchical clustering) from
JUSTIFIED-KEEP to **PORTABLE**, on the premise that "clusters are consumed
only as independent convex-hull groups, and the tests assert only cluster
*count*, never membership" -- but flagged it as needing a differential spike
against real board geometry before execution, since (unlike the
single-point-query cases the same re-triage flipped) Ward linkage
tie-breaking genuinely can produce different-but-valid clusterings from the
same input. This document verifies that premise, evaluates `kodama`, runs
the differential, and (given the result) ports.

**Result: PORTED.** Partition-identical and geometry-identical to scipy on
every real production-board net and every synthetic/symmetric stress case
tested, 60-100x faster at the board's actual net sizes, and confirmed to
build for `wasm32-unknown-unknown`.

---

## 1. Consumer contract: verified, not assumed

Read every call site and test before touching any code:

- **`compute_zones_for_net`** (`zone_emission.py:176-219`) calls
  `_cluster_positions`, then for each returned group independently calls
  `_convex_hull_from_positions` and appends one `ZoneDefinition` per group.
  Nothing downstream reads a cluster *label* -- each group is reduced to its
  own convex-hull polygon before the function returns.
- **`_emit_zone_pours`** (`_zone_pour_stitch.py:220-353`, the sole production
  caller of `compute_zones_for_net`) iterates the returned zone list and
  appends each independently to the output KiCad `(zone ...)`
  s-expressions -- order/identity within one net's cluster list affects only
  where in the file that net's zones appear, not electrical correctness
  (KiCad zones are independent pour regions). It then calls
  `_stitch_isolated_pads` with the already-computed **hull polygons**
  (`zone_points`), not cluster labels -- stitching is a nearest-boundary-point
  query against geometry, again not identity-sensitive.
- **Tests**: `tests/router_v6/test_zone_emission.py`'s
  `TestDataInformedClustering` class asserts only `len(zones)` /
  `len(clusters)` (cluster *count*) -- `test_tight_cluster_produces_single_group`,
  `test_two_widely_separated_groups_produce_two_clusters`,
  `test_single_pad_is_single_cluster`, `test_cluster_positions_single_cluster_at_adjacent_pitch`.
  No test anywhere greps for a specific partition or cluster membership.

**Verdict: count-only + resulting geometry, never membership/identity.**
This confirms the re-triage's stated premise (Section headed "Hierarchical
clustering" in `2026-08-07-scipy-keeps-re-triage.md`) rather than merely
repeating it.

---

## 2. `kodama` evaluation

- **API fit**: `kodama = "0.3"`. `linkage(condensed_dissimilarity_matrix,
  observations, method)` returns a `Dendrogram` of `observations - 1` merge
  `Step`s (`cluster1`, `cluster2`, `dissimilarity`, `size`), using the
  identical `label = N + i` numbering convention scipy's own `Z` matrix
  uses. `Method` includes `Ward` among seven linkage criteria (also Single,
  Complete, Average, Weighted, Centroid, Median).
- **No `fcluster` equivalent.** `kodama` has no flat-cut API -- only the raw
  dendrogram. This port implements the cut itself (union-find reconstruction
  over the `Dendrogram`'s steps, see Section 4 for the boundary-condition
  bug this surfaced and fixed).
- **Maintenance**: `crates.io` `updated_at` 2023-01-04 (created 2017-08-15),
  471,877 total downloads. Not actively maintained, but the algorithm it
  implements (Ward/Lance-Williams recurrence) is closed and well-specified,
  not something needing ongoing upstream development -- and it is verified
  bit-exact against scipy below, not merely assumed stable.
- **Dependencies**: zero production dependencies (`Cargo.toml`:
  dev-dependencies only -- `byteorder`, `rand`, `lazy_static`, `quickcheck`).
- **`wasm32` status: verified directly**, not assumed. A throwaway crate
  depending on `kodama = "0.3"` alone built cleanly for
  `wasm32-unknown-unknown` with no extra feature wiring. After adding
  `kodama` to `packages/temper-geometry/Cargo.toml` and the new
  `hierarchical_clustering.rs` module, `cargo build --target
  wasm32-unknown-unknown --no-default-features` for the **whole crate**
  also succeeds cleanly (this is the WASM tier's actual build
  configuration, plan `2026-08-03-002`).

---

## 3. The differential: methodology

Real pad positions were extracted from `pcb/temper.kicad_pcb` (read-only,
never modified) via `parse_kicad_pcb_v6` + the same net-pin-position
resolution `_write_routes_to_content` uses, then filtered to the
zone-eligible, non-exempt population that actually invokes clustering in
production (`_zone_layers_for_net` non-empty, net class not in
`_CONTINUITY_EXEMPT_CLASSES = {"GND", "ACMains"}`): **all 14 `HighVoltage`
nets** the just-merged clustering-defect fix (`24c71979`) un-exempted.
2 of the 14 have <=2 pads (`tank-out`, `a`) and short-circuit to a trivial
single cluster before reaching either backend -- identical by construction,
not tested further. The remaining **12 nets** (3-12 pads each) genuinely
invoke Ward linkage.

Two comparison axes, matching the task's framing that membership may
legitimately differ but the emitted geometry is what matters:

1. **Partition agreement**, as a SET of sets (order-independent) -- the
   contract Section 1 established.
2. **Emitted-geometry agreement** -- feed each arm's clusters through the
   *unchanged* `_convex_hull_from_positions` + `_clip_to_board` (against the
   real board polygon) and compare the resulting hull-union area in mm^2.

A standalone Rust CLI (`kodama_diff`, not part of the shipped crate --
scratch tooling for this spike) wrapped `kodama::linkage(Method::Ward)` plus
a JSON-in/JSON-out harness, run via subprocess from Python against the exact
same condensed-distance input scipy received (`pdist`-order Euclidean
distances) and the exact same NN-distance-gap threshold `_cluster_positions`
itself computes (that threshold heuristic is plain Python arithmetic, never
scipy, and is unchanged by this port).

---

## 4. First result and its bug: `<` vs `<=` at the cut boundary

The first differential run (naive flat-cut: union merges with
`dissimilarity < threshold`) showed **4 of 12 real nets mismatching**
(`DC_BUS_RTN`, `power_in.ntc-no`, `discharge.k_dis1-nc`,
`discharge.k_dis2-nc`) -- kodama consistently producing MORE clusters than
scipy at the same threshold.

Before concluding this was a genuine kodama-vs-scipy algorithmic
difference, the raw per-merge dissimilarity values were dumped from both
backends for one mismatching net (`power_in.ntc-no`, 4 pads):

```
scipy Z:    [1, 3, 38.68865079063884, 2]
            [0, 2, 76.08509216659989, 2]
            [4, 5, 146.34412569351733, 4]
kodama:     (1, 3, 38.68865079063884, 2)
            (0, 2, 76.08509216659989, 2)
            (4, 5, 146.34412569351733, 4)
```

**Bit-exact.** The two backends' Ward dissimilarity computations agree to
full `f64` precision on every merge -- the mismatch was not in the linkage
algorithm at all. The threshold for this net, `76.08509216659989`, is
*exactly* the pairwise distance between pads 0 and 2 -- `_cluster_positions`'s
own fallback threshold branch (`nn_dists[idx]` at the 95th percentile, used
when no natural NN-distance gap is found) sets the threshold to an actual
pairwise distance already present in the data whenever that percentile
point is itself a nearest-neighbour distance, landing the cut exactly ON a
merge height rather than near it. This is not a rare edge case for this
call site: it happened on 4 of 12 real nets (33%).

Checked scipy's actual boundary behaviour directly:

```python
fcluster(Z, t=76.08509216659989,        criterion="distance")  # [2 1 2 1]
fcluster(Z, t=76.08509216659989 - 1e-9, criterion="distance")  # [2 1 3 1]  <- split
fcluster(Z, t=76.08509216659989 + 1e-9, criterion="distance")  # [2 1 2 1]  <- merged
```

scipy treats a merge exactly AT the cut height as **included** (merged).
The Rust flat-cut reconstruction had used a strict `<`, excluding it.
Switching to `<=` reproduced scipy's partition exactly.

This is recorded here deliberately, not smoothed over: it is exactly the
"looks like a real algorithmic divergence until the actual boundary
semantics are checked" failure mode the source re-triage doc names as its
own methodology ("state the premise, then test it against the actual source
and callers, not against what a docstring claims") -- applied here to my
own port's flat-cut reconstruction, not just to the original scipy-vs-Rust
question.

---

## 5. Differential results (after the `<=` fix)

### 5.1 Real production-board nets (all 12 non-trivial `HighVoltage` nets)

| Net | Pads | Threshold (mm) | scipy clusters | kodama clusters | Partition match | Area diff (mm² / %board) |
|---|---:|---:|---:|---:|---|---:|
| w1_1 | 4 | 48.52 | 3 | 3 | MATCH | 0.00 / 0.0000% |
| +170V_BUS | 11 | 75.02 | 6 | 6 | MATCH | 0.00 / 0.0000% |
| +15V_LS | 3 | 52.77 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| DC_BUS_RTN | 12 | 33.21 | 5 | 5 | MATCH | 0.00 / 0.0000% |
| SW_NODE | 7 | 17.95 | 6 | 6 | MATCH | 0.00 / 0.0000% |
| tank.c_tank1-p2 | 4 | 121.94 | 3 | 3 | MATCH | 0.00 / 0.0000% |
| zcd | 4 | 137.92 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| power_in.ntc-no | 4 | 76.09 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| w1_2 | 3 | 67.81 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| discharge.k_dis1-nc | 4 | 76.02 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| discharge.k_dis2-nc | 4 | 32.96 | 2 | 2 | MATCH | 0.00 / 0.0000% |
| hb.power_loop.q_high-g | 3 | 126.79 | 2 | 2 | MATCH | 0.00 / 0.0000% |

**12/12 real nets: exact partition match, 0.00 mm² geometry divergence**
(board area 35,568.0 mm²). Plus `tank-out` and `a` (2 pads each): trivial
single-cluster match by construction.

### 5.2 Synthetic stress (board-realistic clustered data)

300 randomized trials (seed 42), 3-60 points each, 1-6 tight groups
scattered across a 150x230mm area (matching real component pitch: ~2mm
within a group, tens-to-hundreds of mm between groups), random thresholds
5-100mm: **0 mismatches.**

### 5.3 Symmetric / degenerate configurations

Six crafted cases designed to maximize tie-breaking ambiguity (perfect
square, 3x3 grid, two well-separated squares, regular hexagon, 5 collinear
points, exact-duplicate coincident points), each checked across 10
thresholds spanning the natural distance scales in each shape: **0
mismatches** (60 threshold x configuration combinations).

**Total: 12 real nets + 300 synthetic trials + 60 symmetric/degenerate
combinations = 0 mismatches, after the `<=` boundary fix.**

---

## 6. Performance (informal local A/B; R2's CI-gated `pr_perf_check.yml`
comparison requires an open PR, out of scope for this no-push spike)

In-process comparison (`temper_geometry.ward_cluster_labels_py` vs
`scipy.cluster.hierarchy.linkage`+`fcluster`+`pdist`, 2000 iterations each,
warmed up first), at point counts spanning the real board's net sizes
(3-12) and beyond:

| n points | scipy (ms/call) | kodama/Rust (ms/call) | ratio |
|---:|---:|---:|---:|
| 4 | 0.1918 | 0.0014 | 0.01x (kodama ~137x faster) |
| 12 | 0.1962 | 0.0030 | 0.02x (kodama ~65x faster) |
| 20 | 0.2027 | 0.0057 | 0.03x (kodama ~36x faster) |
| 50 | 0.2327 | 0.0295 | 0.13x (kodama ~8x faster) |
| 100 | 0.3322 | 0.0691 | 0.21x (kodama ~5x faster) |

At the real board's actual net sizes (3-12 pads), the Rust path is roughly
two orders of magnitude faster -- dominated by scipy's fixed per-call Python/
NumPy marshalling overhead (`pdist`, `linkage`, `fcluster` are each separate
Python-level calls with array construction), which the direct pyo3
`Vec<(f64,f64)> -> Vec<u32>` boundary avoids. This is not a marginal case
needing an R2 "no regression beyond noise" carve-out like `radius_pairs.rs`
or `ConvexHull`-area were flagged to expect -- it is an unambiguous win even
before CI's formal A/B runs.

---

## 7. What was ported

- **`packages/temper-geometry/src/hierarchical_clustering.rs`** (new):
  `ward_cluster_labels(points, threshold) -> Vec<usize>` (pure kernel,
  9 unit tests including the exact `<=` boundary regression reproducing the
  real `power_in.ntc-no` tie) + `ward_cluster_labels_py` (pyo3 boundary,
  `catch_unwind`-wrapped per this crate's convention) + its own
  `register()`, wired into `lib.rs`'s `#[pymodule]`.
- **`packages/temper-geometry/Cargo.toml`**: `kodama = "0.3"` added, with
  the wasm32/maintenance rationale recorded inline.
- **`zone_emission.py`**'s `_cluster_positions`: the
  `linkage`/`fcluster`/`pdist` block replaced with
  `_tg.ward_cluster_labels_py(positions, threshold)`. The NN-distance-gap
  threshold heuristic above it is byte-for-byte unchanged (it was never
  scipy). `zone_emission.py` no longer imports `scipy` at all.
- **R19 (pinned oracle)**:
  `packages/temper-placer/tests/router_v6/_zone_emission_clustering_py_oracle.py`
  -- verbatim `_cluster_positions` at base commit `c10523bb`, proven
  byte-identical by `test_oracle_is_verbatim_copy` (re-extracts via `git
  show` and compares character-for-character, not trusted by inspection).
- **Differential test**:
  `packages/temper-placer/tests/router_v6/test_zone_emission_clustering_rust_differential.py`
  -- 22 tests: the oracle-verbatim proof, the 3 existing synthetic cases
  from `test_zone_emission.py`, all 11 real-board nets with >=3 pads
  (parametrized), a 200-trial randomized-clustered-stress corpus, and the 6
  symmetric/degenerate configurations. All partition- and (for real-board
  nets) geometry-compared against the pinned oracle, run through the actual
  shipped `temper_geometry` extension (not a stand-in).
- **`packages/temper-geometry/VERIFICATION.md`**: the "Zone Pour Emission
  Geometry" section's `_cluster_positions` JUSTIFIED-KEEP note replaced with
  a MIGRATED note summarizing this document; the hull-buffer JUSTIFIED-KEEP
  (a separate, unrelated GEOS boundary) is untouched.
- **`test_zone_pour_geometry_rust_differential.py`** and
  **`_zone_pour_geometry_py_oracle.py`**: header comments updated to point
  at this migration instead of describing `_cluster_positions` as
  unmigrated (those two files' own scope -- `emit_zone_s_expr`,
  `_chamfer_path_points`, `_stitch_isolated_pads` -- is otherwise
  unaffected).

### Test results

- `test_zone_emission_clustering_rust_differential.py`: **22/22 passed**
  (against the real built `temper_geometry` extension, not a mock).
- `test_zone_emission.py`: **16/16 passed** (unchanged behavior for every
  existing test, including the two synthetic `TestDataInformedClustering`
  cases the module already had).
- `test_zone_pour_geometry_rust_differential.py`: **11/12 passed**, 1
  pre-existing unrelated failure
  (`test_tie_break_class_exists_direct_cKDTree_comparison`, a hardcoded-
  coordinate `cKDTree` internal-tie-break probe already documented as
  failing in `docs/evidence/2026-08-07-zone-emission-clustering-defect.md`
  Section 5, for the same reason, before this task's changes existed).
- `test_adapter.py`: **54 passed, 1 skipped** (pre-existing skip, unrelated).
- Rust: `cargo test --lib` in `temper-geometry`: **523/523 passed**
  (9 new `hierarchical_clustering` tests + all pre-existing).
- `cargo clippy --lib --features python -- -D warnings`: clean.
- `cargo build --target wasm32-unknown-unknown --no-default-features`:
  clean.

---

## 8. Port decision: PORT, with defence

**Port.** The premise the source re-triage doc asked this spike to verify
(count/geometry-only consumption, no membership dependency) held up under
direct citation. The stronger empirical bar the task itself set --
"does the difference matter to the consumer," checked with evidence, not
assumed -- is answered as strongly as this kind of question can be answered
short of a formal proof: **every real production-board net that invokes
clustering produces byte-identical partitions and 0.00 mm² geometry
divergence**, and the one place a genuine divergence *did* appear (Section
4) was traced to a bug in this port's own flat-cut reconstruction, fixed,
and locked in as a permanent regression test
(`test_exact_threshold_boundary_is_inclusive` in
`hierarchical_clustering.rs`, plus the real-`power_in.ntc-no`-derived case
in the same test) -- not evidence of an unresolved scipy/kodama difference.
Combined with a 60-140x performance win at the board's actual net sizes and
a directly-verified `wasm32-unknown-unknown` build, there is no remaining
axis (correctness, performance, or platform support) favoring KEEP.

**What would have changed this decision**: had the `<=` fix NOT closed the
4/12 mismatch (i.e. had the divergence persisted after fixing the boundary
condition, indicating a genuine kodama-Ward-vs-scipy-Ward algorithmic
difference rather than a flat-cut bug), the task's own framing would have
applied directly -- hold, and document which nets diverge and by how much,
since a silently different `HighVoltage`/switch-node zone geometry is
exactly the class of subtle defect the just-merged clustering fix
(`24c71979`) was written to eliminate, not reintroduce. That did not happen
here: the raw dissimilarity values were bit-exact from the first
comparison, and the only bug was in this port's own reconstruction, not in
`kodama` itself.

---

## 9. Confirmation: the zone-emission clustering-defect fix is intact

`packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py`'s
`_CONTINUITY_EXEMPT_CLASSES = frozenset({"GND", "ACMains"})` -- `HighVoltage`
remains un-exempted (verified: `grep -n "HighVoltage"
zone_emission.py`/`_zone_pour_stitch.py` shows only the historical comment
trail, no re-addition to the frozenset). `compute_zones_for_net`'s
`board_polygon` clip parameter and `_clip_to_board` function are unchanged
by this port -- this migration only touches the clustering *algorithm*
inside `_cluster_positions`, never the exemption logic or the board-outline
clip that R6 added. This port's own differential (Section 5) exercises
exactly the 14 `HighVoltage` nets that fix un-exempted, and confirms the
clustering step they now go through produces the same result regardless of
which backend computes it.

---

## 10. Scope note: what was NOT done

Per this task's explicit framing ("a spike, not necessarily a migration")
and the effort this port already required, the following were not attempted
and are recorded here rather than silently skipped:

- The full induction-proof + mutation-testing + wiring-proof ceremony
  `VERIFICATION.md`'s other Wave-4 entries carry (e.g. "Zone Pour Emission
  Geometry" above this section) was not reproduced for this kernel. The
  differential (12 real nets + 300 synthetic + 60 symmetric/degenerate,
  0 mismatches) is the verification evidence for this port; a follow-up can
  add the induction writeup and mutation-testing table to bring this section
  to full VERIFICATION.md ceremony parity if the project wants it.
- R2's actual CI-gated performance A/B (`pr_perf_check.yml`'s posted
  `## Performance Comparison`) did not run -- this task explicitly
  prohibits pushing / opening a PR. Section 6's local in-process timing is
  the honest substitute available in this context.
- The full `packages/temper-placer/tests/router_v6/` suite (4800+ items)
  was run in full (see this document's companion commit for the tally);
  only pre-existing, already-documented failures were observed.
