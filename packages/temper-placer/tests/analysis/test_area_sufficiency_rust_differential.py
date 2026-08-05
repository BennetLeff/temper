"""Differential test: Rust analysis kernels (temper_geometry) vs the pinned
Python oracle for ``temper_placer/analysis/_area_sufficiency.py``.

Wave 4, Phase 4 — the analysis-surface migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``).
The Rust pyfunctions ``area_sufficiency_compute`` / ``top_courtyards`` /
``py_sum`` (in ``temper_geometry``, from the ``temper-geometry`` crate)
must reproduce the pre-migration Python implementation bit-identically.
The pre-migration implementation is pinned verbatim as the oracle
(``_area_sufficiency_py_oracle.py``, commit c5875adad) and every
assertion here drives IDENTICAL inputs through both sides.

Two arms:

1. **Kernel arm** — ``py_sum`` is CPython 3.12's builtin ``sum()`` float
   semantics (Neumaier fast path with an int-0 start).  The oracle's
   ``sum(c._polygon.area for c in ...)`` calls exactly that builtin, so the
   differential drives adversarial float corpora (empty, single-element,
   -0.0, NaN, ±inf, subnormals, large-magnitude cancellation) through both
   ``sum(areas)`` and ``_tg.py_sum(areas)``, comparing bit patterns via
   ``float.hex()`` AND the concrete leaf type (``sum([])`` is ``int 0``,
   not ``float 0.0``).  ``area_sufficiency_compute`` must agree with
   ``py_sum`` on the same area list (the PBT suite's P1 pins that linkage).

2. **Path arm** — synthetic ``.kicad_pcb`` boards drive the full public
   API: ``compute_area_sufficiency`` (oracle module) vs the delegation
   shim, and ``compute_top_courtyards`` (both arms).  Float fields compare
   via ``float.hex()``; the int-vs-float leaf type is carried in the
   comparison key so an int ``board_width`` (integer s-expr coords) cannot
   hide behind numeric equality.  The ValueError path (non-positive usable
   area) compares the raised messages byte-identically.
"""

from __future__ import annotations

import math
import random
import struct
from pathlib import Path

import pytest
import temper_geometry as _tg

import tests.analysis._area_sufficiency_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
AREA_SUFFICIENCY_COMPUTE = _tg.area_sufficiency_compute
TOP_COURTYARDS = _tg.top_courtyards
PY_SUM = _tg.py_sum

from temper_placer.analysis._area_sufficiency import (
    compute_area_sufficiency,
    compute_top_courtyards,
)

_ORACLE_COMPUTE = _oracle.compute_area_sufficiency
_ORACLE_TOP = _oracle.compute_top_courtyards


# ---------------------------------------------------------------------------
# Canonicalization helpers (bit-exact floats, concrete leaf types).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _type_tag(value):
    """Concrete leaf type tag so int-vs-float cannot hide behind ==."""
    return type(value).__name__


def _result_key(result):
    return (
        _f(result.total_courtyard_area_mm2),
        _type_tag(result.total_courtyard_area_mm2),
        _f(result.usable_area_mm2),
        _type_tag(result.usable_area_mm2),
        _f(result.raw_ratio_pct),
        _type_tag(result.raw_ratio_pct),
        _f(result.board_width_mm),
        _type_tag(result.board_width_mm),
        _f(result.board_height_mm),
        _type_tag(result.board_height_mm),
        result.component_count,
        _type_tag(result.component_count),
    )


def _pairs_key(pairs):
    return tuple((ref, _f(area), _type_tag(area)) for ref, area in pairs)


# ---------------------------------------------------------------------------
# Synthetic board builder (mirrors tests/analysis/test_area_sufficiency_check.py).
# ---------------------------------------------------------------------------


def _make_board(
    width: float,
    height: float,
    footprints: str = "",
) -> str:
    return f"""(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (39 "F.CrtYd" user) (41 "B.CrtYd" user))
  (net 0 "")
  (net 1 "N1")
{footprints}
  (gr_poly
    (pts (xy 0 0) (xy {width} 0) (xy {width} {height}) (xy 0 {height}))
    (layer "Edge.Cuts") (width 0.1)
  )
)
"""


def _footprint(ref: str, at_x: float, at_y: float, rect_w: float, rect_h: float) -> str:
    hw = rect_w / 2.0
    hh = rect_h / 2.0
    return f"""  (footprint "test:{ref}" (layer "F.Cu")
    (property "Reference" "{ref}") (property "Value" "test")
    (at {at_x} {at_y} 0)
    (fp_rect (start {-hw} {-hh}) (end {hw} {hh}) (layer "F.CrtYd") (width 0.1))
    (pad "1" smd rect (at 0 0) (size 1.0 1.0) (layers "F.Cu") (net 1 "N1"))
  )
"""


