"""Differential test: Rust reference-loader kernels (temper_design_bundle_python)
vs the pinned Python oracle.

Wave 4, Phase 3, candidate 5 — the config/reference loaders migration (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, candidate
5).

Scope note (boundary decision, argued in VERIFICATION.md): ``reference_loader.py``
is the one module in this candidate whose *load* path goes through the KiCad
parse engine (``parse_kicad_pcb`` — candidate 3, built in parallel and not
touched here) and numpy ``PlacementState`` (Phase 4/5). Only the two pure
kernels — ``compute_design_stats`` (rounds via CPython's own ``round()``,
called back across the boundary — half-to-even, per the candidate-6 trap) and
``infer_quality_config`` (string classification heuristics) — are migrated
here. ``load_reference_pcb`` / ``filter_components`` /
``netlist_to_placement_state`` / ``list_reference_designs`` stay Python until
the parse engine and ``PlacementState`` land.

The Rust symbols (in ``temper_design_bundle_python``) must reproduce the
pre-migration implementation of ``temper_placer/io/reference_loader.py``
bit-identically, pinned verbatim as the oracle
(``_reference_loader_py_oracle.py``, commit 79ab9bd0e). Floats are compared
as exact bit patterns via ``float.hex()`` and every dict leaf carries its
concrete ``type``.
"""

from __future__ import annotations

from types import SimpleNamespace

import temper_design_bundle_python as _tdb

import tests.io._reference_loader_py_oracle as _oracle
from tests.io._netlist_builder import build_two_component_netlist

COMPUTE_STATS = _tdb.compute_design_stats
INFER_QUALITY = _tdb.infer_quality_config


def _f(value):
    return None if value is None else float(value).hex()


def _stats_key(stats):
    """Canonical key for the stats dict: floats bit-exact, sets sorted,
    every leaf typed."""
    out = []
    for key in sorted(stats.keys()):
        v = stats[key]
        if isinstance(v, float):
            out.append((key, "float", v.hex()))
        elif isinstance(v, int) and not isinstance(v, bool):
            out.append((key, "int", v))
        elif isinstance(v, str):
            out.append((key, "str", v))
        elif isinstance(v, list):
            out.append((key, "list", tuple((type(e).__name__, e) for e in v)))
        elif isinstance(v, set):
            out.append((key, "set", tuple(sorted(v))))
        else:
            out.append((key, type(v).__name__, v))
    return tuple(out)


def _netlist_with(*comps):
    from temper_placer.core.netlist import Netlist

    return Netlist(components=list(comps), nets=[])


def _parse_result_like(netlist, board=None, warnings=()):
    return SimpleNamespace(netlist=netlist, board=board, warnings=warnings)


# ---------------------------------------------------------------------------
# compute_design_stats parity.
# ---------------------------------------------------------------------------


def test_compute_design_stats_matches_oracle_on_two_component_netlist():
    from temper_placer.core.board import Board

    netlist = build_two_component_netlist()
    result = _parse_result_like(netlist, Board(width=100.0, height=50.0), warnings=["w1", "w2"])
    assert _stats_key(COMPUTE_STATS(result)) == _stats_key(_oracle.compute_design_stats(result))


def test_compute_design_stats_without_board_matches_oracle():
    netlist = build_two_component_netlist()
    result = _parse_result_like(netlist, board=None, warnings=[])
    assert _stats_key(COMPUTE_STATS(result)) == _stats_key(_oracle.compute_design_stats(result))


def test_compute_design_stats_empty_netlist_matches_oracle():
    from temper_placer.core.netlist import Netlist

    empty = Netlist(components=[], nets=[])
    result = _parse_result_like(empty, None, [])
    assert _stats_key(COMPUTE_STATS(result)) == _stats_key(_oracle.compute_design_stats(result))


def test_compute_design_stats_footprint_type_extraction_matches_oracle():
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [
        Component(ref="U1", footprint="Package_SO:SOIC-8", bounds=(5.0, 4.0)),
        Component(ref="Q1", footprint="TO-247-3", bounds=(16.0, 21.0)),
        Component(ref="R1", footprint="R_0805", bounds=(2.0, 1.25)),
    ]
    nets = [
        Net(name="NET_A", pins=[("U1", "1"), ("Q1", "2"), ("R1", "1")], net_class="Signal"),
        Net(name="NET_B", pins=[("U1", "2"), ("R1", "2")], net_class="Signal"),
    ]
    netlist = Netlist(components=comps, nets=nets)
    result = _parse_result_like(netlist, None, ["x"])
    assert _stats_key(COMPUTE_STATS(result)) == _stats_key(_oracle.compute_design_stats(result))


