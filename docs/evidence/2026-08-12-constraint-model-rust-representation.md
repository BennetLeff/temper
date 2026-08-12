<!-- provenance: commit=08ea097d505c78c6437581c150ebfba71d725445 dirty=false
     branch=feat/constraint-model-rust-repr
     worktree=/home/bennet/Desktop/temper-worktrees/constraint-model-rust-repr
     base=bf765eb89 (origin/main tip at task start; origin/main advanced to
       1a7365587 DURING this session -- see "Base" below)
     date=2026-08-12
     method=real VmRSS via /proc/self/status (both probes) and VmHWM via
       net_batching's own _watch_peak_rss_kb (per-batch figures); full
       scripts/route_board.py --net-batching runs on pcb/temper.kicad_pcb,
       sha256 compared; pinned pumpkin_engine verified (exit 0) before every
       board run; isolated worktree .venv (make venv-isolate), all 10
       extensions rebuilt and check_stale_extensions.py 10/10 fresh -->

# U1 — `ConstraintModel` gets a Rust-native representation

Unit **U1** of
[`../plans/2026-08-12-002-feat-router-orchestration-rust-plan.md`](../plans/2026-08-12-002-feat-router-orchestration-rust-plan.md)
(R1). Representation only: no algorithm change, no output change, no Python
caller change, and every pyo3 getter keeps its signature and its semantics.

## Verdict

| question | answer |
|---|---|
| Board byte-identical? | **Yes.** 6 full routes (3 before, 3 after), one sha256: `845c144de2b87fd948f19458986ad1f65dac4d7fe9dcfbca6c760d2224a5fd0f` |
| Stored bytes/variable, pinned probe | **326.6 → 25.1** (13.0x) |
| Stored bytes/variable, production-shaped probe | **477.2 → 33.0** (14.5x) |
| Peak RSS with `.variables` materialised | **unchanged** — 0.630 GB → 0.628 GB at N=2,000,000 |
| Per-batch worker peak RSS, real board | 4.20 GB → **3.92 GB** (max of 11 batches), −7% |

The last row is the honest limit of U1 and the reason U2 exists: the
*storage* is 14x smaller, but `list(model.variables)` still builds one
CPython object per variable, so a caller that materialises the whole list
pays the old cost transiently. Removing that materialisation is U2's
Rust→Rust handoff, not this unit's.

## What the representation is

`packages/temper-design-bundle/src/model_builder.rs`. Before:

```rust
pub struct ConstraintModel {
    variables: Vec<Py<PyAny>>,
    constraints: Vec<Py<PyAny>>,
    net_channel_vars: HashMap<(i64, String), Py<PyAny>>,
    bundle_channel_vars: HashMap<(i64, String), Py<PyAny>>,
    via_vars: HashMap<(i64, String), Py<PyAny>>,
}
```

22,493,900 CPython objects for the production board, each a `#[pyclass]`
instance carrying three Rust `String`s, and each variable's `channel_id`
stored **twice** — once in the object, once again as a map key.

After:

- **`PackedVar` — 8 bytes per variable.** A `u32` net index plus a `u32`
  that packs a 2-bit kind tag (`NetChannel` / `Bundle` / `Via` / `Foreign`)
  into the top of a 30-bit interned-string id.
- **`Interner`** — every `channel_id` / `location_id` / diff-pair
  `base_name` stored once (204,490 distinct edge ids on this board, not
  22.5M copies), as `Arc<str>` shared between the table and its reverse
  index so the bytes are not duplicated there either.
- **`PackedConstraint`** — the three shapes the builder emits
  (`Capacity` / `DiffPair` / `Layer`), with capacity terms in a flat
  `(u32 variable index, f64 width)` arena rather than
  `Vec<(Py<PyAny>, f64)>`.
- **`VarIndex` — 4 bytes per slot.** The `(net_idx, interned key) ->
  variable index` reverse index, open-addressed, re-deriving each occupied
  slot's key from the variable it points at (see §"The reverse index" —
  this was the whole remaining cost once the variables were packed).
