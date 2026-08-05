"""Differential test: deterministic channels routability compute, Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). The hot-path compute of
``temper_placer/deterministic/channels.py`` — the worst-severity bottleneck
index build and the ``routability_penalty`` kernel (floor-to-cell, occupancy
clamp, severity-weight arithmetic) — moves to the ``temper-design-bundle``
crate (``temper_design_bundle_python.deterministic_hubs``). The Python module
keeps its public API (``ChannelMap``/``Bottleneck`` stay Python dataclasses —
``dataclasses.replace`` and ``FrozenInstanceError`` are load-bearing for the
2,410-test deterministic + router_v6 suites) and delegates the index build +
penalty to Rust.

The pre-migration implementation is pinned VERBATIM as the oracle
(``_channels_py_oracle.py``) and every assertion here drives IDENTICAL inputs
through both sides.

Bit-exactness conventions (R1a): floats compare via ``float.hex()`` — never a
tolerance; every leaf carries its concrete type via ``canon``
(``tests/core/_contract_canon.py``).

Numerical pins:
- The penalty kernel uses naive ``floor(a / b)`` (the oracle calls
  ``math.floor((x_mm * 1000.0) / cell_size_um)``) — NOT CPython float
  floor-division (that is only used by ``BottleneckMap.score_at``, pinned in
  the bottleneck_map differential).
- ``0.5 + 0.5 * occupancy`` and the severity-weight product are single IEEE-754
  ops; bit-identical on both sides.
- Index-build order-invariance: when several bottlenecks share a cell the
  oracle keeps the worst severity (ties: highest score) while iterating a
  Python ``set`` (per-process-arbitrary order); the penalty reads only the
  kept bottleneck's severity, so the outcome is order-invariant. The shuffled
  payloads below assert that empirically (the anti-vacuity permutation pin).
"""

from __future__ import annotations

import itertools
import json
import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic._channels_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_BUILD = _DH.build_channel_index
RS_PENALTY = _DH.ChannelIndex.penalty


# ---------------------------------------------------------------------------
# Payload + slot generators
# ---------------------------------------------------------------------------

_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _payload(
    *,
    grid=None,
    cell_size_um=1000.0,
    bottlenecks=None,
    schema_hash="temper.channels.v1",
):
    if grid is None:
        grid = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    return {
        "temper_schema_hash": schema_hash,
        "cell_size_um": cell_size_um,
        "grid": grid,
        "bottlenecks": bottlenecks or [],
    }


def _slots(w, h, cell_size_um):
    """Probe slots covering in-grid, on-boundary, straddling, and OOB cells."""
    mm = cell_size_um / 1000.0
    out = []
    for gx in range(-1, w + 1):
        for gy in range(-1, h + 1):
            # cell centre, lower-left corner, and a 1 µm straddle on both edges
            out.append((gx * mm + mm / 2.0, gy * mm + mm / 2.0))
            out.append((gx * mm, gy * mm))
            out.append((gx * mm - 1e-4, gy * mm))
            out.append((gx * mm + 1e-4, gy * mm))
            out.append((gx * mm, gy * mm + 1e-4))
    # deep OOB and negative probes
    out += [(-500.0, -500.0), (1e5, 1e5), (0.0, 0.0), (0.3, 0.7)]
    return out


def _bottleneck_entries(seed):
    rng = random.Random(seed)
    entries = []
    for _ in range(rng.randrange(0, 6)):
        entries.append(
            {
                "x": rng.randrange(-1, 4),
                "y": rng.randrange(-1, 4),
                "layer": "F.Cu",
                "severity": rng.choice(_SEVERITIES),
                "score": round(rng.uniform(0.0, 1.0), 3),
            }
        )
    return entries


# ---------------------------------------------------------------------------
# R1a — bit-identical parity through the shim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 7])
def test_penalty_parity_shim_path(seed):
    """Shim ChannelMap (Rust index) vs oracle ChannelMap (Python index) — the
    full load path, penalties bit-identical over a dense slot probe."""
    payload = _payload(
        grid=[
            [round(random.Random(seed * 100 + i).uniform(0, 1), 3) for _ in range(4)]
            for i in range(4)
        ],
        cell_size_um=random.Random(seed).choice([250.0, 500.0, 1000.0]),
        bottlenecks=_bottleneck_entries(seed),
    )
    oracle_map = _oracle.ChannelMap._from_payload(payload)
    shim_map = _tdb_shim_map(payload)
    for slot in _slots(4, 4, payload["cell_size_um"]):
        o = _oracle.routability_penalty(slot, oracle_map)
        s = shim_penalty(slot, shim_map)
        assert canon(s) == canon(o), f"penalty divergence at slot {slot}: {s} vs {o}"


