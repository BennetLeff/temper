<!-- provenance: commit=6150e18a998dfe3374c6eedc0b6acdadb8e6bcc8 dirty=UNKNOWN -->
spike/orchestration-workers, base origin/main @ 6e81c1d97. Analysis + a new
SPIKE-only crate scaffolding (packages/temper-orchestration-core/, a brand-new
package dir). No existing crate, script, workflow, manifest, or measurement
artifact was modified. `cargo check --target wasm32-unknown-unknown
--no-default-features` verified on the existing temper-orchestration,
temper-rust-router-core and temper-rust-router crates before and after (all
pass, unchanged). -->

# SPIKE — can the Rust orchestration loop logic (U-E/U-F/U-G/U-I) run on the Cloudflare Workers wasm tier?

**Verdict, first.** **Yes — but not by extracting the loop bodies as they exist today.**
The loop *sequencing*, *termination/gate decisions* and *factory ordering* are
already pure Rust control flow and are extractable onto the wasm32 tier **today**
(proof-of-concept below: a pyo3-free `temper-orchestration-core` rlib that
`cargo check`s for `wasm32-unknown-unknown`). But the loop *bodies* of
U-E/U-F/U-G/U-I cannot run on wasm32 until the `BoardState` data model is
ported to owned Rust structs — the `Py<PyAny>` fields and the Python
call-backs are what keep those files `#[cfg(feature = "python")]`-gated, not
their control flow. **The wasm tier is therefore a genuine forcing function
for the pure-Rust data-model port** (`/tmp/opencode/rust-pure-datamodel-brainstorm.md`
U0-U4, ≈40–53 engineer-days), and the sequencing/decision layer can be
extracted ahead of it. A cross-crate `temper-orchestration-core` +
`temper-orchestration` split (the `temper-rust-router-core` template) is the
right *end-state*, but splitting the crates before de-pythoning the data model
would move code without making it wasm-eligible.

## 1. Current state — the orchestration crate is already in-crate-split

`temper-orchestration` already does the split *inside one crate*:

- **Pure kernels survive `--no-default-features`** and already run on the tier:
  `timing`, `feasibility`, `copper_length`, `clearance`, `channel_mapping`,
  `stage` (`Stage<S>` trait + `StageError`), `pipeline` (`PipelineRunner<S>` +
  reports, with a `wasm32` `ClockPoint` that degrades `Instant::now()` to 0.0),
  `pipeline_state`, `stage_ledger`, `trace_filter`, `explainability`. These are
  `pub(crate)` and **not** `#[cfg(feature = "python")]`-gated.
- **The pyo3 surface is `#[cfg(feature = "python")]`-gated**: every
  `#[pyfunction]`/`#[pyclass]`, `BoardState` (23 `Option<Py<PyAny>>` fields),
  and the `Stage<BoardState>` impls.
- **The tier is already live**: `wasm_test_registry.rs` registers **83
  executable tests, all passing** on `temper-wasm-orchestration` (the
  `packages/temper-worker/families/orchestration/` Worker), wired through
  `temper-wasm-test-runner`'s `orchestration-wasm-test-registry` feature and
  `tools/wasm/wasm_tier_topology.json`.

Verified this task: `cargo check --target wasm32-unknown-unknown
--no-default-features --manifest-path packages/temper-orchestration/Cargo.toml`
passes (0.69 s; and the same for `temper-rust-router-core` and
`temper-rust-router`). Nothing was broken.

## 2. Why the U-E/U-F/U-G/U-I loop files are python-gated (the real blocker)

The four files are **entirely** `#[cfg(feature = "python")]`, but reading their
bodies shows the pyo3 dependence is in *two specific places*, neither of which
is the control flow:

1. **The data model.** `BoardState` (`board_state.rs:32`) holds 23
   `Option<pyo3::Py<PyAny>>` fields. The loops thread a Python `BoardState`
   object through a side-channel (`RunContext.current_py_state`,
   `FeedbackRunContext.current_py_state`) so untouched fields keep object
   identity.
2. **The leaf call-backs.** `FeedbackRunContext` holds `Py<PyAny>` call-backs
   (`pipeline`, `drc_runner`, `parse_kicad_drc`, `mapper`, `adjuster`,
   `get_zone_config`, `update_config`, `logger`); `cpsat_loop` calls
   `_call_solver`, `_detect_oscillation`, `_field_compute_fn` and the
   `temper_placer.placer.cp_sat.gates` module back; `deterministic_pipeline`'s
   `PythonStageShim` calls each Python stage's `.run()`.

The *decisions themselves* are pure. The clearest proof is already in-tree:
`router_pipeline.rs:88-103` keeps `dfm_should_fail` and `completion_pct`
deliberately **not** python-gated ("so the wasm tier can pin it"). The rest of
the decision set is the same shape:

