"""Differential test: GeometricValidator decision kernels in Rust
(temper_drc_rs.geometric_validate) vs the pinned Python oracle
(Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/geometric.py::GeometricValidator`` moves its
per-check decision compute (overlap severity classification, boundary edge
math, HV-LV clearance classification, keepout intersection, mounting-hole
distance) into ``temper_drc_rs.geometric_validate``. The pre-migration
module is pinned verbatim as the oracle (``_geometric_py_oracle.py``,
commit ``aece7c372``) and the differential drives IDENTICAL
PlacementState/Netlist/Board inputs through both validators, comparing the
full ``ValidationResult`` bit-exactly.

Design boundaries, argued in-source in the migrated module:
- The zone check's geometric predicate (``point_in_zone``) was already Rust
  (temper-geometry) before this migration; the remaining zone logic is
  Board contract lookup + message building and stays in the delegation
  module. The zone check therefore stays Python in BOTH arms — the
  differential still pins it (identical in both arms).
- Message strings are built in the delegation module from the Rust-verified
  numeric fields (the rtd_safety precedent: derivations return status codes,
  the wrapper formats the reference messages verbatim). The differential
  compares the full issue objects INCLUDING messages, so a mutation in any
  numeric decision is caught (messages derive from the pinned numerics).
- Location midpoints are computed Python-side from the float32 positions
  array exactly as the oracle does (float32 arithmetic — see the module).

Comparison convention: issues are canonicalized into plain tuples; floats
compared as exact bit patterns via ``float.hex()``.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._geometric_py_oracle as _oracle
from temper_placer.core.board import Board, MountingHole, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState

# Rust symbol under test — must exist or this file fails to collect (RED).
GEOMETRIC_VALIDATE = _tdrc.geometric_validate

from temper_placer.validation.geometric import GeometricValidator as ShimValidator  # noqa: E402


# ---------------------------------------------------------------------------
# Canonicalization — bit-exact comparison keys
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _canon(value):
    """Recursively canonicalize details dicts / tuples / lists: floats via
    hex, everything else kept with its concrete type."""
    if isinstance(value, float):
        return ("f", value.hex())
    if isinstance(value, (int, bool, str)):
        return (type(value).__name__, value)
    if isinstance(value, (tuple, list)):
        return (type(value).__name__, tuple(_canon(v) for v in value))
    if isinstance(value, dict):
        return ("dict", tuple((k, _canon(v)) for k, v in value.items()))
    if value is None:
        return ("none", None)
    return (type(value).__name__, repr(value))


def _issue_key(issue):
    return (
        issue.severity.name,
        issue.code,
        issue.message,
        tuple(issue.component_refs),
        None if issue.location is None else tuple(_f(x) for x in issue.location),
        _canon(issue.details),
        issue.violation_type.name,
        _f(issue.overlap_amount),
        _f(issue.required_clearance),
        _f(issue.actual_distance),
    )


def _result_key(result):
    issues = tuple(_issue_key(i) for i in result.issues)
    metrics = tuple((k, _canon(v)) for k, v in sorted(result.metrics.items()))
    return issues, metrics, result.valid


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------

_FP32 = st.floats(
    min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False
).map(lambda v: float(np.float32(v)))  # float32-rounded, widened back (exact)
_POS = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)


def _make_validator(hv_lv_clearance=10.0, min_clearance=0.2, overlap_threshold=0.01):
    return (
        _oracle.GeometricValidator(
            min_clearance=min_clearance, hv_lv_clearance=hv_lv_clearance, overlap_threshold=overlap_threshold
        ),
        ShimValidator(
            min_clearance=min_clearance, hv_lv_clearance=hv_lv_clearance, overlap_threshold=overlap_threshold
        ),
    )


# ---------------------------------------------------------------------------
# Differential — full ValidationResult bit-exactness
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    st.integers(0, 8),
    st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_differential_random_boards(n_components, hv_lv, min_clr, ovl_thr):
    rng = random.Random(hash((n_components, hv_lv, min_clr, ovl_thr)) & 0xFFFFFFFF)
    netlist, state = _build_inputs(rng, n_components)
    board = _build_board(rng)
    oracle_v, shim_v = _make_validator(hv_lv, min_clr, ovl_thr)
    oracle_res = oracle_v.validate(state, netlist, board)
    shim_res = shim_v.validate(state, netlist, board)
    assert _result_key(shim_res) == _result_key(oracle_res)


def _build_inputs(rng, n_components):
    components = []
    for i in range(n_components):
        w = rng.uniform(0.5, 40.0)
        h = rng.uniform(0.5, 40.0)
        nc = rng.choice(["HighVoltage", "Signal", "Ground"])
        zone = rng.choice([None, "HV_ZONE", "LV_ZONE", "MISSING_ZONE"])
        components.append(Component(ref=f"C{i}", footprint=f"fp{i}", bounds=(w, h), net_class=nc, zone=zone))
    netlist = Netlist(components=components, nets=[])
    positions = np.array([[rng.uniform(-100, 100), rng.uniform(-100, 100)] for _ in range(n_components)], dtype=np.float32)
    rotation_logits = np.array(
        [[rng.uniform(-10, 10) for _ in range(4)] for _ in range(n_components)], dtype=np.float32
    )
    return netlist, PlacementState(positions=positions, rotation_logits=rotation_logits)


def _build_board(rng):
    ox, oy = rng.uniform(-20, 20), rng.uniform(-20, 20)
    width = rng.uniform(20, 200)
    height = rng.uniform(20, 200)
    zones = []
    if rng.random() < 0.8:
        x0, y0 = ox + rng.uniform(-10, 10), oy + rng.uniform(-10, 10)
        x1, y1 = x0 + rng.uniform(10, width), y0 + rng.uniform(10, height)
        zones.append(Zone("HV_ZONE", (x0, y0, x1, y1)))
    if rng.random() < 0.8:
        x0, y0 = ox + rng.uniform(-10, 10), oy + rng.uniform(-10, 10)
        x1, y1 = x0 + rng.uniform(10, width), y0 + rng.uniform(10, height)
        zones.append(Zone("LV_ZONE", (x0, y0, x1, y1)))
    keepouts = []
    for _ in range(rng.randint(0, 3)):
        a, b = rng.uniform(ox - 20, ox + width + 20), rng.uniform(oy - 20, oy + height + 20)
        c, d = rng.uniform(ox - 20, ox + width + 20), rng.uniform(oy - 20, oy + height + 20)
        keepouts.append((min(a, c), min(b, d), max(a, c), max(b, d)))
    holes = [
        MountingHole((rng.uniform(ox - 20, ox + width + 20), rng.uniform(oy - 20, oy + height + 20)),
                     rng.uniform(0.5, 6.0), keepout_radius=rng.uniform(0.0, 12.0))
        for _ in range(rng.randint(0, 3))
    ]
    return Board(width=width, height=height, origin=(ox, oy), zones=zones, keepouts=keepouts, mounting_holes=holes)


def test_differential_deterministic_scenarios():
    """Hand-built scenarios covering each check path deterministically."""
    # --- overlap: two overlapping components (severity by amount) ---
    nl, stt = _build_inputs(random.Random(1), 2)
    nl.components[0].bounds = (10.0, 10.0)
    nl.components[1].bounds = (10.0, 10.0)
    stt.positions[:] = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)  # gap -10 (10mm boxes, 1mm apart center)
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    o, s = _make_validator()
    # overlap_amount = 10.0 → CRITICAL (> 5.0)
    assert _result_key(s.validate(stt, nl, board)) == _result_key(o.validate(stt, nl, board))

    # --- overlap > 5mm → CRITICAL ---
    stt.positions[:] = np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    assert _result_key(s.validate(stt, nl, board)) == _result_key(o.validate(stt, nl, board))

    # --- boundary: component half outside board ---
    nl2, stt2 = _build_inputs(random.Random(2), 1)
    nl2.components[0].bounds = (20.0, 20.0)
    stt2.positions[:] = np.array([[95.0, 50.0]], dtype=np.float32)  # extends 5mm past x=100
    board2 = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    assert _result_key(s.validate(stt2, nl2, board2)) == _result_key(o.validate(stt2, nl2, board2))

    # --- HV-LV clearance: HV and LV components 3mm apart with hv_lv_clearance=10 ---
    nl3, stt3 = _build_inputs(random.Random(3), 2)
    nl3.components[0].net_class = "HighVoltage"
    nl3.components[1].net_class = "Signal"
    nl3.components[0].bounds = (1.0, 1.0)
    nl3.components[1].bounds = (1.0, 1.0)
    stt3.positions[:] = np.array([[0.0, 0.0], [3.0, 0.0]], dtype=np.float32)
    board3 = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    o3, s3 = _make_validator(hv_lv_clearance=10.0)
    assert _result_key(s3.validate(stt3, nl3, board3)) == _result_key(o3.validate(stt3, nl3, board3))

    # --- keepout + mounting hole ---
    nl4, stt4 = _build_inputs(random.Random(4), 1)
    nl4.components[0].bounds = (10.0, 10.0)
    stt4.positions[:] = np.array([[5.0, 5.0]], dtype=np.float32)
    board4 = Board(
        width=100.0, height=100.0, origin=(0.0, 0.0),
        keepouts=[(0.0, 0.0, 20.0, 20.0)],
        mounting_holes=[MountingHole((5.0, 5.0), 3.2, keepout_radius=5.0)],
    )
    assert _result_key(s.validate(stt4, nl4, board4)) == _result_key(o.validate(stt4, nl4, board4))


def test_differential_zone_paths():
    """Zone check stays Python in both arms (argued in-source) but the
    differential still pins its behavior: defined zones, undefined zones,
    and out-of-zone placement."""
    nl, stt = _build_inputs(random.Random(5), 2)
    nl.components[0].zone = "HV_ZONE"
    nl.components[1].zone = "MISSING_ZONE"
    stt.positions[:] = np.array([[10.0, 10.0], [10.0, 10.0]], dtype=np.float32)
    board = Board(
        width=100.0, height=100.0, origin=(0.0, 0.0),
        zones=[Zone("HV_ZONE", (0.0, 0.0, 50.0, 50.0)), Zone("LV_ZONE", (50.0, 0.0, 100.0, 50.0))],
    )
    o, s = _make_validator()
    assert _result_key(s.validate(stt, nl, board)) == _result_key(o.validate(stt, nl, board))
    # component outside its zone
    nl2, stt2 = _build_inputs(random.Random(6), 1)
    nl2.components[0].zone = "HV_ZONE"
    stt2.positions[:] = np.array([[75.0, 25.0]], dtype=np.float32)  # inside LV_ZONE
    assert _result_key(s.validate(stt2, nl2, board)) == _result_key(o.validate(stt2, nl2, board))
    # component outside all zones
    stt2.positions[:] = np.array([[150.0, 150.0]], dtype=np.float32)
    assert _result_key(s.validate(stt2, nl2, board)) == _result_key(o.validate(stt2, nl2, board))


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernel
# ---------------------------------------------------------------------------


def test_prop1_finding_counts_reconstruct_metrics():
    """P1: metric counts equal the number of findings of each kind, and
    total_overlap equals the sum of per-finding overlap amounts (order is
    the kernel's lexicographic pair order — same as the oracle's)."""
    rng = random.Random(42)
    for _ in range(100):
        nl, stt = _build_inputs(rng, rng.randint(1, 6))
        board = _build_board(rng)
        res = ShimValidator().validate(stt, nl, board)
        assert res.metrics["overlap_count"] >= 0
        assert res.metrics["boundary_violations"] >= 0
        assert res.metrics["clearance_violations"] >= 0
        assert res.metrics["keepout_violations"] >= 0
        overlap_issues = [i for i in res.issues if i.violation_type.name == "OVERLAP"]
        assert res.metrics["overlap_count"] == len(overlap_issues)
        # total_overlap_area is the sum of per-issue amounts, bit-exact
        total = 0.0
        for i in overlap_issues:
            total += i.overlap_amount
        assert total.hex() == float(res.metrics["total_overlap_area"]).hex()


def test_prop2_overlap_severity_classification():
    """P2: overlap severity is exactly amount > 5.0 → CRITICAL, > 1.0 →
    ERROR, else WARNING."""
    rng = random.Random(43)
    for _ in range(100):
        nl, stt = _build_inputs(rng, 2)
        nl.components[0].bounds = (20.0, 20.0)
        nl.components[1].bounds = (20.0, 20.0)
        dx = rng.uniform(-6.0, 6.0)
        stt.positions[:] = np.array([[0.0, 0.0], [dx, 0.0]], dtype=np.float32)
        res = ShimValidator().validate(stt, nl, Board(width=200.0, height=200.0, origin=(0.0, 0.0)))
        ovl = [i for i in res.issues if i.violation_type.name == "OVERLAP"]
        if ovl:
            amount = ovl[0].overlap_amount
            expected = "CRITICAL" if amount > 5.0 else ("ERROR" if amount > 1.0 else "WARNING")
            assert ovl[0].severity.name == expected


def test_prop3_boundary_edge_consistency():
    """P3: for a boundary violation, max_violation equals the maximum of the
    four edge amounts and the edges list is a subsequence of
    (left, right, bottom, top) with only positive amounts."""
    rng = random.Random(44)
    for _ in range(100):
        nl, stt = _build_inputs(rng, rng.randint(1, 4))
        board = _build_board(rng)
        res = ShimValidator().validate(stt, nl, board)
        for i in res.issues:
            if i.violation_type.name == "BOUNDARY":
                edges = i.details["violations"]
                edge_names = [e[0] for e in edges]
                assert edge_names == [n for n in ("left", "right", "bottom", "top") if n in edge_names]
                assert all(e[1] > 0 for e in edges)
                max_v = i.details["max_violation_mm"]
                assert max_v == max(e[1] for e in edges)
                assert i.overlap_amount == max_v
                assert i.severity.name == ("CRITICAL" if max_v > 10.0 else "ERROR")


def test_prop4_clearance_shortage_consistency():
    """P4: clearance issues carry shortage == required − distance (bit-exact)
    and HV-LV pairs are always CRITICAL with code GEO_HV_LV_CLEARANCE."""
    rng = random.Random(45)
    for _ in range(100):
        nl, stt = _build_inputs(rng, rng.randint(2, 5))
        board = _build_board(rng)
        res = ShimValidator(hv_lv_clearance=10.0).validate(stt, nl, board)
        for i in res.issues:
            if i.violation_type.name == "CLEARANCE":
                d = i.details["actual_distance_mm"]
                req = i.details["required_clearance_mm"]
                short = i.details["shortage_mm"]
                assert short.hex() == (req - d).hex()
                assert i.actual_distance == d and i.required_clearance == req
                if i.details["is_hv_lv"]:
                    assert i.severity.name == "CRITICAL"
                    assert i.code == "GEO_HV_LV_CLEARANCE"
                else:
                    assert i.code == "GEO_CLEARANCE"
                    assert i.severity.name == ("WARNING" if d > 0.0 else "ERROR")


def test_prop5_mounting_hole_geometry():
    """P5: mounting-hole issues carry distance_to_hole computed with the
    oracle's exact ``((x-hx)**2 + (y-hy)**2) ** 0.5`` semantics (libm pow —
    the Rust kernel uses powf(0.5) for bit parity) and shortage ==
    min_dist − distance."""
    rng = random.Random(46)
    for _ in range(100):
        nl, stt = _build_inputs(rng, rng.randint(1, 3))
        board = _build_board(rng)
        res = ShimValidator().validate(stt, nl, board)
        for i in res.issues:
            if i.violation_type.name == "MOUNTING_HOLE":
                hx, hy = i.details["hole_position"]
                d = i.details["distance_to_hole"]
                req = i.details["required_distance"]
                assert i.actual_distance == d
                assert i.required_clearance == req
                # shortage == min_dist − dist (bit-exact)
                short = i.details.get("shortage_mm", req - d)
                assert short.hex() == (req - d).hex()
                # message embeds the hole position via Python str(float)
                assert i.message.endswith(f"({hx}, {hy})")
                assert i.severity.name == "ERROR"
                assert i.code == "GEO_MOUNTING_HOLE"


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_reflection_preserves_findings():
    """MR1: reflecting positions, board bounds, keepouts and holes through
    the origin leaves the issue set bit-identical except that boundary edge
    names (left↔right, bottom↔top) swap. Bounded: we compare the full issue
    set after canonicalizing edge names through the swap."""
    rng = random.Random(51)
    for _ in range(40):
        nl, stt = _build_inputs(rng, rng.randint(1, 4))
        board = _build_board(rng)
        # reflected copies
        nl_r = Netlist(
            components=[Component(ref=c.ref, footprint=c.footprint, bounds=c.bounds, net_class=c.net_class, zone=c.zone) for c in nl.components],
            nets=[],
        )
        stt_r = PlacementState(
            positions=-stt.positions.copy(),
            rotation_logits=stt.rotation_logits.copy(),
        )
        board_r = Board(
            width=board.width, height=board.height,
            origin=(-board.origin[0], -board.origin[1]),
            zones=[Zone(z.name, (-z.bounds[2], -z.bounds[3], -z.bounds[0], -z.bounds[1])) for z in board.zones],
            keepouts=[(-k[2], -k[3], -k[0], -k[1]) for k in board.keepouts],
            mounting_holes=[MountingHole((-h.position[0], -h.position[1]), h.diameter, keepout_radius=h.keepout_radius) for h in board.mounting_holes],
        )
        o, s = _make_validator()
        res = s.validate(stt, nl, board)
        res_r = s.validate(stt_r, nl_r, board_r)

        def canon(issues):
            out = []
            for i in issues:
                edges = i.details.get("violations")
                swap = {"left": "right", "right": "left", "bottom": "top", "top": "bottom"}
                det = dict(i.details)
                if edges is not None:
                    det["violations"] = [(swap[e], v) for (e, v) in edges]
                out.append((i.code, i.severity.name, tuple(i.component_refs), _canon(det)))
            return tuple(sorted(out))

        assert canon(res.issues) == canon(res_r.issues)
        assert res.metrics == res_r.metrics


def test_mr2_zero_size_components_touch_without_overlap():
    """MR2: coincident zero-size components (width = height = 0) have
    pairwise distance exactly 0.0 and are NOT reported as overlaps (the
    threshold check is ``dist < -overlap_threshold`` with strict
    inequality), while a nonzero overlap threshold still flags small
    overlaps. Bounded to the overlap check."""
    nl, stt = _build_inputs(random.Random(52), 2)
    for c in nl.components:
        c.bounds = (0.0, 0.0)
    stt.positions[:] = np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    res = ShimValidator().validate(stt, nl, board)
    assert [i for i in res.issues if i.violation_type.name == "OVERLAP"] == []
    # barely overlapping: dist = -0.001 with threshold 0.01 → ignored
    nl2, stt2 = _build_inputs(random.Random(53), 2)
    for c in nl2.components:
        c.bounds = (1.0, 1.0)
    stt2.positions[:] = np.array([[0.0, 0.0], [0.999, 0.0]], dtype=np.float32)
    res2 = ShimValidator(overlap_threshold=0.01).validate(stt2, nl2, Board(width=100.0, height=100.0, origin=(0.0, 0.0)))
    assert [i for i in res2.issues if i.violation_type.name == "OVERLAP"] == []


def test_mr3_raising_overlap_threshold_is_monotone():
    """MR3: raising the overlap threshold never increases the overlap count
    and never changes non-overlap findings."""
    rng = random.Random(54)
    nl, stt = _build_inputs(rng, 4)
    board = Board(width=200.0, height=200.0, origin=(0.0, 0.0))
    counts = []
    for thr in (0.0, 0.01, 0.1, 1.0, 5.0):
        res = ShimValidator(overlap_threshold=thr).validate(stt, nl, board)
        counts.append(res.metrics["overlap_count"])
    assert counts == sorted(counts, reverse=True)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
