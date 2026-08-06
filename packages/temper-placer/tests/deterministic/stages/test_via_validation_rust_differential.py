"""Differential test: deterministic via_validation compute, Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The via-connectivity counting kernel
(``ViaValidationStage._count_connected_layers``) and the via-position dedup
kernel (``ViaDeduplicationStage.run``'s sweep) of
``temper_placer/deterministic/stages/via_validation.py`` move to the
``temper-drc-rs`` crate (``temper_drc_rs.count_connected_layers_py`` /
``temper_drc_rs.dedup_via_positions_py``); the Python stage keeps its
``run`` orchestration (endpoint-index building, plane-net predicate, via
object bookkeeping) and delegates the kernels. The pre-migration
implementations are pinned VERBATIM as the oracle
(``_via_validation_py_oracle.py``).

Numerical traps pinned here:
- ``count_connected_layers``: ``tol_sq = tol * tol`` is a PLAIN MULTIPLY
  while every distance term is ``** 2`` (libm ``pow``). The Rust replicates
  the split; ``<= tol_sq`` is the boundary.
- plane layers short-circuit the trace/pin sweep; the plane special-case only
  applies when ``is_plane`` (a plane net) is True.
- ``dedup_via_positions``: ``tol_sq = tolerance ** 2`` (libm ``pow``),
  first-seen-wins in input order, ``duplicates`` counted per rejected via.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _drc
import tests.deterministic.stages._via_validation_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
RS_COUNT = _drc.count_connected_layers_py
RS_DEDUP = _drc.dedup_via_positions_py


def _assert_count(via_position, via_layers, tolerance, trace_index, pin_index, is_plane, plane_layers):
    exp = _oracle.count_connected_layers(
        via_position, via_layers, tolerance, trace_index, pin_index, is_plane, set(plane_layers)
    )
    got = RS_COUNT(
        via_position, list(via_layers), tolerance, trace_index, pin_index, is_plane, list(plane_layers)
    )
    assert got == exp, (
        f"count divergence via={via_position} layers={via_layers} tol={tolerance} "
        f"trace={trace_index} pin={pin_index} is_plane={is_plane} plane={plane_layers}: "
        f"{got} vs {exp}"
    )


# --- count_connected_layers -------------------------------------------------

def test_count_no_connections():
    _assert_count((1.0, 1.0), ["F.Cu"], 0.1, {}, {}, False, set())


def test_count_trace_within_tolerance():
    _assert_count((1.0, 1.0), ["F.Cu"], 0.1, {"F.Cu": [(1.05, 1.0)]}, {}, False, set())


def test_count_pin_within_tolerance():
    _assert_count((1.0, 1.0), ["F.Cu"], 0.1, {}, {"F.Cu": [(1.0, 1.08)]}, False, set())


def test_count_trace_just_outside_tolerance():
    _assert_count((1.0, 1.0), ["F.Cu"], 0.1, {"F.Cu": [(1.11, 1.0)]}, {}, False, set())


def test_count_trace_exactly_on_boundary():
    """dist_sq == tol_sq counts as connected (<=)."""
    tol = 0.1
    tx = 1.0 + tol  # dist = tol exactly -> dist_sq == tol*tol
    _assert_count((1.0, 1.0), ["F.Cu"], tol, {"F.Cu": [(tx, 1.0)]}, {}, False, set())


def test_count_two_layers():
    _assert_count(
        (1.0, 1.0),
        ["F.Cu", "In1.Cu"],
        0.1,
        {"F.Cu": [(1.0, 1.02)], "In1.Cu": [(1.0, 1.05)]},
        {},
        False,
        set(),
    )


def test_count_plane_net_plane_layer_auto_connected():
    _assert_count(
        (1.0, 1.0), ["In1.Cu"], 0.1, {}, {}, True, {"In1.Cu", "In2.Cu"}
    )


def test_count_plane_net_non_plane_layer_needs_trace():
    _assert_count(
        (1.0, 1.0), ["F.Cu"], 0.1, {}, {}, True, {"In1.Cu", "In2.Cu"}
    )
    _assert_count(
        (1.0, 1.0), ["F.Cu"], 0.1, {"F.Cu": [(1.0, 1.05)]}, {}, True, {"In1.Cu", "In2.Cu"}
    )


def test_count_non_plane_net_plane_layer_needs_trace():
    """Plane-layer auto-connect is gated on is_plane: a signal net on a plane
    layer still needs a trace/pin."""
    _assert_count(
        (1.0, 1.0), ["In1.Cu"], 0.1, {}, {}, False, {"In1.Cu", "In2.Cu"}
    )
    _assert_count(
        (1.0, 1.0), ["In1.Cu"], 0.1, {"In1.Cu": [(1.02, 1.0)]}, {}, False, {"In1.Cu", "In2.Cu"}
    )


def test_count_layer_connection_not_double_counted():
    """A layer connected via BOTH trace and pin counts once."""
    _assert_count(
        (1.0, 1.0),
        ["F.Cu"],
        0.1,
        {"F.Cu": [(1.02, 1.0)]},
        {"F.Cu": [(1.03, 1.0)]},
        False,
        set(),
    )


def test_count_empty_via_layers():
    _assert_count((1.0, 1.0), [], 0.1, {"F.Cu": [(1.0, 1.0)]}, {}, False, set())


def test_count_plane_plus_signal_layers():
    _assert_count(
        (1.0, 1.0),
        ["In1.Cu", "F.Cu", "B.Cu"],
        0.1,
        {"B.Cu": [(1.02, 1.0)]},
        {},
        True,
        {"In1.Cu", "In2.Cu"},
    )


def test_count_randomized():
    rng = random.Random(5)
    for _ in range(150):
        tol = rng.choice([0.05, 0.1, 0.25, 0.5])
        vx, vy = rng.uniform(-5, 5), rng.uniform(-5, 5)
        layers = rng.sample(["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], k=rng.randint(1, 4))
        trace_index = {}
        pin_index = {}
        for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]:
            pts = []
            for _ in range(rng.randint(0, 5)):
                pts.append((rng.uniform(vx - 2, vx + 2), rng.uniform(vy - 2, vy + 2)))
            if pts:
                trace_index[layer] = pts
            pts2 = []
            for _ in range(rng.randint(0, 5)):
                pts2.append((rng.uniform(vx - 2, vx + 2), rng.uniform(vy - 2, vy + 2)))
            if pts2:
                pin_index[layer] = pts2
        _assert_count((vx, vy), layers, tol, trace_index, pin_index, rng.random() < 0.5, ["In1.Cu", "In2.Cu"])


def test_count_non_vacuity_guard():
    assert RS_COUNT((1.0, 1.0), ["F.Cu"], 0.1, {"F.Cu": [(1.0, 1.0)]}, {}, False, []) == 1


# --- dedup_via_positions -----------------------------------------------------

def _assert_dedup(positions, tolerance):
    exp_unique, exp_dupes = _oracle.dedup_via_positions(list(positions), tolerance)
    got_indices, got_dupes = RS_DEDUP(list(positions), tolerance)
    got_unique = [positions[i] for i in got_indices]
    assert canon(got_unique) == canon(exp_unique), (
        f"dedup divergence positions={positions} tol={tolerance}: "
        f"{canon(got_unique)} vs {canon(exp_unique)}"
    )
    assert got_dupes == exp_dupes


def test_dedup_empty():
    _assert_dedup([], 0.05)


def test_dedup_all_distinct():
    _assert_dedup([(0.0, 0.0), (5.0, 5.0), (1.0, 9.0)], 0.05)


def test_dedup_exact_duplicate():
    _assert_dedup([(1.0, 1.0), (1.0, 1.0), (2.0, 2.0)], 0.05)


def test_dedup_within_tolerance():
    _assert_dedup([(0.0, 0.0), (0.01, 0.01), (5.0, 5.0)], 0.05)


def test_dedup_boundary():
    """dist == tol exactly -> duplicate (<=)."""
    _assert_dedup([(0.0, 0.0), (0.05, 0.0), (5.0, 5.0)], 0.05)


def test_dedup_chain_first_seen_wins():
    """A chain (0,0) (0.03,0) (0.06,0): (0.03) dup of (0.0), (0.06) NEW (0.06
    from (0.0) is > tol; from the kept (0.0) list). Order-sensitive."""
    _assert_dedup([(0.0, 0.0), (0.03, 0.0), (0.06, 0.0)], 0.05)


def test_dedup_negative_coords():
    _assert_dedup([(-1.0, -1.0), (-1.02, -1.0), (3.0, 4.0)], 0.05)


def test_dedup_randomized():
    rng = random.Random(9)
    for _ in range(150):
        tol = rng.choice([0.01, 0.05, 0.1, 0.5, 1.0])
        positions = [
            (rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(rng.randint(0, 12))
        ]
        _assert_dedup(positions, tol)


def test_dedup_non_vacuity_guard():
    indices, dupes = RS_DEDUP([(0.0, 0.0), (0.01, 0.01), (5.0, 5.0)], 0.05)
    assert len(indices) == 2 and dupes == 1