| Decision | Location today | Owned-data form (wasm-eligible) |
|---|---|---|
| `dfm_should_fail(fail_on, critical, total)` | `router_pipeline.rs:88` (already un-gated) | `fail_on=="critical" => critical>0`, else `total>0` |
| `completion_pct(success, failure)` | `router_pipeline.rs:101` (already un-gated) | `100*s/max(1,s+f)` |
| `if not raw_violations: break` | `feedback_loop.rs:215` | `violations.is_empty()` |
| `if not adjustment.adjustments: break` | `feedback_loop.rs:258` | `adjustments.is_empty()` |
| iteration cap | `feedback_loop.rs` (`continue_loop` + `is_active`) | `index >= max_iterations` |
| `placement.status in ("infeasible","model_invalid")` | `cpsat_loop.rs:241` | `is_unsat_status(status: &str)` |
| field-round budget | `cpsat_loop.rs:794` | `counter >= limit` |
| factory ORDER (`drc_aware_stage_order`) | `deterministic_pipeline.rs:110` (pure body, python-gated only by file adjacency) | unchanged, `Vec<&'static str>` |

`drc_aware_stage_order` is the sharpest example: its body maps a `&[&str]`
constant to a `Vec<&'static str>` — zero pyo3 — yet it is `#[cfg(feature =
"python")]`-gated because it sits in the same file as the `DeterministicPipeline`
pyclass.

## 3. The crate-split plan (core + pyo3 layer)

The `temper-rust-router-core` (rlib, wasm-compatible, no pyo3) +
`temper-rust-router` (pyo3 surface, wraps the core) split is the correct
template — **but it is the end-state, not the first step.** The router split
worked because the core's logic was *already* pyo3-free (SAT, topology, loop
extraction). The orchestration loop logic is pyo3-free only in *substance*; its
files are still interwoven with `Py<PyAny>`. Splitting crates now would move
python-gated code into a crate that still cannot build for wasm32 — a rename,
not a de-pythoning.

Recommended landing sequence (cheapest first):

- **O-C1 (1–2 d) — extract the decision kernels + factory ordering onto the
  tier.** Move the decision predicates (table in §2) and `drc_aware_stage_order`
  into un-gated pure functions with `wasm-registry` tests, exactly the
  `dfm_should_fail`/`completion_pct` pattern generalized. This pins the loop's
  *decisions* on wasm32 without touching the data model. (The POC below does
  this, minus the move.)
- **O-C2 (3–5 d) — make the loop sequencing generic over a `Host` trait**
  (port/adapter). Parameterize the U-E/U-F/U-G/U-I loop control flow over a
  `trait LoopHost` (run-stage, run-drc, map-violation, adjust, solve, log), so
  the *control flow* compiles for wasm32 and is testable against a mock host,
  while the pyo3 crate supplies the real host (Python call-backs). This is the
  "loop logic is extractable today" half, and it is what makes O-C3's stages
  drop in.
