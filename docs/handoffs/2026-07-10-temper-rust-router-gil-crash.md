# Rust Router Debugging Handoff — `temper_rust_router` GIL Crash

Date: 2026-07-10
Issue: [#174](https://github.com/BennetLeff/temper/issues/174)
Blocker for: first complete routed temper board → first real helps-battery verdict

## Symptom

```
Fatal Python error: PyInterpreterState_Get: the function must be called with the GIL held,
after Python initialization and before Python finalization, but the GIL is released
```

## Reproduction

```bash
cd packages/temper-rust-router
cargo clean
maturin develop --release
python3 -c "import temper_rust_router"  # crashes 100%
```

Build succeeds (2 warnings). Crash is at Python `import` time — not during `cargo build`, not during `maturin`.

## What was ruled out

- **Not a stale build**: reproduces after `cargo clean` + fresh `maturin develop`.
- **Not a Cargo.toml drift**: reverting to the last known-working commit's Cargo.toml + Cargo.lock does not fix it.
- **Not a source-code regression**: reverting `src/` to the last known-working commit does not fix it.
- **Not fixable with Python patches**: wrapping imports in try/except doesn't help (crash is at PyO3 init, not at function call).
- **Not `maturin develop` specific**: building a wheel and installing it directly produces the same crash.
- **Ruled out as a Python venv issue**: both uv venv and conda produce the same crash.

## Root cause hypothesis

pyo3 0.23 introduced a GIL-acquisition change that conflicts with how the CP-SAT placer's Python interpreter state is set up on macOS arm. The `#[pymodule]` init function runs in a context where the GIL is released — `pyo3::prepare_freethreaded_python()` would be the fix if callable before module init, but the module init is triggered by `import`, and the crash happens before any user code runs.

## Most promising debugging path

**Downgrade pyo3 0.23 → 0.22**. This requires also downgrading edition 2024 → 2021:

```toml
# Cargo.toml
[package]
edition = "2021"    # was "2024"

[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }  # was "0.23"
```

pyo3 0.22 is known to work on macOS arm without this GIL issue. The tradeoff: edition 2021 may require minor source tweaks (async fn in traits, RPIT lifetime capture changes, etc.). Most edition 2024 features are opt-in and the crate is unlikely to use them heavily.

**If downgrade breaks**: check `types_py_bridge.rs` and `loop_extractor/bridge.rs` — these are the most likely files to use edition-2024 features (new `use<>` syntax, `impl Trait` changes). The `lib.rs` safisfies are standard pyo3 patterns that work identically under 0.22.

## Build + test after fix

```bash
cd packages/temper-rust-router
cargo clean && maturin develop --release
python3 -c "import temper_rust_router; print('OK')"  # must succeed

# Then route the board:
cd ../..
uv run temper-placer optimize pcb/temper.kicad_pcb \
  -c /tmp/temper_constraints.yaml \
  -o /tmp/temper_routed.kicad_pcb \
  --seed 42 --epochs 5

# Then run the helps-battery on it:
python3 -c "
from temper_placer.validation.results.battery_run import run_thermal_helps_battery
# ... wire the routed PCB through the battery
"
```

## What's waiting on the other side

Once the router produces a complete routed temper board:
- The helps-battery can render its first real `KEEP` / `KILL` / `INCONCLUSIVE` verdict on real copper.
- ~500 verification tests are green and the safety-path inputs are de-garbaged (copper, power, heatsink, R_θSA).
- The three-target verification ladder (correctness/soundness/validity) is complete except for the hardware power-on measurement (deferred).
- Everything merged to `main` via #172.