def _tdb_shim_map(payload):
    """Build the shim's ChannelMap through its public load path."""
    from temper_placer.deterministic.channels import ChannelMap

    return ChannelMap._from_payload(payload)


def shim_penalty(slot, channel_map):
    from temper_placer.deterministic.channels import routability_penalty

    return routability_penalty(slot, channel_map)


def test_penalty_parity_empty_map():
    """Empty map always returns 0.0 on both sides (empty-input semantics)."""
    oracle_map = _oracle.ChannelMap.empty()
    shim_map = _tdb_shim_map(_payload())
    assert shim_map.has_grid()
    for slot in [(0.0, 0.0), (5.0, 5.0), (-1.0, -1.0), (1e5, 1e5)]:
        assert canon(shim_penalty(slot, _oracle.ChannelMap.empty())) == canon(
            _oracle.routability_penalty(slot, oracle_map)
        )


# ---------------------------------------------------------------------------
# R1a — kernel driven directly (no Python shim in the path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 4, 9])
def test_penalty_parity_direct_kernel(seed):
    """Drive build_channel_index + ChannelIndex.penalty directly against the
    oracle's routability_penalty on a Python-built equivalent map."""
    w = h = 4
    grid = [
        [round(random.Random(seed * 37 + i).uniform(0, 1), 3) for _ in range(w)]
        for i in range(h)
    ]
    cell_size_um = random.Random(seed).choice([250.0, 500.0, 1000.0, 2000.0])
    entries = _bottleneck_entries(seed)
    payload = _payload(grid=grid, cell_size_um=cell_size_um, bottlenecks=entries)
    oracle_map = _oracle.ChannelMap._from_payload(payload)

    grid_flat = [cell for row in grid for cell in row]
    bn_flat = [(e["x"], e["y"], e["severity"], e["score"]) for e in entries]
    index = RS_BUILD(cell_size_um, w, h, grid_flat, bn_flat)

    for slot in _slots(w, h, cell_size_um):
        o = _oracle.routability_penalty(slot, oracle_map)
        s = RS_PENALTY(index, slot[0], slot[1])
        assert canon(s) == canon(o), f"direct kernel divergence at {slot}: {s} vs {o}"


def test_index_order_invariance_shuffled_bottlenecks():
    """Same cell, several bottlenecks, all 6 permutations of the entry order
    must produce the same penalty on both sides (no sort-to-stabilise; the
    worst-severity/max-score selection is proven order-invariant in effect)."""
    grid = [[0.5, 0.5], [0.5, 0.5]]
    entries = [
        {"x": 1, "y": 1, "layer": "F.Cu", "severity": s, "score": sc}
        for s, sc in [
            ("LOW", 0.9),
            ("HIGH", 0.3),
            ("MEDIUM", 0.5),
            ("CRITICAL", 0.1),
            ("LOW", 0.95),
        ]
    ]
    payload = _payload(grid=grid, cell_size_um=1000.0, bottlenecks=entries)
    oracle_map = _oracle.ChannelMap._from_payload(payload)
    outcomes = set()
    for perm in itertools.permutations(entries):
        p = _payload(grid=grid, cell_size_um=1000.0, bottlenecks=list(perm))
        shim_map = _tdb_shim_map(p)
        outcomes.add(canon(shim_penalty((1.5, 1.5), shim_map)))
        outcomes.add(canon(_oracle.routability_penalty((1.5, 1.5), oracle_map)))
    assert len(outcomes) == 1, f"penalty not order-invariant: {outcomes}"


