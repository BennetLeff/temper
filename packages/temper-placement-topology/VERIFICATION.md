# Topological Placement Compute (Rust) — Verification

Wave 4 Phase 4 migration of `packages/temper-placer/src/temper_placer/topological/`
(1,501 LOC, 6 files) from Python to Rust, under the R1 gate set of
`docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`.

Pinned oracle: `origin/main` **f57b52d51**, copied verbatim to
`packages/temper-placer/tests/topological/_*_py_oracle.py`.

---

## Crate choice

**A new crate, `temper-placement-topology`**, rather than
`packages/temper-rust-router-core/`.

`temper-rust-router-core` was the plausible alternative and was rejected on
three counts:

1. **It has no pyo3 surface.** It is `crate-type = ["rlib"]` with no pyo3
   dependency; its Python bridge is a *separate* crate, `temper-rust-router`
   (`cdylib`, module `temper_rust_router`). Landing here would mean editing two
   crates and exporting placement kernels from a module whose manifest
   describes it as "Router V6 topology stage".
2. **Different domain despite the shared word.** "Topological" in router-core
   means net ordering and SAT topology extraction. `topological/` here is
   *placement*: component adjacency, zone assignment, and (x, y) seeding. The
   two share no types and no call path.
3. **Build cost against a hard disk constraint.** router-core's default feature
   pulls `rustsat` + `rustsat-cadical`, i.e. a CaDiCaL C++ build. This crate has
   two dependencies (pyo3, temper-py-bridge) and builds in ~4 s.

The forbidden crates (`temper-geometry`, `temper-io-types`,
`temper-design-bundle`, `temper-quality-oracle`, `temper-thermal`) are
separately confirmed as contended — PRs #695 and #697 are live Phase-4 work in
`temper-geometry` and `temper-quality-oracle` respectively.

The crate follows the `temper-geometry` template: `cdylib` + `rlib`, pyo3 behind
a default-on `python` feature so the kernels stay unit-testable without a Python
interpreter (`cargo test --no-default-features`).

---

## Per-file survey

All six files were **genuine Python compute**; none was an existing shim, so no
part of this scope was already migrated by Waves 1–3.

| File | LOC | Verdict | What moved |
|---|---|---|---|
| `graph.py` | 327 | MIGRATE (partial) | Adjacency-cluster BFS and the separation-conflict scan. networkx `MultiDiGraph` **stays** as storage — `heuristics/topological_init.py` calls `graph.graph.has_edge`, and `.graph` is effectively public. Per-call adjacency queries (`get_neighbors`) stay Python: they are networkx lookups, and marshalling the edge list per call would be a pessimisation. |
| `propagation.py` | 199 | MIGRATE | Whole Floyd-Warshall closure (the O(n³) hot spot). `DistanceBound` stays a Python dataclass so `get_bound()` keeps returning the same mutable objects. |
| `initial_placement.py` | 394 | MIGRATE | Union-find clustering, circular arrangement, cluster placement. `PlacementError` message formatting stays Python (see "Message formatting" below). |
| `force_refinement.py` | 290 | MIGRATE | All four kernels and the iteration loop. |
| `zone_solver.py` | 220 | MIGRATE | Backtracking search. Candidate/MCV ordering stays Python — see "Iteration order". |
| `__init__.py` | 71 | UNCHANGED | Re-exports only. Public API is byte-identical; callers keep importing from `temper_placer.topological.*`. |

Consumer surface is narrow: `heuristics/topological_init.py` is the only
non-test importer. (`core/topology.py` defines an unrelated class of the same
name; the `skeleton.graph` hits in `router_v6/` are a different class again.)
`ZoneSolver` has no non-test caller at all — recorded, not acted on, since
retiring it is out of scope here.

---

## Bit-parity: what was measured, not assumed

Three properties of the Python were measured against CPython 3.12.13 /
NumPy 2.3.5 **before** writing any Rust, because in each case the obvious Rust
spelling is a different operation.

