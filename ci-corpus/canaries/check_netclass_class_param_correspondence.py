"""Canary fixtures for check_netclass_class_param_correspondence.py (R42).

``run()`` already accepts injected ``net_classes``/``kicad_pro_classes``
(added precisely so this gate is unit-testable without a live
``temper_placer`` import or a real ``pcb/temper.kicad_pro`` on disk --
mirrors ``check_hv_netclass_coverage.py``'s own canary module, which uses
the identical injection pattern), so these canaries never touch the real
package or the real board files: only a tiny synthetic
``pcb/temper.kicad_pro`` fixture on disk, plus an in-memory
``net_classes`` override.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class _FakeNetClassRules:
    """Minimal stand-in for NetClassRules: the gate reads only the four
    scalar routing field attributes (clearance, trace_width, via_diameter,
    via_drill)."""

    def __init__(self, clearance, trace_width, via_diameter, via_drill):
        self.clearance = clearance
        self.trace_width = trace_width
        self.via_diameter = via_diameter
        self.via_drill = via_drill


def _write_kicad_pro(root: Path, clearance: float) -> Path:
    path = root / "board.kicad_pro"
    path.write_text(
        json.dumps(
            {
                "net_settings": {
                    "classes": [
                        {
                            "name": "HighVoltage",
                            "clearance": clearance,
                            "track_width": 3.0,
                            "via_diameter": 1.2,
                            "via_drill": 0.6,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _state(gate_module, kicad_pro_path: Path, clearance: float) -> str:
    """Returns "clean" or "violation:<sorted flagged field names>" --
    never the bare overall state. A coarse state-only oracle cannot tell
    "correctly flagged clearance" apart from "wrongly flagged the three
    AGREEING fields instead" -- both collapse to "violation", and a
    comparison-direction mutation (`!=` -> `==`) does exactly that: it
    still reports *some* mismatch (report.mismatches stays non-empty,
    since trace_width/via_diameter/via_drill all agree and would now be
    misreported), so the overall state alone never flips. This mirrors
    check_hv_netclass_coverage.py's own canary docstring precedent
    (seed_unassigned_hv_net) for the identical reason."""
    net_classes = {
        "HighVoltage": _FakeNetClassRules(
            clearance=clearance, trace_width=3.0, via_diameter=1.2, via_drill=0.6
        )
    }
    state, report = gate_module.run(
        kicad_pro_path,
        net_classes=net_classes,
        net_assignments={"dc_bus": "HighVoltage"},
    )
    if state == "clean":
        return "clean"
    if state == "violation":
        fields = sorted(m.field_name for m in report.mismatches)
        return f"violation:{fields}"
    return "error"  # "tool_error"


def pristine_agree(gate_module) -> str:
    """design_rules.py and kicad_pro agree on HighVoltage.clearance (6.0mm
    both sides) -- must be clean."""
    with tempfile.TemporaryDirectory() as td:
        kicad_pro_path = _write_kicad_pro(Path(td), clearance=6.0)
        return _state(gate_module, kicad_pro_path, clearance=6.0)


def seed_mismatch(gate_module) -> str:
    """The real, confirmed defect this gate exists to catch, in miniature:
    design_rules.py says HighVoltage.clearance=6.0, kicad_pro says 2.0,
    every other field agrees -- the exact origin/main shape (docs/
    evidence/2026-08-12-gate-vacuity-structural-prevention.md). Exactly
    ONE field (clearance) must be named in the flagged set."""
    with tempfile.TemporaryDirectory() as td:
        kicad_pro_path = _write_kicad_pro(Path(td), clearance=2.0)
        return _state(gate_module, kicad_pro_path, clearance=6.0)
