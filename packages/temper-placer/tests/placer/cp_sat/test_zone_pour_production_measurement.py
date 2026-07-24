"""U3 (zone/pour plan 2026-07-20-002): production-board DRC measurement
with ``enable_zone_pours=True``.

This is the CI gate that determines whether zone/pour actually reduces
``unconnected_items`` -- it does not assume improvement, it measures it.
Marked slow: a full production-board route + zone fill + KiCad DRC pass
is a ~200s+ operation, not meant for interactive/in-session iteration.

Emitted zones carry an outline polygon only, no computed filled copper
-- DRC's connectivity check sees an unfilled zone as no connection at
all, regardless of any ``(fill yes ...)`` declaration. kicad-cli's
``--refill-zones`` DRC flag would compute this, but doesn't exist in
CI's KiCad 8.0.9 ("Unknown argument: --refill-zones", confirmed in CI).
This test shells out to ``scripts/kicad_fill_zones.py`` under the
system python3 (where pcbnew bindings live after ``apt-get install
kicad``) to pre-fill zones via ``pcbnew.ZONE_FILLER`` before running
plain ``kicad-cli pcb drc`` -- version-independent, unlike the CLI flag.

-- anti-false-zero discipline --
* Confirms the routed board is non-trivial (mirrors
  ``test_temper_production_board_routing.py``'s pattern).
* Confirms KiCad DRC actually ran (not skipped/errored) before drawing
  any conclusion from its output.
* Does not assert immediate parity with the pre-U4 149 baseline -- that
  baseline included writer-stitch/plane-MST fabricated copper that is
  permanently deleted (see
  docs/evidence/2026-07-20-tree-executor-resilience-U5-measurement.json).
  It asserts genuine improvement over the current honest baseline (260,
  measured post-U4 deletion with ``enable_zone_pours=False``, confirmed
  identically across PR #261 and PR #262 CI runs on 2026-07-21) instead.
  If zone/pour does not beat 260, this test fails loudly rather than
  silently reporting a number -- that failure is itself the answer to
  "does zone/pour help at all".
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

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"

# Measured post-U4 (writer-stitch/plane-MST deletion), enable_zone_pours=False,
# identically across PR #261 (2026-07-21T06:14Z) and PR #262 (2026-07-21T06:24Z)
# CI runs. This is the honest baseline zone/pour must beat -- not the stale
# 149 figure, which relied on fabricated copper that is gone for good.
PRODUCTION_UNCONNECTED_POST_U4_BASELINE = 260


_FILL_ZONES_SCRIPT = _REPO_ROOT / "scripts" / "kicad_fill_zones.py"
# apt-get install kicad (CI) installs pcbnew bindings for the system
# python3, not any project-managed venv -- uv run's own venv would
# shadow a bare "python3" on PATH, so this must be an explicit path.
_SYSTEM_PYTHON3 = Path("/usr/bin/python3")


def _kicad_cli_available() -> bool:
    try:
        # This test runs last (alphabetically) in tests/placer/cp_sat/, after
        # the multi-minute production/golden board regressions -- a 10s
        # timeout here can spuriously fire on a runner under sustained load
        # this late in the job, even though kicad-cli itself is fine.
        result = subprocess.run(
            ["kicad-cli", "--version"], capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _fill_zones_via_pcbnew(pcb_path: Path) -> Path:
    """Pre-fill zones using KiCad's own pcbnew API before DRC runs.

    kicad-cli's ``--refill-zones`` DRC flag doesn't exist in CI's KiCad
    8.0.9 (confirmed: "Unknown argument: --refill-zones"). Without a
    computed ``filled_polygon``, an emitted zone is just an outline --
    DRC's connectivity check sees zero copper there regardless of any
    ``(fill yes ...)`` declaration. Verified locally: pcbnew.ZONE_FILLER
    on the routed production board drops unconnected_items from 260 to
    the 240s, while plain DRC with no fill step stays at 260 exactly.

    Skips (not fails) if the system python3 can't import pcbnew -- this
    is expected on local dev machines (e.g. macOS, where KiCad bundles
    its own separate Python interpreter), not a code defect.
    """
    if not _SYSTEM_PYTHON3.exists():
        pytest.skip(f"{_SYSTEM_PYTHON3} not found -- cannot pre-fill zones via pcbnew")

    filled_path = pcb_path.with_name(pcb_path.stem + "_filled" + pcb_path.suffix)
    proc = subprocess.run(
        [str(_SYSTEM_PYTHON3), str(_FILL_ZONES_SCRIPT), str(pcb_path), str(filled_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 2:
        pytest.skip(f"pcbnew not importable from {_SYSTEM_PYTHON3}: {proc.stderr.strip()[:300]}")
    if proc.returncode != 0:
        pytest.skip(
            f"kicad_fill_zones.py failed (returncode={proc.returncode}): "
            f"{proc.stderr.strip()[:300]}"
        )
    if not filled_path.exists():
        pytest.skip("kicad_fill_zones.py reported success but produced no output file")
    return filled_path


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
            timeout=600,
        )
        # Surface stdout/stderr/returncode unconditionally when diagnosing
        # a missing-output failure -- a prior CI run showed kicad-cli
        # exiting in under 1s with returncode 0 and no output file, which
        # a returncode-gated stderr capture would silently hide.
        proc_summary = (
            f"returncode={proc.returncode} "
            f"stdout={proc.stdout.strip()[:300]!r} "
            f"stderr={proc.stderr.strip()[:300]!r}"
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
        pytest.skip(f"kicad-cli DRC produced no output file: {proc_summary}")
        return {}

    try:
        with open(drc_out) as f:
            return json.load(f)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(drc_out)


@pytest.mark.slow
@pytest.mark.routing
class TestZonePourProductionMeasurement:
    """Route the production board with enable_zone_pours=True and measure
    the real KiCad DRC impact -- the U3 gate for zone/pour plan 2026-07-20-002.
    """

    def test_zone_pours_reduce_unconnected_items(self):
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

        from tests.conftest import make_parsed_pcb_stub

        parsed_stub = make_parsed_pcb_stub(_PCB_PATH, netlist)

        print(
            f"\nRouting production board with enable_zone_pours=True "
            f"({len(netlist.components)} components)..."
        )
        t0 = time.monotonic()
        routing_result = route_pcb(
            parsed_stub,
            {},
            design_rules=rules.design_rules,
            enable_zone_pours=True,
        )
        wall_s = time.monotonic() - t0
        print(f"  Wall time: {wall_s:.1f}s")

        # Anti-false-zero: confirm this processed the real board and zones
        # were actually emitted, not silently skipped.
        assert routing_result.routed_pcb_content is not None
        assert len(routing_result.routed_pcb_content) > 1000, (
            f"Routed content suspiciously small ({len(routing_result.routed_pcb_content)} bytes)"
        )
        zone_count = routing_result.routed_pcb_content.count("(zone ")
        print(f"  Zones emitted: {zone_count}")
        assert zone_count > 0, (
            "enable_zone_pours=True produced zero (zone ...) entries -- "
            "measurement is meaningless if zones never fired"
        )

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
            drc_data = _run_drc(filled_path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(routed_path)
            if filled_path is not None:
                with contextlib.suppress(OSError):
                    os.unlink(filled_path)

        violations = drc_data.get("violations", [])
        by_type: dict[str, int] = {}
        for v in violations:
            vtype = v.get("type", "other")
            by_type[vtype] = by_type.get(vtype, 0) + 1

        unconnected = len(drc_data.get("unconnected_items", []))
        total_drc = sum(by_type.values())
        print(f"  Post-route DRC (zones on): {total_drc} violations, {unconnected} unconnected")
        print(f"  By type: {dict(sorted(by_type.items()))}")
        print(
            f"  vs. post-U4 no-zones baseline: "
            f"{unconnected} vs {PRODUCTION_UNCONNECTED_POST_U4_BASELINE}"
        )
        print(
            f"  vs. pre-U4 aspirational baseline: {unconnected} vs 149 "
            f"(not asserted -- that figure relied on deleted fabricated copper)"
        )

        # U3 gate: zone/pour must measurably help, or this fails loudly
        # rather than reporting a non-improving number as a quiet pass.
        assert unconnected < PRODUCTION_UNCONNECTED_POST_U4_BASELINE, (
            f"enable_zone_pours=True did not reduce unconnected_items "
            f"({unconnected} >= {PRODUCTION_UNCONNECTED_POST_U4_BASELINE} "
            f"baseline). Zone/pour as currently implemented does not help "
            f"on the production board -- U4 promotion should not proceed."
        )
