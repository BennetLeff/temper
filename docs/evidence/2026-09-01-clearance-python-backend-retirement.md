<!-- provenance: commit=96baf2dcd8d7d036d38e7cc656709106a6788762 dirty=true (implementation and test evidence recorded against the merged main base; the worktree contained the Rust-only clearance diff when these checks ran) -->

# Clearance Python backend retirement

Date: 2026-09-01

## Change

`temper_placer.router_v6.clearance_check.verify_clearance` now has one
production implementation: the Rust clearance path. The compatibility
selector accepts `auto` and `rust` as equivalent selectors, while
`backend="python"` raises a retirement error. If either Rust extension symbol
is unavailable, verification fails closed instead of silently calculating in
Python. The old production Python geometry and clearance helpers were
deleted; the immutable pre-migration oracle remains test-only.

## Red-before evidence

Before the production change, the strengthened fail-closed test was run with
each required symbol independently disabled:

```text
uv run --no-sync pytest packages/temper-placer/tests/router_v6/test_clearance_check.py -q -k fails_closed_without_complete_rust_backend
4 failed
```

The old `auto` path silently returned a report, and the old `rust` path raised
only its incomplete-backend message. This established that the test exercised
the retired fallback behavior before the implementation changed.

## Proof and verification

- `test_clearance_rust_differential.py` compares production Rust directly
  against `_clearance_family_py_oracle._verify_clearance_python`.
- The fail-closed tests independently cover a missing
  `temper_drc_rs.verify_route_clearance` symbol and a missing
  `temper_orchestration.run_clearance_check` symbol, plus the retired Python
  selector.
- The presence gate derives and checks registered symbols from both Rust
  extension modules.
- Focused clearance, boundary, scale, induction, family differential,
  property, and metamorphic tests passed; the oracle hash, manifest,
  import-boundary, Rust extension freshness, and changed-file Ruff checks
  passed as well.
