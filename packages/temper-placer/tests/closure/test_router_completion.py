"""
Closure test for the ghost-pad injection feature.

Implements U5a (pre-change baseline record) and U5b (post-change
promotion gate).  The baseline fixture
``tests/closure/fixtures/baseline_closure.json`` is committed on
``main`` before U1 lands.  The candidate branch runs the same
closure pipeline at the same fixed seed and asserts SM1/SM2/SM6
gates clear.

SM1: ``router_completion_pct`` ≥ 90% AND ≥ baseline
SM2: DRC clearance pass rate ≥ 96.7% AND ≥ baseline
SM6: Wall time ≤ 105% of baseline wall time
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Fixtures and constants
# ---------------------------------------------------------------------------


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "baseline_closure.json"
)

# Default PCB path used when the gate runs without an explicit
# override.  The closure test now targets ``pcb/temper.kicad_pcb``
# (the canonical "temper_canonical" board, 24 nets, 27 THT pads,
# 5 layers, 33 components) so SM1 reflects the real production
# target rather than a 4-SMD minimal fixture.  Relative to repo
# root so the test works from any cwd.  The promotion gate may
# also be pointed at a different PCB via the TEMPER_CLOSURE_PCB
# env var (which the test still supports).
_DEFAULT_PCB = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "pcb"
    / "temper.kicad_pcb"
)


def _read_baseline() -> dict[str, Any]:
    """Load the committed pre-U1 baseline fixture."""
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def _resolve_pcb_path() -> Path:
    """Resolve the candidate PCB path from env or default."""
    override = os.environ.get("TEMPER_CLOSURE_PCB")
    if override:
        return Path(override)
    return _DEFAULT_PCB


@dataclass
class CandidateClosure:
    """The candidate-branch closure result, populated by the promotion gate."""

    router_completion_pct: float = 0.0
    drc_clearance_pass_pct: float = 100.0
    wall_clock_seconds: float = 0.0
    ghost_pads_injected: int = 0


# ---------------------------------------------------------------------------
# U5b: candidate measurement via real closure runner
# ---------------------------------------------------------------------------


def _measure_candidate_closure() -> CandidateClosure:
    """Run the placer+router closure pipeline on the candidate branch.

    Shells out to ``python -m temper_placer.regression.measure_closure``
    with the resolved PCB path and parses the JSON it emits on
    stdout.  When the runner fails (missing deps, zero-results
    pipeline, etc.) the test is marked as a hard failure via
    :class:`RuntimeError` rather than silently skipped — the whole
    point of the SM1/SM2/SM6 promotion gate is to block merges
    that haven't actually exercised the pipeline.

    The runner module is resolved relative to this test file
    (``packages/temper-placer/src/temper_placer/regression/measure_closure.py``)
    so the gate works from any working directory and from CI.
    """
    runner_module = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "temper_placer"
        / "regression"
        / "measure_closure.py"
    )
    if not runner_module.exists():
        raise RuntimeError(
            f"closure runner module not found at {runner_module}; "
            f"the U5b promotion gate cannot run without it"
        )
    pcb_path = _resolve_pcb_path()
    if not pcb_path.exists():
        raise RuntimeError(
            f"closure PCB path does not exist: {pcb_path}.  "
            f"Set TEMPER_CLOSURE_PCB to a parseable .kicad_pcb."
        )
    # Find a Python interpreter.  Prefer the current ``sys.executable``
    # so the gate uses the same venv as the test runner.
    python = sys.executable or shutil.which("python3") or "python3"
    proc = subprocess.run(
        [python, str(runner_module), str(pcb_path)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"closure runner exited with {proc.returncode}: "
            f"stderr={proc.stderr.strip()!r}, "
            f"stdout={proc.stdout.strip()!r}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"closure runner emitted non-JSON output: {e}; "
            f"stdout={proc.stdout!r}"
        ) from e
    return CandidateClosure(
        router_completion_pct=float(payload.get("router_completion_pct", 0.0)),
        drc_clearance_pass_pct=float(payload.get("drc_clearance_pass_pct", 0.0)),
        wall_clock_seconds=float(payload.get("wall_clock_seconds", 0.0)),
        ghost_pads_injected=int(payload.get("ghost_pads_injected", 0)),
    )


# ---------------------------------------------------------------------------
# U5a: pre-change baseline record
# ---------------------------------------------------------------------------


class TestPreChangeBaseline:
    """U5a: baseline must be present and well-formed."""

    def test_closure_pre_change_baseline_recorded(self):
        """The committed baseline fixture must exist and be valid."""
        assert _FIXTURE_PATH.exists(), (
            f"Missing baseline fixture: {_FIXTURE_PATH}.  "
            f"Run U5a on main to record the pre-U1 numbers."
        )
        baseline = _read_baseline()
        # Required fields
        for required in (
            "router_completion_pct",
            "drc_clearance_pass_pct",
            "wall_clock_seconds",
            "captured_at",
            "captured_on_branch",
            "ghost_pad_injection",
        ):
            assert required in baseline, f"Baseline missing field: {required}"
        # Sanity ranges
        assert 0.0 <= baseline["router_completion_pct"] <= 100.0
        assert 0.0 <= baseline["drc_clearance_pass_pct"] <= 100.0
        assert baseline["wall_clock_seconds"] > 0.0
        # Pre-U1 must have ghost_pad_injection=False
        assert baseline["ghost_pad_injection"] is False, (
            "Baseline must be pre-U1 (ghost_pad_injection=False)"
        )
        # Fixture's commit timestamp must predate the merge of U1.
        # We don't have a clean way to compare dates here, so we
        # assert the recorded branch is "main" (the merge-base).
        assert baseline["captured_on_branch"] == "main"


# ---------------------------------------------------------------------------
# U5b: post-change promotion gate
# ---------------------------------------------------------------------------


def _measure_candidate_closure() -> CandidateClosure:
    """Run the placer+router closure pipeline on the candidate branch.

    Shells out to ``python -m temper_placer.regression.measure_closure``
    with the resolved PCB path and parses the JSON it emits on
    stdout.  When the runner fails (missing deps, zero-results
    pipeline, etc.) the test is marked as a hard failure via
    :class:`RuntimeError` rather than silently skipped — the whole
    point of the SM1/SM2/SM6 promotion gate is to block merges
    that haven't actually exercised the pipeline.
    """
    runner_module = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "temper_placer"
        / "regression"
        / "measure_closure.py"
    )
    if not runner_module.exists():
        raise RuntimeError(
            f"closure runner module not found at {runner_module}; "
            f"the U5b promotion gate cannot run without it"
        )
    pcb_path = _resolve_pcb_path()
    if not pcb_path.exists():
        raise RuntimeError(
            f"closure PCB path does not exist: {pcb_path}.  "
            f"Set TEMPER_CLOSURE_PCB to a parseable .kicad_pcb."
        )
    python = sys.executable or shutil.which("python3") or "python3"
    proc = subprocess.run(
        [python, str(runner_module), str(pcb_path)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"closure runner exited with {proc.returncode}: "
            f"stderr={proc.stderr.strip()!r}, "
            f"stdout={proc.stdout.strip()!r}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"closure runner emitted non-JSON output: {e}; "
            f"stdout={proc.stdout!r}"
        ) from e
    return CandidateClosure(
        router_completion_pct=float(payload.get("router_completion_pct", 0.0)),
        drc_clearance_pass_pct=float(payload.get("drc_clearance_pass_pct", 0.0)),
        wall_clock_seconds=float(payload.get("wall_clock_seconds", 0.0)),
        ghost_pads_injected=int(payload.get("ghost_pads_injected", 0)),
    )


class TestPostChangePromotionGate:
    """U5b: candidate branch must clear SM1/SM2/SM6 against the baseline.

    Each gate test fails loudly on a missing or zero-results
    measurement — there is no longer a "CI-only" escape hatch that
    silently passes when the runner is unavailable.  A gate that
    cannot run is by definition a gate that cannot promote.
    """

    def test_closure_post_change_meets_sm1(self):
        """SM1: candidate router_completion_pct ≥ 90% AND ≥ baseline."""
        baseline = _read_baseline()
        candidate = _measure_candidate_closure()
        target = 90.0
        assert candidate.router_completion_pct > 0.0, (
            "SM1: candidate router_completion_pct is 0.0 — the closure "
            "runner either failed or produced no routing results.  "
            "Investigate the runner output before re-running."
        )
        assert candidate.router_completion_pct >= target, (
            f"SM1 fail: candidate {candidate.router_completion_pct:.1f}% "
            f"< target {target:.1f}%"
        )
        assert candidate.router_completion_pct >= baseline["router_completion_pct"], (
            f"SM1 fail: candidate {candidate.router_completion_pct:.1f}% "
            f"< baseline {baseline['router_completion_pct']:.1f}%"
        )

    def test_closure_post_change_meets_sm2(self):
        """SM2: candidate DRC clearance pass rate ≥ 96.7% AND ≥ baseline."""
        baseline = _read_baseline()
        candidate = _measure_candidate_closure()
        target = 96.7
        assert candidate.drc_clearance_pass_pct > 0.0, (
            "SM2: candidate drc_clearance_pass_pct is 0.0 — the closure "
            "runner did not exercise the DRC step.  Investigate the "
            "runner output (kicad-cli availability) before re-running."
        )
        assert candidate.drc_clearance_pass_pct >= target, (
            f"SM2 fail: candidate {candidate.drc_clearance_pass_pct:.1f}% "
            f"< target {target:.1f}%"
        )
        assert candidate.drc_clearance_pass_pct >= baseline["drc_clearance_pass_pct"], (
            f"SM2 fail: candidate {candidate.drc_clearance_pass_pct:.1f}% "
            f"< baseline {baseline['drc_clearance_pass_pct']:.1f}%"
        )

    def test_closure_post_change_meets_sm6(self):
        """SM6: candidate wall time ≤ 105% of baseline wall time."""
        baseline = _read_baseline()
        candidate = _measure_candidate_closure()
        ceiling = baseline["wall_clock_seconds"] * 1.05
        assert candidate.wall_clock_seconds > 0.0, (
            "SM6: candidate wall_clock_seconds is 0.0 — the closure "
            "runner did not measure wall time.  Investigate the "
            "runner output before re-running."
        )
        assert candidate.wall_clock_seconds <= ceiling, (
            f"SM6 fail: candidate {candidate.wall_clock_seconds:.2f}s "
            f"> ceiling {ceiling:.2f}s (105% of baseline "
            f"{baseline['wall_clock_seconds']:.2f}s)"
        )
