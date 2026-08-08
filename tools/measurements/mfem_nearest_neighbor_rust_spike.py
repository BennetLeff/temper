#!/usr/bin/env python3
"""Perf spike: Rust nearest-neighbor lookup (``rstar`` R*-tree, via
``temper_geometry.nearest_neighbor_transform``) vs
``scipy.interpolate.griddata(method="nearest")`` -- the primitive behind
``validation/mfem_compare.py``'s ``project_mfem_to_fdm``.

Context: ``docs/evidence/2026-08-07-scipy-keeps-re-triage.md`` Sec 4 flagged
this call site PORTABLE, low priority, and predicted -- from call shape
alone, before measuring -- that it would land in the same "one-shot batch
slower than scipy's C" band as ``radius_pairs.rs`` (1.8-2.0x) and
``connected_components.rs`` (1.0-2.6x), not the persistent-structure band
(``persistent_radius_index.rs``, 3.4-20x FASTER) -- because
``project_mfem_to_fdm`` builds a tree once and queries it once per call (a
board evaluation), never reusing a standing index across many calls. This
script measures that prediction against scipy at representative scale.

No real MFEM run is available in this environment (external MFEM binary is
not installed, matching the "likely unavailable in most CI/dev
environments" framing the migration evidence doc's own low-priority
argument rests on) -- this uses synthetic mesh-node and FDM-grid point
counts drawn from the production defaults actually present in this repo:
- ``ThermalFDMConfig``'s own module-level default grid,
  ``physics/thermal_fdm.py``: ``height_cells=100, width_cells=200`` (20,000
  query points).
- ``mfem_gate.py``'s gate-time config: ``height_cells=min(50, board.height)``
  / ``width_cells=min(50, board.width)`` (up to 2,500 query points) -- the
  actual call site's own config, generally smaller than the module default.
- Mesh node counts (500, 2,000, 5,000) span plausible coarse-to-moderate
  tetrahedral mesh densities for a board-scale domain; no production count
  is on record since no MFEM run has been captured in this repo yet.

Run:
    <venv>/bin/python tools/measurements/mfem_nearest_neighbor_rust_spike.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import temper_geometry as tg
from scipy.interpolate import griddata

REPO_ROOT = Path(__file__).resolve().parents[2]


def _scipy_nearest(src: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    return griddata(src, values, query, method="nearest", rescale=False)


def _rust_nearest(src: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    src_c = np.ascontiguousarray(src, dtype=np.float64)
    query_c = np.ascontiguousarray(query, dtype=np.float64)
    idx_bytes = tg.nearest_neighbor_transform(
        src_c.tobytes(), len(src_c), query_c.tobytes(), len(query_c)
    )
    idx = np.frombuffer(idx_bytes, dtype="<i8")
    return values[idx]


def _best_of(fn, *args, n=5) -> float:
    best = float("inf")
    for _ in range(n):
        t0 = time.perf_counter()
        fn(*args)
        best = min(best, time.perf_counter() - t0)
    return best


def main() -> None:
    rng = np.random.RandomState(0)
    cases = [
        ("n_src=500, grid=50x50 (mfem_gate min-cap)", 500, (50, 50)),
        ("n_src=2000, grid=50x50 (mfem_gate min-cap)", 2000, (50, 50)),
        ("n_src=2000, grid=100x200 (thermal_fdm default)", 2000, (100, 200)),
        ("n_src=5000, grid=100x200 (thermal_fdm default)", 5000, (100, 200)),
    ]

    results = []
    for label, n_src, (h, w) in cases:
        n_query = h * w
        src = rng.uniform(0, 200, size=(n_src, 2))
        values = rng.uniform(20.0, 120.0, size=n_src)
        query = rng.uniform(-10, 210, size=(n_query, 2))

        # Correctness check alongside the timing (same corpus).
        rust_out = _rust_nearest(src, values, query)
        scipy_out = _scipy_nearest(src, values, query)
        agree = bool(np.array_equal(rust_out, scipy_out))

        scipy_t = _best_of(_scipy_nearest, src, values, query)
        rust_t = _best_of(_rust_nearest, src, values, query)

        row = {
            "case": label,
            "n_src": n_src,
            "n_query": n_query,
            "values_agree": agree,
            "scipy_s": scipy_t,
            "rust_s": rust_t,
            "rust_over_scipy": rust_t / scipy_t if scipy_t > 0 else None,
        }
        results.append(row)
        print(
            f"{label:55s} scipy={scipy_t*1000:8.3f}ms rust={rust_t*1000:8.3f}ms "
            f"ratio={row['rust_over_scipy']:.2f}x agree={agree}"
        )

    out_path = REPO_ROOT / "tools" / "measurements" / "mfem_nearest_neighbor_rust_spike_results.json"
    out_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
