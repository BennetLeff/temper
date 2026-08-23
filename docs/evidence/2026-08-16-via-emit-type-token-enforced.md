<!-- provenance: commit=ec79d0c967d9382ee219cf9eaf8a1782023214e9 dirty=UNKNOWN -->
---
module: temper-orchestration / temper-placer router_v6
tags: [router, kiCad, via, drc, sexpr, emission, enforcement, type-safety, wasm-tier]
problem_type: correctness-bug
---

# 2026-08-16 — Via type token made inseparable from emission

## Summary

Agent 65's fix (2026-08-15, `docs/evidence/2026-08-15-via-type-emission-fix.md`)
stopped the router emitting token-less vias (KiCad defaults a token-less
`(via ...)` to THROUGH, piercing every copper layer) by adding a **free
function** `via_type_token(from_layer, to_layer)` that the emission loop
called. The free function could be forgotten: the `Via` data still travelled
as a raw 6-tuple through the whole payload path, and any future code path
that formatted a via string directly would silently regress to the
no-token THROUGH emission the fix was built to kill. The emission did not
*enforce* the type computation — it *invited* it.

This change makes the computation inseparable from the emission:

- A real `Via` struct now exists in
  `packages/temper-orchestration/src/pipeline_route.rs` with **private
  fields** — `x`, `y`, `from_layer`, `to_layer`, `diameter`, `drill`.
- `Via::emit_s_expr(...)` is the **only** way to turn a `Via` into a KiCad
  `(via ...)` s-expression, and it ALWAYS computes the type token from the
  private layer pair first (`Via::via_type_token`). There is no free
  function and no public field access left to build the sexpr without it.
- The free `via_type_token()` is gone; the classification rule lives as a
  private method on the struct.
- The payload wire type `RouteEmission` now carries `Vec<Via>` instead of
  `Vec<(f64, f64, f64, f64, String, String)>`, so the layer pair is private
  from payload-build to emission.
- A `compile_fail` doctest on `Via` pins the structural guarantee: reading
  `via.from_layer` from an external crate must not compile. It runs under
  CI's `cargo test --doc --no-default-features` step (the struct and the
  re-export are deliberately unconditional, pyo3-free).

Emitted bytes are **unchanged** — the type token was already correct in
agent 65's output; this change only makes the correct computation
unavoidable. All differential suites (Rust vs pinned oracle, byte-for-byte)
pass without any oracle re-pin.

## The failure mode this closes

Pre-fix state (agent 58 → agent 65): vias were `(via (at ...) ...)` with no
type token → KiCad parses them as THROUGH → phantom copper on layers
outside the declared pair (16 phantom DRC shorts measured). Agent 65 added
the token via the free `via_type_token()` helper. Residual risk: the
payload type was still a bare tuple and the emission was a `format!` string
in one function; a second caller (or a refactor) could emit a via string
without ever calling the helper — the original bug's shape, one level up.

## What changed

### `packages/temper-orchestration/src/pipeline_route.rs`

- New `pub struct Via` (private fields) + `Via::new` constructor.
- `Via::via_type_token(&self) -> Option<&'static str>` — private; the
  classification rule verbatim from the removed free function (including
  the degenerate same-layer pair → no token, which keeps the pre-fix
  emission for a pair that "should not occur").
- `Via::emit_s_expr(py, net_num, tstamp) -> PyResult<String>` —
  `#[cfg(feature = "python")]`; renders floats through CPython `"{:.4f}"`
  (`py_fmt4`, the crate's bit-exactness convention) and ALWAYS calls
  `via_type_token` first. Output is byte-identical to agent 65's emission.
- `RouteEmission`'s vias element: `Vec<(f64, f64, f64, f64, String,
  String)>` → `Vec<Via>`.
- `run_build_route_payload` constructs `Via::new(...)` from the Python via
  duck-typed attributes (position/diameter/drill/from_layer/to_layer),
  exactly as before.
- `emit_route`'s via loop: `segments.push(via.emit_s_expr(py, *net_num,
  &seg_id)?)` — no format string left in the emission core.
- pyo3 boundary conversions (`IntoPyObject` / `FromPyObject`) so the
  marshalled payload can still round-trip through Python between
  `run_build_route_payload` and `run_write_route_segments` — the
  6-tuple wire format is unchanged; the conversions build a `Via`, they
  never expose fields or emit a sexpr.
- Tests:
  - 3 existing classification tests now exercise the method
    (`Via::new(...).via_type_token()`), same pairs, same expectations.
  - 3 new python-gated emission byte-pins:
    `emit_s_expr_full_stack_pair_has_no_type_token`,
    `emit_s_expr_outer_to_inner_emits_blind_token`,
    `emit_s_expr_inner_to_inner_emits_buried_token` — assert the exact
    sexpr bytes (through = no token, `F.Cu↔In3.Cu` = `blind`,
    `In1.Cu↔In3.Cu` = `buried`).
  - New `compile_fail` doctest on `Via` (private-field access from an
    external crate must not compile).
- Wasm test registry regenerated (`scripts/gen_wasm_test_registry.py
  --crate temper-orchestration`): 1022 → 1025 registered tests; the 3
  emission pins are registered with `#[cfg(feature = "python")]` guards
  exactly like the crate's other python-gated tests (structurally absent
  from wasm builds; the classification pins run everywhere).

