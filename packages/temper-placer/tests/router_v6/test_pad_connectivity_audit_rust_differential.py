"""Differential and boundary tests for the Rust-owned pad audit graph."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest
import temper_geometry as _tg

from temper_placer.router_v6 import pad_connectivity_audit as audit
from tests.router_v6 import _pad_connectivity_audit_py_oracle as oracle

REPO_ROOT = Path(__file__).resolve().parents[4]


def _rust_case(pads, segments, vias, all_layers=(), tolerance=0.02, zones=()):
    result = _tg.pad_connectivity_audit_py(
        [(x, y) for x, y, _layer in pads],
        [layer for _x, _y, layer in pads],
        [(x1, y1, x2, y2) for x1, y1, x2, y2, _layer in segments],
        [layer for _x1, _y1, _x2, _y2, layer in segments],
        [(x, y) for x, y, _layers in vias],
        [list(layers) for _x, _y, layers in vias],
        list(all_layers),
        tolerance,
        list(zones),
    )
    return (result[0], result[1], result[2], tuple(result[3]), tuple(result[4]), result[5])


def test_curated_graph_cases_match_pinned_oracle():
    cases = [
        # WDT_KICK's sub-nanometre transform noise at a half-even boundary.
        (
            [(117.3925, 139.53000000000003, "F.Cu"), (36.64, 56.96, "F.Cu")],
            [(117.3925, 139.53, 36.64, 56.96, "In4.Cu")],
            [(117.3925, 139.53, ("F.Cu", "In4.Cu")), (36.64, 56.96, ("In4.Cu", "F.Cu"))],
            ("F.Cu", "In4.Cu"),
            (),
        ),
        # THT expansion must be complete before roots are read.
        (
            [(0.0, 0.0, "F.Cu"), (10.0, 0.0, "*"), (20.0, 0.0, "*")],
            [(0.0, 0.0, 10.0, 0.0, "F.Cu"), (10.0, 0.0, 20.0, 0.0, "F.Cu")],
            [],
            ("B.Cu", "F.Cu", "In1.Cu"),
            (),
        ),
        # Same coordinates on the wrong layer must not complete SMD pads.
        (
            [(0.0, 0.0, "F.Cu"), (20.0, 0.0, "F.Cu")],
            [(0.0, 0.0, 20.0, 0.0, "B.Cu")],
            [],
            ("F.Cu", "B.Cu"),
            (),
        ),
        # Through and blind/buried spans differ; this via is intentionally
        # unable to bridge F.Cu to B.Cu.
        (
            [(0.0, 0.0, "F.Cu"), (20.0, 0.0, "B.Cu")],
            [(0.0, 0.0, 10.0, 0.0, "F.Cu"), (10.0, 0.0, 20.0, 0.0, "B.Cu")],
            [(10.0, 0.0, ("F.Cu", "In1.Cu"))],
            ("F.Cu", "In1.Cu", "B.Cu"),
            (),
        ),
        # Two equal-size components keep the first pad component as majority.
        (
            [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (10.0, 0.0, "F.Cu"), (11.0, 0.0, "F.Cu")],
            [(0.0, 0.0, 1.0, 0.0, "F.Cu"), (10.0, 0.0, 11.0, 0.0, "F.Cu")],
            [],
            (),
            (),
        ),
        # Zone coverage only changes the classification, never graph verdict.
        (
            [(0.0, 0.0, "F.Cu"), (10.0, 0.0, "F.Cu")],
            [],
            [],
            (),
            ("F.Cu",),
        ),
        # An unreached THT pad is not zone-dependent when no zone exists;
        # the ALL_LAYERS marker alone must not make the predicate true.
        (
            [(0.0, 0.0, "*"), (10.0, 0.0, "*")],
            [],
            [],
            (),
            (),
        ),
    ]
    for pads, segments, vias, layers, zones in cases:
        expected = oracle.graph_verdict(pads, segments, vias, layers, 0.02, zones)
        assert _rust_case(pads, segments, vias, layers, 0.02, zones) == expected


def test_rounding_tie_boundaries_match_pinned_oracle():
    # 0.01 / 0.02 is a half-even tie (zero is even), while 0.03 / 0.02
    # rounds to two.  These are genuine nanometre-resolution points, so the
    # pre-bucket snap must not erase the boundary itself.
    pads = [(0.01, 0.0, "F.Cu"), (0.03, 0.0, "F.Cu")]
    segments = [(0.01, 0.0, 0.03, 0.0, "F.Cu")]
    expected = oracle.graph_verdict(pads, segments, [], (), 0.02, ())
    assert _rust_case(pads, segments, [], (), 0.02, ()) == expected


def test_through_via_and_typed_via_have_distinct_layer_universes():
    pads = [(0.0, 0.0, "F.Cu"), (2.0, 0.0, "B.Cu")]
    segments = [(0.0, 0.0, 1.0, 0.0, "F.Cu"), (1.0, 0.0, 2.0, 0.0, "B.Cu")]
    through = [(1.0, 0.0, ())]
    typed = [(1.0, 0.0, (("F.Cu", "In1.Cu")))]
    for vias in (through, typed):
        expected = oracle.graph_verdict(pads, segments, vias, ("F.Cu", "In1.Cu", "B.Cu"), 0.02, ())
        assert _rust_case(pads, segments, vias, ("F.Cu", "In1.Cu", "B.Cu"), 0.02, ()) == expected


def test_randomized_graph_cases_match_pinned_oracle():
    rng = random.Random(0xC0FFEE)
    layers = ("F.Cu", "In1.Cu", "B.Cu")
    for _ in range(300):
        pads = [
            (rng.choice((0.0, 0.02, 1.0, 10.0)), rng.choice((0.0, 0.02, 1.0)), rng.choice((*layers, "*")))
            for _ in range(rng.randrange(0, 7))
        ]
        segments = [
            (rng.random() * 10, rng.random() * 10, rng.random() * 10, rng.random() * 10, rng.choice(layers))
            for _ in range(rng.randrange(0, 7))
        ]
        vias = [
            (rng.random() * 10, rng.random() * 10, rng.choice(((), ("F.Cu", "B.Cu"), ("In1.Cu", "B.Cu"))))
            for _ in range(rng.randrange(0, 5))
        ]
        all_layers = layers if rng.randrange(2) else ()
        zones = tuple(layer for layer in layers if rng.randrange(2))
        expected = oracle.graph_verdict(pads, segments, vias, all_layers, 0.02, zones)
        assert _rust_case(pads, segments, vias, all_layers, 0.02, zones) == expected


def test_production_core_calls_rust_graph_once(monkeypatch):
    calls = []
    rust_graph = _tg.pad_connectivity_audit_py

    def wrapped(*args):
        calls.append(args)
        return rust_graph(*args)

    monkeypatch.setattr(audit._tg, "pad_connectivity_audit_py", wrapped)
    result = audit.check_net_pad_connectivity(
        "probe",
        [audit.NetPad((0.0, 0.0), "F.Cu"), audit.NetPad((1.0, 0.0), "F.Cu")],
        [audit.CopperSegment((0.0, 0.0), (1.0, 0.0), "F.Cu")],
        [],
    )
    assert result.fully_connected
    assert len(calls) == 1


@pytest.mark.parametrize("pad_count", (0, 1))
@pytest.mark.parametrize("tolerance", (0.0, float("nan"), float("inf"), -float("inf")))
def test_trivial_pad_counts_match_historical_oracle_for_invalid_tolerances(pad_count, tolerance):
    """Trivial nets short-circuit before Rust's graph-input validation.

    This preserves the pre-migration result exactly, including copper and
    zone fields. The oracle's early return intentionally characterizes that
    historical contract rather than attempting to validate an unused
    tolerance.
    """
    pads = [(0.0, 0.0, "F.Cu")] * pad_count
    segments = [(0.0, 0.0, 1.0, 0.0, "F.Cu")]
    vias = [(1.0, 0.0, ("F.Cu", "B.Cu"))]
    expected = oracle.graph_verdict(
        pads, segments, vias, ("F.Cu", "B.Cu"), tolerance, ("F.Cu",)
    )
    result = audit.check_net_pad_connectivity(
        "TRIVIAL",
        [audit.NetPad((x, y), layer) for x, y, layer in pads],
        [audit.CopperSegment((x1, y1), (x2, y2), layer) for x1, y1, x2, y2, layer in segments],
        [audit.CopperVia((x, y), layers) for x, y, layers in vias],
        all_layers=("F.Cu", "B.Cu"),
        tolerance_mm=tolerance,
        zone_layers=("F.Cu",),
    )
    assert (
        result.pads_connected,
        result.fully_connected,
        result.has_any_copper,
        (),
        result.zone_layers,
        result.zone_dependent_unmeasured,
    ) == expected


@pytest.mark.parametrize("tolerance", (0.0, float("nan"), float("inf"), -float("inf")))
def test_nontrivial_pad_counts_keep_rust_tolerance_validation(tolerance):
    pads = [audit.NetPad((0.0, 0.0), "F.Cu"), audit.NetPad((1.0, 0.0), "F.Cu")]
    with pytest.raises(ValueError, match="tolerance_mm must be finite and non-zero"):
        audit.check_net_pad_connectivity("NONTRIVIAL", pads, [], [], tolerance_mm=tolerance)


@pytest.mark.slow
def test_production_board_net_set_matches_kicad_unconnected_items():
    """Compare only the overlapping net-level verdict, not raw item counts.

    KiCad reports representative missing-connection items and the audit
    deliberately cannot inspect zone fill geometry, so item-count equality
    would be a false claim.  On the committed board KiCad 10.0.5 reports 348
    items spanning 80 nets; the audit's 80 non-fully-connected net names must
    be exactly that set.
    """
    if shutil.which("kicad-cli") is None:
        pytest.skip("kicad-cli unavailable")
    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not board.exists():
        pytest.skip("production board unavailable")
    from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file
    from temper_placer.validation._drc_api import run_drc

    report = run_drc(board)
    kicad_nets = {
        net
        for error in report.errors
        if error.rule == "unconnected_items"
        for net in error.nets
    }
    audit_results = audit_pcb_file(board)
    audit_nets = {name for name, result in audit_results.items() if not result.fully_connected}
    assert kicad_nets
    assert audit_nets
    assert kicad_nets == audit_nets