- **Names are derived, not stored.** `uses_N{net}_{edge}`,
  `uses_B{bundle}_{edge}`, `via_N{net}_{node}`, `cap_{edge}`,
  `diff_{base}_{edge}`, `layer_restr_N{net}_{edge}` are exactly what the
  builder formats, so the packed fields reproduce them byte-for-byte.

Two escape hatches keep "unchanged semantics" total rather than
approximate:

- Anything `add_variable` cannot reproduce from packed fields — a `net_idx`
  outside `u32`, an unexpected `var_type`, a hand-written name such as
  `NetChannelVar(name="BOGUS", net_idx=0, channel_id="EDGE")` (which
  `test_constraint_model_builder_pbt.py` asserts on) — is retained as the
  caller's original object and still routed into the same dict. No
  production path takes it.
- `add_constraint` always retains the caller's object verbatim. Its only
  two users are the PCL lowering paths, which pass constraints referencing
  objects the model knows nothing about — `_augment_with_pcl_constraints`
  constructs a `DiffPairConstraint` whose `p_var` is a bare `str`.

`CapacityConstraint.terms` and `DiffPairConstraint.p_var`/`n_var` resolve
**lazily**, through a `Py<ConstraintModel>` handle. That laziness is
load-bearing: resolving eagerly would rebuild one Python variable object
per term while materialising `list(model.constraints)` — exactly the 22.5M
objects this unit exists to delete.

### The one observable difference

Object *identity*. Two reads of `.variables` used to hand back the same
instances and now hand back equal-valued fresh ones. Checked rather than
assumed: nothing in the tree compares model variables by identity or uses
one as a dict key (`types_py_bridge.rs` reads `.name`;
`pipeline_route.rs`'s clause-origin walk reads attributes; the differential
suite canonicalises by field value), and these pyclasses define neither
`__eq__` nor `__hash__` for such a comparison to have been meaningful
through.

## The measurement

### The pinned probe understates the reverse index, and here is why

`2026-08-12-router-model-memory-probe.py` (from
`spike/router-orchestration-rust`, vendored onto this branch unchanged)
generates `net_idx = i % 110`, `channel_id = edge_id(i % 204490)`. Because

```
204490 = 110 * 1859       exactly
```

`i % 110` is a *function of* `i % 204490`. Its `(net_idx, channel_id)`
pairs therefore take only **204,490** distinct values however many
variables it creates — MEASURED: `len(cm.net_channel_vars) == 204490` at
N = 2,000,000, against a `variable_count` of 2,000,000.
`ConstraintModel.net_channel_vars` is keyed by exactly that pair, so the
probe's reverse index is ~10x smaller than any real model's, where every
(net, edge) pair is distinct by construction.

That degeneracy did not matter before this change — the cost was in the
22.5M CPython objects, and the dict held refcounted aliases of them. It
matters a great deal afterwards, when the reverse index is one of the two
things left.

`2026-08-12-router-model-memory-probe-distinct-keys.py` is the same
measurement with `net_idx = i // EDGES`, so every pair is distinct. At
N = 10 x 204,490 = **2,044,900** it is exactly the production **per-batch**
model: `DEFAULT_BATCH_SIZE = 10` nets over this board's 204,490-edge
skeleton.

### Numbers

Both probes, same host, same venv, real `VmRSS`:

| | pinned probe (N=2,000,000) | distinct-key probe (N=2,044,900) |
|---|---:|---:|
| `origin/main` | **326.6** B/var (0.608 GB) | **477.2** B/var (0.909 GB) |
| packed vars, `HashMap` index | — | 74.9 B/var (0.143 GB) |
| packed vars + `VarIndex` | **25.1** B/var (0.047 GB) | **33.0** B/var (0.063 GB) |
| reduction | **13.0x** | **14.5x** |

Extrapolated to the full 22,493,900-variable monolithic model, pinned
probe: **7.35 GB → 0.56 GB**.

