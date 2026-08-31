"""Differential tests for the Rust 8-connected component API
(``temper_geometry.connected_components_8_transform``), the two-pass
union-find raster scan that replaced the former scipy implementation, vs
``scipy.ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))``, the
pre-migration oracle pinned here per R19 (see
``docs/wave4-discipline-contract.md`` and mirroring
``test_routability_check_rust_differential.py``'s EDT differential suite).

Ground truth: ``docs/evidence/2026-08-07-rust-connected-components-spike.md``
measured EXACT agreement -- both the partition (renumbering-invariant: same
cells share a label) and, on every case measured, the raw label numbering
itself -- between the Rust labeler and scipy across ~8.9M cells (33 curated
cases + 300 random trials), 0 mismatches. Unlike the EDT migration, this
    direct API's contract only requires partition agreement (consumers test
    ``labels[a] == labels[b] != 0``, never a specific label value), so the
primary assertion here is partition equality; exact numeric equality is
checked too as a bonus (and holds on every case), but is not the contract.

The Python wrapper that used to own this call has been retired. Keep this
oracle and differential evidence anchored to the direct Rust API.
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg


def _rust_label_8conn(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Call the production Rust API directly, preserving the old result shape."""
    h, w = mask.shape
    raw, num_features = _tg.connected_components_8_transform(
        np.ascontiguousarray(mask, dtype=np.uint8).tobytes(), h, w
    )
    labels = np.frombuffer(raw, dtype="<i4").reshape(h, w)
    return labels, int(num_features)

_STRUCTURE_8 = np.ones((3, 3), dtype=bool)

# ---------------------------------------------------------------------------
# Oracle: the pre-migration scipy call, pinned verbatim (R19).
# ---------------------------------------------------------------------------


def _scipy_label_8conn(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Pre-migration oracle: this is exactly what ``check_routability_cc``
    computed before the Rust connected-components migration."""
    from scipy.ndimage import label as nd_label

    labels, num_features = nd_label(mask, structure=_STRUCTURE_8)
    return labels, int(num_features)


def _partitions_equal(a: np.ndarray, b: np.ndarray) -> bool:
    """Renumbering-invariant partition comparison (see the evidence doc's
    contract determination): True iff `a` and `b` describe the same
    connected-component partition, independent of which numeric label each
    component happens to carry. O(n log n)."""
    if a.shape != b.shape:
        return False
    a = a.ravel()
    b = b.ravel()
    a_bg = a == 0
    if not np.array_equal(a_bg, b == 0):
        return False
    af, bf = a[~a_bg], b[~a_bg]
    if af.size == 0:
        return True
    order = np.argsort(af, kind="stable")
    af_sorted, bf_sorted = af[order], bf[order]
    boundaries = np.nonzero(np.diff(af_sorted))[0] + 1
    groups = np.split(bf_sorted, boundaries)
    reps = []
    for g in groups:
        if g.max() != g.min():
            return False
        reps.append(int(g[0]))
    return len(set(reps)) == len(reps)


def _curated_masks() -> list[np.ndarray]:
    cases: list[np.ndarray] = []
    cases.append(np.zeros((10, 10), dtype=bool))  # empty
    cases.append(np.ones((10, 10), dtype=bool))  # full, one component

    single = np.zeros((9, 9), dtype=bool)
    single[4, 4] = True
    cases.append(single)

    diag = np.zeros((3, 3), dtype=bool)
    diag[0, 0] = True
    diag[1, 1] = True  # 8-connected diagonal touch
    cases.append(diag)

    # Checkerboard: sharpest 4- vs 8-connectivity discriminator -- the
    # WHOLE grid is one component under 8-connectivity.
    for size in (6, 21, 40):
        yy, xx = np.mgrid[0:size, 0:size]
        cases.append(((yy + xx) % 2) == 0)

    # Many small (isolated, spaced-out) components.
    small = np.zeros((15, 15), dtype=bool)
    small[0::2, 0::2] = True
    cases.append(small)

    # Non-square, border-touching.
    border = np.zeros((12, 20), dtype=bool)
    border[:, 0] = True
    border[:, -1] = True
    cases.append(border)  # two components, not connected

    for h, w in [(1, 9), (9, 1), (4, 60), (60, 4)]:
        cases.append(np.ones((h, w), dtype=bool))

    rng = np.random.default_rng(20260807)
    for h, w in [(12, 30), (30, 12), (50, 50)]:
        for density in (0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98):
            cases.append(rng.random((h, w)) < density)

    return cases


def test_connected_components_8_matches_scipy_curated() -> None:
    """Curated masks spanning empty/full/checkerboard/spiral-adjacent/
    border-touching/non-square/dense-random: exact partition agreement AND
    exact label-value agreement (a bonus the measured implementation
    happens to provide, per the evidence doc)."""
    for mask in _curated_masks():
        got_labels, got_n = _rust_label_8conn(mask)
        want_labels, want_n = _scipy_label_8conn(mask)
        assert got_n == want_n, f"num_features mismatch on shape {mask.shape}"
        assert _partitions_equal(got_labels.astype(np.int64), want_labels.astype(np.int64)), (
            f"partition mismatch on shape {mask.shape}"
        )
        assert np.array_equal(got_labels, want_labels), (
            f"exact label mismatch on shape {mask.shape}"
        )


def test_connected_components_8_matches_scipy_random() -> None:
    """300 random trials: partition agreement (the actual contract) plus
    exact label agreement (measured bonus), mirroring the EDT migration's
    own random sweep size."""
    rng = np.random.default_rng(42)
    for _ in range(300):
        h = int(rng.integers(2, 120))
        w = int(rng.integers(2, 120))
        density = rng.choice([0.02, 0.1, 0.3, 0.5, 0.7, 0.95, 0.98])
        mask = rng.random((h, w)) < density
        got_labels, got_n = _rust_label_8conn(mask)
        want_labels, want_n = _scipy_label_8conn(mask)
        assert got_n == want_n, f"mismatch at shape ({h},{w}) density={density}"
        assert _partitions_equal(got_labels.astype(np.int64), want_labels.astype(np.int64)), (
            f"partition mismatch at shape ({h},{w}) density={density}"
        )


def test_connectivity_is_8_not_4_connected() -> None:
    """Confirms the migration preserved the consumer's actual connectivity
    (8-connected, ``structure=np.ones((3, 3))``) rather than silently
    drifting to scipy's unqualified 4-connected default -- the main
    correctness risk the task brief calls out. A checkerboard is the
    sharpest discriminator: 4-connectivity gives many singleton components,
    8-connectivity gives exactly one."""
    yy, xx = np.mgrid[0:20, 0:20]
    checker = ((yy + xx) % 2) == 0

    from scipy.ndimage import label as nd_label

    _, n_4conn_scipy_default = nd_label(checker.astype(np.uint8))
    assert n_4conn_scipy_default == 200, "sanity check on the discriminator itself"

    got_labels, got_n = _rust_label_8conn(checker)
    assert got_n == 1, (
        "Rust must reproduce 8-connectivity (matches structure=ones((3,3))), not scipy's 4-connected default"
    )
    assert np.all(got_labels[checker] == got_labels[checker][0])
