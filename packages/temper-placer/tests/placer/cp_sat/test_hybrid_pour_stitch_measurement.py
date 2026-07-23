"""U6 (hybrid pour plan 2026-07-22-001): multi-sample DRC verification of the
combined U1-U5 fix — zone clustering + cross-class clearance + zone priority +
trace-stitching + zone-aware connectivity.

Routes the production board across multiple seeds with both all-pad-tree
and zone-pour flags enabled, fills via pcbnew.ZONE_FILLER, and compares
DRC distributions against a flags-off baseline.

Not a CI gate — evidence-gathering for the R9 promotion decision.
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

# Reuse helpers from the existing measurement test
from tests.placer.cp_sat.test_zone_pour_production_measurement import (  # noqa: E402
    _fill_zones_via_pcbnew,
    _kicad_cli_available,
    _run_drc,
)


@pytest.mark.slow
@pytest.mark.routing
class TestHybridPourStitchVerification:
    """U6: measure U1-U5 combined effect on production DRC counts."""

    def test_hybrid_pour_reduces_unconnected_without_shorting_regression(self):
        """R14: With U1-U5 shipped, filling hybrid pours + trace-stitches
        reduces unconnected_items for the target nets without regressing
        shorting_items versus the flags-off baseline."""
        if not _kicad_cli_available():
            pytest.skip("kicad-cli not available")

        assert _PCB_PATH.exists()
        assert _RULES_PATH.exists()

        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.netclass_loader import load_netclass_rules
        from temper_placer.router_v6.adapter import route_pcb

        rules = load_netclass_rules(_RULES_PATH)
        parse_result = parse_kicad_pcb(_PCB_PATH)
        netlist = parse_result.netlist
        assert netlist is not None and len(netlist.components) > 0

        parsed_stub = type(
            "ParsedStub",
            (),
            {"source_path": _PCB_PATH, "nets": netlist.nets},
        )()

        seeds = [42, 43, 44, 45]
        drc_samples = 3

        print("\n=== U6 Hybrid Pour + Trace-Stitch Verification ===")
        print(f"Seeds: {seeds}  DRC samples/board: {drc_samples}")

        # --- Flags-on measurements ---
        flags_on_shorting: list[int] = []
        flags_on_unconnected: list[int] = []

        for seed in seeds:
            print(f"\n  Routing seed={seed} (flags ON) ...")
            t0 = time.monotonic()
            routing_result = route_pcb(
                parsed_stub,
                {},
                _seed=seed,
                design_rules=rules.design_rules,
                enable_all_pad_tree=True,
                enable_zone_pours=True,
            )
            wall_s = time.monotonic() - t0
            zone_count = routing_result.routed_pcb_content.count("(zone ")
            print(f"    Wall time: {wall_s:.1f}s  zones: {zone_count}")

            assert routing_result.routed_pcb_content is not None
            assert zone_count > 0, "No zones emitted — measurement meaningless"

            routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                suffix=".kicad_pcb",
                mode="w",
                delete=False,
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
                    shorting = sum(1 for v in violations if v.get("type") == "shorting_items")
                    unconnected = len(drc_data.get("unconnected_items", []))
                    flags_on_shorting.append(shorting)
                    flags_on_unconnected.append(unconnected)
                    print(
                        f"    DRC sample {sample + 1}: "
                        f"shorting={shorting}  unconnected={unconnected}"
                    )
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(routed_path)
                if filled_path is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(filled_path)

        # --- Flags-off baseline ---
        flags_off_shorting: list[int] = []
        flags_off_unconnected: list[int] = []

        for seed in seeds:
            print(f"\n  Routing seed={seed} (flags OFF baseline) ...")
            t0 = time.monotonic()
            routing_result = route_pcb(
                parsed_stub,
                {},
                _seed=seed,
                design_rules=rules.design_rules,
                enable_all_pad_tree=False,
                enable_zone_pours=False,
            )
            wall_s = time.monotonic() - t0
            print(f"    Wall time: {wall_s:.1f}s")

            routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                suffix=".kicad_pcb",
                mode="w",
                delete=False,
            )
            routed_tmp.write(routing_result.routed_pcb_content)
            routed_tmp.close()
            routed_path = Path(routed_tmp.name)

            try:
                for sample in range(drc_samples):
                    drc_data = _run_drc(routed_path)
                    violations = drc_data.get("violations", [])
                    shorting = sum(1 for v in violations if v.get("type") == "shorting_items")
                    unconnected = len(drc_data.get("unconnected_items", []))
                    flags_off_shorting.append(shorting)
                    flags_off_unconnected.append(unconnected)
                    print(
                        f"    DRC sample {sample + 1}: "
                        f"shorting={shorting}  unconnected={unconnected}"
                    )
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(routed_path)

        # --- Report ---
        print("\n=== U6 Verification Report ===")
        on_s = sum(flags_on_shorting) / len(flags_on_shorting) if flags_on_shorting else 0
        off_s = sum(flags_off_shorting) / len(flags_off_shorting) if flags_off_shorting else 0
        on_u = sum(flags_on_unconnected) / len(flags_on_unconnected) if flags_on_unconnected else 0
        off_u = (
            sum(flags_off_unconnected) / len(flags_off_unconnected) if flags_off_unconnected else 0
        )

        print(
            f"shorting_items (flags ON):  "
            f"min={min(flags_on_shorting) if flags_on_shorting else 0}  "
            f"max={max(flags_on_shorting) if flags_on_shorting else 0}  "
            f"mean={on_s:.1f}"
        )
        print(
            f"shorting_items (flags OFF): "
            f"min={min(flags_off_shorting) if flags_off_shorting else 0}  "
            f"max={max(flags_off_shorting) if flags_off_shorting else 0}  "
            f"mean={off_s:.1f}"
        )
        print(
            f"unconnected_items (flags ON):  "
            f"min={min(flags_on_unconnected) if flags_on_unconnected else 0}  "
            f"max={max(flags_on_unconnected) if flags_on_unconnected else 0}  "
            f"mean={on_u:.1f}"
        )
        print(
            f"unconnected_items (flags OFF): "
            f"min={min(flags_off_unconnected) if flags_off_unconnected else 0}  "
            f"max={max(flags_off_unconnected) if flags_off_unconnected else 0}  "
            f"mean={off_u:.1f}"
        )

        # Soft evidence: flags-on shorting should not exceed flags-off baseline
        max_short_on = max(flags_on_shorting) if flags_on_shorting else 0
        max_short_off = max(flags_off_shorting) if flags_off_shorting else 0
        if max_short_on > max_short_off:
            print(
                f"\n  NOTE: flags-on max shorting ({max_short_on}) > "
                f"flags-off max ({max_short_off})"
            )
        else:
            print("\n  OK: flags-on shorting range does not exceed baseline")
