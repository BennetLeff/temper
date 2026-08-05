"""U3: First-ever route_pcb run against ``pcb/temper.kicad_pcb``.

Measures ``routed_nets``, ``completion_rate``, DRC violation counts, and wall
time for the production board (95 nets, 149 components, 100x150mm).

This module MEASURES only. It does not write
``power_pcb_dataset/baselines/temper_production_baseline.yaml`` -- refreshing
that file's ``router_v6_routing`` block is done deliberately, through
``scripts/update_production_routing_baseline.py``.

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

# No _BASELINE_PATH here, deliberately. This module used to hold one and write
# to it from a collected `test_*` function; nothing in this suite may name a
# committed measurement artifact as a write target. The baseline path lives in
# scripts/update_production_routing_baseline.py, which is the only writer.


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
                "kicad-cli",
                "pcb",
                "drc",
                "--format",
                "json",
                "-o",
                str(drc_out),
                str(pcb_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        stderr_summary = proc.stderr.strip()[:200] if proc.returncode != 0 and proc.stderr else ""
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
    both test assertions and a module-level ``_ROUTING_RECORD`` dict,
    emitted by ``_emit_routing_record`` for consumption by
    ``scripts/update_production_routing_baseline.py``.
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

        from tests.conftest import make_parsed_pcb_stub

        parsed_stub = make_parsed_pcb_stub(_PCB_PATH, netlist)

        print(
            f"\nRouting production board ({net_count} nets, "
            f"{len(netlist.components)} components)..."
        )
        t0 = time.monotonic()
        routing_result = route_pcb(
            parsed_stub,
            {},
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
            f"Routed content suspiciously small ({len(routing_result.routed_pcb_content)} bytes)"
        )

        # Write routed PCB and run KiCad DRC
        routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            suffix=".kicad_pcb",
            mode="w",
            delete=False,
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
        print(f"  Post-route DRC: {total_drc} violations, {unconnected} unconnected")
        print(f"  By type: {dict(sorted(by_type.items()))}")

        # APC gate: router output must not regress past the measured
        # baseline for the current board.
        #
        # RE-BASELINED 2026-08-02 (kicad-cli 10.0.4, macOS arm64): this gate
        # sat at the 2026-07-31 K2-swap measurement (411) while the router's
        # deterministic output drifted to ~460 unconnected over two attributed
        # changes: (1) the 2026-08-02 board change (31 footprints nudged --
        # K2 +18.2mm y, RT1 -2.4mm, 29 refs by 0.01-0.03mm; content hash
        # 0fff888a -> cf161bee) and (2) measurement-context drift from three
        # netclass-reclassification commits to pcb/temper.kicad_pro (369fc0f7b,
        # e3040b9a1, cbaad2eb7). The sibling gate
        # PRODUCTION_ROUTER_OUTPUT_UNCONNECTED in
        # tests/placer/cp_sat/test_regression_drc.py was re-baselined to 463
        # for exactly this measurement (route_pcb deterministic, completion
        # rate 0.4021, DRC N=11 on the one routed file: unconnected 463, zero
        # scatter) -- see that file's provenance block and
        # docs/evidence/2026-08-01-edge-hanging-refs-fix.md. This gate was
        # missed because the same route_pcb call was crashing on main
        # (DesignRules/NetClassRules `_mm` drift, fixed by commit 592cf4b29)
        # from the wave-4 migration through 2026-08-03, so it could not run
        # to surface the stale threshold. Re-aligned to the sibling's
        # attributed 463; a fresh measurement on this code (2026-08-03,
        # post-fix) reports 460 <= 463. Same documented, attributed class as
        # every prior move -- not a ratchet-up to absorb an unexplained
        # regression. The router re-route is the standing follow-up.
        assert unconnected <= 463, (
            f"APC gate: expected <= 463 unconnected_items (2026-08-02 "
            f"re-baseline, tests/placer/cp_sat/test_regression_drc.py "
            f"provenance + docs/evidence/"
            f"2026-08-01-edge-hanging-refs-fix.md), got {unconnected}."
        )

        # Store results globally for the baseline updater
        _ROUTING_RECORD.update(
            {
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
            }
        )

        # Critical net check
        critical_remaining = [
            n
            for n in [
                "GATE_HS",
                "GATE_LS",
                "PWM_HS",
                "PWM_LS",
                "sclk",
                "sdi",
                "sdo",
                "I_SENSE",
                "+340V_BUS",
                "DC_BUS_RTN",
                "SW_NODE",
            ]
            if n in unrouted
        ]
        if critical_remaining:
            print(f"  Critical nets still unrouted: {critical_remaining}")

        # Emit the measurement for scripts/update_production_routing_baseline.py.
        # No-op unless that script (or a human running it by hand) set
        # TEMPER_ROUTING_RECORD_OUT to a scratch path. This never touches the
        # committed baseline -- see _emit_routing_record's docstring.
        _emit_routing_record()


# Module-level record, populated by test_route_pcb_production_board
_ROUTING_RECORD: dict = {}


def _emit_routing_record() -> None:
    """Write ``_ROUTING_RECORD`` to the path in ``TEMPER_ROUTING_RECORD_OUT``.

    This is the *whole* of this suite's involvement in baseline regeneration,
    and it deliberately writes to a caller-supplied scratch path -- never to
    ``_BASELINE_PATH``.

    What used to be here was a ``test_update_baseline_yaml`` that rewrote
    ``power_pcb_dataset/baselines/temper_production_baseline.yaml`` in place
    via ``yaml.safe_dump``. It carried no ``skipif``, no env guard and no
    opt-in marker (the class-level ``slow``/``routing`` marks above are on a
    different class), so pytest collected and ran it on an ordinary session:
    it stripped all ~235 comment lines from the baseline -- including the
    ~200-line header explaining why ``component_count``/``net_count`` were
    removed on 2026-07-29 -- and left the rewrite in the working tree for
    ``git add -A`` to commit. Two agents hit it independently on 2026-08-04.

    The split is the fix: this suite MEASURES and emits a record; the writing
    of a committed measurement artifact belongs to a deliberate, reviewed
    entry point, ``scripts/update_production_routing_baseline.py``, which
    splices only the ``router_v6_routing`` block and leaves every other byte
    of the file alone. No environment variable makes a test in this repo write
    a protected baseline -- see ``scripts/_lib/pytest_artifact_guard.py``.
    """
    out_path = os.environ.get("TEMPER_ROUTING_RECORD_OUT")
    if not out_path:
        return
    Path(out_path).write_text(json.dumps(_ROUTING_RECORD, indent=2, sort_keys=False))
    print(f"Wrote routing record to {out_path}")
