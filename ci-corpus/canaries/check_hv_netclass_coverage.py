"""Canary fixtures for check_hv_netclass_coverage.py (R42).

``run()`` already accepts injected ``net_classes``/``net_assignments``/
``dru_content``/``kicad_class_name_fn`` (added precisely so this gate is
unit-testable without a live package import -- see its own module
docstring's ``_default_live_inputs`` comment), so these canaries never
touch the real ``temper_placer`` package or the real board files: only a
tiny synthetic domain manifest and ``kicad_pro`` JSON on disk, plus
in-memory overrides for everything else.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

MANIFEST_TEXT = """
schema_version: 1
domains:
  HV:
    nets: ["ac_l", "dc_bus"]
  SELV:
    nets: ["gnd"]
"""

KICAD_PRO = {
    "net_settings": {
        "classes": [
            {"name": "HighVoltage", "description": "HV mains/DC-bus routing class"},
        ]
    }
}


def _write_inputs(root: Path) -> tuple[Path, Path]:
    manifest_path = root / "manifest.yaml"
    manifest_path.write_text(MANIFEST_TEXT, encoding="utf-8")
    kicad_pro_path = root / "board.kicad_pro"
    kicad_pro_path.write_text(json.dumps(KICAD_PRO), encoding="utf-8")
    return manifest_path, kicad_pro_path


def _run(gate_module, manifest_path: Path, kicad_pro_path: Path, net_assignments: dict, dru_content: str):
    return gate_module.run(
        manifest_path,
        kicad_pro_path,
        net_classes={"HighVoltage": {}},
        net_assignments=net_assignments,
        dru_content=dru_content,
        kicad_class_name_fn=lambda name: name,
    )


def _state(gate_module, manifest_path: Path, kicad_pro_path: Path, net_assignments: dict, dru_content: str) -> str:
    state, _report = _run(gate_module, manifest_path, kicad_pro_path, net_assignments, dru_content)
    if state == "clean":
        return "clean"
    if state == "violation":
        return "violation"
    return "error"  # "tool_error"


def pristine_fully_covered(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest_path, kicad_pro_path = _write_inputs(root)
        net_assignments = {"ac_l": "HighVoltage", "dc_bus": "HighVoltage"}
        dru_content = "(rule hv (condition \"A.NetClass == 'HighVoltage'\") (clearance 6.0))"
        return _state(gate_module, manifest_path, kicad_pro_path, net_assignments, dru_content)


def seed_unassigned_hv_net(gate_module) -> str:
    """dc_bus is declared HV in the manifest but has no netclass assignment
    -- the real, confirmed +170V_BUS defect this gate exists to catch.

    Returns "violation:<sorted unclassified nets>" rather than the bare
    overall state: a coarse state-only oracle cannot tell "correctly
    flagged dc_bus" apart from "wrongly flagged ac_l instead" -- both
    collapse to "violation" -- and a mutation that swaps WHICH net gets
    reported is exactly as real a defect as one that swaps whether a
    violation is reported at all.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest_path, kicad_pro_path = _write_inputs(root)
        net_assignments = {"ac_l": "HighVoltage"}  # dc_bus missing
        dru_content = "(rule hv (condition \"A.NetClass == 'HighVoltage'\") (clearance 6.0))"
        state, report = _run(gate_module, manifest_path, kicad_pro_path, net_assignments, dru_content)
        if state != "violation":
            return state
        return f"violation:{sorted(report.unclassified_hv_nets)}"


def seed_class_with_no_rules(gate_module) -> str:
    """HighVoltage is declared (with a real description) but the generated
    DRU text never references it positively -- the HighVoltageIsolated
    zero-rules defect this gate exists to catch."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest_path, kicad_pro_path = _write_inputs(root)
        net_assignments = {"ac_l": "HighVoltage", "dc_bus": "HighVoltage"}
        dru_content = "(rule other (condition \"A.NetClass != 'HighVoltage'\") (clearance 0.2))"
        return _state(gate_module, manifest_path, kicad_pro_path, net_assignments, dru_content)
