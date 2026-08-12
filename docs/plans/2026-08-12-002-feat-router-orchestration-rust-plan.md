---
title: Router Orchestration to Rust — scoping verdict and landing sequence
type: feat
date: 2026-08-12
topic: router-orchestration-rust
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Router Orchestration to Rust — Scoping Verdict and Landing Sequence

## Goal Capsule

**Verdict, stated first.** Net-batching **does not survive in its present
form, and its stated reason is already false.** `net_batching.py`'s module
docstring justifies the whole mechanism by a monolithic SAT model that
"OOMs at 5.43GB under an 8GB `ulimit -v` cap before ever reaching Rust's
`encode_to_cnf`." That 5.43GB is **not** in `encode_to_cnf`, **not** in
CaDiCaL, and **not** intrinsic to the problem. MEASURED this task: it is
**326.7 bytes per SAT variable of CPython heap object**, because
`ConstraintModel` stores `Vec<Py<PyAny>>` — Rust holding 22.5M *Python*
objects (`packages/temper-design-bundle/src/model_builder.rs:486`) — which
`solve_topology_rust` then reads back attribute-by-attribute into a Rust
enum (`packages/temper-rust-router/src/types_py_bridge.rs:61-67`). The
model is built in Rust and consumed in Rust with a full
**Rust→Python→Rust round trip in between**, and there is no fast path
because `temper-rust-router` does not depend on `temper-design-bundle`;
their only shared currency is Python objects. A packed, index-based Rust
representation of the identical model measures **8.9 bytes/variable —
0.19GB against 7.35GB, a 38× reduction** with no algorithmic change
(§"The memory measurement"). So the ~610 LOC of `multiprocessing`, pickle,
`_project_skeletons`, `_DesignRulesStub`, `_write_shared_context`,
`_watch_peak_rss_kb` and the 900s timeout exist to work around a data
representation, not a problem size. **The batch *loop* may still be worth
keeping; the subprocess *isolation* is not, and becomes a `for` loop.**

**Second finding, and it is the more consequential one.** At the production
batch size the Stage-3 SAT model **encodes no capacity constraint at all.**
`encoding.rs:148` encodes AtMostK only when `max_nets < len(terms)`, and
`encode_at_most_k` early-returns when `k >= n` (`encoding.rs:28-30`).
DERIVED-exact from the measured CNF (§"The capacity finding"): the mean
capacity bound is **K ≈ 17**, from two independent equations that agree.
`DEFAULT_BATCH_SIZE = 10` means `len(terms) ≤ 10 < 17`, so the guard fails
and **not one `CapacityConstraint` is encoded in a batch**. Capacity — the
docstring's "one constraint class `constraint_model.py` actually encodes as
a cross-net SAT constraint" — is in production enforced *entirely* by the
`_shrink_channel_widths` / `_consume_capacity` bookkeeping between batches,
which is greedy sequential allocation, and which **already lives in Rust**
(`temper_rust_router_core::net_batching`, landed as Phase E E5). This
explains the standing "0 conflicts, 0 decisions" result. It also means the
batched and monolithic paths are **not two ways of computing the same
board** — they are different algorithms, and the committed baseline board
was produced by the batched one.

**How much of the 33,143 LOC is really portable: 82.0%, and *none* of it is
CPython-bound.** MEASURED: `router_v6/` contains **zero** imports of
`ortools`, `pcbnew`, `networkx`, `pydantic`, or any C-extension whose
semantics are CPython-specific — every mention is a comment. Bucket (b) is
**0 LOC**. The four third-party libraries present (numpy 24 modules,
shapely 15, scipy 1 site, kiutils 1 site) are incidental, and in-repo Rust
replacements already exist and are already wired elsewhere for the load-
bearing cases. The honest brake on this port is **not** language binding —
it is volume, the differential-oracle discipline in
[`../migration-pipeline.md`](../migration-pipeline.md), and one genuine
bit-exactness hazard (GEOS Voronoi in `channel_skeleton.py`, which names
every SAT variable and therefore determines the board).

**The first landable step is U1: give `ConstraintModel` a Rust-native
representation and a Rust→Rust path to `encode_to_cnf`, changing no
algorithm and no output.** It is independently verifiable by the strongest
test available — byte-identical `temper_routed.kicad_pcb` against the
verified-deterministic baseline — it deletes the *reason* net-batching
exists before touching net-batching, and it is the prerequisite that makes
every later step's "does the monolith fit?" question answerable rather than
assumed. Everything else in this plan is sequenced behind it.

## Product Contract

### Summary

This plan does three things, in order, and deliberately does **not** attempt
a 33k-LOC port:

1. **Remove the artificial memory ceiling** (U1–U2). Fix the model
   representation and the Rust→Python→Rust round trip. Measure what the
   unbatched model actually costs once the round trip is gone. This
   converts "does net-batching survive?" from an argument into a
   measurement.
2. **Resolve net-batching on that evidence** (U3–U5). Replace the
   subprocess driver with an in-process Rust loop; decide the batch loop's
   fate against the measured monolith; and — separately and explicitly —
   settle the capacity-semantics question the batching finding exposes.
3. **Drain the cheap surface that is already proven** (U6–U8): collapse the
   20 already-thin wrappers, delete the 1,590 LOC that has no production
   caller or exists only as a Python workaround, and repair the scipy
   regression.

The A* core, the copper-generation trio, and `channel_skeleton.py` are
scoped **out** and named as separate projects (§Scope Boundaries). Saying
so plainly is part of the deliverable: those are ~9,000 LOC of real
algorithm with no oracle and no Rust counterpart, and folding them into
this plan would make it undeliverable.

### The memory measurement

The question the task poses — *is the 5.43GB in Python-side construction,
in FFI marshalling, or in `encode_to_cnf`?* — has a fourth answer that is
none of those three, and it is the reason the mechanism was misdiagnosed:
**the memory is in the model's data representation, which is CPython
objects held inside a Rust struct.**

Reproduce with
[`../evidence/2026-08-12-router-model-memory-probe.py`](../evidence/2026-08-12-router-model-memory-probe.py)
(Python, current post-E1 types) and
[`../evidence/2026-08-12-router-model-memory-counterfactual.rs`](../evidence/2026-08-12-router-model-memory-counterfactual.rs)
(Rust, zero dependencies). Both measure real `VmRSS`, not `sys.getsizeof`.