def test_penalty_nonfinite_slot_error_parity():
    """NaN/±inf slots raise the EXACT Python errors on both sides:
    ``math.floor(nan)`` -> ValueError, ``math.floor(±inf)`` -> OverflowError
    (the Rust kernel must not let ``as i64`` saturate NaN into cell (0, 0))."""
    grid = [[0.5, 0.5], [0.5, 0.5]]
    entries = [{"x": 0, "y": 0, "layer": "F.Cu", "severity": "HIGH", "score": 0.9}]
    payload = _payload(grid=grid, cell_size_um=1000.0, bottlenecks=entries)
    oracle_map = _oracle.ChannelMap._from_payload(payload)
    shim_map = _tdb_shim_map(payload)
    for slot in [
        (float("nan"), 0.5),
        (0.5, float("nan")),
        (float("inf"), 0.5),
        (float("-inf"), 0.5),
    ]:
        o = canon_call_raises(_oracle.routability_penalty, slot, oracle_map)
        s = canon_call_raises(shim_penalty, slot, shim_map)
        assert s == o, f"non-finite penalty divergence at {slot}: {s} vs {o}"


def test_penalty_severity_weight_pins():
    """One bottleneck per severity at a fixed occupancy — pins the exact
    weight arithmetic ``weight * (0.5 + 0.5 * occupancy)`` (discriminates
    weight-value mutants like M3 in the mutation campaign)."""
    grid = [[0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]]
    for i, sev in enumerate(_SEVERITIES):
        entries = [{"x": i, "y": 0, "layer": "F.Cu", "severity": sev, "score": 1.0}]
        payload = _payload(grid=grid, cell_size_um=1000.0, bottlenecks=entries)
        oracle_map = _oracle.ChannelMap._from_payload(payload)
        shim_map = _tdb_shim_map(payload)
        slot = (i * 1.0 + 0.5, 0.5)
        o = _oracle.routability_penalty(slot, oracle_map)
        s = shim_penalty(slot, shim_map)
        assert canon(s) == canon(o), f"weight pin divergence for {sev}: {s} vs {o}"
        assert canon(o) == canon(_oracle.SEVERITY_WEIGHTS[sev] * 0.75)


def test_schema_and_cell_validation_error_parity():
    """Malformed payloads raise ChannelSidecarError with IDENTICAL messages on
    both sides (the shim keeps the message-exact Python validation)."""

    bad_payloads = [
        _payload(schema_hash="temper.channels.v999"),
        _payload(cell_size_um=-5),
        _payload(cell_size_um="big"),
        _payload(grid=[]),
        _payload(grid=[[0.0, 0.0], [0.0]]),  # ragged
        _payload(grid=[[0.0, "x"]]),
        _payload(grid=[[1.5]]),  # occupancy out of range
        _payload(bottlenecks=[{"x": 0, "y": 0, "severity": "GIGA", "score": 1.0}]),
        _payload(bottlenecks=[{"x": "a", "y": 0, "severity": "LOW", "score": 1.0}]),
        _payload(bottlenecks=[{"x": 0, "y": 0, "severity": "LOW", "score": "hi"}]),
        "not a dict",
    ]
    for payload in bad_payloads:
        o = canon_call_raises(_oracle.ChannelMap._from_payload, payload)
        s = canon_call_raises(_tdb_shim_map, payload)
        assert s == o, f"error parity divergence for {payload!r}: {s} vs {o}"


def canon_call_raises(fn, *args, **kwargs):
    try:
        return ("ok", fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 — comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))


def test_sidecar_file_roundtrip_parity(tmp_path):
    """End-to-end load_from_sidecar: shim vs oracle, penalties identical."""
    payload = _payload(
        grid=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        cell_size_um=500.0,
        bottlenecks=[{"x": 1, "y": 1, "layer": "F.Cu", "severity": "HIGH", "score": 0.9}],
    )
    path = tmp_path / "placement.channels.json"
    path.write_text(json.dumps(payload))

    from temper_placer.deterministic.channels import ChannelMap

    oracle_map = _oracle.ChannelMap.load_from_sidecar(path)
    shim_map = ChannelMap.load_from_sidecar(path)
    for slot in _slots(3, 3, 500.0):
        assert canon(shim_penalty(slot, shim_map)) == canon(
            _oracle.routability_penalty(slot, oracle_map)
        )


def test_bottleneck_to_dict_parity():
    """Bottleneck.to_dict surface is unchanged (container stays Python)."""
    from temper_placer.deterministic.channels import Bottleneck

    b = Bottleneck(x=1, y=2, layer="In1.Cu", severity="HIGH", score=0.75)
    assert b.to_dict() == {"x": 1, "y": 2, "layer": "In1.Cu", "severity": "HIGH", "score": 0.75}
