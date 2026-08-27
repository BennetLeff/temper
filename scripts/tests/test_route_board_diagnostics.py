from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "route_board.py"
_SPEC = importlib.util.spec_from_file_location("route_board_diagnostics", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_format_run_surfaces_ranked_decline_evidence() -> None:
    result = {
        "routed": 1,
        "attempted": 3,
        "completion_rate": 1 / 3,
        "segments": 2,
        "vias": 0,
        "zones": 0,
        "wall_s": 1.0,
        "failure_reports": {
            "A": {
                "failure_reason": "no_path",
                "rule_id": None,
                "attribution_gap": True,
            },
            "B": {
                "failure_reason": "no_path",
                "rule_id": None,
                "attribution_gap": True,
            },
            "C": {
                "failure_reason": "pad_layer_landing_blocked:source",
                "rule_id": "pad_layer_landing",
                "attribution_gap": False,
            },
        },
    }

    rendered = _MODULE._format_run("Result", result)

    assert "decline evidence): 3 reports; rule-attributed=1" in rendered
    assert "reasons: no_path=2, pad_layer_landing_blocked:source=1" in rendered
    assert "rules: UNATTRIBUTED=2, pad_layer_landing=1" in rendered
