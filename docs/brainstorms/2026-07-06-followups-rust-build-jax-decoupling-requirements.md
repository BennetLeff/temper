---
date: "2026-07-06"
topic: followups-rust-build-jax-decoupling
---

# Follow-Up: Portable Rust Build + Final JAX Decoupling

Two low-scope fixes that close the remaining edges of the umbrella.

---

## Problem Frame

Two machine-specific or incomplete artifacts from the paradigm swap:

1. **Rust rpath is machine-specific.** `RUSTFLAGS='-C link-arg=-Wl,-rpath,/Users/bennet/Miniforge3/lib'` hardcodes a home directory. CI and other developers on different Python installs (brew, pyenv, system) can't build `temper_rust_router` without manually discovering and setting the rpath. The compound learning at `docs/solutions/build-errors/stale-rust-build-artifacts-gil-crash-2026-07-06.md` documents the symptom but not the portable fix.

2. **12 files still import JAX at function level.** These are the strangler's tail from the JAX Retirement workstream (F1 of the umbrella) — located across `geometry/`, `algo/`, `core/`, `extraction/`, `cli/`, `profiling/`, `manufacturing/`, and `regression/`. They use `jax.lax.scan`, `jax.vmap`, `jax.grad`, `jax.experimental.sparse` inside function bodies. `pyproject.toml` carries JAX as a dependency solely for these survivors. The round-2 review flagged this as the "highest-risk refactor in umbrella" (residual concern #3).

---

## Requirements

### R1 — Portable Rust rpath

The `temper_rust_router` and `temper_constraint_compiler` crates must build on any developer's machine (brew Python, pyenv Python, conda Python) and in CI without manual `RUSTFLAGS` configuration.

**Approach:** Extend the existing `build.rs` in `temper-rust-router` (which already auto-detects LIBDIR via `sysconfig` for `cargo:rustc-link-search`) to also emit `cargo:rustc-link-arg=-Wl,-rpath,<lib_dir>` for runtime library resolution. Add an equivalent `build.rs` to `temper-constraint-compiler`.

**Success criteria:**
- `cargo clean && maturin develop` succeeds on a fresh checkout without setting `RUSTFLAGS`
- CI builds pass without hardcoded paths
- The compound learning doc is updated to note the fix

### R2 — Final JAX decoupling

Eliminate all 12 remaining JAX imports so `pyproject.toml` can drop `jax`, `jaxlib`, `optax`, and `flax` from dependencies.

**Approach:** Two-phase:
1. Audit callers of each JAX-dependent function. Delete dead code (functions with zero callers).
2. For live callers, replace JAX operations with numpy/Python equivalents:
   - `jax.lax.scan` → Python `for` loop
   - `jax.vmap` → `np.vectorize` or list comprehension
   - `jax.grad` → finite-difference (`scipy.optimize.approx_fprime`) — only if callers exist
   - `jax.nn.sigmoid` → `1/(1+np.exp(-x))`
   - `jax.lax.stop_gradient` → identity (no-op in eager mode)
   - `jax.random.uniform` → `np.random.default_rng().uniform()`
   - `jax.experimental.sparse.BCOO` → `scipy.sparse.coo_matrix`

**Success criteria:**
- `rg "import jax|from jax" packages/temper-placer/src/` returns zero matches
- `pyproject.toml` drops `jax>=0.4.20`, `jaxlib>=0.4.20`, `optax>=0.1.7`, `flax>=0.7.0`
- `uv sync` succeeds without JAX
- Existing tests pass (any tests exercising the decoupled functions)
- The `pyproject.toml` TODO comment tracking the 12 files is removed

---

## Scope Boundaries

### In scope
- `build.rs` extension for `temper_rust_router`, new `build.rs` for `temper_constraint_compiler`
- 12 JAX-importing files across `geometry/`, `algo/`, `core/`, `extraction/`, `cli/`, `profiling/`, `manufacturing/`, `regression/`
- `pyproject.toml` dependency cleanup

### Outside scope
- Replacing JAX autodiff in functions that have callers and need it — stub or mark as `NotImplementedError`
- `temper_drc_rs` build fix (already has a separate build failure, not related to rpath)
- Any performance regression from numpy-for-JAX substitutions (correctness first)

---

## Outstanding Questions

### Resolve Before Planning

_None — both problems are well-understood. The build script approach is deterministic; the JAX decoupling is a known quantity from the F1 PlacementState migration._

### Deferred to Implementation

- Whether `sdf.py::sdf_gradient()` has callers — determines whether it needs numpy finite-difference replacement or deletion
- Whether `jax.experimental.sparse.BCOO` callers in hypergraph modules can use `scipy.sparse` without algorithmic changes