- **O-C3 (≈40–53 d, the brainstorm's U0–U4) — the `CoreBoardState` data-model
  port.** Replace the 23 `Option<Py<PyAny>>` fields with owned structs; add the
  `Val`-enum (or per-field canonical-type proof) for bit-exact `repr`/`==`/dtype;
  generalize `d1_bridge.rs` into the `to_owned`/`to_py` boundary with the
  round-trip invariant. This is the actual gate for *running the loop* on wasm32.
- **O-C4 (2–4 d, only after O-C3) — the physical crate split.** `git mv` the
  now-py3-free `stage`/`pipeline`/`board_state`/`decisions`/`factory` + loop
  bodies into a new `temper-orchestration-core` rlib; `temper-orchestration`
  keeps the `#[pyfunction]`/`#[pyclass]` wrappers delegating to it. Wire a
  `orchestration-core-wasm-test-registry` feature in `temper-wasm-test-runner`,
  a `packages/temper-worker/families/orchestration-core/` Worker, and a
  `wasm_tier_topology.json` entry — the verbatim `router-core` wiring.

## 4. The BoardState → CoreBoardState transformation

Fully specified by the brainstorm (`/tmp/opencode/rust-pure-datamodel-brainstorm.md`
§1.1 table, 23 rows). The transformation relevant to the wasm question:

- `Option<Py<PyAny>>` → owned Rust type per field. Trivial rows (the "yes"
  rows): `zones` → `Vec<ZoneOwned{name, bounds: Rect}>`, `placements` →
  `HashMap<String, PlacementOwned>`, `drc_violations` →
  `Vec<ViolationOwned{...}>`, `used_slots` → `HashSet`, `component_domain_map`
  → `HashMap<String, Domain>`. The POC's `board_state.rs` demonstrates this
  shape on that subset.
- **Hard keeps (3 of 23) stay out of the core**: `config` (pydantic, R7 SSOT —
  carried as an opaque host-owned token in the core), `routing_corridors`/
  `domain_regions` (shapely — portable as `Vec<PolygonOwned>` *only if* no
  stage computes on them in Rust; GEOS buffer/union parity is a separate port).
- **The identity subtlety**: `BoardState`'s `Clone` is a reference-count bump;
  `CoreBoardState`'s `Clone` is a real clone, so the real port must `Arc` the
  large fields (grid, oracle) or the per-stage clone becomes the bottleneck.
- The concrete-Python-type hazard (brainstorm §5.1) — `Component("R1","fp",
  (1,2))` keeping `int` bounds without widening to `f64` — is the dominant
  cost driver and is unchanged by the wasm question.

## 5. The wasm wiring (what already exists vs. what's new)

Already exists and needs no change for O-C1/O-C2: the orchestration family
Worker, the `wasm_test_registry.rs` registry (new pure kernels' `WASM_TESTS`
are added by `scripts/gen_wasm_test_registry.py`), and the tier topology. For
O-C4's new crate, the wiring is exactly the `router-core` pattern: (1) a
`wasm-registry-orchestration-core` family feature lattice in the new crate's
`Cargo.toml`; (2) a `orchestration-core-registry` +
`orchestration-core-wasm-test-registry` feature pair in
`temper-wasm-test-runner` with the dep edge `default-features = false`; (3) a
new `packages/temper-worker/families/orchestration-core/{index.js,wrangler.toml}`
pair; (4) a topology entry + `wasm_expected_failures_orchestration_core.json`;
(5) a `scripts/stage_wasm_families.sh` staged-module name. The POC's
`wasm_test_registry.rs` and feature lattice already mirror the target shape.

## 6. Proof-of-concept result

New SPIKE-only crate `packages/temper-orchestration-core/` (no pyo3 dependency
anywhere, rlib only) containing: `stage.rs` (`Stage<S>` + error/contract types),
`pipeline.rs` (`PipelineRunner<S>` with the wasm32 `ClockPoint`), `board_state.rs`
(`CoreBoardState` with owned `ZoneOwned`/`PlacementOwned`/`ViolationOwned`/
`Domain` structs and a `CoreConfig` hard-keep placeholder), `decisions.rs`
(7 pure decision kernels from the table in §2), `factory.rs`
(`drc_aware_stage_order` + `DRC_AWARE_STAGE_KINDS`), and a hand-written
`wasm_test_registry.rs`.

Verified:
- `cargo check --target wasm32-unknown-unknown` — **passes** (0.19 s); the
  crate has no `python` feature at all, so this is the whole crate compiling
  for wasm32.
- `cargo check --target wasm32-unknown-unknown --features wasm-test-registry` —
  **passes** (the exact tier build shape).
- `cargo test` — **12/12 pass** natively.
- `cargo tree | grep pyo3` — **empty**; pyo3 is absent from the dependency
  graph.

The POC proves the sequencing + decisions + factory ordering + a
`CoreBoardState` skeleton are pyo3-free and wasm32-compilable. It does **not**
claim the real U-E/U-F/U-G/U-I bodies are de-pythoned — they are not; that is
O-C3's work.

## 7. Effort estimate (summary)

| Unit | Scope | Effort |
|---|---|---|
| O-C1 decision-kernel + factory extraction | move predicates/ordering to un-gated pure fns + tests | 1–2 d |
| O-C2 loop-as-generic-over-`Host`-trait | de-couple control flow from `Py<PyAny>` call-backs | 3–5 d |
| O-C3 `CoreBoardState` data-model port | brainstorm U0–U4, `Val` enum, round-trip gate | ≈40–53 d |
| O-C4 physical crate split + tier wiring | `git mv` + runner/topology/Worker scaffolding | 2–4 d |

The wasm tier is free to start O-C1 immediately (no data-model dependency); it
is *blocked* on O-C3 for "run the actual loop with real board data on a
Worker."

## Things I could not verify (per "absence is not evidence" discipline)

- The POC's `wasm_test_registry.rs` is hand-written, not generated — whether
  `scripts/gen_wasm_test_registry.py` handles a new crate without further
  changes (a new `--crate` entry) was not attempted; the existing script's
  census is per-crate and the runner/topology files are hand-edited for each
  new crate anyway (see the `router-core` entries).
- The exact count of decision predicates remaining after O-C1 was not
  exhaustively enumerated — the table in §2 lists the ones the four loop files
  expose; `cpsat_loop.rs`'s stability-round and gate-status checks (§"gate
  checks") are additional predicates of the same pure string/int-compare shape
  that a full extraction would sweep.
- The "40–53 d" figure is the brainstorm's own U0–U7 estimate, re-cited, not
  re-derived; it already excludes the CP-SAT solver question and the residual
  router_v6 shapely/networkx compute.
