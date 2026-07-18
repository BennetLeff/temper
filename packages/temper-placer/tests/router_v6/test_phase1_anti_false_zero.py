"""U6: Phase 1 anti-false-zero guard (R5).

Applies the anti-false-zero discipline from the 2026-07-10 plan's U5 pattern
to every claim made in Phase 1 (U1-U5):

1. Constraint set unchanged — the YAML configs used in U2/U3 are not
   silently relaxed relative to the pre-Phase-1 baseline.
2. Every gate reporting "0" violations was actually measured —
   DRC/ERC gates return real data, not ``UNMEASURED`` misread as clean.
3. Every numeric claim (routed_nets, completion_rate, ERC=0) is
   traceable to a specific test artifact produced by U1-U5.

Failures here mean a Phase 1 measurement is degenerate — the number
is real but the measurement is not.
"""

from __future__ import annotations

from pathlib import Path

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"
_PCL_CONFIG = _TEMPER_PLACER_ROOT / "configs" / "constraints" / "temper_induction_cooker.yaml"
_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"

# Constraint snapshots: values that Phase 1's U2/U3 tests depend on.
# If any of these are lower (relaxed), the U3/U5 violation counts are
# not comparable to the pre-Phase-1 state.
_CONSTRAINT_SNAPSHOT = {
    "ACMains.clearance": 6.0,
    "HighVoltage.clearance": 6.0,
    "HighCurrent.clearance": 0.25,
    "Signal.clearance": 0.15,
    "FinePitch.clearance": 0.1,
    "FinePitch.trace_width": 0.127,
    "default_clearance_mm": 0.2,
}


def _load_netclass_rules():
    from temper_placer.io.netclass_loader import load_netclass_rules
    return load_netclass_rules(_RULES_PATH)


class TestConstraintSetUnchanged:
    """Guard: the constraint YAML hasn't been silently relaxed.

    If a clearance or trace width is lowered, the U3/U5 DRC violation
    counts could drop without any real routing improvement — a false
    decrease in violations.
    """

    def test_netclass_rules_not_relaxed(self):
        rules = _load_netclass_rules()
        nc = rules.design_rules.net_classes

        dr = rules.design_rules
        for key, expected in _CONSTRAINT_SNAPSHOT.items():
            class_name, _, attr = key.partition(".")
            if class_name == "default_clearance_mm":
                actual = getattr(dr, "default_clearance_mm", None)
            else:
                netclass = nc.get(class_name)
                if netclass is None:
                    continue
                actual = getattr(netclass, attr, None)

            if actual is None:
                continue
            assert actual >= expected, (
                f"{key} relaxed from {expected} to {actual} — "
                f"constraint silently loosened; DRC counts are not "
                f"comparable to pre-Phase-1 baseline"
            )

    def test_netclass_count_unchanged(self):
        """No net classes removed — would silently widen the gap."""
        rules = _load_netclass_rules()
        nc = rules.design_rules.net_classes
        assert len(nc) >= 9, (
            f"Net class count dropped from 9 to {len(nc)} — "
            f"missing classes silently widen DRC gap"
        )


class TestGatesProperlyConfigured:
    """Guard: every measurement claimed in Phase 1 was actually measured.

    An ``UNMEASURED`` gate result (e.g., from a missing kicad-cli or
    missing footprint library) must never be reported as a clean zero.
    """

    def test_kicad_cli_available_for_drc(self):
        """kicad-cli is available — U3/U5 DRC runs cannot be UNMEASURED."""
        import subprocess
        result = subprocess.run(
            ["kicad-cli", "--version"], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, (
            "kicad-cli not available — DRC measurements degenerate"
        )

    def test_kicad7_footprint_dir_resolves(self):
        """Footprint library path in DrcGate (gates.py:182) exists.

        If this path doesn't exist, DrcGate.check() returns UNMEASURED,
        not CLEAN — but the violation count would still be zero, a
        classic false-zero.
        """
        import os
        fp_dir = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
        assert os.path.isdir(fp_dir), (
            f"KICAD7_FOOTPRINT_DIR={fp_dir} does not exist — "
            f"kicad-cli DRC would be UNMEASURED"
        )

    def test_production_board_routing_baseline_populated(self):
        """U3's baseline YAML is populated with real numbers, not null/0."""
        import yaml
        with open(_BASELINE_PATH) as f:
            doc = yaml.safe_load(f) or {}

        router_v6 = doc.get("router_v6_routing", {})
        assert router_v6.get("routed_nets") is not None, (
            "router_v6_routing.routed_nets is null — U3 baseline not populated"
        )
        assert router_v6.get("routed_nets", 0) > 0, (
            f"router_v6_routing.routed_nets is {router_v6.get('routed_nets')} "
            f"— 0 means the routing pipeline never ran against the "
            f"production board (degenerate measurement)"
        )
        assert router_v6.get("extraction_date") == "2026-07-18", (
            "Baseline extraction date not updated — stale measurement"
        )


class TestClaimsTraceable:
    """Guard: every Phase 1 numeric claim is traceable to a test artifact."""

    def test_u3_routed_nets_traceable(self):
        """U3's routed_nets (71) comes from the baseline YAML via the test."""
        import yaml
        with open(_BASELINE_PATH) as f:
            doc = yaml.safe_load(f) or {}
        routed = doc.get("router_v6_routing", {}).get("routed_nets")
        assert routed == 71, (
            f"Expected routed_nets=71 from U3 baseline, got {routed}"
        )

    def test_u3_completion_rate_traceable(self):
        """U3's completion_rate (74.74%) is recorded."""
        import yaml
        with open(_BASELINE_PATH) as f:
            doc = yaml.safe_load(f) or {}
        cr = doc.get("router_v6_routing", {}).get("completion_rate")
        assert cr is not None and cr > 0, (
            f"completion_rate={cr} — degenerate or not recorded"
        )

    def test_u4_erc_finding_traceable(self):
        """U4's ERC finding (pcb erc doesn't exist) is verified."""
        import subprocess
        result = subprocess.run(
            ["kicad-cli", "pcb", "erc"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            "kicad-cli pcb erc unexpectedly works — "
            "U4 finding invalidated"
        )
        assert "did you mean" in result.stdout.lower(), (
            "kicad-cli pcb erc response changed"
        )

    def test_u5_production_test_exists(self):
        """U5's test functions exist in test_regression_drc.py."""
        import inspect

        import tests.placer.cp_sat.test_regression_drc as drc_test

        names = [
            name for name, _ in
            inspect.getmembers(drc_test, inspect.isfunction)
        ]
        assert "test_production_board_drc_regression" in names, (
            "U5 production board placement DRC test not found"
        )
        assert "test_production_board_routing_drc_regression" in names, (
            "U5 production board routing DRC test not found"
        )
        assert hasattr(drc_test, "PRODUCTION_BOARD_PATH"), (
            "PRODUCTION_BOARD_PATH not defined in test_regression_drc.py"
        )