The plan's counterfactual quotes **8.9 bytes/var**. That figure is *not*
reachable by a real `ConstraintModel` and the gap is not a shortfall in the
implementation:
`2026-08-12-router-model-memory-counterfactual.rs` case (C) measures a
`Vec<PackedNetChannelVar>` plus interned strings and **no reverse index at
all** — it never builds `net_channel_vars`, which the builder cannot work
without. 33.0 B/var decomposes as roughly 8.2 (the `PackedVar` vector,
including power-of-two `Vec` slack) + ~8.2 (`VarIndex` slots) + ~13
(interner, amortised over one batch's 2.04M variables rather than the
monolith's 22.5M) + allocator slack. R1's stated bar is **< 40
bytes/variable**; both probes clear it.

### The reverse index

Packing the variables exposed the next cost. A `HashMap<(i64, u32), u32>`
costs 21 bytes per *bucket* — a 16-byte padded key, a 4-byte value, a
1-byte control word — and rounds its bucket count up to a power of two: at
2,044,900 entries that is 4,194,304 buckets and 88 MB. MEASURED: with the
variables already packed, it was **53 of the remaining 74.9 bytes per
variable**, more than the variables themselves.

`VarIndex` stores only the 4-byte variable index per slot and re-derives
each occupied slot's key from the variable it points at, so no key is
stored twice. Open addressing, linear probing, 0.75 load factor; entries
are only ever inserted or overwritten, never removed, so there are no
tombstones. Foreign variables carry their dict key in a side table parallel
to `foreign_vars`, since their `PackedVar` has no `net_idx` to re-derive
from.

Semantics preserved, including last-writer-wins on a duplicate
`(net_idx, channel_id)` and arbitrary dict iteration order (the `HashMap`'s
was arbitrary too). Covered by a unit test that drives `VarIndex` and a
`HashMap` through the same 4,000-operation, deliberately duplicate-heavy
workload and compares `get()`, `len()` and `iter()` against it.

## Board byte-identity

Engine gate first, every time:
`python3 scripts/verify_pumpkin_engine.py` → exit 0,
`sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e`,
`source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd`.

```
python3 scripts/route_board.py --net-batching --output <path>
```

against `pcb/temper.kicad_pcb` as committed on `origin/main`, twice on each
side of the change:

| run | build | result | wall | sha256 |
|---|---|---|---:|---|
| before_a | `origin/main` | 62/102 nets, 3193 seg / 24 via / 84 zone | 423.0 s | `845c144d…` |
| before_b | `origin/main` | 62/102 nets, 3193 seg / 24 via / 84 zone | 380.2 s | `845c144d…` |
| before_trace | `origin/main`, `TEMPER_BATCH_TRACE=1` | 62/102 nets, 3193 seg / 24 via / 84 zone | 412.1 s | `845c144d…` |
| after_a | this branch | 62/102 nets, 3193 seg / 24 via / 84 zone | 401.6 s | `845c144d…` |
| after_b | this branch | 62/102 nets, 3193 seg / 24 via / 84 zone | 398.0 s | `845c144d…` |
| after_trace | this branch, `TEMPER_BATCH_TRACE=1` | 62/102 nets, 3193 seg / 24 via / 84 zone | 647.2 s | `845c144d…` |

`diff` empty across all six. `[net-batching] 11 batch(es), 11 solved at
batch level, 0 crashed` on every run. Wall times are reported but no claim
is made from them: `after_trace` is a visible outlier against a 380-423 s
spread on an otherwise-identical run, unexplained and not investigated,
while that same run's *Stage 3* total was the fastest of the six
(`total_wall_s=269.41` vs `277.68` before). Nothing here is a performance
result.

**On the baseline figure.** These runs do not reproduce 2,514/22/76/168,
and they are not supposed to: that figure comes from a *place-and-route*
recipe on a reconciled board that is not on `origin/main`
(`2026-08-12-place-and-reroute-connectivity.md` explicitly does not land
its board). This unit's gate is before-vs-after equality on one recipe, one
board, one pinned engine, in one worktree — which is what makes it a
statement about the change rather than about the environment. The
`board_origin` hazard that invalidated a prior PR's measurements does not
arise here: `route_pcb` only calls `_apply_placements_to_pcb` under
`if placements:`, and this recipe passes none, so no footprint is
rewritten.

## Per-batch peak RSS on the real board

`TEMPER_BATCH_TRACE=1` makes `net_batching.py` print each batch worker's
peak RSS, taken from the kernel's own `VmHWM` high-water mark by
`_watch_peak_rss_kb` — the mechanism the plan's R4 names. 11 batches,
**2,041,440 variables each** (10 nets x 204,144 candidate edges):

| | min | max | mean |
|---|---:|---:|---:|
| `origin/main` | 3,855,720 kB | 4,401,024 kB | 4,067,174 kB |
| this branch | 3,566,588 kB | 4,109,472 kB | 3,772,265 kB |
| delta | −289,132 kB | −291,552 kB | −294,909 kB |

A flat **~0.29 GB off every batch, about 7%** — and that number is the
honest one, not a disappointment to be explained away. The model's *stored*
cost fell by 2,041,440 x (477 − 33) B = **0.90 GB**, but the batch worker's
peak is set at the moment `list(cm.variables)` exists, and that list is
still one CPython object per variable. Before: 0.97 GB of stored objects
plus a 16 MB list of pointers to them. After: 0.07 GB of packed storage
plus ~0.65 GB of freshly built objects. The 0.28 GB gap between those two
is what the trace measures, and it matches.

The remaining ~3.9 GB per batch is downstream of the model — CNF and
CaDiCaL — which is `2026-08-12-004-feat-cnf-representation-plan.md`'s
subject, not this one's.

## Test evidence

- `cargo test --features python model_builder` — 12 tests, all pass,
  including `var_index_agrees_with_a_hashmap_over_a_mixed_workload`,
  `last_writer_wins_on_a_duplicate_dict_key`,
  `non_canonical_name_falls_back_to_the_original_object`,
  `packed_variables_rebuild_their_python_objects_exactly`.
  (The crate's pyo3 feature carries `extension-module`, which cannot link a
  test binary; the run swaps it for `auto-initialize` locally and restores
  it. Those tests are therefore not executed by CI today — a pre-existing
  gap, named here rather than left implicit.)
- `pytest packages/temper-placer/tests/router_v6/test_constraint_model*.py`
  — **319 passed**, including the untouched
  `_constraint_model_builder_py_oracle` differential, which compares both
  arms' `variables`, `constraints`, `net_channel_vars`,
  `bundle_channel_vars` and `via_vars` field-by-field and bit-exactly
  (`float.hex()`).
- Full `pytest packages/temper-placer/tests/router_v6/` run on both sides of
  the change: identical failure sets (see §Pre-existing failures).

## The monolithic path is unbounded on both sides — checked, not assumed

`test_temper_production_board_routing.py::test_route_pcb_production_board`
calls `route_pcb(...)` with **no** `enable_net_batching`, i.e. the
monolithic model. Running the full `router_v6` suite on this branch,
`systemd-oomd` killed the pytest process at **56.9 GB anon-RSS** inside
that test. On the `origin/main` run of the same suite the test had reported
`s` (skipped), so there was no comparison — and a 56.9 GB kill inside a
memory change is exactly the shape of thing that must be measured rather
than argued away.

Why it skipped once and ran once: the test's first statement is
`if not _kicad_cli_available(): pytest.skip(...)`, which shells out to
`kicad-cli --version` with a 10 s timeout. The `origin/main` suite ran
concurrently with a full board route on the same machine; that
`kicad-cli --version` timed out and the test skipped. The second run had
the machine to itself, kicad-cli answered, and the test proceeded into the
monolithic route. Nothing about the change.

Measured directly, same watchdog script and same 30 GiB cap on both builds
(`scripts/route_board.py` with no `--net-batching`, `TEMPER_MODEL_TRACE=1`,
peak taken from `/proc/<pid>/status` `VmHWM`):

| build | model | peak `VmHWM` | outcome |
|---|---|---:|---|
| `origin/main` | 22,455,840 vars / 110,283 constraints, built in 148.9 s | 31,500,164 kB | killed at the cap |
| this branch | 22,455,840 vars / 110,283 constraints, built in 166.0 s | 31,892,880 kB | killed at the cap |

**Both run away past 30 GB; neither completes.** The monolithic path does
not fit on today's 204,144-candidate-edge skeleton with or without this
change — which is what
`2026-08-12-004-feat-cnf-representation-plan.md` already concluded from the
CNF side (~128-146 GB, 91.5-92.6% of it solver-internal), and it is the
reason net-batching survives. The identical model size on both sides
(22,455,840 / 110,283, exactly) is also a useful cross-check that the
representation swap changed nothing about *what* is built.

Two caveats stated rather than buried. The peaks are watchdog cap values,
not natural peaks, so they are not comparable *to each other* beyond "both
exceed 30 GB". And `TEMPER_MODEL_TRACE=1` adds two extra full
`.variables` materialisations on both sides — which, on this branch, means
two extra passes of building 22.5M CPython objects; the trace was enabled
identically on both runs so the comparison holds, but it is not a
production configuration.

## Base

Every measurement above is `bf765eb89` (the `origin/main` tip when this
task started) against `bf765eb89` + this branch — a clean A/B on one base,
one board, one engine, one worktree.

`origin/main` advanced to `1a7365587` **during** the session, 26 commits,
including `756968706 fix(sat-encoding): delete dead aux-var-name allocation
+ pack CnfFormula.clauses` — the parallel CNF-layer work in
`temper-rust-router-core/src/encoding.rs`, deliberately untouched here.
`packages/temper-design-bundle/src/model_builder.rs` is not touched by any
of those 26 commits, so there is no textual conflict; but a merge changes
the CNF encoder underneath the same board, so **the board byte-identity
above must be re-established on the merged tree before landing**, and doing
that on a tree carrying both changes would conflate them. That
re-verification is a landing step, not a result of this unit.

## Scope held

- `DEFAULT_BATCH_SIZE` and the capacity guard are untouched (R6 — plan 003's
  territory).
- **Net-batching survives.** This unit makes no claim about monolithic
  solving. `2026-08-12-004-feat-cnf-representation-plan.md` measured
  CaDiCaL's own storage at 152-175 bytes/clause and the fully-packed
  monolith at ~128-146 GB, 91.5-92.6% of it solver-internal; nothing here
  moves that.
- No `pcb/**` file is touched.
- No pyo3 getter's Python-visible signature or semantics changed. Two
  getters changed their *Rust* receiver (`&self` → `&Bound<'_, Self>`) or
  return type (`Py<PyAny>` → `PyResult<Py<PyAny>>`) — invisible from
  Python, where a getter either yields a value or raises.

## What is left out

- **The materialisation cost is unchanged.** `list(model.variables)` still
  builds every variable object; `net_batching.py`'s worker reads
  `cm.variables` three times per batch. Peak RSS of a full route is
  therefore roughly unchanged, and this unit does not claim otherwise. U2
  (the Rust→Rust handoff to `encode_to_cnf`) is what removes it.
- **`foreign_vars` / `foreign_cons` still hold `Py<PyAny>`.** They are the
  fidelity escape hatches, and are empty on every production path — but R1's
  literal check (`rg 'Py<PyAny>' model_builder.rs` finds nothing in the
  storage fields) is not met, deliberately: meeting it would mean silently
  changing what `add_variable`/`add_constraint` do with an object they
  cannot pack.
- **The full-route peak-RSS verdict (R4) belongs to U2.** The per-batch
  worker figure is recorded below, and it is small for exactly the reason
  above.
