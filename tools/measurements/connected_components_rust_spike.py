#!/usr/bin/env python3
"""KTD8 follow-up spike: exact Rust 8-connected component labeling
(union-find raster scan) vs ``scipy.ndimage.label`` -- parity + perf.

Context: ``routability_check.py``'s ``check_routability_cc`` is the last
scipy binding in that module (see
``docs/evidence/2026-08-07-exact-edt-rust-spike.md`` Sec 3/7, which
explicitly left this out of scope). It calls
``scipy.ndimage.label(passable_mask, structure=np.ones((3, 3), dtype=bool))``
-- 8-connected connected-component labeling, not the 4-connected default.
This script is the differential + perf harness for
``packages/temper-geometry/src/connected_components.rs``'s
``connected_components_8_transform`` (Rust, two-pass union-find raster
scan), built via ``maturin develop`` against a Python 3.12 venv.

It does not touch the production call site (``routability_check.py``) --
this script only measures.

Run:
    <venv>/bin/python tools/measurements/connected_components_rust_spike.py

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
import temper_geometry as tg
from scipy.ndimage import label as scipy_label

_STRUCTURE_8 = np.ones((3, 3), dtype=bool)


def rust_label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Call the Rust labeler the same way a migrated call site would: one
    contiguous uint8 buffer in, one i32 label buffer + a feature count out,
    one FFI crossing."""
    h, w = mask.shape
    raw_bytes, num_features = tg.connected_components_8_transform(
        np.ascontiguousarray(mask, dtype=np.uint8).tobytes(), h, w
    )
    labels = np.frombuffer(raw_bytes, dtype=np.int32).reshape(h, w)
    return labels, int(num_features)


def partitions_equal(a: np.ndarray, b: np.ndarray) -> tuple[bool, str]:
    """Renumbering-invariant partition comparison: True iff `a` and `b`
    describe the same set of connected components, independent of which
    numeric label each component happens to carry (label VALUES are not
    part of the consumer's contract -- see the evidence doc's Sec 2). O(n
    log n) via a stable sort, not O(n^2) -- usable at real board scale.

    Checks:
      1. Background (label == 0) cells match exactly in both.
      2. The induced label_a -> label_b mapping restricted to foreground
         cells is a well-defined function (every cell with a given `a`
         label maps to the same `b` label) AND injective (no two distinct
         `a` labels map to the same `b` label) -- together this is exactly
         "same partition."
    """
    if a.shape != b.shape:
        return False, "shape mismatch"
    a = a.ravel()
    b = b.ravel()
    a_bg = a == 0
    b_bg = b == 0
    if not np.array_equal(a_bg, b_bg):
        return False, "background (label==0) cells differ"

    af = a[~a_bg]
    bf = b[~a_bg]
    if af.size == 0:
        return True, "no foreground cells"

    order = np.argsort(af, kind="stable")
    af_sorted = af[order]
    bf_sorted = bf[order]
    boundaries = np.nonzero(np.diff(af_sorted))[0] + 1
    groups_b = np.split(bf_sorted, boundaries)

    reps = []
    for g in groups_b:
        if g.max() != g.min():
            return False, "one `a` component maps to multiple `b` labels (not a function)"
        reps.append(int(g[0]))
    if len(set(reps)) != len(reps):
        return False, "two distinct `a` components map to the same `b` label (not injective)"
    return True, "ok"


@dataclass
class CaseResult:
    name: str
    shape: tuple[int, int]
    scipy_num_features: int
    rust_num_features: int
    partition_match: bool
    partition_note: str
    exact_label_match: bool  # bonus: raw numeric equality, not required by contract
    n_cells: int


@dataclass
class Corpus:
    results: list[CaseResult] = field(default_factory=list)

    def add(self, name: str, mask: np.ndarray) -> None:
        s_labels, s_n = scipy_label(mask.astype(np.uint8), structure=_STRUCTURE_8)
        r_labels, r_n = rust_label(mask)
        ok, note = partitions_equal(s_labels.astype(np.int64), r_labels.astype(np.int64))
        exact = bool(np.array_equal(s_labels, r_labels))
        self.results.append(
            CaseResult(
                name=name,
                shape=mask.shape,
                scipy_num_features=int(s_n),
                rust_num_features=r_n,
                partition_match=ok,
                partition_note=note,
                exact_label_match=exact,
                n_cells=int(mask.size),
            )
        )


