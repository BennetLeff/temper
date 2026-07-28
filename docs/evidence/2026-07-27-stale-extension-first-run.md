# The stale-extension gate's first real run: 7 of 10 crates stale

<!-- provenance: commit=0b19a584b9203838f30d992f488b2ecc977c0ad6 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Gate:** `scripts/check_stale_extensions.py` (merged in `f1c8f5b7`)

## What it found immediately

First run against a clean tree: **exit 3, 10 crates discovered, 10 checked,
7 stale.** Two of those matter beyond housekeeping.

| Crate | Installed artifact | Source moved | Stale by |
|---|---|---|---|
| `temper_rust_router` | 2026-06-29 | 2026-07-27 | **28.2 days** |
| `temper_constraint_compiler` | 2026-07-06 | 2026-07-27 | **21.0 days** |
| `temper_quality_oracle` | 2026-07-09 | 2026-07-24 | 15.0 days |
| `temper_dsn` | 2026-07-13 | 2026-07-23 | 10.0 days |
| `temper_geometry` | 2026-07-15 | 2026-07-24 | 9.0 days |
| `temper_design_bundle_python` | 2026-07-17 | 2026-07-24 | 7.0 days |
| `temper_ipc` | 2026-07-22 | 2026-07-23 | 0.8 days |

All seven rebuilt; gate now exits 0. The two fixed by hand earlier
(`temper_io_types`, `temper_drc_rs`) were already reported `[OK]`, which is a
small independent confirmation that the gate reads freshness correctly rather
than always alarming.

## Why the top two are not housekeeping

Both are on the routing hot path, not optional accelerators:

```
packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py
  :289  from temper_rust_router import solve_topology_rust_bundled
  :310  from temper_rust_router import solve_topology_rust
  :405  from temper_rust_router import audit_result
  :72   from temper_constraint_compiler import (...)
```

`temper_constraint_compiler`'s staleness was triggered by
`packages/temper-rust-router-core/src/combinator/rewrite.rs` — the exact file
whose `cap_infos.iter().find(...)` → `cap_infos.get(orig_idx)` change was made
**today**. That change was therefore never in the binary Python imported.

## What this calls into question

Routing measurements taken earlier today ran against a **June 29** router
binary while the source had moved to July 27. Specifically:

- the 37/96 = 38.5% completion figure,
- the 500k → 4,000,000 iteration-cap sweep,
- the determinism runs,
- the bundled-encoding work wired up today.

**What still stands regardless.** The mechanism finding for the 45 unrouted
nets is unaffected: `_allow_forced_segments()` is hard-coded `False` in
`router_v6/_astar_reconstruct.py`, which is **Python**, not Rust. The
fail-closed argument does not depend on any extension.

**What must be re-measured**: the completion rate and the cap sweep, because
both exercised `solve_topology_rust`.

## UNVERIFIED

- Whether the June 29 binary is *functionally* different from the current
  source, or merely older. Staleness by mtime proves the artifact was not
  rebuilt; it does not by itself prove behaviour changed. The re-measurement
  above is what would settle it.
- Whether the three in-flight DRC burn-down agents inherited the same
  staleness in their own worktree `.venv`s. Their briefs required each to
  establish its own baseline across N>=4 runs before claiming any improvement,
  so their before/after comparisons remain internally valid even if their
  absolute numbers differ from the 24 / 33 / 16 quoted to them.

## Lesson

The gate found in one run a class of defect that had been accumulating for a
month across seven crates. Two independent failures had to combine to hide it:
the macOS link failure (no `.cargo/config.toml`) meant rebuilds silently could
not happen, and `cargo test` linking libpython normally meant the Rust suites
stayed green and were mistaken for evidence about the installed artifact.
