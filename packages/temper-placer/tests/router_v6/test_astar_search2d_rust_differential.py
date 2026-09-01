"""Differential: the Rust 2D corridor A* vs its pinned Python oracle.

Feeds the **real corridor-backbone grids** -- every one of the 283 searches a
full ``scripts/route_board.py`` pass over ``pcb/temper.kicad_pcb`` actually
performs -- to both ``astar_search2d_rust._astar_search_2d_rust`` and the
pinned ``_astar_core_py_oracle._astar_search``, and requires **bit-exact**
agreement on the emitted cell sequence, including on the 272 searches that
find no path at all.

Why a recorded corpus rather than grids built in a fixture
----------------------------------------------------------
A differential proves only what it is fed, and these inputs cannot be
rebuilt from the board. ``_ground_plane`` / ``_power_islands`` rasterize the
search grid from the board polygon, the HV keepout, every other net's
resolved per-net-pair clearance polygon **and the F.Cu copper that same run
has already emitted** -- so the grids only exist partway through ground-plane
and power-island generation. ``scripts/capture_astar_backbone_corpus.py``
records them from a live route; the fixture's metadata carries the routed
board's own sha256 as evidence that the recording shim left the route
byte-identical, so the corpus is a record of production and not of an
instrumented variant of it.

The synthetic alternative would have been badly unrepresentative in exactly
the dimension that matters. The captured grids run to 979,400 cells (median
185,640), 96% of the searches exhaust their frontier without reaching the
goal, and this search keeps **no closed set** -- so those runs re-expand
nodes and fully re-process stale heap entries, which is where tie-break order
actually decides anything.

Why bit-exact rather than invariant-level
------------------------------------------
``test_astar_kernel_rust_differential`` holds ``astar_kernel_3d`` to
invariants only, because that kernel computes in f32 and the f64->f32
heuristic cast can reorder heap ties. This kernel is f64 end to end and was
written to mirror the Python statement for statement, so it is held to the
stronger standard: "the path is legal" would not detect a port that quietly
routes somewhere else, and where this copper lands is a clearance question on
a mains-voltage board.

The board is read strictly read-only. Nothing here writes to ``pcb/``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.astar_search2d_rust import _astar_search_2d_rust
from tests.router_v6._astar_core_py_oracle import _astar_search as _oracle_search

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]
_FIXTURE = _REPO_ROOT / "packages/temper-placer/tests/fixtures/astar_backbone_corpus"

# Keep in sync with the oracle's own docstring; `test_oracle_is_verbatim_copy`
# re-runs this extraction against the committed file.
ORACLE_COMMIT = "9bf6e5df797cf93e0122b742ab87661bf097dd81"
ORACLE_SOURCE = "packages/temper-placer/src/temper_placer/router_v6/astar_core.py"
ORACLE_RANGES: tuple[tuple[int, int], ...] = ((18, 53), (136, 147), (221, 366))
VERBATIM_MARKER = "# --- BEGIN VERBATIM EXTRACTION ---"

# The digest the corpus was captured under, and the board it was captured
# from. Both are asserted below rather than merely recorded: a corpus taken
# against a different board is not evidence about this one.
EXPECTED_PCB_SHA256 = "00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9"
EXPECTED_ROUTED_SHA256 = "7ca01328a795ef43376ca28f601e0ff04b4ab2a73c22b7ede45fd75c247aaf85"


class _GridAdapter:
    """Minimal ``OccupancyGrid``-compatible view over a decoded corpus grid.

    Both engines read only ``grid`` / ``width_cells`` / ``height_cells`` on the
    ``net_id >= 0`` branch, which is the only branch this call site takes.
    """

    def __init__(self, arr: np.ndarray) -> None:
        self.grid = arr
        self.height_cells, self.width_cells = arr.shape


@pytest.fixture(scope="module")
def corpus():
    npz = _FIXTURE / "astar_backbone_corpus.npz"
    meta_path = _FIXTURE / "astar_backbone_corpus_meta.json"
    if not npz.exists() or not meta_path.exists():
        pytest.skip(
            f"{_FIXTURE} not present -- regenerate with "
            "scripts/capture_astar_backbone_corpus.py"
        )
    meta = json.loads(meta_path.read_text())
    return np.load(npz), meta


def _case(data, meta, i):
    """Decode one recorded call into (grid, mask, start, goal, expected)."""
    rec = meta["calls"][i]
    h, w = rec["shape"]
    blocked = np.unpackbits(data[f"blocked_{i}"])[: h * w].reshape(h, w).astype(bool)
    mask = np.unpackbits(data[f"mask_{i}"])[: h * w].reshape(h, w).astype(bool)
    grid = _GridAdapter(np.where(blocked, -1, 0).astype(np.int8))
    expected = (
        [(int(x), int(y)) for x, y in data[f"path_{i}"]] if rec["found"] else None
    )
    return grid, mask, tuple(rec["start"]), tuple(rec["goal"]), rec, expected


# ---------------------------------------------------------------------------
# The corpus is only evidence if it is evidence about THIS board.
# ---------------------------------------------------------------------------


def test_corpus_provenance(corpus):
    _data, meta = corpus
    s = meta["summary"]
    assert s["pcb_sha256"] == EXPECTED_PCB_SHA256, (
        "the corpus was captured from a different board than the one this "
        "repo ships; it is not evidence about this one"
    )
    assert s["routed_content_sha256"] == EXPECTED_ROUTED_SHA256, (
        "the capture run did not reproduce the reference route, so the "
        "recorded searches are not the ones production performs"
    )
    board = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if board.exists():
        import hashlib

        assert (
            hashlib.sha256(board.read_bytes()).hexdigest() == EXPECTED_PCB_SHA256
        ), "pcb/temper.kicad_pcb changed; the corpus needs recapturing"


def test_corpus_covers_the_production_argument_shape(corpus):
    """The captured calls take exactly one shape, and it is the live one.

    This is the check that keeps the differential honest about coverage. The
    2026-08-11 ampacity divergence in this repo survived a genuinely-running
    differential because its input was a net name absent from this board; the
    guard against repeating that is to assert what production actually passes,
    not to assume it.
    """
    _data, meta = corpus
    shapes = meta["summary"]["argument_shapes_seen"]
    assert shapes == [
        "neighbor_tensor_is_none=True thermal_flat_is_none=True "
        "thermal_weight=0.0 net_id=1 corridor_mask_is_none=False"
    ], f"the production call shape changed: {shapes}"
    assert meta["summary"]["calls_with_occupancy_values_outside_0_and_minus_1"] == 0
    assert all(c["net_id"] == 1 for c in meta["calls"])


def test_corpus_is_the_full_recorded_pass(corpus):
    data, meta = corpus
    n = len(meta["calls"])
    assert n == meta["summary"]["calls"] == 283, f"expected 283 recorded calls, got {n}"
    # 96% of the real searches find nothing. That is the regime this kernel
    # spends its time in -- a corpus of only successful routes would exercise
    # almost none of the frontier exhaustion, node re-expansion, and stale-entry
    # re-processing this closed-set-free search does.
    found = sum(1 for c in meta["calls"] if c["found"])
    assert found == 11, f"expected 11 successful searches, got {found}"
    assert all(f"blocked_{i}" in data for i in range(n))


# ---------------------------------------------------------------------------
# The differential proper.
# ---------------------------------------------------------------------------


def test_real_backbone_searches_are_bit_identical(corpus):
    """Every recorded production search returns the identical cell sequence."""
    data, meta = corpus
    mismatches = []
    for i in range(len(meta["calls"])):
        grid, mask, start, goal, rec, expected = _case(data, meta, i)
        py = _oracle_search(start, goal, grid, net_id=rec["net_id"], corridor_mask=mask)
        rs = _astar_search_2d_rust(
            start, goal, grid, net_id=rec["net_id"], corridor_mask=mask
        )
        if not (py == rs == expected):
            mismatches.append(
                f"call {i} {rec['shape']} {start}->{goal}: "
                f"oracle={_summarize(py)} rust={_summarize(rs)} "
                f"recorded={_summarize(expected)}"
            )
    assert not mismatches, "\n".join(mismatches[:10])


def test_no_path_is_none_not_empty(corpus):
    """A failed search returns ``None``. ``route_edge_astar`` branches on
    truthiness, so ``[]`` would be read the same way -- but every other caller
    of a path list would not, and the two are not the same value."""
    data, meta = corpus
    idx = next(i for i, c in enumerate(meta["calls"]) if not c["found"])
    grid, mask, start, goal, rec, _ = _case(data, meta, idx)
    rs = _astar_search_2d_rust(start, goal, grid, net_id=rec["net_id"], corridor_mask=mask)
    assert rs is None and rs != []


def test_diagonal_cost_factor_is_read_per_call(corpus):
    """``DIAGONAL_COST_FACTOR`` is a module attribute the Python multiplied in
    on every diagonal expansion, and the module documents assigning to it
    directly. The port must read it per call, not bake it in at import -- and
    it must move the answer, or reading it would be untestable ceremony."""
    from temper_placer.router_v6 import astar_core
    from tests.router_v6 import _astar_core_py_oracle as oracle_mod

    data, meta = corpus
    idx = next(i for i, c in enumerate(meta["calls"]) if c["found"])
    grid, mask, start, goal, rec, _ = _case(data, meta, idx)

    # The oracle is a standalone verbatim copy and therefore carries its OWN
    # module attribute; the live value the Rust reads lives on `astar_core`.
    # Both have to move, or this test compares two different cost models and
    # reports the difference as a port bug (it did, on first run).
    original_live = astar_core.DIAGONAL_COST_FACTOR
    original_oracle = oracle_mod.DIAGONAL_COST_FACTOR
    try:
        base_py = _oracle_search(start, goal, grid, net_id=rec["net_id"], corridor_mask=mask)
        base_rs = _astar_search_2d_rust(
            start, goal, grid, net_id=rec["net_id"], corridor_mask=mask
        )
        assert base_py == base_rs

        # 0.5 makes a diagonal step cheaper than a cardinal one, so the octile
        # heuristic stops being admissible. That is the regime worth testing:
        # with an overestimating heuristic this search's lack of a closed set
        # stops being an optimisation detail and starts deciding the answer,
        # which is exactly where a port with a different heap discipline would
        # diverge.
        astar_core.DIAGONAL_COST_FACTOR = 0.5
        oracle_mod.DIAGONAL_COST_FACTOR = 0.5
        cheap_py = _oracle_search(
            start, goal, grid, net_id=rec["net_id"], corridor_mask=mask
        )
        cheap_rs = _astar_search_2d_rust(
            start, goal, grid, net_id=rec["net_id"], corridor_mask=mask
        )
        assert cheap_py == cheap_rs, "the two engines disagree once the factor moves"
        assert cheap_rs != base_rs, (
            "halving the diagonal cost changed nothing, so this test would "
            "pass against a kernel that ignored the factor entirely"
        )
    finally:
        astar_core.DIAGONAL_COST_FACTOR = original_live
        oracle_mod.DIAGONAL_COST_FACTOR = original_oracle


# ---------------------------------------------------------------------------
# Float-spelling counterexamples.
#
# Measured in this repo on 2026-08-18: `d ** 2` is not `d * d` (one ulp at
# ordinary board coordinates), and `math.sqrt(s)` is not `s ** 0.5` (IEEE-754
# requires `sqrt` correctly rounded and requires nothing of `pow`). The search
# ported here spells its only root as `math.sqrt(2.0)`, so the Rust must use
# `f64::sqrt`'s value -- `std::f64::consts::SQRT_2` -- and not a `powf`.
# ---------------------------------------------------------------------------


def test_sqrt2_spelling_matches_the_python():
    import math

    from temper_placer.router_v6.astar_core import OCTILE_DIAG

    py_sqrt2 = math.sqrt(2.0)
    assert py_sqrt2.hex() == float.fromhex("0x1.6a09e667f3bcdp+0").hex()
    assert py_sqrt2 - 1.0 == OCTILE_DIAG
    # The two counterexamples that make the spelling load-bearing rather than
    # pedantic. Neither is reachable from inside this search -- it spells its
    # only root `math.sqrt(2.0)` and never squares with `**` -- and pinning
    # them here is what keeps that true if someone "simplifies" either site.
    d = 98.07985406973864
    assert (d**2) != (d * d), "the ** vs * divergence this repo measured"
    s = 55489.646545994874
    assert math.sqrt(s) != (s**0.5), "the sqrt vs ** 0.5 divergence this repo measured"


# ---------------------------------------------------------------------------
# The oracle must stay the oracle.
# ---------------------------------------------------------------------------


def test_oracle_is_verbatim_copy():
    """The oracle is byte-identical to the pinned commit's source ranges.

    Re-runs the extraction rather than trusting the file, so an edit to the
    oracle -- or a change in what those line ranges mean -- fails closed
    instead of silently redefining the reference the differential compares to.
    """
    blob = subprocess.run(
        ["git", "show", f"{ORACLE_COMMIT}:{ORACLE_SOURCE}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = blob.split("\n")
    expected_parts: list[str] = []
    for start, end in ORACLE_RANGES:
        expected_parts.extend(lines[start - 1 : end])
        expected_parts.append("")
        expected_parts.append("")
    expected = "\n".join(expected_parts).rstrip("\n") + "\n"

    text = (_HERE / "_astar_core_py_oracle.py").read_text()
    marker_at = text.index(VERBATIM_MARKER)
    actual = text[marker_at + len(VERBATIM_MARKER) :].lstrip("\n")

    assert actual == expected, (
        "oracle drifted from its pinned extraction -- the differential would be "
        "comparing Rust against a redefined reference"
    )


def test_the_ported_python_is_gone():
    """The migration is not finished while two implementations coexist.

    This repo's standing rule is make Rust right, prove it, delete the Python,
    keep the oracle -- because two homes that agree today drift tomorrow.
    """
    from temper_placer.router_v6 import astar_core

    assert not hasattr(astar_core, "_astar_search"), (
        "astar_core._astar_search is back; the Rust port and the Python it "
        "replaced are both live again"
    )
    assert not hasattr(astar_core, "_heuristic")


def _summarize(path):
    if path is None:
        return "None"
    return f"len={len(path)} head={path[:3]} tail={path[-3:]}"