### 1. `np.linalg.norm` on a 2-vector — no FMA, *on this platform*

NumPy evaluates `sqrt(dot(v,v))`; for length-2 float64 that is `x*x + y*y`.
Compared against `math.sqrt(x*x + y*y)` over **200,000 randomised vectors**
spanning 1e-8…1e6 in magnitude, using `float.hex()`: **0 mismatches**. The Rust
uses the same unfused association and explicitly **not** `f64::mul_add` —
mutation **M3** confirms an FMA-contracted norm is caught.

**This one is platform-conditional, and that is a genuine limit of the port's
parity — not a property of the Rust.** `v.dot(v)` is a BLAS `ddot`. In the
OpenBLAS that ships inside NumPy's manylinux wheels, `ddot`'s microkernel is
selected from CPUID at load time (`gotoblas_dynamic_init`), the n<16 tail is a
scalar `dot += x[i]*y[i]` loop, and whether that loop is contracted into an FMA
depends on which kernel the CPU selected. So the *Python* answer is not fixed
by the source: it is fixed by the machine.

Measured 2026-08-04 (CPython 3.12.13 / NumPy 2.3.5, darwin/arm64 Accelerate),
over 200,000 random 2-vectors in this fixture's magnitude range:

| candidate reduction | mismatches vs `np.linalg.norm` |
| --- | --- |
| `sqrt(x*x + y*y)`      (what `norm2` does) | **0** (0.00%) |
| `sqrt(fma(y, y, x*x))` (a contracted ddot) | 16,260 (8.13%) |
| `sqrt(fma(x, x, y*y))` (the other association) | 16,312 (8.16%) |

So: **`norm2` is bit-identical to `np.linalg.norm` on every platform whose
2-element BLAS reduction is unfused, and on no other.** Where the reduction
contracts, the two differ by 1 ULP on ~8% of vectors. There is no in-repo
change that makes the Python side agree with itself across such machines — the
divergence is upstream of this crate.

`test_norm_contract_holds_on_this_platform` in the differential asserts the
precondition directly, over 20,000 vectors, so a non-conforming runner reports
*that* rather than an unexplained downstream disagreement. See "The #714 perf
A/B flake" below for what that disagreement looked like before the test existed.

### 2. CPython `sum()` is Neumaier-compensated

`place_components_in_zone` computes
`total_area = sum(w*h for ref in components)`. Since Python 3.12 `sum()` uses
Neumaier compensation, so it is neither `np.sum` (blocked pairwise) nor `+=`.
Measured divergence from naive accumulation at **n = 8**:

```
[0.1]*8   sum() = 0x1.999999999999ap-1     naive += = 0x1.9999999999999p-1
[0.1]*10 + [1e100, -1e100]   sum() = 1.0   naive += = 0.0
```

`numeric::neumaier_sum` transliterates CPython's `builtin_sum_impl` float path.

**This value gates control flow, not just a returned number** — it feeds
`total_area > zone_area * 0.8`, which raises `PlacementError`. A differential
that merely computed a different sum would prove nothing, so the suite carries
a constructed case where the compensated and naive sums land on *opposite
sides* of the threshold: 8 components of area 0.1 in a zone of area
`0.9999999999999999`, where the threshold is exactly the naive value. Correct
code raises; a naive accumulator returns positions. That is mutation **M1**.

### 3. Force accumulation is naive `+=`, and order-dependent

`forces[i] += force_i` is plain float64 accumulation — not compensated, not
pairwise. It is therefore **not associative**, so refined positions depend on
edge order. See "Iteration order" for why that order is preserved rather than
normalised.

### dtype width

Every array on this path is **float64**: `pos_array` from Python float tuples,
`np.zeros(2)`, `np.zeros((n,2))`, `zone_bounds`. No float32 anywhere, so the f64
port is width-correct. The differential's comparison key
(`tests/topological/_diffhelp.py`) carries `dtype.str` for numpy scalars and
arrays and a concrete `type` tag on every non-float leaf, so an `int`/`float`/
`bool` substitution cannot compare equal to what it replaced.