def _write_pcb(tmp_path: Path, name: str, content: str) -> Path:
    pcb_path = tmp_path / name
    pcb_path.write_text(content)
    return pcb_path


# ---------------------------------------------------------------------------
# Kernel arm: py_sum vs CPython 3.12 builtin sum (Neumaier fast path).
# ---------------------------------------------------------------------------


def _sum_key(value):
    """int 0 vs float: carry the concrete type; floats via hex()."""
    if isinstance(value, int):
        return ("int", value)
    return ("float", float(value).hex())


# Deterministic adversarial corpus (seeded; no hypothesis dependency here).
def _float_corpus() -> list[list[float]]:
    rng = random.Random(20260804)
    cases: list[list[float]] = [
        [],
        [0.0],
        [1.0],
        [-0.0],
        [-0.0, -0.0, -0.0],
        [0.1, 0.2, 0.3],
        [1e16, 1.0, -1e16],  # Neumaier discriminator: sum == 1.0, naive == 0.0
        [1e16, 1.0, 1e16],
        [float("inf"), 1.0],
        [1.0, float("inf"), -1.0],
        [float("nan"), 1.0],
        [1.0, float("nan")],
        [5e-324, 5e-324, 5e-324],
        [1.7976931348623157e308, 1.7976931348623157e308],
        [1e308, -1e308, 1.0],
    ]
    for _ in range(60):
        n = rng.randint(0, 30)
        cases.append([rng.uniform(-1e12, 1e12) for _ in range(n)])
    for _ in range(20):
        n = rng.randint(1, 12)
        cases.append(
            [struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0] for _ in range(n)]
        )
    # Long mixed-sign runs (Neumaier vs naive diverge with cancellation).
    for _ in range(10):
        n = rng.randint(8, 40)
        cases.append([rng.uniform(-1e8, 1e8) for _ in range(n)])
    return cases


@pytest.mark.parametrize("areas", _float_corpus())
def test_py_sum_matches_builtin_sum_bit_exact(areas):
    oracle = sum(areas)  # CPython 3.12 builtin — the oracle's kernel verbatim
    rust = PY_SUM(areas)
    assert _sum_key(rust) == _sum_key(oracle), f"{areas!r}: {rust!r} vs {oracle!r}"


def test_py_sum_empty_is_int_zero():
    rust = PY_SUM([])
    assert type(rust) is int and rust == 0


def test_py_sum_single_negative_zero_normalises_to_positive():
    # CPython: 0 (int) + -0.0 == +0.0 via PyNumber_Add (round-to-nearest).
    rust = PY_SUM([-0.0])
    assert _sum_key(rust) == _sum_key(0.0)
    assert math.copysign(1.0, float(rust)) == 1.0


# ---------------------------------------------------------------------------
# Path arm: full public API on synthetic boards, oracle vs shim.
# ---------------------------------------------------------------------------


def _board_cases(tmp_path: Path) -> list[tuple[Path, float]]:
    """(pcb_path, margin) pairs covering empty, ties, many components, int
    widths, and the error path."""
    cases = []
    # Empty courtyards (no footprints), float board dims.
    p1 = _write_pcb(tmp_path, "empty.kicad_pcb", _make_board(100.0, 100.0))
    cases.append((p1, 5.0))
    cases.append((p1, 0.0))
    # One component.
    p2 = _write_pcb(
        tmp_path,
        "single.kicad_pcb",
        _make_board(100.0, 100.0, _footprint("R1", 50.0, 50.0, 10.0, 10.0)),
    )
    cases.append((p2, 5.0))
    # Many components with unequal areas (dict insertion order matters).
    fps = "".join(
        _footprint(f"C{i}", 10.0 + 5.0 * i, 20.0, 2.0 + i * 0.37, 3.0 + (i % 3) * 0.5)
        for i in range(24)
    )
    p3 = _write_pcb(tmp_path, "many.kicad_pcb", _make_board(200.0, 200.0, fps))
    cases.append((p3, 5.0))
    # Integer s-expr coords → int board_width/height leaf types.
    p4 = _write_pcb(
        tmp_path,
        "intdims.kicad_pcb",
        _make_board(100, 60, _footprint("R2", 50, 30, 8, 4)),
    )
    cases.append((p4, 5.0))
    # Exact ties in courtyard area (sorted() stability is observable).
    tie = _footprint("T1", 10.0, 10.0, 6.0, 6.0) + _footprint("T2", 40.0, 40.0, 6.0, 6.0)
    p5 = _write_pcb(tmp_path, "ties.kicad_pcb", _make_board(90.0, 90.0, tie))
    cases.append((p5, 5.0))
    return cases


