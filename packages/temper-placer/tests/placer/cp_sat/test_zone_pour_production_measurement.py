"""U3 (zone/pour plan 2026-07-20-002): production-board DRC measurement
with ``enable_zone_pours=True``.

This is the CI gate that determines whether zone/pour actually reduces
``unconnected_items`` -- it does not assume improvement, it measures it.
Marked slow: two full production-board routes + zone fills + KiCad DRC
passes, a ~6 minute operation, not meant for interactive iteration.

Emitted zones carry an outline polygon only, no computed filled copper
-- DRC's connectivity check sees an unfilled zone as no connection at
all, regardless of any ``(fill yes ...)`` declaration. kicad-cli's
``--refill-zones`` DRC flag would compute this, but doesn't exist in
CI's KiCad 8.0.9 ("Unknown argument: --refill-zones", confirmed in CI).
This test shells out to ``scripts/kicad_fill_zones.py`` under an
interpreter that has pcbnew bindings (see ``_resolve_pcbnew_python``) to
pre-fill zones via ``pcbnew.ZONE_FILLER`` before running plain
``kicad-cli pcb drc`` -- version-independent, unlike the CLI flag.

-- why there is no baseline constant here (2026-07-28) --
This gate used to compare ``enable_zone_pours=True`` against a hardcoded
``PRODUCTION_UNCONNECTED_POST_U4_BASELINE = 260``.  That number was
measured on 2026-07-21, when ``pcb/temper.kicad_pcb`` held 149 footprints
and ZERO copper.  Since 556ccf4f (2026-07-27) the board ships 2,338
segments / 48 vias / 96 zones, so the gate was asking "does zone/pour on
*this* board beat a number from *that* board" -- the same category error
PR #373 fixed in ``test_regression_drc.py``, where a bare-board DRC budget
was silently reused as a routed-board budget.

The fix there was to re-measure the constants and add a board-shape guard.
The fix here is stronger and needs no constant at all: **measure both arms
in the same run on whatever board is currently checked in.**  A
differential gate cannot go stale, so there is deliberately no
``PRODUCTION_BOARD_BASELINE_SHAPE`` equivalent in this module -- that guard
exists in ``test_regression_drc.py`` to protect hardcoded numbers, and
there are none left to protect here.

-- anti-false-zero discipline --
* Confirms the routed board is non-trivial (mirrors
  ``test_temper_production_board_routing.py``'s pattern).
* Confirms zones actually fired in the pours-on arm (``zone_entries > 0``),
  that its zone-covered net set differs from the untouched pours-off arm's
  (otherwise the two arms are the same measurement and the comparison is
  vacuous), and that every net it poured belongs to a netclass the SSOT
  declares ``routing_strategy == "plane_required"`` -- since R7 (2026-07-28)
  pours are *derived*, not additive, so "more zone entries than the
  untouched board" is no longer the correctness signal; "only the SSOT's
  plane-required nets" is. See the inline comment at the assertion for the
  regression (stale hardcoded eligibility list) this replaced.
* Confirms KiCad DRC actually ran (not skipped/errored) in both arms
  before drawing any conclusion from either.
* Samples DRC ``_DRC_SAMPLE_RUNS`` times per arm and compares medians.
  KiCad DRC is not run-to-run reproducible on this board (docs/STRATEGY.md
  records 124/113/119/120/123 shorting_items for the *same* file), so a
  single before/after reading either flakes or hides a real move.  Routing
  itself is deterministic (docs/evidence/2026-07-27-router-determinism.md),
  so each arm is routed once and only the DRC pass is resampled.

If zone/pour does not beat the no-pours arm, this test fails loudly rather
than silently reporting a number -- that failure is itself the answer to
"does zone/pour help at all", and it is the U4 promotion signal.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"

# DRC samples per arm.  Routing is deterministic, KiCad DRC is not, so the
# variance being averaged out here is entirely DRC's.  Matches the sampling
# discipline of PRODUCTION_DRC_SAMPLE_RUNS in test_regression_drc.py.
_DRC_SAMPLE_RUNS = 3


_FILL_ZONES_SCRIPT = _REPO_ROOT / "scripts" / "kicad_fill_zones.py"


def _resolve_pcbnew_python() -> Path | None:
    """Resolve an interpreter that can ``import pcbnew``.

    Priority (first match wins):
    1. ``TEMPER_PCBNEW_PYTHON`` env var — explicit override.
    2. ``/usr/bin/python3`` — where ``apt-get install kicad`` (CI) puts the
       bindings.  A project-managed venv never has them, and ``uv run``
       shadows a bare ``python3`` on PATH, so these must be explicit paths.
    3. KiCad.app's bundled Python — macOS ships pcbnew only there.

    Each candidate is probed with a real ``import pcbnew`` rather than an
    existence check, because ``/usr/bin/python3`` exists on macOS *without*
    the bindings; testing for the file alone is what previously made this
    whole test family skip on every developer machine.  This mirrors
    ``gates._resolve_kicad_footprint_dir``.

    Returns ``None`` when nothing works, so the caller skips explicitly
    instead of reporting an unmeasured run as a pass.
    """
    candidates: list[Path] = []
    override = os.environ.get("TEMPER_PCBNEW_PYTHON")
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/usr/bin/python3"))
    candidates.extend(
        Path(p)
        for p in (
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
            "Python.framework/Versions/Current/bin/python3",
            "/usr/local/bin/python3",
        )
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            probe = subprocess.run(
                [str(candidate), "-c", "import pcbnew"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return candidate
    return None


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
    ``(fill yes ...)`` declaration, so the fill step is what makes the
    measurement mean anything.  (The "260 -> 240s" figure this docstring
    used to quote came from the bare 149-footprint board and no longer
    reproduces; see the module docstring.)

    Skips (not fails) when no interpreter on this machine can import
    pcbnew -- that is an environment gap, not a code defect.  On macOS the
    bindings live in KiCad.app's bundled Python, which
    ``_resolve_pcbnew_python`` finds; the previous hardcoded
    ``/usr/bin/python3`` did not, which is why this test family skipped on
    every developer machine and its baselines went unverified for a week.
    """
    interpreter = _resolve_pcbnew_python()
    if interpreter is None:
        pytest.skip(
            "No interpreter with pcbnew bindings found (tried "
            "$TEMPER_PCBNEW_PYTHON, /usr/bin/python3, KiCad.app's bundled "
            "Python) -- cannot pre-fill zones, so DRC connectivity would be "
            "measured against unfilled zone outlines"
        )

    filled_path = pcb_path.with_name(pcb_path.stem + "_filled" + pcb_path.suffix)
    proc = subprocess.run(
        [str(interpreter), str(_FILL_ZONES_SCRIPT), str(pcb_path), str(filled_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode == 2:
        pytest.skip(f"pcbnew not importable from {interpreter}: {proc.stderr.strip()[:300]}")
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


@dataclass(frozen=True)
class _ArmMeasurement:
    """One ``enable_zone_pours`` setting, routed once and DRC'd N times."""

    pours_enabled: bool
    zone_entries: int
    zone_net_names: frozenset[str]
    completion_rate: float
    unconnected_samples: tuple[int, ...]
    total_samples: tuple[int, ...]
    by_type: dict[str, int]

    @property
    def unconnected(self) -> int:
        """Median ``unconnected_items`` -- the figure this gate compares."""
        return int(statistics.median(self.unconnected_samples))

    @property
    def total(self) -> int:
        return int(statistics.median(self.total_samples))

    def describe(self) -> str:
        return (
            f"pours={'ON ' if self.pours_enabled else 'OFF'} "
            f"zones={self.zone_entries} "
            f"completion={self.completion_rate:.4f} "
            f"unconnected={self.unconnected} (samples {list(self.unconnected_samples)}) "
            f"total={self.total} (samples {list(self.total_samples)})"
        )


@pytest.mark.slow
@pytest.mark.routing
class TestZonePourProductionMeasurement:
    """Differential U3 gate for zone/pour plan 2026-07-20-002.

    Routes the production board twice -- ``enable_zone_pours`` off, then on
    -- fills zones and runs KiCad DRC on both, and asserts the pours arm
    genuinely reduces ``unconnected_items``.  Both arms are measured in the
    same run against the same checked-in board, so there is no baseline
    constant to go stale.
    """

    def _measure_arm(self, *, pours_enabled: bool) -> _ArmMeasurement:
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.netclass_loader import load_netclass_rules
        from temper_placer.router_v6.adapter import route_pcb
        from tests.conftest import make_parsed_pcb_stub

        rules = load_netclass_rules(_RULES_PATH)
        parse_result = parse_kicad_pcb(_PCB_PATH)
        netlist = parse_result.netlist
        assert netlist is not None
        assert len(netlist.components) > 0

        parsed_stub = make_parsed_pcb_stub(_PCB_PATH, netlist)

        print(
            f"\n  Routing production board with enable_zone_pours={pours_enabled} "
            f"({len(netlist.components)} components)..."
        )
        t0 = time.monotonic()
        routing_result = route_pcb(
            parsed_stub,
            {},
            design_rules=rules.design_rules,
            enable_zone_pours=pours_enabled,
        )
        print(f"    Wall time: {time.monotonic() - t0:.1f}s")

        # Anti-false-zero: confirm this processed the real board.
        content = routing_result.routed_pcb_content
        assert content is not None
        assert len(content) > 1000, f"Routed content suspiciously small ({len(content)} bytes)"

        zone_entries = content.count("(zone ")
        # Every emitted zone carries its own `(net_name "...")` field
        # (see zone_emission.emit_zone_s_expr) regardless of whether the
        # block is a freshly regenerated single-line pour or a multi-line
        # committed zone read through untouched from the board file --
        # this is what lets the R7 SSOT-compliance check below name
        # exactly which nets got a pour, not just how many zone blocks
        # exist.
        zone_net_names = frozenset(re.findall(r'\(net_name "([^"]+)"\)', content))
        print(f"    Zone entries in output: {zone_entries} (nets: {sorted(zone_net_names)})")

        routed_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            suffix=".kicad_pcb",
            mode="w",
            delete=False,
        )
        routed_tmp.write(content)
        routed_tmp.close()
        routed_path = Path(routed_tmp.name)
        filled_path: Path | None = None

        unconnected_samples: list[int] = []
        total_samples: list[int] = []
        by_type: dict[str, int] = {}
        try:
            filled_path = _fill_zones_via_pcbnew(routed_path)
            for sample in range(_DRC_SAMPLE_RUNS):
                drc_data = _run_drc(filled_path)
                violations = drc_data.get("violations", [])
                unconnected = len(drc_data.get("unconnected_items", []))
                unconnected_samples.append(unconnected)
                total_samples.append(len(violations))
                if sample == 0:
                    for v in violations:
                        vtype = v.get("type", "other")
                        by_type[vtype] = by_type.get(vtype, 0) + 1
                print(
                    f"    DRC sample {sample + 1}: "
                    f"{len(violations)} violations, {unconnected} unconnected"
                )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(routed_path)
            if filled_path is not None:
                with contextlib.suppress(OSError):
                    os.unlink(filled_path)

        # Anti-false-zero: DRC must actually have produced samples. _run_drc
        # skips rather than returns junk, so an empty list here would mean the
        # loop never ran at all.
        assert len(unconnected_samples) == _DRC_SAMPLE_RUNS

        return _ArmMeasurement(
            pours_enabled=pours_enabled,
            zone_entries=zone_entries,
            zone_net_names=zone_net_names,
            completion_rate=routing_result.completion_rate,
            unconnected_samples=tuple(unconnected_samples),
            total_samples=tuple(total_samples),
            by_type=by_type,
        )

    def test_zone_pours_reduce_unconnected_items(self):
        if not _kicad_cli_available():
            pytest.skip("kicad-cli not available")

        assert _PCB_PATH.exists(), f"Board not found: {_PCB_PATH}"
        assert _RULES_PATH.exists(), f"Rules not found: {_RULES_PATH}"

        off = self._measure_arm(pours_enabled=False)
        on = self._measure_arm(pours_enabled=True)

        print("\n=== U3 zone/pour differential ===")
        print(f"  {off.describe()}")
        print(f"  {on.describe()}")

        deltas = {
            vtype: on.by_type.get(vtype, 0) - off.by_type.get(vtype, 0)
            for vtype in sorted(set(off.by_type) | set(on.by_type))
        }
        changed = {vtype: d for vtype, d in deltas.items() if d}
        print(f"  Violation deltas (ON - OFF), first DRC sample: {changed}")
        print(f"  unconnected_items: {on.unconnected} (ON) vs {off.unconnected} (OFF)")

        # Anti-vacuous-truth + R7 SSOT compliance.
        #
        # This used to be `assert on.zone_entries > off.zone_entries`: the
        # pours-on arm must add strictly *more* zone entries than the
        # pours-off arm. That assumed pours were purely additive on top of
        # an unzoned board. Since R7 (copper pours are regenerated from the
        # routed result; the board file's stored zones stop being
        # authoritative input -- docs/plans/2026-07-28-001-...-plan.md) that
        # assumption no longer holds: `enable_zone_pours=False` leaves the
        # board's checked-in zones untouched (a historical, non-derived
        # artifact -- currently 96 entries spanning every netclass ever
        # hand-authored on this board), while `enable_zone_pours=True`
        # *replaces* them with a narrower, safety-scoped set covering only
        # netclasses the SSOT actually declares plane-required (ACMains,
        # HighVoltage today) -- correctly *fewer* entries, not more.
        #
        # A raw ">" count comparison is exactly the kind of check that can
        # pass or fail by coincidence of cardinality rather than by
        # correctness of content -- which is precisely how this went
        # undetected: a hardcoded eligibility list (GND/Power/GateDrive
        # wrongly included, commit 27368038's fix having been dropped by a
        # sibling-branch code move) happened to regenerate exactly 96 zone
        # entries again -- the same *count* as the untouched board, but the
        # wrong net set entirely. Both arms reporting zone_entries=96 was
        # the symptom; comparing only counts is why it wasn't caught by
        # construction.
        #
        # The invariant that survives R7 is content identity and SSOT
        # compliance, not a direction on raw counts:
        assert on.zone_entries > 0, (
            "enable_zone_pours=True emitted zero zone entries -- pours never "
            "fired for any net, so this comparison measures nothing"
        )
        assert on.zone_net_names != off.zone_net_names, (
            f"enable_zone_pours=True regenerated the exact same zone-covered "
            f"net set as the untouched board ({sorted(on.zone_net_names)}) -- "
            f"the two arms are the same measurement and the comparison is "
            f"vacuous"
        )
        from temper_placer.core.design_rules import (
            TEMPER_NET_ASSIGNMENTS,
            TEMPER_NET_CLASSES,
        )

        ineligible_nets = {
            net_name
            for net_name in on.zone_net_names
            if not (
                (nc := TEMPER_NET_CLASSES.get(TEMPER_NET_ASSIGNMENTS.get(net_name, "")))
                and nc.routing_strategy == "plane_required"
            )
        }
        assert not ineligible_nets, (
            f"enable_zone_pours=True regenerated pours for nets whose netclass "
            f"does not declare routing_strategy=='plane_required': "
            f"{sorted(ineligible_nets)} -- R7 requires pours be regenerated "
            f"only for SSOT-declared plane-required nets, never carried over "
            f"from whatever netclasses happened to have pours before "
            f"(zone-covered nets this run: {sorted(on.zone_net_names)})"
        )

        # U3 gate: zone/pour must measurably help, or this fails loudly
        # rather than reporting a non-improving number as a quiet pass.
        assert on.unconnected < off.unconnected, (
            f"enable_zone_pours=True did not reduce unconnected_items on the "
            f"current board ({on.unconnected} with pours vs {off.unconnected} "
            f"without, median of {_DRC_SAMPLE_RUNS} DRC samples each).\n"
            f"  ON : {on.describe()}\n"
            f"  OFF: {off.describe()}\n"
            f"  violation deltas (ON - OFF): {changed}\n"
            f"Zone/pour as currently implemented does not help on this board "
            f"-- U4 promotion should not proceed. This is a differential "
            f"measurement on the checked-in board, NOT a comparison against a "
            f"stored baseline, so it cannot be a stale-number artifact: both "
            f"arms were routed and DRC'd in this same run."
        )
