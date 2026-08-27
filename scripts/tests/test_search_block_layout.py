from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "search_block_layout.py"
_SPEC = importlib.util.spec_from_file_location("search_block_layout", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_preflight_cannot_trade_removed_pair_for_new_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MODULE, "_pair_set", lambda *_: {"C<->D", "E<->F"})
    monkeypatch.setattr(_MODULE.regional, "_body_overlaps", lambda *_: {})
    verdict = _MODULE._preflight(
        {"A<->B", "C<->D"}, {}, Path("candidate.kicad_pcb"), Path("manifest"), 12.6
    )
    assert verdict["accepted"] is False
    assert verdict["new_cross_domain_pairs"] == ["E<->F"]


def test_search_fails_before_measurement_for_unknown_block_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "_positions", lambda *_: {"R4": (1.0, 2.0, 0.0)})
    with pytest.raises(ValueError, match="absent from board: C404"):
        _MODULE.search(
            Path("board"),
            Path("manifest"),
            Path("rules"),
            ["C404"],
            step_mm=5.0,
            max_rings=1,
            max_candidates=1,
            max_routed_candidates=0,
            threshold_mm=12.6,
            bounds=(0.0, 0.0, 10.0, 10.0),
            route=False,
        )