| representation | bytes/var | full 22,493,900-var model | MEASURED/DERIVED |
|---|---:|---:|---|
| **(A) today** — `ConstraintModel{variables: Vec<Py<PyAny>>}`, each var a pyclass with 3 Rust `String`s | **326.7** | **7.35 GB** | MEASURED |
| (A') one `.variables` access — a *fresh* `PyList` per read, and `_batch_worker_entry` reads it 3× | +11.8 | +0.26 GB per read | MEASURED |
| **(B)** `temper_rust_router_core::types::InternalVariable` (the enum the bridge converts *to*) | **224.0** | **4.69 GB** | MEASURED |
| **(C)** packed `{net_idx: u32, edge_idx: u32}` + edge-id strings interned once (204,490, not 22.5M) | **8.9** | **0.19 GB** | MEASURED |

Three facts follow, all structural:

- **The 5.43GB figure is a floor, not the model's cost.** It was the RSS at
  which `MemoryError` fired under an 8GB `ulimit -v` — construction died
  partway. The completed model at today's 204,490-edge skeleton is 7.35 GB
  for the variables alone.
- **E1 moved the builder to Rust but left the representation in CPython.**
  `ConstraintModel` (`model_builder.rs:483-491`) stores `Vec<Py<PyAny>>`
  *and* a `HashMap<(i64, String), Py<PyAny>>` — so each variable's
  `channel_id` string is stored **twice**, once in the object and once as
  the map key. `variables`/`constraints`/`terms` are getters that
  **rebuild a fresh Python list on every access**
  (`model_builder.rs:543-564`, `:330-342`).
- **There is no Rust→Rust shortcut and cannot be one today.**
  `solve_topology_rust` takes `&Bound<'_, PyList>`
  (`packages/temper-rust-router/src/lib.rs:156-163`) and reconstructs
  `InternalConstraintModel` by duck-typed `getattr` per object
  (`types_py_bridge.rs:11-99`). `packages/temper-rust-router/Cargo.toml`
  has no `temper-design-bundle` dependency; they are two separate
  `cdylib`s that can only exchange Python objects.

**Inconvenient counterweight, reported in full.** Fixing the
representation does **not** by itself make the monolith fit, and this plan
does not claim it does. The CNF *downstream* is real Rust memory: the
2026-07-27 baseline measured **42,145,777 vars / 78,107,180 clauses** from a
3.876M-variable model on a **20,734-edge** skeleton. Today's skeleton is
**204,490 edges** — 9.9× larger. `CnfFormula` stores
`clauses: Vec<Vec<i32>>` (78M+ *separate heap allocations*) and
`var_map: Vec<SatVariable>` (two `String`s each, `types.rs:74-77`), both of
which are themselves representation problems of the same shape and both of
which are addressable (CSR-flatten the clauses, drop or intern the names).
Whether the monolith fits after *all* of that is exactly what U2 exists to
measure, and this plan deliberately does not pre-judge it. If it does not
fit, the batch loop stays — but as a Rust loop, and for a stated reason
that is measured rather than inherited.

### The capacity finding

DERIVED-exact from the 2026-07-27 measurement (3,876,012 raw vars →
42,145,777 CNF vars / 78,107,180 clauses over 20,734 `CapacityConstraint`s):

```
aux vars              = 42,145,777 − 3,876,012 = 38,269,765
aux per constraint    = 38,269,765 / 20,734    = 1,845.7
clauses per constraint= 78,107,180 / 20,734    = 3,767.1

Sinz: aux = (n−1)·K,  clauses ≈ K·(2n−1)
  n = 108 nets →  K = 1845.7/107 = 17.2   and   K = 3767.1/215 = 17.5
```

Two independent equations agree at **K ≈ 17**. The encoder's guard is
`max_nets < var_indices.len()` (`encoding.rs:148`), with a second
early-return at `k >= n` (`encoding.rs:28-30`). Because
`ModelBuilder` is constructed with only the batch's nets
(`net_batching.py:470-478`), `var_indices.len() ≤ batch_size = 10`:

| path | terms per capacity constraint | K | `K < len(terms)`? | encoded? |
|---|---:|---:|---|---|
| monolithic | 110 | ~17 | 17 < 110 ✓ | **yes** |
| batched, `B = 10` | ≤ 10 | ~17 | 17 < 10 ✗ | **no** |

Consequences, stated plainly because they change what "port net-batching"
even means:

- The production Stage-3 SAT solve contains **no cardinality constraint**.
  What remains are `DiffPair` equivalences and `LayerRestriction` units —
  both unconditional, both trivially satisfiable. This is why every
  completed solve has reported **0 conflicts, 0 decisions**, and why the
  recorded run shows *12 batches, 12 solved at batch level, 0 crashed*.
- Capacity is therefore enforced **only** by `_shrink_channel_widths` /
  `_consume_capacity` — greedy sequential allocation across batches. That
  logic is already Rust (`temper_rust_router_core/src/net_batching.rs`,
  574 LOC, landed E5). **The one genuine cross-net constraint has already
  been ported; what is left in Python around it is the process machinery.**
- Caveat, held honestly: `_shrink_channel_widths` reduces `capacity` as
  batches commit, so K falls monotonically and a congested edge can drop
  below 10 in a late batch. The claim is "no capacity constraint is encoded
  for an edge whose K is still ≥ 10", not "never, for any edge, ever." U5
  measures the actual per-batch encoded-constraint count rather than
  arguing about it.

### The four-way classification

108 files / **33,143 LOC** (`wc -l`, exact). Built on the repo's existing
R1 ledger in [`../wave4-verdicts.yaml`](../wave4-verdicts.yaml) (which
already carries a verdict for 90 of the 108 files / 23,262 LOC) plus
assignment of the 20 untriaged files, most of which post-date it.

| bucket | files | LOC | share |
|---|---:|---:|---:|
| **(a) mechanically portable** | 73 | **27,163** | 82.0% |
| **(b) genuinely CPython-bound** | **0** | **0** | **0.0%** |
| **(c) deletable** | 6 | **1,590** | 4.8% |
| **(d) legitimately Python** | 29 | **4,390** | 13.2% |
| total | 108 | 33,143 | 100% |

**(b) is empty, and that is a measured claim, not an optimistic one.**
`grep` over all 108 files: `networkx` → comments only (the migration to
`SkeletonGraph`/`temper_geometry.min_cut_py` completed); `ortools`,
`cp_model` → comments only (the CP-SAT boundary is in
`placer/cp_sat/`, **not** in `router_v6/`); `pcbnew` → one comment;
`pydantic`, `matplotlib`, `click`, `typer` → absent. What remains:

| library | modules | LOC | essential or incidental? |
|---|---:|---:|---|
| numpy | 24 | ~10,368 | **Incidental.** Dense-array arithmetic over `f64`/`i8` grids. No numpy-specific semantics (no masked arrays, no object dtype, no broadcasting subtleties relied on). Direct `Vec`/`ndarray` translation. |
| shapely (GEOS) | 15 | ~7,595 | **Incidental except one.** Polygon buffer/intersection/contains — `temper_geometry` already replaces this class of call in 34 of the 108 modules. **The exception is `channel_skeleton.py`'s GEOS Voronoi medial axis**, which is *bit-exactness*-bound, not CPython-bound (see below). |
| scipy | 1 site | 587 | **Incidental, and a regression.** `_corridor_backbone.py:549` `from scipy.ndimage import label`, introduced **today** (`d8e6efd48`, #1052). `temper_geometry.connected_components_8_transform` already exists and already replaced exactly this call in `routability_check.py`/`_astar_heuristics.py` (`1efa1cb33`, `3ba16bfbd`). scipy was a **closed** migration; this reopened it. |
| kiutils | 1 site | 665 | **Incidental.** `constraints_design_rules.py:535`. `temper_design_bundle_python.parse_kicad_pcb` already parses this format. |
| multiprocessing | 1 | 1,224 | **Not a binding — the workaround.** Counted in (c), not (b). |

**(c) deletable — 1,590 LOC, itemised, nothing padded:**

| item | LOC | why |
|---|---:|---|
| `net_batching.py` subprocess driver (`:493-967` + its docstring `:47-122` + crash plumbing in the loop) | 610 | Exists solely because Python cannot control allocation and cannot catch a Rust `abort()`. In Rust: a `for` loop. |
| `routability_check.py` | 546 | **Zero production inbound references** (42 test-only, all coverage-paydown). Rust differential already exists. |
| `congestion_analysis.py` | 144 | **Zero production inbound references.** Mirrored by `temper-geometry/src/congestion_analysis.rs`. |
| `test_boards.py` | 162 | Test fixtures shipped inside `src/`. |
| `placement_audit.py` + `placement_legalization.py` | 128 | Vestigial seam: `legalize()` is a documented no-op; its only caller is the other file. |

**(d) legitimately Python — 4,390 LOC**: reporting and audit
(`diagnostics`, `manufacturing_report`, `_routing_reports`,
`topology_copper_audit`, `pad_connectivity_audit`, `verifier`,
`astar_monitor`, `benchmark`), pure type/dataclass carriers
(`stage0_data` — fan-in 43, the highest in the package —
`routing_results`, `_pipeline_types`, `_adapter_types`), and stage/facade
glue. A port buys nothing here until the top-level driver is Rust, and
`stage0_data.py`/`routing_results.py` should move **only** with the driver
that consumes them.

**Already-thin wrappers — 20 files / 3,979 LOC — the cheapest wins, called
out separately as instructed.** These are subset of (a) and are near-pure
delegation into one of the **seven** pyo3 crates the router imports
(`temper_geometry` 34 modules / 89 sites, `temper_drc_rs` 9/33,
`temper_orchestration` 8/19, `temper_rust_router` 8/20,
`temper_design_bundle_python` 4/11, `temper_io_types` 2/9,
`temper_quality_oracle` 2/9):

`topology_extraction.py` (53, zero `def`s — three pyclass re-exports, the
purest shim in the tree) · `metrics/slop_linter.py` (66, 5 defs → 5
delegations) · `diff_pair_inference.py` (69) · `corridor_erosion.py` (73) ·
`_strip_copper.py` (83) · `terminal_extraction.py` (91) ·
`terminal_tree.py` (94) · `path_simplify.py` (93) · `grid_converter.py`
(116) · `stage_ledger.py` (138, self-described "delegation shim") ·
`escape_via_generator.py` (149) · `net_classification.py` (188) ·
`constraints_geometry.py` (214, 12 delegation sites) ·
`quality/via_count.py` (291) · `net_ordering.py` (299) ·
`astar_core_rust.py` (312, dispatch-only) · `channel_mapping.py` (315) ·
`constraint_model.py` (445) · `clearance_check.py` (**837 — the largest,
and the whole check is a single call at `clearance_check.py:284`**) ·
`corridor.py` (53).

Phase B of plan
[`2026-08-09-001`](2026-08-09-001-feat-rust-orchestration-engine-plan.md)
scoped exactly this collapse (U11–U13) and **never ran as its own batch**.
It is the highest ratio of removed-LOC to risk anywhere in this document.

### What would change the board — flagged deliberately

The correctness bar is a byte-identical `temper_routed.kicad_pcb` against
the baseline verified in
`docs/evidence/2026-08-12-board-recipe-reproducibility.md` (**not yet on
`origin/main`** — at commit `0659ef39b`; `git show
0659ef39b:docs/evidence/2026-08-12-board-recipe-reproducibility.md`)
(**168 footprints, 3,349 segments, 56 vias, 70 zones, 80/105 nets routed**;
`diff` empty and sha256 equal across two concurrent independent runs).
Three changes in scope here **would** move that board, and each must be a
decision, not a discovery:

- **R6 — batch size or batch composition.** Because K ≈ 17 > B = 10, any
  change to `DEFAULT_BATCH_SIZE` crossing ~17 switches capacity encoding
  **on**, which changes topology, which changes the board. `B ≥ 17` is a
  different algorithm, not a tuning knob.
- **R7 — running unbatched.** The baseline was produced *with*
  `--net-batching`. The monolithic path encodes ~204,490 capacity
  constraints the batched path does not. Byte-equality between the two is
  **not expected and must not be asserted**; the acceptance test for U1/U2
  is batched-vs-batched.
- **R8 — `channel_skeleton.py`.** GEOS Voronoi output determines the
  skeleton, which determines `edge_id`, which determines every SAT variable
  *name*, which determines solver tie-breaking. A non-bit-exact port
  changes the board even when it is geometrically correct. This is the one
  place where a library's role is **essential** — not because it is
  CPython, but because it is *this* GEOS.

### Requirements

Requirement IDs are stable and become `@req(2026-08-12-002, Rn)`.

- **R1.** `ConstraintModel` stores variables and constraints in a
  Rust-native representation with no `Py<PyAny>` in the hot path, and the
  per-variable edge-id string is interned once per edge rather than stored
  per variable (today it is stored **twice** per variable —
  `model_builder.rs:486-490`). **Check:** a repeat of
  `2026-08-12-router-model-memory-probe.py` reports **< 40 bytes/variable**
  (against 326.7 today); `rg 'Py<PyAny>' packages/temper-design-bundle/src/model_builder.rs`
  returns no hit inside the variable/constraint storage fields.
- **R2.** A Rust→Rust path exists from the built model to
  `encode_to_cnf` that materializes **zero** Python objects. **Check:** a
  counter or trace asserting `variables`/`constraints`/`terms` getters are
  called zero times during a production route; the CNF is byte-identical to
  the Python-round-trip path on a fixture board.
- **R3.** The board is unchanged. **Check:** `diff` empty and sha256 equal
  against the U0 baseline artifact, for the full recipe run with
  `--net-batching` (§Verification protocol).
- **R4.** Peak RSS of a full batched route is **measured and reported**
  before and after R1/R2, by the same `/proc/<pid>/status` `VmHWM`
  mechanism `_watch_peak_rss_kb` already uses. No estimate substitutes.
- **R5.** The unbatched model's true cost is **measured, not argued**: raw
  variable bytes, CNF vars, CNF clauses, and peak RSS, under an explicit
  `ulimit -v`, after R1/R2 land. The verdict on the batch loop is written
  from that number.
- **R6.** `DEFAULT_BATCH_SIZE` is not changed in this plan. Any future
  change crossing K (~17) is a board-changing algorithmic change and needs
  its own plan and its own baseline.
- **R7.** No step asserts byte-equality between the batched and monolithic
  paths. Where both are run, the comparison recorded is *topology
  agreement* and *DRC delta*, with the capacity-encoding difference stated.
- **R8.** `channel_skeleton.py` is **out of scope**. If any step's diff
  perturbs skeleton geometry, the step is wrong and is reverted, not
  re-baselined.
- **R9.** The subprocess driver is deleted only after an in-process Rust
  batch loop has produced a byte-identical board on **three** consecutive
  runs, and only after R1/R2 removed the allocation pressure that motivated
  it. Deleting it first would reintroduce the uncatchable-`abort()` failure
  the isolation was added for.
- **R10.** Crash-vs-UNSAT remains distinguishable. In Rust this is a
  `Result` variant rather than an exit-code inference, and
  `NetBatchResult.status` keeps `"crashed"` as a value distinct from
  `"unsat"`. The 900s wall-clock timeout is removed only if R5 shows the
  in-process loop has no unbounded-wall failure mode; otherwise it is
  reimplemented as a Rust deadline.
- **R11.** The per-batch count of **actually encoded** `CapacityConstraint`s
  is instrumented and reported. **Check:** the number is emitted alongside
  the existing `[net-batching]` summary line, so the K-vs-B finding is a
  standing measurement rather than a one-off derivation.
- **R12.** `_corridor_backbone.py:549`'s `scipy.ndimage.label` is replaced
  by `temper_geometry.connected_components_8_transform`, restoring the
  closed scipy migration. **Check:** `rg -c scipy` over
  `packages/temper-placer/src/` returns 0; board byte-identical.
- **R13.** The 1,590 LOC in bucket (c) is deleted with production-Python
  LOC measured before and after. The value of this plan is a **decreasing**
  figure; if it does not move, say so.
- **R14.** Every deletion follows [`../migration-pipeline.md`](../migration-pipeline.md)
  stages 7–8 — **not** a bulk import scan. `scripts/route_board.py` is in
  the scan path (this is the `47349a50d` / `pad_connectivity_audit.py`
  failure case, which cost three days of unmeasurable completion).
- **R15.** Oracle disposition is declared per retirement: FREEZE /
  REIMPLEMENT / KEEP. `_net_batching_py_oracle.py` is **KEEP** while the
  batch loop's fate is open, then FREEZE. The clearance/creepage family is
  **REIMPLEMENT**-class and exempt from the sustained-agreement bar.

### Verification protocol (applies to every unit)

Every unit's acceptance test is the same, and it is the strongest one
available:

```
# full recipe, twice, concurrently, then:
diff  route_a/temper_routed.kicad_pcb route_b/temper_routed.kicad_pcb   # must be empty
sha256sum route_a/... route_b/...                                       # must match
diff  route_a/temper_routed.kicad_pcb baseline/temper_routed.kicad_pcb  # must be empty
```

with `python3 scripts/route_board.py --runs N --net-batching` for the
built-in spread report (fixed in `0659ef39b` to actually forward the flag —
before that fix, `--runs N --net-batching` silently measured the
*monolithic* path). Baseline: 168 footprints / 3,349 segments / 56 vias /
70 zones / 80 of 105 nets. Secondary, **advisory only**: `kicad-cli pcb drc
--all-track-errors --refill-zones --format json` — note that bare
`kicad-cli` DRC is itself not repeatable (`clearance` measured
∈ {499, 500, 501, 502, 504} over 7 samples of a *byte-identical* file), so
DRC counts are a smell test and the `diff` is the gate.

## Units

### U0 — Pin the baseline (half a day)

Regenerate the baseline artifact from today's committed `pcb/**` and store
its sha256. Nothing in this plan is verifiable without it, and
`2026-08-12-board-recipe-reproducibility.md` already showed a footprint
edit (`T2`, `CST3015.kicad_mod`) silently moved segments 3,319 → 3,349.
**Verified by:** two concurrent runs, `diff` empty, counts match the
recorded baseline. **Effort:** 0.5 day, mostly wall-clock (≈350s/run).

### U1 — Rust-native `ConstraintModel` (R1) — **the first landable step**

Replace `Vec<Py<PyAny>>` / `HashMap<(i64,String), Py<PyAny>>` in
`model_builder.rs:483-491` with typed Rust storage and an interned edge-id
table. Keep every Python-facing getter working (they rebuild lists from the
Rust representation on demand, exactly as today) so **no Python caller
changes**. No algorithm changes; no output changes.

Independently landable because the pyo3 surface is unchanged — this is a
representation swap behind a stable API. **Verified by:** R3 board
byte-identity; R1's < 40 bytes/variable probe; the existing
`_constraint_model_builder_py_oracle` differential, untouched.
**Effort: 5–8 days.** Risk: low-medium — the getters must preserve
insertion order exactly, because variable order feeds `name_to_idx` and
therefore CNF variable numbering and therefore solver tie-breaking.

### U2 — Rust→Rust model handoff, and the monolith measurement (R2, R4, R5)

`temper-rust-router` cannot name `temper-design-bundle`'s types today (no
Cargo dependency; separate `cdylib`s). Resolve by moving the shared model
types into a crate both depend on — `temper-rust-router-core` already
defines `InternalConstraintModel` and is the natural home — then expose a
handoff that skips Python entirely. **Then measure the unbatched model**
(R5) and write the verdict on the batch loop from that number.

**Verified by:** R3 byte-identity; zero-getter-call assertion; CNF
byte-identity against the round-trip path on a fixture. **Effort: 8–14
days.** Risk: medium — this is a crate-boundary change, and
`types_py_bridge.rs`'s duck-typed `getattr` reading is what the pinned
oracles currently exercise.

### U3 — In-process Rust batch loop, subprocess driver retained (R9, R10)

Port `run_net_batched_stage3`'s sequencing into Rust as a plain loop, using
the E5 kernels already in `temper_rust_router_core::net_batching`. Run it
**behind a flag, with the subprocess path still default**, so both can be
compared on the same board. Nothing is deleted in this unit.

**Verified by:** byte-identical board from the Rust loop vs. the subprocess
loop, three consecutive runs. **Effort: 8–12 days.**

### U4 — Retire the subprocess driver (R9, R13, R14, R15)

Flip the default, then delete the 610 LOC. Only after U1/U2 have removed
the allocation pressure and U3 has three clean runs.

**Verified by:** R3; `--runs 3 --net-batching` spread report shows zero
segment/via/zone spread; production-Python LOC measured before/after.
**Effort: 2–3 days.**

### U5 — Instrument encoded-capacity count; settle the semantics question (R5, R7, R11)

Emit the per-batch count of actually-encoded `CapacityConstraint`s. Then
answer, on evidence, the question this spike raised: **if the production
SAT model encodes no capacity constraint, what is the SAT solve buying over
the greedy `_shrink_channel_widths` allocation alone?** This unit's output
is a measurement and a recommendation, not a code change — and the
recommendation may be that Stage 3 should be reformulated, which would be
its own plan.

**Verified by:** the count appears in the default `[net-batching]` summary;
an A/B of SAT-topology vs. greedy-only topology recorded with DRC deltas.
**Effort: 3–5 days.** This is the highest-information unit in the plan.

### U6 — Collapse the 20 thin wrappers (R13, R14, R15)

Phase B of `2026-08-09-001` (U11–U13), which never ran. 3,979 LOC across 20
files reduced to `.pyi`-style re-export or removed where the caller can
import the kernel directly. Start with `topology_extraction.py` (53 LOC,
zero `def`s) to establish the pattern; `clearance_check.py` (837 LOC around
a single delegation at `:284`) is the largest single win.

**Verified by:** R3 per batch of ~5 files; each file's pinned oracle
differential unchanged; `scripts/check_unwired_kernels.py` clean.
**Effort: 6–10 days.** Risk: low — but `scripts/` must be in the reference
scan (R14).

### U7 — Delete bucket (c)'s zero-caller and vestigial modules (R13, R14)

`routability_check.py` (546), `congestion_analysis.py` (144),
`test_boards.py` (162), `placement_audit.py` + `placement_legalization.py`
(128). **Verified by:** R3; `scripts/route_board.py` exercised explicitly.
**Effort: 2–3 days.**

### U8 — Repair the scipy regression (R12)

One import site, `_corridor_backbone.py:549`. **Verified by:** `rg -c
scipy` returns 0 over production Python; R3 byte-identity. **Effort: 1
day.** Smallest unit here; listed because a closed migration silently
reopened and nothing caught it.

### Sequencing

```
U0 ──> U1 ──> U2 ──> U3 ──> U4
                └──> U5
U6, U7, U8  (independent of the above; land in parallel)
```

**Total for U0–U5: 27–43 days.** **U6–U8: 9–14 days.** These are honest
figures for the scoped work and they deliberately exclude the three
projects named below.

## Scope Boundaries

**Explicitly not in this plan**, and each is a real project rather than an
optimistic decomposition:

- **The A* core** — `_astar_search.py` (700), `astar_core.py` (669),
  `_astar_nlayer.py` (548), `_astar_reconstruct.py` (532),
  `astar_grid.py` (350), `_astar_ordering.py` (162),
  `terminal_tree_execution.py` (225): **~3,186 LOC with no pinned oracle
  and no Rust counterpart.** Rust A*/theta-star kernels exist but this is
  the search *driver*, not the kernel. Estimate if attempted: **20–35
  days.**
- **Copper generation** — `_ground_plane.py` (1,142),
  `_power_islands.py` (691), `_corridor_backbone.py` (587): ~2,420 LOC,
  GEOS-heavy, no oracle, and the newest code in the package (two of the
  three first appeared 2026-08-11/12). Porting live code is how you get
  two bugs. Estimate: **15–25 days**, and it should wait for the code to
  settle.
- **`channel_skeleton.py`** (667) — the GEOS Voronoi bit-exactness hazard
  (R8). `extract_medial_axis_py` exists as a differential only. This is a
  numerical-agreement project, not a translation. Estimate: **10–20 days**,
  high risk of never reaching bit-exactness.
- **CP-SAT / ortools** — not in `router_v6/` at all; already scoped by
  [`../evidence/2026-08-11-rust-driver-endgame-assessment.md`](../evidence/2026-08-11-rust-driver-endgame-assessment.md)
  (2,858–4,400 LOC, one `CpSatModel(` instantiation, Pumpkin evaluated).
- **`bundle_analyzer.py`** (546) — reachable only via `enable_bundling`,
  a path with a missing binding and a known net-index/bundle-id collision.
  `2026-08-07-sat-model-reduction-options.md` §8 **recommends reviving**
  it. Left in (a), not (c), on that basis. Decide separately.

**Already done — do not re-scope.** Plan
[`2026-08-09-001`](2026-08-09-001-feat-rust-orchestration-engine-plan.md)
landed E1–E6 in full (E1 `constraint_model` 1,150→445; E3 clearance family
→ `clearance.rs` 1,661 LOC; E4 `channel_mapping` 639→315; E5 the batch
kernels; E6 → `pipeline_route.rs` 758 LOC), and `temper-orchestration` is a
real 26,507-LOC Rust `Stage`/`PipelineRunner` engine with ~24 stage impls.
The one thing that plan left unbuilt at the top is that `PipelineRunner`
was **never wired as the driver** — stages are invoked individually from
Python shims.

## Dependencies / Assumptions

- **Assumes** the 204,490-edge skeleton figure from
  `2026-08-07-sat-model-reduction-options.md` still holds. It predates the
  T2 footprint change. U2 should re-measure it rather than inherit it; if
  the skeleton shrank, the monolith arithmetic changes.
- **Assumes** `temper-rust-router-core` is an acceptable home for the
  shared model types (U2). If not, a fourth crate is needed and U2 grows.
- **Depends on** the recipe staying deterministic. Every acceptance test in
  this plan is a `diff`; if determinism regresses, the plan is blocked, not
  degraded. `PYTHONHASHSEED` is deliberately unset in the verified recipe.
- **Depends on** `scripts/route_board.py`'s `--runs` flag forwarding
  `--net-batching` (fixed in `0659ef39b`); without it the harness measures
  the wrong path.

## Outstanding Questions

1. **Does the monolith fit after U1+U2?** Unanswerable today; U2 answers
   it. The variable-side arithmetic says 0.19 GB; the CNF side at a
   204,490-edge skeleton is the open term, and `Vec<Vec<i32>>` for ~450M
   clauses is itself a representation problem before it is a scale problem.
2. **If the SAT model encodes no capacity constraint, is Stage 3's SAT
   solve load-bearing at all?** U5. If the answer is "no", the correct
   change is much larger and much better than this plan — and this repo has
   a documented pattern of exactly this kind of component being assumed
   load-bearing when it is not.
3. **Should `DEFAULT_BATCH_SIZE` rise above K?** Deliberately deferred (R6).
   It would switch capacity encoding on and change the board — possibly for
   the better, since capacity would then actually be solved rather than
   greedily allocated. Needs its own plan and its own baseline.
4. **Do the 42 test-only references to `routability_check.py` represent
   real coverage?** If they are coverage-paydown scaffolding, deleting the
   module deletes the tests too, and the CI floors in
   `2026-08-11-python-ci-load-inventory.md` must be re-baselined.

## Sources / Research

- MEASURED this task:
  [`../evidence/2026-08-12-router-model-memory-probe.py`](../evidence/2026-08-12-router-model-memory-probe.py) ·
  [`../evidence/2026-08-12-router-model-memory-counterfactual.rs`](../evidence/2026-08-12-router-model-memory-counterfactual.rs)
- `docs/evidence/2026-08-12-board-recipe-reproducibility.md` @ `0659ef39b` (unlanded) — the baseline and the determinism proof
- [`../evidence/2026-08-07-sat-model-reduction-options.md`](../evidence/2026-08-07-sat-model-reduction-options.md) — 5.43GB / 22,493,900 vars / 204,490 edges; the "22.5M objects ≈ 5.43GB" line at §7
- [`../evidence/2026-08-07-router-oom-diagnosis.md`](../evidence/2026-08-07-router-oom-diagnosis.md) — 42,145,777 vars / 78,107,180 clauses; the Sinz attribution
- [`../evidence/2026-08-07-net-batching-prototype.md`](../evidence/2026-08-07-net-batching-prototype.md) · [`../evidence/2026-08-08-net-batching-subprocess-isolation.md`](../evidence/2026-08-08-net-batching-subprocess-isolation.md)
- [`../evidence/2026-08-11-rust-driver-endgame-assessment.md`](../evidence/2026-08-11-rust-driver-endgame-assessment.md) — scipy closure; the CP-SAT floor
- [`../evidence/2026-08-11-python-deprecation-inventory.md`](../evidence/2026-08-11-python-deprecation-inventory.md) · [`../evidence/2026-08-11-python-ci-load-inventory.md`](../evidence/2026-08-11-python-ci-load-inventory.md)
- [`2026-08-09-001-feat-rust-orchestration-engine-plan.md`](2026-08-09-001-feat-rust-orchestration-engine-plan.md) — E1–E6, all landed
- [`../migration-pipeline.md`](../migration-pipeline.md) — stages 7–8, oracle disposition, the retirement bar
- [`../wave4-verdicts.yaml`](../wave4-verdicts.yaml) — R1/R7 verdicts for 90 of 108 files
- Code: `packages/temper-design-bundle/src/model_builder.rs:483-491,543-564` ·
  `packages/temper-rust-router/src/lib.rs:156-176` ·
  `packages/temper-rust-router/src/types_py_bridge.rs:11-99` ·
  `packages/temper-rust-router-core/src/encoding.rs:21-30,148` ·
  `packages/temper-rust-router-core/src/types.rs:67-77` ·
  `packages/temper-rust-router-core/src/net_batching.rs` ·
  `packages/temper-placer/src/temper_placer/router_v6/net_batching.py:456-490,493-967`