def _border_mask(h: int, w: int) -> np.ndarray:
    m = np.ones((h, w), dtype=bool)
    m[0, :] = False
    m[-1, :] = False
    m[:, 0] = False
    m[:, -1] = False
    return m


def _spiral_mask(h: int, w: int) -> np.ndarray:
    """Rectangular spiral arm with gap rows/columns -- exercises the
    union-find "conflict" resolution: a naive single-pass-without-union
    scan mislabels a spiral because the arm touches itself again several
    rows later."""
    mask = np.zeros((h, w), dtype=np.uint8)
    top, bottom, left, right = 0, h - 1, 0, w - 1
    turn = 0
    while top <= bottom and left <= right:
        if turn % 4 == 0:
            mask[top, left : right + 1] = 1
            top += 2
        elif turn % 4 == 1:
            mask[top : bottom + 1, right] = 1
            right -= 2
        elif turn % 4 == 2:
            if top <= bottom:
                mask[bottom, left : right + 1] = 1
            bottom -= 2
        else:
            if left <= right:
                mask[top : bottom + 1, left] = 1
            left += 2
        turn += 1
    return mask.astype(bool)


def _snake_mask(h: int, w: int) -> np.ndarray:
    """Boustrophedon (back-and-forth) snake, one cell wide, connected only
    at alternating row ends -- 4-connectivity would still connect this (the
    turns are axis-aligned), but a NARROWER variant using single-cell
    diagonal stitches would not; used together with the checkerboard case
    as the sharpest 4- vs 8-connectivity discriminators."""
    mask = np.zeros((h, w), dtype=bool)
    for r in range(0, h, 2):
        mask[r, :] = True
    for r in range(0, h - 2, 2):
        # diagonal stitch cell connecting row r to row r+2 only via a
        # corner touch at alternating ends (4-conn would NOT connect these
        # two rows; 8-conn does).
        c = w - 1 if (r // 2) % 2 == 0 else 0
        mask[r + 1, c] = True
    return mask


def _many_small_components_mask(h: int, w: int) -> tuple[np.ndarray, int]:
    mask = np.zeros((h, w), dtype=bool)
    n = 0
    for r in range(0, h, 2):
        for c in range(0, w, 2):
            mask[r, c] = True
            n += 1
    return mask, n


def _routing_area_like_mask(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """Mirrors exact_edt_rust_spike.py's real-call-site-shape generator:
    mostly-open interior with a boundary ring and scattered circular
    keepouts -- the actual mask shape produced by _rasterize_boundary_mask/
    OccupancyGrid and consumed as `passable_mask` here."""
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


def build_corpus() -> Corpus:
    c = Corpus()
    rng = np.random.default_rng(20260807)

    # --- Structural / degenerate cases ---------------------------------
    c.add("empty (all background, 20x30)", np.zeros((20, 30), dtype=bool))
    c.add("full (all foreground, 20x30)", np.ones((20, 30), dtype=bool))
    c.add("full (all foreground, 1x1)", np.ones((1, 1), dtype=bool))
    c.add("empty (all background, 1x1)", np.zeros((1, 1), dtype=bool))
    c.add("single isolated cell (9x9)", np.eye(1, 81).reshape(9, 9).astype(bool))

    mask = np.zeros((3, 3), dtype=bool)
    mask[0, 0] = True
    mask[1, 1] = True
    c.add("diagonal touch, 2 cells (3x3)", mask)

    # --- Many small components (known count, spaced so 4- and 8-conn agree)
    mask, expected_n = _many_small_components_mask(21, 21)
    c.add(f"many small components ({expected_n} isolated cells, 21x21)", mask)

    # --- Checkerboard: sharpest 4- vs 8-connectivity discriminator ------
    for size in (8, 40, 100):
        yy, xx = np.mgrid[0:size, 0:size]
        checker = ((yy + xx) % 2) == 0
        c.add(f"checkerboard ({size}x{size})", checker)

    # --- Spiral / snake shapes (union-find "conflict" stress) -----------
    for h, w in [(11, 11), (25, 40), (40, 25)]:
        c.add(f"rectangular spiral ({h}x{w})", _spiral_mask(h, w))
    for h, w in [(9, 9), (20, 30)]:
        c.add(f"diagonal-stitched snake ({h}x{w})", _snake_mask(h, w))

    # --- Components touching borders -------------------------------------
    h, wgt = 15, 15
    mask = np.zeros((h, wgt), dtype=bool)
    mask[:, 0] = True  # left border column
    mask[:, -1] = True  # right border column
    mask[0, :] = True  # top border row (connects the two columns via corners)
    c.add("border-touching components, connected via top row (15x15)", mask)

    mask = np.zeros((h, wgt), dtype=bool)
    mask[:, 0] = True
    mask[:, -1] = True
    c.add("border-touching components, NOT connected (15x15)", mask)

    # --- Non-square grids --------------------------------------------------
    for h, w in [(1, 9), (9, 1), (4, 60), (60, 4), (5, 400), (400, 5)]:
        c.add(f"non-square all-foreground ({h}x{w})", np.ones((h, w), dtype=bool))
    c.add("non-square random dense (7x23)", rng.random((7, 23)) < 0.5)

    # --- Dense/sparse random at several densities ------------------------
    for density, label_ in [
        (0.02, "sparse"),
        (0.1, "light"),
        (0.3, "medium"),
        (0.5, "dense"),
        (0.7, "heavy"),
        (0.95, "near-full"),
    ]:
        mask = rng.random((60, 80)) < density
        c.add(f"random {label_} (density={density}, 60x80)", mask)

    # --- Real call-site shapes -------------------------------------------
    # cell_size = 0.1mm, same as the EDT spike's shapes (routability_check
    # consumes the same EDT grid/mask as channel_widths.py/_astar_heuristics.py).
    cell_size = 0.1
    for label_, w_mm, h_mm in [
        ("default fallback board (100x100mm)", 100.0, 100.0),
        ("real production board (~185x288mm)", 185.3, 287.5),
    ]:
        w = int(np.ceil(w_mm / cell_size)) + 1
        h = int(np.ceil(h_mm / cell_size)) + 1
        m = _routing_area_like_mask(h, w, rng)
        c.add(f"real call-site shape: {label_} [{h}x{w}]", m)
    # test suite's realistic board grid (test_latency_realistic_board_grid)
    m = _routing_area_like_mask(1501, 1001, rng)
    c.add("test-suite realistic board grid [1501x1001]", m)

    return c


def print_corpus_summary(c: Corpus) -> None:
    print(
        f"{'case':<62} {'shape':>14} {'scipy_n':>8} {'rust_n':>8} "
        f"{'partition_ok':>13} {'exact_match':>12}"
    )
    n_fail = 0
    n_exact = 0
    total_cells = 0
    for r in c.results:
        if not r.partition_match:
            n_fail += 1
        if r.exact_label_match:
            n_exact += 1
        total_cells += r.n_cells
        print(
            f"{r.name:<62} {str(r.shape):>14} {r.scipy_num_features:>8} "
            f"{r.rust_num_features:>8} {str(r.partition_match):>13} {str(r.exact_label_match):>12}"
            + ("" if r.partition_match else f"   <-- {r.partition_note}")
        )
    print()
    print(f"corpus size (cases):                  {len(c.results)}")
    print(f"corpus size (cells):                  {total_cells}")
    print(f"cases with partition mismatch:        {n_fail} / {len(c.results)}")
    print(f"cases with exact label-value match:   {n_exact} / {len(c.results)}")
    print(
        f"cases with num_features mismatch:     "
        f"{sum(1 for r in c.results if r.scipy_num_features != r.rust_num_features)} / {len(c.results)}"
    )


def stress_random(n_trials: int = 300, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n_partition_mismatch = 0
    n_feature_count_mismatch = 0
    n_exact_match = 0
    total_cells = 0
    for _ in range(n_trials):
        h = int(rng.integers(2, 120))
        w = int(rng.integers(2, 120))
        density = rng.choice([0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98])
        mask = rng.random((h, w)) < density
        s_labels, s_n = scipy_label(mask.astype(np.uint8), structure=_STRUCTURE_8)
        r_labels, r_n = rust_label(mask)
        ok, _ = partitions_equal(s_labels.astype(np.int64), r_labels.astype(np.int64))
        if not ok:
            n_partition_mismatch += 1
        if s_n != r_n:
            n_feature_count_mismatch += 1
        if np.array_equal(s_labels, r_labels):
            n_exact_match += 1
        total_cells += mask.size
    return {
        "trials": n_trials,
        "total_cells": int(total_cells),
        "partition_mismatches": n_partition_mismatch,
        "num_features_mismatches": n_feature_count_mismatch,
        "exact_label_matches": n_exact_match,
    }


def connectivity_discriminator_check() -> dict:
    """Confirms the 4- vs 8-connectivity distinction is real and that this
    implementation picked the right one: on a checkerboard, scipy's DEFAULT
    (4-connected, no `structure=`) gives many components, while scipy with
    `structure=ones((3,3))` (8-connected, what the consumer actually passes)
    and the Rust implementation both collapse it to one -- proving Rust
    matches the *consumer's* connectivity, not scipy's unqualified default."""
    yy, xx = np.mgrid[0:20, 0:20]
    checker = ((yy + xx) % 2) == 0
    _, n_4conn = scipy_label(checker.astype(np.uint8))  # scipy default: 4-connected
    _, n_8conn_scipy = scipy_label(checker.astype(np.uint8), structure=_STRUCTURE_8)
    _, n_8conn_rust = rust_label(checker)
    return {
        "checkerboard_20x20_scipy_4conn_default_num_features": int(n_4conn),
        "checkerboard_20x20_scipy_8conn_structure_num_features": int(n_8conn_scipy),
        "checkerboard_20x20_rust_8conn_num_features": n_8conn_rust,
    }


def benchmark(shapes: list[tuple[str, int, int]], reps: int = 5) -> list[dict]:
    rng = np.random.default_rng(1)
    rows = []
    for label_, h, w in shapes:
        mask = _routing_area_like_mask(h, w, rng)
        mask_u8 = np.ascontiguousarray(mask, dtype=np.uint8)

        t0 = time.perf_counter()
        for _ in range(reps):
            s_labels, s_n = scipy_label(mask_u8, structure=_STRUCTURE_8)
        t_scipy = (time.perf_counter() - t0) / reps

        t0 = time.perf_counter()
        for _ in range(reps):
            raw_bytes, r_n = tg.connected_components_8_transform(mask_u8.tobytes(), h, w)
            r_labels = np.frombuffer(raw_bytes, dtype=np.int32).reshape(h, w)
        t_rust = (time.perf_counter() - t0) / reps

        ok, note = partitions_equal(s_labels.astype(np.int64), r_labels.astype(np.int64))
        assert ok, f"{label_}: rust/scipy diverge under benchmark ({note})"
        assert s_n == r_n, f"{label_}: num_features diverge under benchmark"

        rows.append(
            {
                "label": label_,
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

    print("=== KTD8 follow-up: exact-CC parity corpus ===")
    corpus = build_corpus()
    print_corpus_summary(corpus)

    print()
    print("=== KTD8 follow-up: bulk random differential (300 trials, varied size/density) ===")
    stress = stress_random()
    for k, v in stress.items():
        print(f"{k}: {v}")

    print()
    print("=== Connectivity discriminator (4- vs 8-connected on a checkerboard) ===")
    disc = connectivity_discriminator_check()
    for k, v in disc.items():
        print(f"{k}: {v}")

    print()
    print("=== Benchmark: scipy vs Rust (incl. FFI boundary crossing) ===")
    shapes = [
        ("small (100x100 cells, e.g. a coarse test fixture)", 100, 100),
        ("test-suite realistic board grid (1501x1001)", 1501, 1001),
        ("default-fallback board @ 0.1mm cell (100x100mm -> 1001x1001)", 1001, 1001),
        ("real production board @ 0.1mm cell (~185x288mm -> ~1854x2876)", 1854, 2876),
    ]
    bench_rows = benchmark(shapes, reps=5)
    for row in bench_rows:
        print(
            f"{row['label']:<60} n_cells={row['n_cells']:>9} "
            f"scipy={row['scipy_seconds'] * 1000:>9.3f}ms "
            f"rust(+ffi)={row['rust_incl_ffi_seconds'] * 1000:>9.3f}ms "
            f"speedup={row['speedup']:.2f}x"
        )

    if args.json_out:
        out = {
            "corpus": [r.__dict__ for r in corpus.results],
            "stress_random": stress,
            "connectivity_discriminator": disc,
            "benchmark": bench_rows,
        }
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