### NaN

`np.minimum`/`np.maximum` propagate NaN; `f64::min`/`f64::max` discard it; and
**CPython's `min`/`max` do neither** — they keep the incumbent unless the
candidate strictly compares, so NaN propagates from the *first* argument and is
discarded from the second. This module uses CPython `min`/`max` (in
`tighten_max`/`tighten_min` and in every coordinate clamp), so `numeric::py_min`
/ `py_max` reproduce that asymmetry exactly. Mutation **M2** (swap in
`f64::min`) is caught by a NaN-component-size case.

The `1e308` adjacency fixture drives a genuine overflow → NaN through the whole
refinement loop, and both arms agree bit-for-bit including the NaN.

---

## Iteration order — preserved, never imposed

Graph algorithms here iterate structures whose order is **incidental**, and in
one case that incidental order **decides the answer**. Following the #688
`yaml.safe_load` judgment, the port reproduces the order rather than sorting it,
because sorting would be a behaviour change no differential against a live
Python run could detect.

**Measured nondeterminism.** `ZoneSolver.solve()` iterates
`self._candidates[component]`, a `set` of zone names, and returns the first
success (`_is_consistent` is unconditionally `True`). String hashing is salted
per process, so on origin/main f57b52d51 the same 3 components over 5 zones
assign to different zones purely as a function of `PYTHONHASHSEED`:

```
seed=0 -> ZA    seed=1 -> ZD    seed=2 -> ZB    seed=3 -> ZD
seed=4 -> ZA    seed=5 -> ZD    seed=6 -> ZA    seed=7 -> ZB
```

`TopologicalGraph.from_pcl` has the same shape: it collects refs into a `set`
before inserting nodes, so networkx's node/edge order — and hence the *list*
order of `find_separation_conflicts` and the edge order feeding force
accumulation — is seed-dependent too.

**How parity is achieved anyway.** Every order-sensitive input is an *ordered
argument* to the Rust kernel, and nothing in the crate sorts a caller-supplied
sequence. The Python shim passes its own live iteration order through:

- `zone_solver` passes `list(self._candidates[c])` per component, in this
  process's set order, plus the MCV `sorted()` result (kept in Python because
  `sorted` is stable and its tie order is observable).
- `graph` / `force_refinement` / `initial_placement` pass
  `list(graph.edges(data=True))` in networkx order.

So the *composed* behaviour is bit-identical to the pre-migration code on every
run, hash seed included, without the port either inheriting nondeterminism into
Rust or silently "fixing" it. Mutation **M14** (sorting candidates inside the
kernel) is caught.

**Which results are order-invariant, proven rather than assumed.** Metamorphic
relation MR2 shows cluster decomposition and propagated bounds are invariant
under edge permutation; MR6 is a *witness in the opposite direction*, asserting
that force refinement genuinely is order-sensitive, so MR2's silence about it is
a measured boundary rather than an untested assumption.

---

## Message formatting stays in Python

`find_separation_conflicts` interpolates distances into
`f"adjacent({adj_max}) < separated({sep_min})"`, and `PlacementError` uses
`{:.1f}`. Rust's `{}` does not reproduce `repr(float)` (`5.0` vs `5`, `1e+308`
vs a 309-digit expansion). So the conflict kernel returns *index pairs* into the
caller's own edge list and the placement kernel returns its operands, letting
Python render the text from its own float objects. Parity here is structural,
not approximated.

---

## Proof by induction

### Force refinement

**Claim.** For every iteration count `k`, the Rust refinement produces the same
float64 position array as the pinned NumPy oracle.

**Base case (k = 0).** The loop body never executes; both return a copy of the
input array unchanged. Asserted by
`test_zero_iterations_is_the_identity` (Rust) and
`test_apply_force_refinement_identical[.../0/...]` (differential).

