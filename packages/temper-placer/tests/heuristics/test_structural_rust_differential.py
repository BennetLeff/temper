"""R1a differential: heuristics/structural.py's ``create_keepout_mask`` vs its
pinned oracle.

**THIS SUITE IS DELIBERATELY RED** until Phase B lands. Gate G1 requires the
differential that pins the pre-migration implementation verbatim to exist and
fail *before* the Rust exists, so every comparison below resolves its Rust
arm through ``tests.router_v6._pending_rust`` and fails with a named
``PendingRustError`` until the ``temper_geometry`` extension exports
``keepout_mask_flags_py``. See that module's docstring for why a skip, an
``xfail``, and a module-scope import were all rejected.

Arms
----
* **oracle** -- ``tests/heuristics/_structural_py_oracle.py``, a verbatim
  ``git show`` copy of ``create_keepout_mask`` at
  ``d5f4593142da87c75f9b21734e0e65d0e991f16d`` (``origin/main``).
* **rust** -- ``temper_geometry.keepout_mask_flags_py``, Phase B's pyfunction.
  Named in :data:`REQUIRED_RUST_SYMBOLS`; the adapter block below is the only
  place that knows it exists.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``):
``dtype`` + ``shape`` + per-element hex/bool. **No tolerance anywhere.**

Traps this file pins explicitly
--------------------------------
``int(x)`` truncates toward zero throughout this function (margin_cells,
hole cx/cy/cr, region mx_min/my_min/mx_max/my_max) -- exercised by
:func:`test_origin_not_at_zero` (negative origin offsets force negative
numerators through ``int()``) and :func:`test_fuzz_random_boards`.

``mask[-margin_cells:, :] = False`` is a literal negative slice, guarded
behind ``if margin_cells > 0`` -- :func:`test_zero_margin_zero_buffer` (guard
not taken) and :func:`test_margin_larger_than_board_clears_everything`
(guard taken, slice bounds overlap/clamp).

The keepout-region loop's ``mx_max = min(width_cells, int(...) + 1)`` is a
*plain int*, not a slice literal -- when it goes negative, Python slicing
means "count back from the end", not "clamp to zero"
(:func:`test_keepout_region_off_board_negative`). A naive Rust port using
``.max(0)`` instead of Python's slice-normalization semantics passes every
other test in this file and fails only this one (see
``packages/temper-geometry/src/heuristics_geometry.rs``'s own
``test_negative_region_bound_counts_from_end`` for the Rust-side pure-kernel
mirror of this same case).

The three keepout sources (margin, holes, regions) only ever clear bits, so
their union is order-independent -- exercised by
:func:`test_holes_and_regions_overlapping`.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import numpy as np
import pytest

import tests.heuristics._structural_py_oracle as ORACLE
from temper_placer.core.board import Board, MountingHole
from temper_placer.io.config_loader import PlacementConstraints
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
#
# Phase B binds this; nothing below this block changes. A diff of the Rust
# PR that touches anything past the closing banner is a weakened assertion.
# ===========================================================================

#: Migration target: temper-geometry already hosts the placer's 2D geometry
#: math (grid_raster.rs's rasterisation kernels are this function's closest
#: sibling), so this is where the mask-construction kernel lives too.
_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("keepout_mask_flags_py",)


def _rust_create_keepout_mask(
    board: Board,
    constraints: PlacementConstraints,
    resolution_mm: float = 1.0,
    buffer_mm: float = 1.0,
) -> np.ndarray:
    """Mirrors the production delegation shim: extract primitives from the
    contract objects, call the Rust kernel, reshape the flat bool list back
    into an (H, W) numpy array -- exactly what
    ``heuristics/structural.py::create_keepout_mask`` does once Phase B
    lands.
    """
    fn = rust(_RUST_MODULE, "keepout_mask_flags_py")
    ox, oy = board.origin
    width_cells = int(board.width / resolution_mm) + 1
    height_cells = int(board.height / resolution_mm) + 1
    holes = [(hole.position[0], hole.position[1], hole.keepout_radius) for hole in board.mounting_holes]
    regions = [tuple(float(v) for v in r) for r in board.keepout_regions]
    flags = fn(
        width_cells,
        height_cells,
        ox,
        oy,
        resolution_mm,
        constraints.board_margin_mm,
        buffer_mm,
        holes,
        regions,
    )
    return np.array(flags, dtype=np.bool_).reshape((height_cells, width_cells))


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "d5f4593142da87c75f9b21734e0e65d0e991f16d"
_ORACLE_PATH = "packages/temper-placer/src/temper_placer/heuristics/structural.py"


def _repo_root() -> Path:
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


def _segment_at_pin(name: str) -> str:
    import ast

    src = subprocess.run(
        ["git", "show", f"{_ORACLE_PIN_SHA}:{_ORACLE_PATH}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_repo_root(),
    ).stdout
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in tree.body:
        if getattr(node, "name", None) == name:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            return "\n".join(lines[start : node.end_lineno])
    raise AssertionError(f"{name} not found in {_ORACLE_PATH} at {_ORACLE_PIN_SHA}")


def _segment_in_oracle(name: str) -> str:
    import ast

    src = Path(ORACLE.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in tree.body:
        if getattr(node, "name", None) == name:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            return "\n".join(lines[start : node.end_lineno])
    raise AssertionError(f"{name} not found in the oracle module")


def test_oracle_is_verbatim_copy():
    """The oracle's ``create_keepout_mask`` is character-identical to the pin.

    If anyone "improves" the oracle, the differential stops proving
    anything, so drift here fails CI instead of passing quietly.
    """
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{_ORACLE_PIN_SHA}^{{commit}}"],
            capture_output=True,
            check=True,
            cwd=_repo_root(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    assert _segment_in_oracle("create_keepout_mask") == _segment_at_pin("create_keepout_mask")


def test_rust_symbols_exist():
    """Checklist for Phase B: every symbol this differential needs."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert missing == [], f"Phase B must still add: {missing}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _board(
    width: float = 100.0,
    height: float = 80.0,
    origin: tuple[float, float] = (0.0, 0.0),
    mounting_holes: list | None = None,
    keepouts: list | None = None,
) -> Board:
    return Board(
        width=width,
        height=height,
        origin=origin,
        mounting_holes=mounting_holes or [],
        keepouts=keepouts or [],
    )