def test_compute_area_sufficiency_oracle_vs_shim(tmp_path):
    for pcb, margin in _board_cases(tmp_path):
        oracle_result = _ORACLE_COMPUTE(pcb, margin_mm=margin)
        shim_result = compute_area_sufficiency(pcb, margin_mm=margin)
        assert _result_key(shim_result) == _result_key(oracle_result), (
            f"{pcb.name} margin={margin}: shim {shim_result!r} vs oracle {oracle_result!r}"
        )


def test_compute_top_courtyards_oracle_vs_shim(tmp_path):
    for pcb, _margin in _board_cases(tmp_path):
        for n in (0, 1, 3, 8, 100, -1, -2, -100):
            oracle_pairs = _ORACLE_TOP(pcb, n=n)
            shim_pairs = compute_top_courtyards(pcb, n=n)
            assert _pairs_key(shim_pairs) == _pairs_key(oracle_pairs), (
                f"{pcb.name} n={n}: shim {shim_pairs} vs oracle {oracle_pairs}"
            )


def test_non_positive_usable_area_raises_identical_message(tmp_path):
    pcb = _write_pcb(tmp_path, "tiny.kicad_pcb", _make_board(10.0, 10.0))
    for margin in (5.0, 6.0, 100.0):
        with pytest.raises(ValueError) as oracle_exc:
            _ORACLE_COMPUTE(pcb, margin_mm=margin)
        with pytest.raises(ValueError) as shim_exc:
            compute_area_sufficiency(pcb, margin_mm=margin)
        assert str(shim_exc.value) == str(oracle_exc.value), (
            f"margin={margin}: shim {str(shim_exc.value)!r} vs oracle {str(oracle_exc.value)!r}"
        )


def test_non_positive_usable_area_int_dims_identical_message(tmp_path):
    # Integer board dims render as "10" in the message, not "10.0".
    pcb = _write_pcb(tmp_path, "tiny_int.kicad_pcb", _make_board(10, 10))
    with pytest.raises(ValueError) as oracle_exc:
        _ORACLE_COMPUTE(pcb, margin_mm=6.0)
    with pytest.raises(ValueError) as shim_exc:
        compute_area_sufficiency(pcb, margin_mm=6.0)
    assert str(shim_exc.value) == str(oracle_exc.value)


# ---------------------------------------------------------------------------
# Kernel-linkage arm: area_sufficiency_compute total == py_sum(areas).
# ---------------------------------------------------------------------------


def test_compute_total_equals_py_sum_on_adversarial_areas():
    for areas in _float_corpus():
        total, _usable, _ratio, _w, _h, n = AREA_SUFFICIENCY_COMPUTE(100.0, 100.0, 5.0, areas)
        assert _sum_key(total) == _sum_key(PY_SUM(areas)), f"{areas!r}"
        assert n == len(areas)


def test_compute_ratio_is_total_over_usable_times_100():
    areas = [10.0, 20.5, 3.25]
    total, usable, ratio, w, h, n = AREA_SUFFICIENCY_COMPUTE(100.0, 100.0, 5.0, areas)
    assert usable == 90.0 * 90.0
    assert ratio == (float(total) / usable) * 100.0
    assert w == 100.0 and h == 100.0 and n == 3


def test_compute_returns_original_width_height_objects():
    # int board dims must pass through unchanged (leaf-type parity).
    total, usable, ratio, w, h, n = AREA_SUFFICIENCY_COMPUTE(100, 60, 5.0, [4.0])
    assert type(w) is int and w == 100
    assert type(h) is int and h == 60


def test_compute_ratio_ordering_matches_oracle_on_overflow_band():
    # The oracle computes raw_ratio_pct = (total / usable) * 100.0, NOT
    # (total * 100.0) / usable: at total == usable == 1e308 the former is
    # 100.0 while the latter overflows to inf.  The shim must reproduce
    # the oracle's operand order.
    total, usable, ratio, w, h, n = AREA_SUFFICIENCY_COMPUTE(1e154, 1e154, 5.0, [1e308])
    assert usable == 1e308
    assert ratio == (float(total) / usable) * 100.0
    assert ratio == 100.0