**Inductive step.** Assume both arms hold identical position arrays after `k`
iterations. Within iteration `k+1`:

1. **Force array init.** Both start from an all-zero `(n,2)` float64 buffer.
2. **Per-edge forces.** For each edge in *the same caller-supplied order*, both
   compute `delta = pos_b − pos_a` (exact same subtraction on identical
   inputs), `distance = sqrt(dx*dx + dy*dy)` (shown bit-identical to
   `np.linalg.norm` over 200k samples, and unfused in both), the same `< 1e-6`
   degeneracy branch with the same constants, the same `direction = delta /
   distance`, and the same `magnitude`. Identical inputs through identical
   operations in identical order give identical results.
3. **Accumulation.** Both add into the buffer with naive `+=`, in the same edge
   order, so the same non-associative rounding sequence occurs.
4. **Boundary term.** Added per index `0..n` in ascending order in both, using
   strict `<`/`>` comparisons (so NaN contributes zero identically).
5. **Update.** Both compute `forces * lr` first and then add — never fused.

Every step maps identical inputs to identical outputs, so the arrays agree
after `k+1`. By induction they agree for all `k`. Mutations **M4** (spring
constant), **M5** (degeneracy floor), **M6** (separation boundary), **M7**
(fusing the update) and **M8** (boundary comparison strictness) each break one
of these steps and are each caught.

### Constraint propagation

**Claim.** For every iteration budget `m`, the Rust closure produces the same
bounds matrix and the same feasibility verdict as the oracle.

**Base case (m = 0).** Neither enters the loop; both return the seeded matrix.
Seeding applies `tighten_max`/`tighten_min` over the same edges, and both are
`min`/`max` folds — commutative and idempotent, hence seeding is
order-insensitive and identical. `feasible` is still `true`, since it is only
ever cleared inside the loop. Asserted by
`zero_iterations_leaves_the_seeded_matrix_untouched`.

**Inductive step.** Assume identical matrices after `m` sweeps. Sweep `m+1`
visits `(k, i, j)` in the same nesting and skips on the same predicate
(`i == j || i == k || j == k`). For each surviving triple both compute
`new_max = max(i,k) + max(k,j)` and `new_min = min(i,k) − max(k,j)` from
identical operands, apply the same strict-improvement test, and tighten through
the same CPython-semantics `min`/`max`. `changed` and `feasible` are therefore
set identically, so both take the same early-exit decision. Hence the matrices
agree after `m+1`, and by induction for all `m`.

**Termination.** Every update strictly decreases a `max` or strictly increases a
`min`, and neither is unbounded within a sweep; when no update fires, `changed`
is false and both break. The `max_iterations` cap bounds the worst case in both.

**A quirk pinned rather than fixed.** `feasible` is only cleared *inside* the
triple loop, whose predicate needs three distinct indices. With `n = 2` no
triple qualifies, so `propagate()` returns `True` even when the single pair's
bounds are contradictory — while `get_infeasible_pairs()` still lists it.
Confirmed on origin/main f57b52d51 (`propagate() -> True`,
`get_infeasible_pairs() -> [('A','B',10.0,5.0)]`). Reproduced deliberately and
pinned by `a_two_node_conflict_is_not_reported_by_the_feasibility_flag`, so the
port cannot silently "fix" an unrequested behaviour.

**A directional asymmetry pinned rather than smoothed.** The *max* matrix stays
symmetric, but the *min* matrix does not: `min(i,j) ≥ min(i,k) − max(k,j)` reads
`min` from the row and `max` from the column, so `(i,j)` and `(j,i)` consult
different quantities. With A–B adjacent(1.0) and A–C separated(2.0):
`min(C,B) = 1.0` while `min(B,C) = 0.0`. The PBT asserts max-symmetry only, and
`test_min_bound_propagation_is_directional` pins the asymmetry as a fixture.

### Union-find clustering

**Claim.** The cluster list is a function of (component order, adjacency edge
*set*) alone — independent of edge order and of union tie-breaking.

