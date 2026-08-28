"""Tests for the JSON report boundary in scripts/route_board.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import route_board  # noqa: E402


def test_worker_report_serializes_rust_route_verdicts() -> None:
    report = {
        "routed_pcb_content": "(pcb ...)",
        "net_route_results": {
            "connected-net": SimpleNamespace(disposition="connected"),
            "partial-net": SimpleNamespace(disposition="partial"),
        },
    }

    worker_report = route_board._prepare_worker_report(report)
    encoded = json.dumps(worker_report)

    assert "routed_pcb_content" not in worker_report
    assert json.loads(encoded)["net_route_results"] == {
        "connected-net": {"disposition": "connected"},
        "partial-net": {"disposition": "partial"},
    }
    formatted = route_board._format_run(
        "Run 1/1",
        {
            "routed": 1,
            "attempted": 1,
            "completion_rate": 1.0,
            "segments": 2,
            "vias": 0,
            "zones": 0,
            "wall_s": 0.1,
            "net_route_results": worker_report["net_route_results"],
        },
    )
    assert formatted.startswith("Run 1/1: 1/1 nets")
    assert "1 connected" in formatted
    assert "1 partial" in formatted
