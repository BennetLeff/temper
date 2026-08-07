#!/usr/bin/env python3
"""KTD8 spike: exact Rust EDT (Felzenszwalb-Huttenlocher) vs scipy parity + perf.

Context: docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md
re-triages ``scipy.ndimage.distance_transform_edt`` (673 LOC, three
``router_v6`` call sites) as a **BLOCKER** for removing Python. The prior
record, ``docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md``,
rejected the third-party ``edt`` crate (max diff 2.0-2.236 vs scipy -- an
*approximate* implementation) but never evaluated an exact algorithm. This
script is the differential + perf harness for
``packages/temper-geometry/src/edt.rs``'s ``exact_edt_transform`` (Rust,
Felzenszwalb-Huttenlocher separable lower-envelope EDT over squared
distances), built via ``maturin develop`` against a Python 3.12 venv.

It does not touch any of the three consumer call sites
(``channel_widths.py``, ``_astar_heuristics.py``, ``routability_check.py``)
-- per the spike brief, those are untouched.

Run:
    <venv>/bin/python tools/measurements/exact_edt_rust_spike.py

Requires ``temper_geometry`` built with the ``python`` feature into the
venv running this script (``maturin develop --release``), plus ``numpy``
and ``scipy``.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import distance_transform_edt as scipy_edt

import temper_geometry as tg


def rust_edt(mask: np.ndarray) -> np.ndarray:
    """Call the Rust exact EDT the same way a migrated call site would:
    one contiguous uint8 buffer in, one f64 buffer out, one FFI crossing."""
    h, w = mask.shape
    raw = tg.exact_edt_transform(np.ascontiguousarray(mask, dtype=np.uint8).tobytes(), h, w)
    return np.frombuffer(raw, dtype=np.float64).reshape(h, w)


@dataclass
class CaseResult:
    name: str
    shape: tuple[int, int]
    max_abs_diff: float
    n_differing: int
    n_cells: int
    n_finite_mismatch: int  # cells where finiteness itself disagrees
    notes: str = ""


@dataclass
class Corpus:
    results: list[CaseResult] = field(default_factory=list)

    def add(self, name: str, mask: np.ndarray, notes: str = "") -> None:
        s = scipy_edt(mask.astype(np.uint8))
        r = rust_edt(mask)

        s_finite = np.isfinite(s)
        r_finite = np.isfinite(r)
        finite_mismatch = int(np.sum(s_finite != r_finite))

        both_finite = s_finite & r_finite
        if np.any(both_finite):
            diff = np.abs(s[both_finite] - r[both_finite])
            max_diff = float(diff.max())
            n_differing = int(np.sum(diff > 0))
        else:
            max_diff = 0.0
            n_differing = 0

        self.results.append(
            CaseResult(
                name=name,
                shape=mask.shape,
                max_abs_diff=max_diff,
                n_differing=n_differing,
                n_cells=int(mask.size),
                n_finite_mismatch=finite_mismatch,
                notes=notes,
            )
        )


def build_corpus() -> Corpus:
    c = Corpus()
    rng = np.random.default_rng(20260807)

    # --- Degenerate / structural cases -------------------------------
    c.add("empty (all background, 20x30)", np.zeros((20, 30), dtype=bool),
          "every cell is a source; expect all zeros")
    c.add("full (all foreground, 20x30)", np.ones((20, 30), dtype=bool),
          "NO background cell anywhere -- degenerate, see finiteness note")
    c.add("full (all foreground, 5x5)", np.ones((5, 5), dtype=bool), "small full-grid case")
    c.add("full (all foreground, 1x1)", np.ones((1, 1), dtype=bool), "")
    c.add("empty (all background, 1x1)", np.zeros((1, 1), dtype=bool), "")

    mask = np.ones((25, 25), dtype=bool)
    mask[12, 12] = False
    c.add("single seed, centered (25x25)", mask, "")

    mask = np.ones((25, 25), dtype=bool)
    mask[0, 0] = False
    c.add("single seed, corner (25x25)", mask, "")

    mask = np.ones((40, 40), dtype=bool)
    for r, cc in [(0, 0), (39, 39), (10, 15), (3, 27), (20, 2), (39, 0), (0, 39)]:
        mask[r, cc] = False
    c.add("sparse seeds (40x40, 7 seeds)", mask, "")

    for density, label in [(0.05, "sparse"), (0.3, "medium"), (0.5, "dense")]:
        mask = rng.random((60, 80)) >= density
        c.add(f"random {label} (density={density}, 60x80)", mask, "")

    # thin diagonal feature: a 1-cell-wide diagonal background line
    mask = np.ones((50, 50), dtype=bool)
    for i in range(50):
        mask[i, i] = False
    c.add("thin diagonal feature (50x50)", mask, "")

    # thin diagonal foreground line surrounded by background
    mask = np.zeros((50, 50), dtype=bool)
    for i in range(50):
        mask[i, i] = True
    c.add("thin diagonal foreground line on background (50x50)", mask, "")

    # all-background row and column
    mask = rng.random((45, 55)) >= 0.4
    mask[20, :] = False
    mask[:, 30] = False
    c.add("all-background row+column embedded in random (45x55)", mask, "")

    mask = np.ones((30, 30), dtype=bool)
    mask[0, :] = False
    c.add("all-background top row only (30x30)", mask, "")

    mask = np.ones((30, 30), dtype=bool)
    mask[:, -1] = False
    c.add("all-background rightmost column only (30x30)", mask, "")

    # non-square aspect ratios
    c.add("very wide (5x400)", rng.random((5, 400)) >= 0.3, "")
    c.add("very tall (400x5)", rng.random((400, 5)) >= 0.3, "")
    c.add("wide, all foreground except border (5x400)",
          _border_mask(5, 400), "")

    # ring / annulus (common shape from polygon-with-hole rasterization)
    c.add("annulus (80x80)", _annulus_mask(80, 80), "")

    # checkerboard (worst case for column/row source density)
    yy, xx = np.mgrid[0:40, 0:40]
    checker = ((yy + xx) % 2) == 0
    c.add("checkerboard (40x40)", checker, "background is odd/even parity")

    # --- Real consumer grid shapes -------------------------------------
    # cell_size = 0.1mm is used at every EDT-building call site
    # (channel_widths.py::compute_channel_widths, _astar_heuristics.py::
    # _build_edt_from_grid's caller default, capacity_check.py's
    # _EDT_CELL_SIZE). Board extents: pcb/temper.kicad_pcb's Edge.Cuts
    # bounding box is ~185.3mm x 287.5mm; RoutingSpace.available_area
    # falls back to width=height=100mm when board dims are unset
    # (_adapter_core.py:273-274). Both are exercised below.
    cell_size = 0.1
    for label, w_mm, h_mm in [
        ("default fallback board (100x100mm)", 100.0, 100.0),
        ("real production board (~185x288mm)", 185.3, 287.5),
    ]:
        w = int(np.ceil(w_mm / cell_size)) + 1
        h = int(np.ceil(h_mm / cell_size)) + 1
        # A routing-area-shaped mask: an outer rounded rectangle minus a
        # scatter of component keepout holes, roughly matching what
        # _rasterize_boundary_mask / OccupancyGrid produce (mostly-True
        # interior, False boundary ring, False circular keepouts).
        m = _routing_area_like_mask(h, w, rng)
        c.add(f"real call-site shape: {label} [{h}x{w}]", m, "")

    return c


def _border_mask(h: int, w: int) -> np.ndarray:
    m = np.ones((h, w), dtype=bool)
    m[0, :] = False
    m[-1, :] = False
    m[:, 0] = False
    m[:, -1] = False
    return m


def _annulus_mask(h: int, w: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h / 2, w / 2
    d = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_outer, r_inner = min(h, w) * 0.45, min(h, w) * 0.2
    return (d <= r_outer) & (d >= r_inner)


def _routing_area_like_mask(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    m = np.ones((h, w), dtype=bool)
    m[0, :] = False
    m[-1, :] = False
    m[:, 0] = False
    m[:, -1] = False
    n_holes = max(1, (h * w) // 20000)
    for _ in range(n_holes):
        cy = rng.integers(5, h - 5)
        cx = rng.integers(5, w - 5)
        rad = rng.integers(3, 25)
        y0, y1 = max(0, cy - rad), min(h, cy + rad)
        x0, x1 = max(0, cx - rad), min(w, cx + rad)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d2 = (yy - cy) ** 2 + (xx - cx) ** 2
        m[y0:y1, x0:x1][d2 <= rad * rad] = False
    return m


def print_corpus_summary(c: Corpus) -> None:
    print(f"{'case':<55} {'shape':>14} {'max|diff|':>12} {'ndiff':>8} {'ncells':>10} {'finite-mismatch':>16}")
    for r in c.results:
        print(
            f"{r.name:<55} {str(r.shape):>14} {r.max_abs_diff:>12.3e} "
            f"{r.n_differing:>8} {r.n_cells:>10} {r.n_finite_mismatch:>16}"
        )

    overall_max = max((r.max_abs_diff for r in c.results), default=0.0)
    overall_ndiff = sum(r.n_differing for r in c.results)
    overall_ncells = sum(r.n_cells for r in c.results)
    overall_finite_mismatch = sum(r.n_finite_mismatch for r in c.results)
    print()
    print(f"corpus size (cases):          {len(c.results)}")
    print(f"corpus size (cells):          {overall_ncells}")
    print(f"max abs diff (both finite):   {overall_max:.6e}")
    print(f"differing cells (both finite):{overall_ndiff}")
    print(f"finiteness mismatches:        {overall_finite_mismatch}")


def stress_random(n_trials: int = 300, seed: int = 42) -> dict:
    """Bulk random differential: many small/medium grids at varied density,
    independent of the curated corpus above. Reports aggregate agreement
    stats only (per-trial detail would be noise at this volume)."""
    rng = np.random.default_rng(seed)
    max_diff = 0.0
    n_diff_total = 0
    n_cells_total = 0
    n_finite_mismatch_total = 0
    for _ in range(n_trials):
        h = int(rng.integers(2, 120))
        w = int(rng.integers(2, 120))
        density = rng.choice([0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98])
        mask = rng.random((h, w)) < density
        s = scipy_edt(mask.astype(np.uint8))
        r = rust_edt(mask)
        sf, rf = np.isfinite(s), np.isfinite(r)
        n_finite_mismatch_total += int(np.sum(sf != rf))
        both = sf & rf
        n_cells_total += mask.size
        if np.any(both):
            d = np.abs(s[both] - r[both])
            max_diff = max(max_diff, float(d.max()))
            n_diff_total += int(np.sum(d > 0))
    return {
        "trials": n_trials,
        "total_cells": n_cells_total,
        "max_abs_diff": max_diff,
        "n_differing_cells": n_diff_total,
        "n_finite_mismatch": n_finite_mismatch_total,
    }


def benchmark(shapes: list[tuple[str, int, int]], reps: int = 5) -> list[dict]:
    rng = np.random.default_rng(1)
    rows = []
    for label, h, w in shapes:
        mask = _routing_area_like_mask(h, w, rng)
        mask_u8 = np.ascontiguousarray(mask, dtype=np.uint8)

        # scipy timing: pure compute, matches how the three call sites use it
        # (they pass a numpy uint8 array already resident in the process).
        t0 = time.perf_counter()
        for _ in range(reps):
            s = scipy_edt(mask_u8)
        t_scipy = (time.perf_counter() - t0) / reps

        # Rust timing INCLUDING the Python<->Rust boundary crossing: bytes
        # serialization in, bytes deserialization out, exactly what a real
        # call site pays if migrated (tobytes() + frombuffer(), not a
        # zero-copy buffer protocol).
        t0 = time.perf_counter()
        for _ in range(reps):
            raw = tg.exact_edt_transform(mask_u8.tobytes(), h, w)
            r = np.frombuffer(raw, dtype=np.float64).reshape(h, w)
        t_rust = (time.perf_counter() - t0) / reps

        assert np.abs(s - r).max() < 1e-9, f"{label}: rust/scipy diverge under benchmark"

        rows.append(
            {
                "label": label,
                "shape": [h, w],
                "n_cells": h * w,
                "scipy_seconds": t_scipy,
                "rust_incl_ffi_seconds": t_rust,
                "speedup": t_scipy / t_rust if t_rust > 0 else float("inf"),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None, help="write machine-readable results here")
    args = ap.parse_args()

    print("=== KTD8 exact-EDT parity corpus ===")
    corpus = build_corpus()
    print_corpus_summary(corpus)

    print()
    print("=== KTD8 bulk random differential (300 trials, varied size/density) ===")
    stress = stress_random()
    for k, v in stress.items():
        print(f"{k}: {v}")

    print()
    print("=== Benchmark: scipy vs Rust (incl. FFI boundary crossing) ===")
    shapes = [
        ("small (100x100 cells, e.g. a coarse test fixture)", 100, 100),
        ("default-fallback board @ 0.1mm cell (100x100mm -> 1001x1001)", 1001, 1001),
        ("real production board @ 0.1mm cell (~185x288mm -> ~1854x2876)", 1854, 2876),
    ]
    bench_rows = benchmark(shapes, reps=5)
    for row in bench_rows:
        print(
            f"{row['label']:<60} n_cells={row['n_cells']:>9} "
            f"scipy={row['scipy_seconds']*1000:>9.3f}ms "
            f"rust(+ffi)={row['rust_incl_ffi_seconds']*1000:>9.3f}ms "
            f"speedup={row['speedup']:.2f}x"
        )

    if args.json_out:
        out = {
            "corpus": [r.__dict__ for r in corpus.results],
            "stress_random": stress,
            "benchmark": bench_rows,
        }
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
