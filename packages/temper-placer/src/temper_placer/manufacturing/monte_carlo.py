"""
Monte Carlo simulation for statistical tolerance analysis.

This module provides tools to estimate yield probability and identify
manufacturing failure modes using statistical sampling of process variations.

The implementation migrated to Rust (``temper_design_bundle_python``,
``manufacturing_monte_carlo.rs``) under the Wave 4 Phase 4 leftovers slice —
the home crate is ``temper-design-bundle`` (the data-contract home; the
sibling ``manufacturing/tolerances.py`` migration landed there). This module
keeps the pre-migration public API unchanged and re-exports the Rust
pyclasses directly (the pure-delegation pattern established by
``core/loop.py``, ``core/priority.py`` and ``manufacturing/tolerances.py``).

Two KTD9 boundaries stay Python-side (argued in
``packages/temper-design-bundle/src/manufacturing_monte_carlo.rs`` and
``packages/temper-design-bundle/VERIFICATION.md``):

- **The RNG stream**: ``np.random.default_rng(seed)`` (PCG64 + Ziggurat) is
  created and advanced by numpy itself on both sides — the pyclass stores
  the numpy ``Generator`` as ``_rng`` and every draw is a Python call with
  the oracle's exact arguments in the oracle's exact order. Same seed ⇒
  same samples, bit-for-bit.
- **The statistical aggregations**: ``np.mean``/``np.std``/``astype`` use
  numpy's pairwise summation whose block size is SIMD-dispatch-dependent
  (build and platform), so they run through numpy on both sides. The
  migrated compute is the [S,N,N] clearance kernel (expansion, pairwise
  separations, ``np.maximum``, the 1e6 self-comparison mask, exact min
  reduction) — every elementwise op is a single IEEE-754 double operation
  with the oracle's parenthesization, proven bit-exact in VERIFICATION.md.

Verification: bit-identical parity against the pinned pre-migration
implementation — including the concrete Python type of every field, the
``(dtype, shape, tobytes())`` of every sampled array, ``float.hex()`` of
every statistic, the exact ``ValueError``/``IndexError`` texts, and the
error-path RNG stream state — is asserted by
``tests/manufacturing/test_monte_carlo_rust_differential.py`` (oracle:
``tests/manufacturing/_monte_carlo_py_oracle.py``) and the closed-form
properties in ``tests/manufacturing/test_monte_carlo_pbt.py``.

Deliberately NOT migrated (R3 verdict, named blocker)
-----------------------------------------------------
Nothing in this module stays Python: the whole surface is the five pyclasses
below (the numpy Generator is a stored field, not module compute). The
documented deviations (fresh default ``MonteCarloConfig`` per simulator;
the ndim ≥ 3 input envelope) are recorded in VERIFICATION.md.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

DistributionParams = _tdb.DistributionParams
ManufacturingVariables = _tdb.ManufacturingVariables
MonteCarloConfig = _tdb.MonteCarloConfig
MonteCarloResult = _tdb.MonteCarloResult
MonteCarloSimulator = _tdb.MonteCarloSimulator

__all__ = [
    "DistributionParams",
    "ManufacturingVariables",
    "MonteCarloConfig",
    "MonteCarloResult",
    "MonteCarloSimulator",
]
