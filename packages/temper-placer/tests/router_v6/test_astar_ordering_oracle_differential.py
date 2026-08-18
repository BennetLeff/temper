"""Differential: shipped ``_compute_net_order`` vs its pinned Python oracle.

``_compute_net_order`` (``router_v6/_astar_ordering.py``) decides the order
in which nets are handed to Stage 4's A*. Two facts about it, both measured
2026-08-18 and both easy to get wrong:

1.  It is the ordering that governs the **live** routing path. The
    Rust-backed ``order_nets_py`` in ``router_v6/net_ordering.py`` is a
    different function whose result is assigned to an unused local
    (``route_stage.py:99``) and discarded.
2.  Its live call site is ``_astar_nlayer.py`` (reached from
    ``_pipeline_route._run_stage4`` whenever more than two routable layers
    exist, which is always true for ``pcb/temper.kicad_pcb``) -- **not**
    ``_astar_reconstruct.py``, which for this board is never entered.

The shipped module carries a ``TEMPER_NET_ORDER_MODE`` experiment selector.
Its default, ``"baseline"``, must be a bit-exact no-op relative to the
pre-selector implementation. That is what this file pins.

The corpus is the production board's own channel-path set (112 nets, 496
waypoints), captured from a real route via ``TEMPER_CHANNEL_DUMP`` -- not a
synthetic fixture. AGENTS.md records why that distinction matters: a
Rust/Python ampacity divergence once survived a genuinely-running
differential because the test's input was a net name absent from this board.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from temper_placer.router_v6._astar_ordering import _compute_net_order

from ._astar_ordering_py_oracle import _compute_net_order as oracle_compute_net_order

CORPUS = Path(__file__).parent / "data" / "astar_ordering_real_board_channels.json"

# The nine nets the 2026-08-18 connectivity investigation tracked. Their
# presence is asserted so the corpus cannot silently drift into a net set
# that no longer represents the board the ordering question was asked about.
NINE = (
    "+170V_BUS",
    "DC_BUS_RTN",
    "PWR_RTN",
    "SW_NODE",
    "ac_n",
    "power_in.ntc-no",
    "tank.c_tank1-p2",
    "w1_1",
    "w1_2",
)


@dataclass
class _Path:
    net_name: str
    waypoints: list[tuple[float, float]]
    total_length: float = 0.0
    preferred_layer: str = "F.Cu"
    channel_sequence: list = field(default_factory=list)


class _Mapping:
    def __init__(self, paths):
        self.channel_paths = paths


def _corpus() -> _Mapping:
    raw = json.loads(CORPUS.read_text())
    return _Mapping(
        {
            name: _Path(net_name=name, waypoints=[tuple(w) for w in pts])
            for name, pts in raw.items()
        }
    )


def test_corpus_is_the_real_board() -> None:
    """The corpus is the production net set, not a synthetic sample."""
    mapping = _corpus()
    assert len(mapping.channel_paths) == 112
    missing = [n for n in NINE if n not in mapping.channel_paths]
    assert not missing, f"corpus no longer covers the tracked nets: {missing}"


def test_default_mode_matches_oracle_exactly(monkeypatch) -> None:
    """Unset ``TEMPER_NET_ORDER_MODE`` reproduces the pinned oracle exactly.

    Equality, not a weaker invariant: two orderings can both be "valid
    permutations" and still route differently, so only equality shows the
    experiment selector did not perturb production.
    """
    monkeypatch.delenv("TEMPER_NET_ORDER_MODE", raising=False)
    mapping = _corpus()
    assert _compute_net_order(mapping) == oracle_compute_net_order(mapping)


def test_explicit_baseline_matches_oracle_exactly(monkeypatch) -> None:
    monkeypatch.setenv("TEMPER_NET_ORDER_MODE", "baseline")
    mapping = _corpus()
    assert _compute_net_order(mapping) == oracle_compute_net_order(mapping)


def test_default_mode_matches_oracle_with_bottleneck_widths(monkeypatch) -> None:
    """The ``bottleneck_widths`` branch is covered too.

    The live ``_astar_nlayer`` call passes no widths, but
    ``_astar_reconstruct`` does, and the oracle must pin both branches or a
    future port could reproduce only the one this board happens to take.
    """
    monkeypatch.delenv("TEMPER_NET_ORDER_MODE", raising=False)
    mapping = _corpus()
    widths = {
        name: 0.1 + (i % 7) * 0.35
        for i, name in enumerate(sorted(mapping.channel_paths))
    }
    assert _compute_net_order(mapping, bottleneck_widths=widths) == (
        oracle_compute_net_order(mapping, bottleneck_widths=widths)
    )


def test_unknown_mode_is_rejected(monkeypatch) -> None:
    """A typo must fail loudly, not silently measure the baseline."""
    monkeypatch.setenv("TEMPER_NET_ORDER_MODE", "hv-first")
    with pytest.raises(ValueError, match="TEMPER_NET_ORDER_MODE"):
        _compute_net_order(_corpus())


@pytest.mark.parametrize("mode", ["hv_first", "width_desc"])
def test_experiment_modes_are_permutations(monkeypatch, mode: str) -> None:
    """Experiment modes reorder, and only reorder.

    They must never add, drop or duplicate a net -- an ordering experiment
    that silently loses a net would show up as a connectivity "improvement"
    that is really a missing attempt.
    """
    monkeypatch.setenv("TEMPER_NET_ORDER_MODE", mode)
    mapping = _corpus()
    got = _compute_net_order(mapping)
    baseline = oracle_compute_net_order(mapping)
    assert sorted(got) == sorted(baseline)
    assert len(got) == len(set(got))


def test_hv_first_actually_promotes_hv_copper(monkeypatch) -> None:
    """``hv_first`` moves the HV nets ahead of where baseline put them.

    Without ``design_rules`` the SSOT half of ``_is_hv_like`` cannot fire and
    only the two name-classified nets (``SW_NODE``, ``ac_n``) move -- which
    is precisely the near-no-op that made the first run of this experiment
    look like a null result for the wrong reason. This pins that the
    name-classifier reaches at least those two, so a regression to "nothing
    moves" is caught.
    """
    mapping = _corpus()
    monkeypatch.delenv("TEMPER_NET_ORDER_MODE", raising=False)
    base = _compute_net_order(mapping)
    monkeypatch.setenv("TEMPER_NET_ORDER_MODE", "hv_first")
    hv = _compute_net_order(mapping)
    for net in ("SW_NODE", "ac_n"):
        assert hv.index(net) < base.index(net), f"{net} not promoted by hv_first"
