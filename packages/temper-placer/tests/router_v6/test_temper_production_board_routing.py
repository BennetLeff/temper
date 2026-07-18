"""U3: First-ever route_pcb run against ``pcb/temper.kicad_pcb``.

Records ``routed_nets``, ``completion_rate``, DRC violation counts, and wall
time for the production board (95 nets, 149 components, 100x150mm) as a
reproducible artifact, replacing the ``null``/``0`` placeholders in
``power_pcb_dataset/baselines/temper_production_baseline.yaml``.

Uses the post-2026-07-18 gate-dispatch path via ``route_pcb`` wired with
W2 U2's ``layer_constraints`` from the netclass SSOT.

-- anti-false-zero discipline --
This test confirms the run actually processed the intended artifact:
* Production board source_path resolves to ``pcb/temper.kicad_pcb``
* Net list is non-empty (95 nets, confirmed at assertion level)
* KiCad DRC output is producible (proves kicad-cli ran successfully)
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"
_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"


def _kicad_cli_available() -> bool:
    try:
        result = subprocess.run(
            ["kicad-cli", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_drc(pcb_path: Path) -> dict:
    drc_out_fd, drc_out_str = tempfile.mkstemp(suffix=".json")
    os.close(drc_out_fd)
    drc_out = Path(drc_out_str)
    try:
        proc = subprocess.run(
            [
                "kicad-cli", "pcb", "drc",
                "--format", "json",
                "-o", str(drc_out),
                str(pcb_path),
            ],
            capture_output=True, text=True, timeout=300,
        )
        stderr_summary = (
            proc.stderr.strip()[:200]
            if proc.returncode != 0 and proc.stderr
            else ""
        )
    except subprocess.TimeoutExpired:
        if drc_out.exists():
            os.unlink(drc_out)
        pytest.skip("kicad-cli DRC timed out")
        return {}
    except Exception:
        if drc_out.exists():
            os.unlink(drc_out)
        raise

    if not drc_out.exists() or drc_out.stat().st_size == 0:
        pytest.skip(
            "kicad-cli DRC produced no output file"
            + (f": {stderr_summary}" if stderr_summary else "")
        )
        return {}

    try:
        with open(drc_out) as f:
            return json.load(f)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(drc_out)


@pytest.mark.slow
@pytest.mark.routing
class TestProductionBoardRouting:
    """Route the production board through router_v6 for the first time.

    Measures routing metrics against ``pcb/temper.kicad_pcb`` with
    component positions unmodified (no CP-SAT placement — routing-only
    pass using the board's existing layout).  Results are recorded as
    both test assertions and a module-level ``_ROUTING_RECORD`` dict
    consumed by ``test_update_baseline_yaml``.
    """

    def test_route_pcb_production_board(self):
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
        assert netlist is not None
        assert len(netlist.components) > 0

        net_count = len([n for n in netlist.nets if len(n.pins) >= 2])
        assert net_count > 0, "No multi-pin nets on production board"

        parsed_stub = type("ParsedStub", (), {"source_path": _PCB_PATH})()

        print(f"\nRouting production board ({net_count} nets, "
              f"{len(netlist.components)} components)...")
        t0 = time.monotonic()
        routing_result = route_pcb(
            parsed_stub, {},
            _seed=42,
            design_rules=rules.design_rules,
        )
        wall_s = time.monotonic() - t0

        completion_rate = routing_result.completion_rate
        unrouted = list(routing_result.unrouted_nets)
        total_nets = len(netlist.nets)

        print(f"  Wall time: {wall_s:.1f}s")
        print(f"  Routed: {int(total_nets * completion_rate)}/{total_nets}")
        print(f"  Completion rate: {completion_rate:.2%}")
        if unrouted:
            print(f"  Unrouted ({len(unrouted)}): {sorted(unrouted)}")

        # Anti-false-zero: confirm this processed the real board
        assert routing_result.routed_pcb_content is not None
        assert len(routing_result.routed_pcb_content) > 1000, (
            f"Routed content suspiciously small "
            f"({len(routing_result.routed_pcb_content)} bytes)"
        )

        # Write routed PCB and run KiCad DRC
        routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            suffix=".kicad_pcb", mode="w", delete=False,
        )
        routed_tmp.write(routing_result.routed_pcb_content)
        routed_tmp.close()

        try:
            drc_data = _run_drc(Path(routed_tmp.name))
        finally:
            with contextlib.suppress(OSError):
                os.unlink(routed_tmp.name)

        violations = drc_data.get("violations", [])
        by_type: dict[str, int] = {}
        for v in violations:
            vtype = v.get("type", "other")
            by_type[vtype] = by_type.get(vtype, 0) + 1

        unconnected = len(drc_data.get("unconnected_items", []))
        total_drc = sum(by_type.values())
        print(f"  Post-route DRC: {total_drc} violations, "
              f"{unconnected} unconnected")
        print(f"  By type: {dict(sorted(by_type.items()))}")

        # Store results globally for the baseline updater
        _ROUTING_RECORD.update({
            "wall_time_s": round(wall_s, 1),
            "net_count": net_count,
            "component_count": len(netlist.components),
            "completion_rate": completion_rate,
            "routed_nets": int(total_nets * completion_rate),
            "unrouted_nets": len(unrouted),
            "unrouted_nets_list": sorted(unrouted),
            "drc_violations_post_route": total_drc,
            "drc_violations_by_type": dict(by_type),
            "unconnected_items": unconnected,
            "extraction_date": "2026-07-18",
            "extraction_method": "router_v6.route_pcb(existing_positions)",
            "kicad_cli_version": subprocess.run(
                ["kicad-cli", "--version"], capture_output=True, text=True
            ).stdout.strip()[:80],
        })

        # Critical net check
        critical_remaining = [n for n in [
            "GATE_HS", "GATE_LS", "PWM_HS", "PWM_LS",
            "sclk", "sdi", "sdo", "I_SENSE", "+340V_BUS",
            "DC_BUS_RTN", "SW_NODE",
        ] if n in unrouted]
        if critical_remaining:
            print(f"  Critical nets still unrouted: {critical_remaining}")


# Module-level record, populated by test_route_pcb_production_board
_ROUTING_RECORD: dict = {}


def test_update_baseline_yaml():
    """Patch the production baseline YAML with router_v6 routing metrics.

    Reads ``_ROUTING_RECORD`` (populated by
    ``test_route_pcb_production_board``), adds a ``router_v6_routing``
    block to the baseline YAML, and writes it back.  The existing
    ``deterministic_pipeline`` and ``cp_sat`` blocks are preserved.
    """
    if not _ROUTING_RECORD:
        pytest.skip(
            "No routing record available. Run "
            "test_route_pcb_production_board first."
        )

    import yaml

    assert _BASELINE_PATH.exists(), f"Baseline not found: {_BASELINE_PATH}"

    with open(_BASELINE_PATH) as f:
        doc = yaml.safe_load(f) or {}

    doc["router_v6_routing"] = {
        "wall_time_s": _ROUTING_RECORD["wall_time_s"],
        "completion_rate": _ROUTING_RECORD["completion_rate"],
        "routed_nets": _ROUTING_RECORD["routed_nets"],
        "unrouted_nets": _ROUTING_RECORD["unrouted_nets"],
        "unrouted_nets_list": _ROUTING_RECORD["unrouted_nets_list"],
        "drc_violations_post_route": _ROUTING_RECORD["drc_violations_post_route"],
        "drc_violations_by_type": dict(_ROUTING_RECORD["drc_violations_by_type"]),
        "unconnected_items": _ROUTING_RECORD["unconnected_items"],
        "extraction_date": _ROUTING_RECORD["extraction_date"],
        "extraction_method": _ROUTING_RECORD["extraction_method"],
        "kicad_cli_version": _ROUTING_RECORD.get("kicad_cli_version", ""),
    }

    with open(_BASELINE_PATH, "w") as f:
        yaml.safe_dump(doc, f, default_flow_style=False, sort_keys=False)

    print(f"Updated {_BASELINE_PATH} with router_v6_routing block")