def test_compute_design_stats_float_rounding_matches_oracle():
    """The stats dict rounds (banker's) via CPython round() — .5 ticks must
    round half-to-even on both arms (the candidate-6 trap). The density
    ratio 6.25/100 = 0.0625 is exactly representable: round(0.0625, 3) is a
    tie, so CPython gives 0.062 while f64::round would give 0.063."""
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [
        Component(ref="R1", footprint="A:B", bounds=(2.5, 2.5)),  # area 6.25
    ]
    nets = [Net(name="N", pins=[("R1", "1")] * 3, net_class="Signal")]
    netlist = Netlist(components=comps, nets=nets)
    board = SimpleNamespace(width=10.0, height=10.0)  # area 100 -> ratio .0625
    result = _parse_result_like(netlist, board, [])
    py_key = _stats_key(_oracle.compute_design_stats(result))
    rs_key = _stats_key(COMPUTE_STATS(result))
    assert rs_key == py_key
    # non-vacuity: the discriminator actually fires (a half-away-from-zero
    # port would produce 0.063 here, not 0.062)
    assert _oracle.compute_design_stats(result)["density"] == 0.062


# ---------------------------------------------------------------------------
# infer_quality_config parity.
# ---------------------------------------------------------------------------


def _quality_design():
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [
        Component(ref="Q1", footprint="TO-247-3", bounds=(16.0, 21.0)),      # thermal + HV
        Component(ref="U1", footprint="Package_QFP:QFP-64", bounds=(10.0, 10.0)),  # LV-ish, area 100
        Component(ref="R1", footprint="R_0805", bounds=(2.0, 1.25)),
        Component(ref="Q2", footprint="TO-220-3", bounds=(10.0, 9.0)),       # thermal
        Component(ref="D1", footprint="D_SOD-123", bounds=(2.7, 1.6)),
        Component(ref="U2", footprint="Package_SO:SOIC-8", bounds=(5.0, 4.0)),  # LV
    ]
    nets = [
        Net(name="GATE_H", pins=[("U1", "1"), ("Q1", "1"), ("Q2", "1")], net_class="Signal"),
        Net(name="VIN", pins=[("Q1", "2"), ("Q2", "2")], net_class="Power"),
        Net(name="PWM_L", pins=[("U2", "1")], net_class="Signal"),
    ]
    return Netlist(components=comps, nets=nets)


def _quality_key(cfg):
    return tuple(
        (k, tuple(sorted(v)) if isinstance(v, (set, list)) else v)
        for k, v in sorted(cfg.items())
    )


def test_infer_quality_config_matches_oracle():
    netlist = _quality_design()
    design = SimpleNamespace(netlist=netlist)
    assert _quality_key(INFER_QUALITY(design)) == _quality_key(_oracle.infer_quality_config(design))


def test_infer_quality_config_loop_cap_matches_oracle():
    """loops[:3] caps the inferred loop list at 3 — the oracle's slice is
    load-bearing; a port that dropped it would diverge on >3 gate nets."""
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [Component(ref=f"C{i}", footprint="R_0805", bounds=(2.0, 1.25)) for i in range(8)]
    nets = [
        Net(name=f"GATE_{i}", pins=[(f"C{j}", "1") for j in range(2)], net_class="Signal")
        for i in range(5)
    ]
    netlist = Netlist(components=comps, nets=nets)
    design = SimpleNamespace(netlist=netlist)
    rs = INFER_QUALITY(design)
    py = _oracle.infer_quality_config(design)
    assert len(rs["loop_components"]) == len(py["loop_components"]) == 3


def test_infer_quality_config_min_hv_lv_clearance_constant_matches_oracle():
    netlist = _quality_design()
    design = SimpleNamespace(netlist=netlist)
    assert INFER_QUALITY(design)["min_hv_lv_clearance"] == 4.0
    assert _oracle.infer_quality_config(design)["min_hv_lv_clearance"] == 4.0
