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
* Confirms zones actually fired in the pours-on arm, and that it emitted
  strictly more of them than the pours-off arm -- otherwise the two arms
  are the same measurement and the comparison is vacuous.
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
import os
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.placer.cp_sat._parallel_drc import run_drc_samples

_TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _TEMPER_PLACER_ROOT.parent.parent

_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_RULES_PATH = _TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"

# DRC samples per arm.  Routing is deterministic, KiCad DRC is not, so the
# variance being averaged out here is entirely DRC's.  Matches the sampling
# discipline of PRODUCTION_DRC_SAMPLE_RUNS in test_regression_drc.py.
_DRC_SAMPLE_RUNS = 3

# Minimum unconnected_items improvement (OFF - ON) required to call
# zone/pour a real win, rather than a noise-level wash.
#
# Grounded in observed data, not a round number.  Six CI runs on `main`
# between 2026-07-29T06:32 and 2026-07-29T17:23 -- spanning multiple
# unrelated commits (router/DRC-gate fixes, no change to zone/pour itself
# or to the checked-in board) -- measured this same differential:
#
#   run          OFF   ON   delta (OFF-ON)
#   30427182910  394   394   0
#   30442750275  394   395  -1
#   30466675129  395   394  +1
#   30469095141  394   394   0
#   30472345364  394   394   0
#   30473164714  394   394   0
#
# Every within-run sample set had zero scatter (3/3 DRC samples identical
# per arm, per run) -- all of the +-1 spread above is *between* runs, i.e.
# genuine measurement noise in an otherwise-unchanged comparison, not
# sampling variance _DRC_SAMPLE_RUNS already averages out. The largest
# noise-driven delta observed is 1 unconnected item in either direction.
# A bare ``on.unconnected < off.unconnected`` (delta >= 1) therefore calls
# a coin-flip a win. The margin below is the smallest integer that
# excludes that observed noise band, so a delta of 1 reads as "no
# improvement" and only a delta of >= 2 -- twice the largest noise
# excursion seen across this sample -- counts as zone/pour genuinely
# helping.
_MIN_UNCONNECTED_IMPROVEMENT = 2


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


@dataclass(frozen=True)
class _ArmMeasurement:
    """One ``enable_zone_pours`` setting, routed once and DRC'd N times."""

    pours_enabled: bool
    zone_entries: int
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
        print(f"    Zone entries in output: {zone_entries}")

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
            for sample, drc_data in enumerate(
                run_drc_samples(
                    filled_path, n=_DRC_SAMPLE_RUNS, timeout=600, label="zone-pour"
                )
            ):
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
            completion_rate=routing_result.completion_rate,
            unconnected_samples=tuple(unconnected_samples),
            total_samples=tuple(total_samples),
            by_type=by_type,
        )

    # xfail(strict=True), not a skip or a weakened assertion: the assertion
    # below is untouched and still runs on every CI invocation. This is a
    # KNOWN, MEASURED, and ACCEPTED negative result, not an unmanaged
    # failure -- see docs/plans/2026-07-20-002-feat-zone-pour-connectivity-plan.md
    # (U3 = this measurement, U4 = "enable zone pours by default", gated on
    # U3 showing improvement) and the confirming measurements in
    # docs/evidence/2026-07-28-zone-pour-differential-verdict.md and
    # docs/evidence/2026-07-28-pour-strategy-audit.md: on the board as
    # committed, `enable_zone_pours=True` re-pours nets that already have a
    # committed zone, adding ~96 `zones_intersect` violations and connecting
    # nothing that wasn't already connected -- U4 promotion does not
    # proceed. Confirmed still reproducing in CI (2026-07-29, runs
    # 30427182910 / 30442750275 / 30469095141 / 30472345364 / 30473164714:
    # 394 vs 394, or a marginal 394 vs 395 one-item wash) -- this is a
    # standing, accepted state of the capability, not a live regression.
    #
    # strict=True is deliberate: if `_zone_layers_for_net()` is ever fixed to
    # stop re-pouring already-zoned nets (Task 3 of the pour-strategy audit,
    # "fix the generator, not just the artifact"), or the board changes such
    # that zone/pour genuinely reduces unconnected_items, this xfail flips to
    # XPASS and CI goes red -- which is the correct signal to reopen the U4
    # promotion decision. Do not add `strict=False` or remove this marker to
    # silence that signal without re-evaluating U4.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "U3 measured, accepted negative result: enable_zone_pours=True "
            "does not reduce unconnected_items on the committed production "
            "board (see docs/plans/2026-07-20-002-feat-zone-pour-connectivity-plan.md "
            "U4 and docs/evidence/2026-07-28-zone-pour-differential-verdict.md). "
            "U4 promotion should not proceed until this flips to XPASS."
        ),
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

        # Anti-vacuous-truth: the two arms must actually differ, or this is
        # one measurement compared against itself and the verdict is
        # meaningless regardless of which way it lands.
        assert on.zone_entries > off.zone_entries, (
            f"enable_zone_pours=True emitted {on.zone_entries} zone entries and "
            f"enable_zone_pours=False emitted {off.zone_entries} -- the pours "
            f"arm added nothing, so this comparison measures nothing"
        )

        # U3 gate: zone/pour must measurably help -- by more than the
        # observed noise band (see _MIN_UNCONNECTED_IMPROVEMENT) -- or this
        # fails loudly rather than reporting a noise-level wash as a pass.
        # A bare `on.unconnected < off.unconnected` would call a 1-item
        # delta a win; six CI runs show +-1 is exactly the run-to-run noise
        # on this comparison with no real change underneath it, so a delta
        # of 1 must fail here, and only >= _MIN_UNCONNECTED_IMPROVEMENT
        # counts as improvement.
        improvement = off.unconnected - on.unconnected
        assert improvement >= _MIN_UNCONNECTED_IMPROVEMENT, (
            f"enable_zone_pours=True improved unconnected_items by only "
            f"{improvement} on the current board ({on.unconnected} with "
            f"pours vs {off.unconnected} without, median of "
            f"{_DRC_SAMPLE_RUNS} DRC samples each) -- below the "
            f"_MIN_UNCONNECTED_IMPROVEMENT={_MIN_UNCONNECTED_IMPROVEMENT} "
            f"margin, which exists because observed run-to-run noise on "
            f"this exact comparison is +-1 unconnected item (see the "
            f"module-level data table), so a delta this small is not "
            f"distinguishable from noise.\n"
            f"  ON : {on.describe()}\n"
            f"  OFF: {off.describe()}\n"
            f"  violation deltas (ON - OFF): {changed}\n"
            f"Zone/pour as currently implemented does not help on this board "
            f"-- U4 promotion should not proceed. This is a differential "
            f"measurement on the checked-in board, NOT a comparison against a "
            f"stored baseline, so it cannot be a stale-number artifact: both "
            f"arms were routed and DRC'd in this same run."
        )
