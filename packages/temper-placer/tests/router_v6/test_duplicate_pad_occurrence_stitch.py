"""Collision gate for local copper between duplicate physical pad occurrences."""

from __future__ import annotations

from types import SimpleNamespace

import temper_orchestration as _to

from temper_placer.router_v6._zone_pour_stitch import (
    _stitch_duplicate_pad_occurrences,
)


class _Rules:
    def get_rules_for_net(self, net_name: str) -> SimpleNamespace:
        assert net_name == "RELAY_NO"
        return SimpleNamespace(trace_width=0.5)


def _edge():
    return [
        (
            "RELAY_NO",
            "K2",
            "3",
            (0, 137.32, 72.21),
            (1, 144.82, 72.21),
            "F.Cu",
        )
    ]


def test_clear_duplicate_contact_edge_emits_netclass_width(monkeypatch):
    monkeypatch.setattr(_to, "run_collect_duplicate_pad_edges", lambda _pcb: _edge())
    monkeypatch.setattr(
        "temper_placer.router_v6.zone_pour_clearance.collect_zone_obstacle_records",
        lambda *_args, **_kwargs: [],
    )
    segments: list[str] = []
    emitted = _stitch_duplicate_pad_occurrences(
        segments,
        {"RELAY_NO": 17},
        design_rules=_Rules(),
        tstamp_counter=[0],
        pcb=object(),
    )

    assert emitted == 1
    assert len(segments) == 1
    assert "(start 137.3200 72.2100) (end 144.8200 72.2100)" in segments[0]
    assert '(width 0.5000) (layer "F.Cu") (net 17)' in segments[0]


def test_foreign_copper_intersection_skips_duplicate_contact_edge(monkeypatch):
    monkeypatch.setattr(_to, "run_collect_duplicate_pad_edges", lambda _pcb: _edge())
    # A foreign vertical track crosses the proposed horizontal stitch.
    monkeypatch.setattr(
        "temper_placer.router_v6.zone_pour_clearance.collect_zone_obstacle_records",
        lambda *_args, **_kwargs: [(1, 141.07, 71.0, 141.07, 73.0, 0.2, 0.2)],
    )
    segments: list[str] = []
    emitted = _stitch_duplicate_pad_occurrences(
        segments,
        {"RELAY_NO": 17},
        design_rules=_Rules(),
        tstamp_counter=[0],
        pcb=object(),
    )

    assert emitted == 0
    assert segments == []


def test_missing_board_context_fails_closed(monkeypatch):
    called = False

    def _unexpected(_pcb):
        nonlocal called
        called = True
        return _edge()

    monkeypatch.setattr(_to, "run_collect_duplicate_pad_edges", _unexpected)
    segments: list[str] = []
    emitted = _stitch_duplicate_pad_occurrences(
        segments,
        {"RELAY_NO": 17},
        design_rules=_Rules(),
        tstamp_counter=[0],
        pcb=None,
    )

    assert emitted == 0
    assert segments == []
    assert not called


def test_retained_existing_zones_fail_closed(monkeypatch):
    called = False

    def _unexpected(_pcb):
        nonlocal called
        called = True
        return _edge()

    monkeypatch.setattr(_to, "run_collect_duplicate_pad_edges", _unexpected)
    segments: list[str] = []
    emitted = _stitch_duplicate_pad_occurrences(
        segments,
        {"RELAY_NO": 17},
        design_rules=_Rules(),
        tstamp_counter=[0],
        pcb=SimpleNamespace(zones=[object()]),
    )

    assert emitted == 0
    assert segments == []
    assert not called


def test_missing_netclass_width_fails_closed(monkeypatch):
    monkeypatch.setattr(_to, "run_collect_duplicate_pad_edges", lambda _pcb: _edge())
    monkeypatch.setattr(
        "temper_placer.router_v6.zone_pour_clearance.collect_zone_obstacle_records",
        lambda *_args, **_kwargs: [],
    )
    segments: list[str] = []

    emitted = _stitch_duplicate_pad_occurrences(
        segments,
        {"RELAY_NO": 17},
        design_rules=None,
        tstamp_counter=[0],
        pcb=object(),
    )

    assert emitted == 0
    assert segments == []