### `packages/temper-orchestration/src/lib.rs`

- `pub use pipeline_route::Via;` — unconditional, so the `compile_fail`
  doctest is reachable from an external crate under CI's
  `cargo test --doc --no-default-features` invocation (a python-gated
  re-export would make the guarantee decorative there).

### Incidental fix: agent 65's change broke the wasm32 build

Agent 65's `via_type_token` was gated
`#[cfg(any(feature = "python", test))]`, but the tests module that calls it
compiles under `#[cfg(any(test, feature = "wasm-registry"))]` — so the
`wasm-registry` build (python and test both off) failed with 10×
`E0425: cannot find function via_type_token`. Verified on origin/main
before this change:

```
error[E0425]: cannot find function `via_type_token` in this scope
  --> src/pipeline_route.rs:1443:20   (×10, all in the tests module)
```

The nightly wasm tier (`wasm-tier-nightly.yml`, orchestration shard) would
have gone red on main. This change fixes it structurally: `Via` (and its
methods) are unconditional pure Rust, available in every configuration the
tests module compiles in. `cargo check --target wasm32-unknown-unknown
--no-default-features --features wasm-registry` now passes.

## Verification

| check | result |
|---|---|
| `cargo test --no-default-features --lib` (wasm-parity native arm) | 1064 passed |
| `cargo test --lib` (default features, live interpreter) | 1161 passed (incl. 3 emission byte-pins) |
| `cargo test --tests` (lib + all integration targets) | 1161 + integration, all passed (2 consecutive runs) |
| `cargo test --doc --no-default-features` (CI's doctest step) | compile_fail doctest: ok |
| `cargo test --doc` (default features) | compile_fail doctest: ok |
| `cargo check --target wasm32-unknown-unknown --no-default-features --features wasm-registry` | passes (was broken on main — see above) |
| `cargo clippy --all-features --all-targets -- -D warnings` | clean |
| `pytest tests/router_v6/` (isolated worktree venv, rebuilt extension) | 6804 passed; 24 failed — all pre-existing on origin/main (see below) |
| via/adapter differential + metamorphic + PBT + oracle suites | 184 passed, 1 skipped (byte-identical output vs pinned oracle) |
| `test_pipeline_route_rust_differential.py` | 41 passed |
| `scripts/check_oracle_hashes.py` | 167/167 OK — **no oracle re-pin needed** (output unchanged) |
| `scripts/import_linter_gate.py` | PASSED — 0 new violations |

### Pre-existing failures (identical on origin/main, unrelated)

The 24 failing `tests/router_v6/` tests are all in categories documented
before this change (agent 65's evidence doc, handoff §4): the stale
`nx.Graph` mock (`'Graph' object has no attribute 'is_connected'`,
handoff's PR #1199 trunk green-up), missing KiCad footprint library
directory (`test_phase1_anti_false_zero`, environment), net-name boundary
classification (HV/GND word-boundary churn), `initial_rotation` fixture
drift, real-board oracle pins (corridor scores, power islands, zone
counts), generated-table staleness (`temper.kicad_dru` absent → zone-pour
tables regenerate differently), a latency benchmark threshold, and the
6-layer stackup-role assertion. None of the failing test files reference
the via emission path (verified by grep: zero hits on
`run_write_route_segments` / `run_build_route_payload` /
`_write_routes_to_content` / `emit_route` / `Via`). The worktree's Python
sources are byte-identical to origin/main (only `.rs` files + the
generated registry changed), so these failures are origin/main's own.

### Oracle pin

`_adapter_convert_py_oracle.py` and `scripts/oracle_hashes.json` are
**unchanged**. The oracle mirrors the emitted *bytes*, and the bytes did
not move: the classification is verbatim, the format string is
byte-identical, and the differential suites pin Rust output against the
oracle byte-for-byte (184 passed). No re-pin, no `Ceiling-Approval`
trailer needed.

## Latent same-pattern risk (unchanged, re-stated)

The two legacy exporters named in the 2026-08-15 doc —
`io/kicad_exporter.py::add_vias_to_board` and
`io/_write_tracks.py::write_routes_to_pcb` — still create kiutils `Via`
objects without setting `type`. They have no production callers and remain
out of scope (YAGNI), but they are now the *only* remaining code in the
repo that can write a via without a type token. A future consumer that
re-activates either must route through the emission core or set `type`
itself.

## Files changed

- `packages/temper-orchestration/src/pipeline_route.rs` — `Via` struct
  (private fields) + `emit_s_expr`, free `via_type_token` removed,
  pyo3 boundary conversions, `Vec<Via>` payload, emission loop, tests
  (3 adapted + 3 emission byte-pins + compile_fail doctest)
- `packages/temper-orchestration/src/lib.rs` — `pub use pipeline_route::Via`
- `packages/temper-orchestration/src/wasm_test_registry.rs` — regenerated
  (1022 → 1025 registered)
- `docs/evidence/2026-08-16-via-emit-type-token-enforced.md` — this file