def _constraints(board_margin_mm: float = 3.0) -> PlacementConstraints:
    return PlacementConstraints(board_margin_mm=board_margin_mm)


def _assert_matches(board, constraints, resolution_mm=1.0, buffer_mm=1.0):
    oracle_mask = ORACLE.create_keepout_mask(board, constraints, resolution_mm, buffer_mm)
    rust_mask = _rust_create_keepout_mask(board, constraints, resolution_mm, buffer_mm)
    assert sig(rust_mask) == sig(oracle_mask)


# ---------------------------------------------------------------------------
# Differential cases
# ---------------------------------------------------------------------------


def test_no_keepouts_default_margin():
    _assert_matches(_board(), _constraints())


def test_zero_margin_zero_buffer():
    _assert_matches(_board(), _constraints(board_margin_mm=0.0), buffer_mm=0.0)


def test_mounting_holes():
    holes = [
        MountingHole(position=(10.0, 10.0), diameter=2.0, keepout_radius=3.0),
        MountingHole(position=(90.0, 70.0), diameter=2.0, keepout_radius=5.0),
    ]
    _assert_matches(_board(mounting_holes=holes), _constraints())


def test_keepout_regions():
    regions = [(20.0, 20.0, 40.0, 30.0), (60.0, 5.0, 80.0, 15.0)]
    _assert_matches(_board(keepouts=regions), _constraints())


def test_keepout_region_off_board_negative():
    """Region whose buffered edges lie entirely off-board (negative origin
    offset), the concrete scenario for the negative-slice-bound trap.
    """
    regions = [(-200.0, 10.0, -5.0, 60.0)]
    _assert_matches(_board(keepouts=regions), _constraints())


def test_holes_and_regions_overlapping():
    holes = [MountingHole(position=(25.0, 25.0), diameter=2.0, keepout_radius=4.0)]
    regions = [(20.0, 20.0, 30.0, 30.0)]
    _assert_matches(_board(mounting_holes=holes, keepouts=regions), _constraints())


def test_non_default_resolution_and_buffer():
    _assert_matches(_board(), _constraints(), resolution_mm=0.5, buffer_mm=2.0)


def test_origin_not_at_zero():
    holes = [MountingHole(position=(15.0, -5.0), diameter=2.0, keepout_radius=2.5)]
    _assert_matches(
        _board(origin=(-10.0, -10.0), mounting_holes=holes),
        _constraints(),
    )


def test_margin_larger_than_board_clears_everything():
    _assert_matches(_board(width=10.0, height=8.0), _constraints(board_margin_mm=50.0))


def test_fuzz_random_boards():
    rng = random.Random(20260806)
    for _ in range(40):
        width = rng.uniform(20.0, 200.0)
        height = rng.uniform(20.0, 200.0)
        ox = rng.uniform(-20.0, 20.0)
        oy = rng.uniform(-20.0, 20.0)
        n_holes = rng.randint(0, 3)
        holes = [
            MountingHole(
                position=(rng.uniform(ox, ox + width), rng.uniform(oy, oy + height)),
                diameter=rng.uniform(0.5, 3.0),
                keepout_radius=rng.uniform(0.5, 6.0),
            )
            for _ in range(n_holes)
        ]
        n_regions = rng.randint(0, 3)
        regions = []
        for _ in range(n_regions):
            x_min = rng.uniform(ox - 30.0, ox + width)
            y_min = rng.uniform(oy - 30.0, oy + height)
            regions.append((x_min, y_min, x_min + rng.uniform(1.0, 20.0), y_min + rng.uniform(1.0, 20.0)))
        board = _board(width=width, height=height, origin=(ox, oy), mounting_holes=holes, keepouts=regions)
        constraints = _constraints(board_margin_mm=rng.uniform(0.0, 10.0))
        resolution = rng.choice([0.5, 1.0, 2.0])
        buffer_mm = rng.uniform(0.0, 3.0)
        _assert_matches(board, constraints, resolution_mm=resolution, buffer_mm=buffer_mm)
