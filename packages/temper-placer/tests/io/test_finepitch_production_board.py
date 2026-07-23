"""U2: Verify FinePitch netclass + DRC footprint-library-table on production board.

Tests that the already-implemented FinePitch netclass (commit 051152e7) and
footprint-library-table configuration (``KICAD7_FOOTPRINT_DIR`` in gates.py)
apply correctly to ``pcb/temper.kicad_pcb``'s real net names and footprints.

Expected finding: the constraint config's ``net_classes`` dict is keyed to
corpus-board net names (``SPI_CLK``, ``USB_D+``, etc.) which do not match the
production board's hierarchical net names (``sclk``, ``cs_n``, ``bias``,
``refin_n``, etc.).  Fine-pitch nets on the production board (SSOP-20 U8, 0.635
mm pitch) currently receive the ``Default`` netclass rather than ``FinePitch``.
This test surfaces that gap explicitly rather than silently passing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Fine-pitch threshold: pads with pitch <= 0.65 mm are considered fine-pitch.
# This matches the SSOP-20 (0.635 mm) and would also catch QFN, TSSOP, and
# fine-pitch connectors if present.
_FINE_PITCH_THRESHOLD_MM = 0.65

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"


def _identify_fine_pitch_nets() -> set[str]:
    """Extract nets that connect to fine-pitch component pads from the
    production board.

    Walks each component, extracts its footprint pitch from known
    footprint-name patterns, and collects the net names of all pins on
    components whose pitch is below the threshold.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(_PCB_PATH)
    fine_nets: set[str] = set()

    for comp in parse_result.netlist.components:
        fp = getattr(comp, "footprint", "")
        pitch = _footprint_pitch_mm(fp)
        if pitch is not None and pitch <= _FINE_PITCH_THRESHOLD_MM:
            for pin in getattr(comp, "pins", []):
                if pin.net:
                    fine_nets.add(pin.net)

    return fine_nets


def _footprint_pitch_mm(footprint: str) -> float | None:
    """Extract pin pitch in mm from a KiCad footprint name string.

    KiCad footprint names encode pitch as ``P0.50mm`` / ``P0.635mm`` /
    ``P1.27mm`` patterns.  Returns ``None`` when no parseable pitch
    is found.
    """
    import re

    m = re.search(r"P(\d+\.?\d*)mm", footprint)
    if m is None:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _netclass_for_net(net_name: str) -> str | None:
    """Return the netclass name assigned to *net_name* by the design rules SSOT.

    Uses the same resolution path ``get_rules_for_net`` that the router
    adapter's ``route_pcb`` and ``layer_assignments_from_netclass`` paths
    use, so the result reflects the actual classification that routing
    sees at runtime.
    """
    from temper_placer.io.netclass_loader import load_netclass_rules

    rules = load_netclass_rules(_RULES_PATH)
    dr = rules.design_rules
    result = dr.get_rules_for_net(net_name)
    return getattr(result, "net_class", None)


class TestFinePitchProductionBoard:
    """FinePitch netclass assignment on the production board."""

    @classmethod
    def setup_class(cls):
        assert _PCB_PATH.exists(), f"Production board not found: {_PCB_PATH}"
        assert _RULES_PATH.exists(), f"Netclass rules not found: {_RULES_PATH}"
        cls._fine_nets = _identify_fine_pitch_nets()

    def test_fine_pitch_nets_exist(self):
        """The production board has at least one fine-pitch component.

        If this fails, the board has changed such that there are no
        fine-pitch nets at all -- FinePitch netclass verification is
        vacuously true, which may itself be a configuration drift
        worth investigating.
        """
        assert len(self._fine_nets) > 0, (
            "No fine-pitch nets (pitch <= 0.65 mm) found on the production "
            "board. This is unexpected -- verify the board still has U8 "
            "(SSOP-20, 0.635 mm pitch) or other fine-pitch components."
        )

    @pytest.mark.xfail(
        reason=(
            "Known gap (2026-07-18): net_classes in the constraint config is "
            "keyed to corpus-board flat net names (SPI_CLK, USB_D+, etc.) "
            "and has no entries for the production board's hierarchical net "
            "names (sclk, cs_n, bias, refin_n, etc.).  FinePitch "
            "classification can only happen via explicit net name entries "
            "-- there is no pattern-based fallback.  See U2 in "
            "2026-07-18-002-feat-board-routing-completion-plan.md.  Once "
            "net_class_assignments entries for these nets are added (or a "
            "pattern-based _is_fine_pitch_net fallback is implemented), "
            "this xfail should be removed."
        ),
        strict=True,
    )
    def test_fine_pitch_nets_assigned_finepitch_class(self):
        """Every fine-pitch net should resolve to the FinePitch netclass."""
        assigned = 0
        missing = []
        for net_name in sorted(self._fine_nets):
            nc = _netclass_for_net(net_name)
            if nc == "FinePitch":
                assigned += 1
            else:
                missing.append(f"{net_name} ({nc if nc else 'no netclass'})")

        total = len(self._fine_nets)
        assert assigned == total, (
            f"Only {assigned}/{total} fine-pitch nets assigned FinePitch.\n"
            f"Missing: {missing}\n"
            f"Root cause: net_class_assignments is keyed to corpus board "
            f"net names (SPI_CLK, USB_D+, etc.) and has no entries for "
            f"the production board's hierarchical net names.\n"
            f"Fix: either (a) add production-board net name entries to "
            f"net_classes in the constraint config, or (b) add a "
            f"pattern-based _is_fine_pitch_net fallback to "
            f"DesignRules.get_rules_for_net."
        )


class TestKicadFootprintLibrary:
    """Footprint-library-table configuration for the production board.

    ``KICAD7_FOOTPRINT_DIR`` is hardcoded as an env override in
    ``DrcGate.check`` (gates.py:182) rather than exposed as a
    module-level constant.  These tests verify the hardcoded path
    exists on the current system so that ``kicad-cli pcb drc``
    called by ``DrcGate`` can resolve footprints on the production
    board.
    """

    # Mirrors the hardcoded path in gates.py:182.
    _FOOTPRINT_DIR = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

    def test_kicad7_footprint_dir_exists(self):
        """The footprint library path hardcoded in DrcGate exists."""
        assert os.path.isdir(self._FOOTPRINT_DIR), (
            f"KICAD7_FOOTPRINT_DIR={self._FOOTPRINT_DIR} does not exist "
            f"on this system.  DrcGate.check() will fail to resolve "
            f"footprints for the production board."
        )

    def test_kicad7_footprint_dir_contains_footprints(self):
        """The footprint library directory has footprint files."""
        assert os.path.isdir(self._FOOTPRINT_DIR), (
            "Footprint directory does not exist -- skipping content check"
        )
        contents = os.listdir(self._FOOTPRINT_DIR)
        assert len(contents) > 0, f"Footprint directory {self._FOOTPRINT_DIR} exists but is empty"