**Proof.** Union-find computes connected components regardless of the union
heuristic; rank only affects tree depth. The returned list groups by
`find(c)` while scanning `components` in order, so its outer order is the order
of first appearance of each *class*, which depends on class membership and the
scan order, not on which element became the representative. Hence both edge
permutation (MR2) and rank inversion leave the output unchanged. Verified
exhaustively — see "Equivalent mutants" below.

---

## Gate results

| Gate | Result |
|---|---|
| R1a bit-identical differential | **478 assertions pass** vs the verbatim pinned oracles, all via `float.hex()`, no tolerance. Includes an explicit anti-vacuity guard asserting each live module resolves through the extension, so the suite cannot degrade into Python-vs-Python. |
| R1b performance A/B | Registered in `benchmarks/perf_ab.py`. `constraint_propagation` ratio **0.0624 (16.0× faster)**; `force_refinement` ratio **0.0050 (199× faster)**. Both arms assert parity inside the harness. First appearance ⇒ `NEW_BENCHMARK` (#696); the baseline row is captured on CI, per the harness's platform-bias note. |
| R1c ≥5 properties per module | **27 properties**: graph 5, propagation 5, force 6, initial placement 6, zone solver 5, plus a G4 anti-vacuity test asserting all 18 tagged interesting branches were actually reached. |
| R1d ≥3 metamorphic relations | **6**: node relabelling (×2), edge-order permutation (×2), translation equivariance, x-reflection equivariance, power-of-two distance scaling, plus the MR6 order-sensitivity witness and the MR4 degeneracy-exception fixture. |
| R1e induction proof | Above — force refinement and propagation are both iterative; union-find carries a structural proof. |
| R1f TDD, RED demonstrated | Commit 1 lands oracles + all three suites; all three fail to collect (`ModuleNotFoundError: temper_placement_topology`). Commit 2 turns them green. |
| R1g Rust practice | `borrow over clone` throughout (kernels take `&[T]`; the graph kernels borrow `&str` out of the caller's buffers). `unwrap_used`/`expect_used` denied at the manifest level. `catch_unwind` at every pyo3 entry point via `temper-py-bridge`. Bounds are validated before indexing, returning `PyIndexError`/`PyValueError` rather than panicking. |
| R1h state | **N/A — not physics-gated.** These modules compute component adjacency, zone membership and (x, y) seeds; no thermal, creepage, isolation or other physical quantity is derived. The R24 discipline applies to the DRC/thermal surfaces, not here. |

`cargo test --no-default-features`: 47 pass. `cargo clippy --all-features
--all-targets -- -D warnings`: clean.

---

## Anti-vacuity: mutation testing

17 mutants, each applied to the Rust source, rebuilt, and run against
`cargo test` **and** the three pytest suites. **15 killed; 2 proven
equivalent.**

| # | Mutation | Result | Caught by |
|---|---|---|---|
| M1 | Neumaier `sum()` → naive accumulation | KILLED | `test_place_in_zone_neumaier_and_naive_straddle_the_packing_threshold` |
| M2 | CPython `min` → `f64::min` (NaN discarded) | KILLED | `test_place_components_in_zone_with_nan_component_sizes` |
| M3 | Unfused norm → `mul_add` (FMA) | KILLED | `test_compute_adjacency_force_identical` |
| M4 | Spring constant `0.5` → `0.500000001` | KILLED | `test_apply_force_refinement_identical[0.1-2-clique4]` |
| M5 | Degeneracy floor `1e-6` → `1e-9` | KILLED | `test_compute_adjacency_force_identical[at_epsilon]` |
| M6 | Separation `>=` → `>` | KILLED | `test_compute_separation_force_identical[10.0-simple]` |
| M7 | Position update → fused multiply-add | KILLED | `test_apply_force_refinement_identical[0.1-1-clique4]` |
| M8 | Boundary `>` → `>=` | KILLED | `boundary_tests_are_strict_so_the_lower_branch_survives_on_a_reversed_box` (Rust) |
| M9 | Floyd-Warshall drops the `i == k` guard | KILLED | `test_propagation_identical[1-conflict]` |
| M10 | `tighten_max` stops taking the minimum | KILLED | `TestPropagationInvariants::test_propagation_only_tightens` |
| M11 | Cluster radius `sin(π/n)` → `sin(π/(n+1))` | KILLED | `test_place_cluster_identical[1-cycle4]` |
| M12 | Packing limit 80% → 81% | KILLED | `test_place_in_zone_packing_limit_is_exactly_eighty_percent` |
| M13 | Clamp order `max(min(..))` → `min(max(..))` | KILLED | `test_place_components_in_zone_with_nan_component_sizes` |
| M14 | Zone backtracking sorts the candidate order | KILLED | `zone::tests::candidate_order_is_never_normalised` (Rust) |
| M15 | Conflict test `<` → `<=` | KILLED | `graph::tests::equal_bounds_are_satisfiable_and_not_a_conflict` (Rust) |
| M16 | Union-by-rank comparison inverted | **EQUIVALENT** | see below |
| M17 | BFS visited-set → linear scan over `cluster` | **EQUIVALENT** | see below |

**Four mutants initially survived and the gap was closed by adding
discriminating cases, not by weakening the claim.** M1 and M12 survived because
`total_area` is observable *only* through a threshold branch — both were killed
by constructing inputs that straddle the threshold. M2 and M13 survived because
`Zone` validates its bounds (`Rect` requires `x_max > x_min`), making NaN and
inverted boxes unreachable through that type; they were killed by routing
through `place_cluster`/`place_components_in_zone`, which do **not** validate
component sizes. M15 was initially killed only by a lucky Hypothesis draw and
was made deterministic with an exactly-equal-bounds fixture. M14 was killed once
the harness was corrected to run `cargo test` as well as pytest — the gate set
is both, and scoring against only one understated it.

**M16 and M17 are equivalent mutants, demonstrated rather than asserted.** Both
were applied, rebuilt, and run over an exhaustive domain — every graph of
n ≤ 5 with every adjacency subset up to 4 edges, dumping `identify_clusters` and
`adjacency_cluster` for every seed: **41,388 records, byte-identical to the
clean build** (sha256 `28b35d41…`). M16 changes only union-find tree depth (the
partition, and hence the output, is invariant under the union heuristic — see
the structural proof above); M17 swaps an O(1) membership test for an O(n) one
over a container holding exactly the same elements. Neither is observable
through any public API, so neither is a test gap.

---

## The #714 perf A/B flake — and what it actually proved

`benchmarks/perf_ab.py::bench_topological_force_refinement` asserts the two arms
agree bit-for-bit before timing them. On PR #714 it **failed** (run
`30950000723`, commit `914697ff6`) and then **passed** (run `30954298616`,
commit `5c9fb4c48`) with no fix. The two commits differ in nothing the benchmark
executes — `git diff` over `benchmarks/`, `packages/temper-placer/src/`,
`packages/temper-placement-topology/`, `packages/temper-placer/tests/topological/`,
`uv.lock` and `pyproject.toml` returns only two comment-only edits in unrelated
modules. Same code, opposite verdicts.

**It was not `PYTHONHASHSEED`.** That was the first hypothesis, and it is wrong
for this benchmark: the fixture is built from a *list* of refs in list order, so
the graph's edge order is a function of `n` alone. Measured over **32 explicit
seeds × 2 harnesses × 2 reduction kernels = 128 runs**: the edge-list digest and
the refined-position digest are identical in all 128, and no cell's verdict moves
with the seed. (`ZoneSolver.solve()` *is* seed-dependent — it iterates a `set` of
candidates — but force refinement is not, and the benchmark does not call it.)

**It was the 2-vector reduction of §1**, amplified. Two facts compose:

1. The benchmark's fixture is a bounded but **non-converging** force
   simulation. Its per-iteration step is still O(1) at iteration 400, and a
   **single ULP** perturbation of one input coordinate grows to **1.2e-1 mm**
   by iteration 120:

   | iterations | components differing | max \|Δ\| |
   | --- | --- | --- |
   | 1 | 1/26 | 1.8e-15 |
   | 8 | 20/26 | 1.2e-12 |
   | 17 | 26/26 | 4.0e-11 |
   | 40 | 26/26 | 9.6e-03 |
   | 120 | 26/26 | 1.2e-01 |

2. Per §1, a contracted `ddot` changes ~8% of distances by 1 ULP. The fixture
   has 73 edges, so on a non-conforming runner *some* edge diverges on the very
   first iteration — reproduced by substituting `sqrt(fma(y,y,x*x))` for
   `np.linalg.norm` in the oracle arm: parity fails at **iteration 1**
   (Δ 4.4e-16) and at 120 (Δ 8.2e-3).

Fewer iterations would therefore not have helped, and neither would a smaller
fixture: the differential's own `adjacent_pair` (2 components) also breaks at 8
iterations under the same substitution. **Every bit-exact force-refinement
comparison in this repo is conditional on the runner's BLAS reduction.** That is
recorded here rather than papered over, and it is asserted directly by
`test_norm_contract_holds_on_this_platform`.

What changed in response:

* **The perf A/B pins the primitive, not the result.** For the duration of its
  parity check only — never around the timed runs, which feed a ratio measured
  against a committed baseline — `np.linalg.norm` on a 2-vector is bound to the
  association §1 documents and `norm2` implements. This is the same move the
  graph shim already makes for edge order: make the shared input explicit
  instead of letting the environment pick it. Nothing is sorted, no tolerance is
  introduced, no iteration count is reduced, and the equality assertion itself
  is unchanged. On any platform CI is green on the binding is provably a no-op,
  because the contract test asserts exactly that.
* **The benchmark and the differential now share one fixture module**
  (`tests/topological/_topo_bench_fixture.py`). The gap that let this reach a
  perf job at all was that the differential parametrised force refinement over
  `iterations ∈ [0,1,2,8,17,100]` on graphs of ≤ 4 components while the
  benchmark ran `(120, 0.05)` on 26 — so no behavioral gate ever executed the
  benchmark's parameters. `test_apply_force_refinement_identical_at_benchmark_parameters`
  now does, on the same fixture object, and
  `test_bench_fixture_edge_order_does_not_move_with_the_hash_seed` pins the
  order property the exactness depends on.

Evidence, 32 seeds per cell (`bench_topological_force_refinement` run end to
end in a fresh interpreter per seed; "pre-fix" is a verbatim `git show HEAD:`
copy of the harness):

| harness | ddot reduction | parity |
| --- | --- | --- |
| pre-fix | unfused | 32 pass / 0 fail |
| pre-fix | FMA-contracted | 0 pass / **32 fail** |
| post-fix | unfused | 32 pass / 0 fail |
| post-fix | FMA-contracted | **32 pass** / 0 fail |

The two new differential cases are anti-vacuous against the same perturbation:
under a contracted reduction `test_norm_contract_holds_on_this_platform` and
`test_apply_force_refinement_identical_at_benchmark_parameters` both fail (the
former naming the cause), while
`test_bench_fixture_edge_order_does_not_move_with_the_hash_seed` still passes —
it is about order, which the reduction does not touch.

---

## Deviations from the Python

None in behaviour. Two structural differences, both to *preserve* behaviour:

1. `separation_conflicts` and `place_components_in_zone` return operands rather
   than formatted strings, so CPython renders all float text (see "Message
   formatting").
2. `ZoneSolver._backtrack` / `_is_consistent` were removed from the Python
   (the search now lives in `zone.rs`). Both were private and had no caller
   outside the module; `_is_consistent` survives as a named seam in Rust so a
   future real consistency check is a local change.
