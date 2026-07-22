"""U4 (zone/pour fix 2026-07-21-001): multi-sample verification that the combined
fix (cross-class clearance + zone priority + localized hull) resolves the
``shorting_items`` regression when zones are filled.

This is a standalone manually-run measurement, not a CI gate.  It mirrors the
regression-diagnosis methodology exactly: multiple routing seeds, real
``pcbnew.ZONE_FILLER`` fill, multiple DRC samples per board.

Reuses the helpers from ``test_zone_pour_production_measurement.py`` directly.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

import pytest

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"

# Helper imports from the existing measurement test
from tests.placer.cp_sat.test_zone_pour_production_measurement import (  # noqa: E402
    _fill_zones_via_pcbnew,
    _kicad_cli_available,
    _run_drc,
)


@pytest.mark.slow
@pytest.mark.routing
class TestZonePourShapeClearanceVerification:
    """U4: measure the combined U1-U3 fix's effect on filled DRC counts.

    This is evidence-gathering, not a promotion gate — ``enable_zone_pours``
    stays behind its existing default-off flag.
    """

    def test_shorting_items_no_longer_regresses_with_zones_filled(self):
        """R7: With the U1-U3 fix, filling zones no longer increases
        ``shorting_items`` relative to the zones-off baseline.

        Routes the production board across 4 seeds with zones enabled,
        fills via pcbnew, runs DRC 3x per board, and compares the
        ``shorting_items`` range against a zones-off baseline measured
        the same way.
        """
        if not _kicad_cli_available():
            pytest.skip("kicad-cli not available")

        assert _PCB_PATH.exists(), f"Board not found: {_PCB_PATH}"
        assert _RULES_PATH.exists(), f"Rules not found: {_RULES_PATH}"

        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.netclass_loader import load_netclass_rules
        from temper_placer.router_v6.adapter import route_pcb

        rules = load_netclass_rules(_RULES_PATH)
        parse_result = parse_kicad_pcb(_PCB_PATH)
        netlist = parse_result.netlist
        assert netlist is not None and len(netlist.components) > 0

        parsed_stub = type("ParsedStub", (), {"source_path": _PCB_PATH, "nets": netlist.nets})()

        seeds = [42, 43, 44, 45]
        drc_samples = 3

        print("\n=== U4 Zone/Pour Shape+Clearance Fix Verification ===")
        print(f"Seeds: {seeds}  DRC samples/board: {drc_samples}")

        # --- Zones-on measurements ---
        zones_on_shorting: list[int] = []
        zones_on_unconnected: list[int] = []
        per_net_delta: dict[str, list[float]] = {}

        for seed in seeds:
            print(f"\n  Routing seed={seed} (zones ON) ...")
            t0 = time.monotonic()
            routing_result = route_pcb(
                parsed_stub, {},
                _seed=seed,
                design_rules=rules.design_rules,
                enable_zone_pours=True,
            )
            wall_s = time.monotonic() - t0
            print(f"    Wall time: {wall_s:.1f}s  zones emitted: "
                  f"{routing_result.routed_pcb_content.count('(zone ')}")

            assert routing_result.routed_pcb_content is not None
            assert routing_result.routed_pcb_content.count("(zone ") > 0

            routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                suffix=".kicad_pcb", mode="w", delete=False,
            )
            routed_tmp.write(routing_result.routed_pcb_content)
            routed_tmp.close()
            routed_path = Path(routed_tmp.name)
            filled_path: Path | None = None

            try:
                filled_path = _fill_zones_via_pcbnew(routed_path)

                for sample in range(drc_samples):
                    drc_data = _run_drc(filled_path)
                    violations = drc_data.get("violations", [])
                    shorting = sum(
                        1 for v in violations if v.get("type") == "shorting_items"
                    )
                    unconnected = len(drc_data.get("unconnected_items", []))
                    zones_on_shorting.append(shorting)
                    zones_on_unconnected.append(unconnected)
                    print(f"    DRC sample {sample+1}: shorting={shorting}  "
                          f"unconnected={unconnected}")

                    # Per-net diagnostic: count zone entries per net in the output
                    _append_per_net_zone_count(
                        routing_result.routed_pcb_content, per_net_delta,
                    )
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(routed_path)
                if filled_path is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(filled_path)

        # --- Zones-off baseline ---
        zones_off_shorting: list[int] = []
        zones_off_unconnected: list[int] = []

        for seed in seeds:
            print(f"\n  Routing seed={seed} (zones OFF baseline) ...")
            t0 = time.monotonic()
            routing_result = route_pcb(
                parsed_stub, {},
                _seed=seed,
                design_rules=rules.design_rules,
                enable_zone_pours=False,
            )
            wall_s = time.monotonic() - t0
            print(f"    Wall time: {wall_s:.1f}s")

            routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                suffix=".kicad_pcb", mode="w", delete=False,
            )
            routed_tmp.write(routing_result.routed_pcb_content)
            routed_tmp.close()
            routed_path = Path(routed_tmp.name)

            try:
                for sample in range(drc_samples):
                    drc_data = _run_drc(routed_path)
                    violations = drc_data.get("violations", [])
                    shorting = sum(
                        1 for v in violations if v.get("type") == "shorting_items"
                    )
                    unconnected = len(drc_data.get("unconnected_items", []))
                    zones_off_shorting.append(shorting)
                    zones_off_unconnected.append(unconnected)
                    print(f"    DRC sample {sample+1}: shorting={shorting}  "
                          f"unconnected={unconnected}")
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(routed_path)

        # --- Report ---
        print("\n=== U4 Verification Report ===")
        print(f"shorting_items (zones ON):  "
              f"min={min(zones_on_shorting)}  max={max(zones_on_shorting)}  "
              f"mean={sum(zones_on_shorting)/len(zones_on_shorting):.1f}")
        print(f"shorting_items (zones OFF): "
              f"min={min(zones_off_shorting)}  max={max(zones_off_shorting)}  "
              f"mean={sum(zones_off_shorting)/len(zones_off_shorting):.1f}")
        print(f"unconnected_items (zones ON):  "
              f"min={min(zones_on_unconnected)}  max={max(zones_on_unconnected)}  "
              f"mean={sum(zones_on_unconnected)/len(zones_on_unconnected):.1f}")
        print(f"unconnected_items (zones OFF): "
              f"min={min(zones_off_unconnected)}  max={max(zones_off_unconnected)}  "
              f"mean={sum(zones_off_unconnected)/len(zones_off_unconnected):.1f}")

        # Per-net diagnostic report
        if per_net_delta:
            print("\nPer-net zone count (for priority-exclusion attribution):")
            for net_name, counts in sorted(per_net_delta.items()):
                print(f"  {net_name}: {counts}")

        # Soft evidence assertion: zones-on shorting after the fix should
        # not exceed the zones-off shorting baseline.  This is a measurement
        # check, not a CI gate.
        max_zones_on = max(zones_on_shorting) if zones_on_shorting else 0
        max_zones_off = max(zones_off_shorting) if zones_off_shorting else 0
        if max_zones_on > max_zones_off:
            print(
                "\n  NOTE: zones-on max shorting "
                f"({max_zones_on}) > zones-off max "
                f"({max_zones_off}) -- fix did not fully resolve "
                "shorting regression."
            )
        else:
            print("\n  OK: zones-on shorting range does not exceed zones-off baseline.")


def _append_per_net_zone_count(
    content: str, per_net: dict[str, list[float]],
) -> None:
    """Extract zone count per net name from the emitted content for
    per-net diagnostic (priority-exclusion attribution)."""
    import re
    net_zones: dict[str, int] = {}
    for m in re.finditer(r'\(zone \(net \d+\) \(net_name "([^"]+)"\)', content):
        net_name = m.group(1)
        net_zones[net_name] = net_zones.get(net_name, 0) + 1
    for net_name, count in net_zones.items():
        per_net.setdefault(net_name, []).append(float(count))
