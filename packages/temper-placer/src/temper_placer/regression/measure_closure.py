"""Closure-measurement runner for the U5b SM1/SM2/SM6 promotion gate.

Wraps :class:`temper_placer.regression.closure_test.ClosureTest` with
the conventions the promotion gate expects:

  - A single function ``measure_closure(pcb_path, baseline)`` that
    returns a dict of measurements (router completion %, DRC clearance
    pass %, wall-clock seconds, etc.).  This is the function the
    promotion gate calls.

  - A ``python -m temper_placer.regression.measure_closure`` CLI mode
    that takes a PCB path and emits JSON on stdout.  The promotion
    gate (``tests/closure/test_router_completion.py``) shells out to
    this CLI and parses the JSON, so the gate runs against a real
    pipeline result rather than a structural stub.

The runner is intentionally thin — all real work lives in
``ClosureTest.run()``.  When Benders, Router V6, or KiCad DRC are
unavailable, ``ClosureTest`` reports a zero-results failure; the
runner propagates that and exits non-zero so the promotion gate
fails loudly rather than silently passing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def measure_closure(
    pcb_path: Path,
    baseline: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
    strategy: str = "template",
) -> dict[str, Any]:
    """Run the closure pipeline and return a CandidateClosure-shaped dict.

    Args:
        pcb_path: Path to a parseable ``.kicad_pcb`` file.
        baseline: Optional baseline dict (unused by the runner itself,
            kept for forward-compat with future ceiling comparisons).
        repo_root: Repository root for ceiling lookup.  Defaults to
            ``Path.cwd()``.
        strategy: Placement strategy name forwarded to
            :class:`ClosureTest`.

    Returns:
        A dict with keys: ``router_completion_pct`` (0..100),
        ``drc_clearance_pass_pct`` (0..100), ``wall_clock_seconds``,
        ``ghost_pads_injected`` (always 0 — the runner does not
        count ghost pads; that metric is logged by the placer).
        Also includes the raw :class:`ClosureResult` summary under
        ``closure_summary`` for debugging.

    Raises:
        RuntimeError: If the closure pipeline produced zero results
            (no placement iterations AND no router completion).  This
            is the truth-gate failure mode the SM1/SM2/SM6 gate
            exists to catch.
    """
    from temper_placer.regression.closure_test import ClosureTest

    pcb_path = Path(pcb_path)
    repo_root = repo_root or Path.cwd()
    test = ClosureTest(
        pcb_path=pcb_path,
        repo_root=repo_root,
        strategy=strategy,
        require_all_stages=False,
    )
    result = test.run()

    # DRC clearance pass pct is a property of the *measurement*, not a
    # default derived from how many stages ran.  We map the 3-state
    # ``DrcStatus`` directly to a numeric or null value — the only
    # place that turns a measurement into a percentage.  An UNVERIFIED
    # result (kicad-cli missing or invocation errored) emits ``None``,
    # not 100.0, so a missing measurement cannot be misread as a
    # measured-clean result.
    from temper_placer.validation.drc_runner import DrcStatus

    match result.drc_status:
        case DrcStatus.PASS:
            drc_clearance_pass_pct: float | None = 100.0
        case DrcStatus.FAIL:
            # Defensive: avoid div-by-zero / negative; clamp to [0, 100].
            drc_clearance_pass_pct = max(0.0, 100.0 - 10.0 * result.drc_errors)
        case DrcStatus.UNVERIFIED:
            # The tool wasn't available or errored — the gate gets
            # ``None`` and the SM2 promotion test fails loudly rather
            # than silently passing on a missing measurement.
            drc_clearance_pass_pct = None
        case _:
            # ``drc_status is None`` (legacy callers or pre-U1 fixture
            # paths) — same floor as "DRC stage never ran": 0.0.
            drc_clearance_pass_pct = 0.0

    payload: dict[str, Any] = {
        "router_completion_pct": float(result.router_completion_pct),
        "drc_clearance_pass_pct": drc_clearance_pass_pct,
        "drc_status": result.drc_status.value if result.drc_status else None,
        "wall_clock_seconds": float(result.wall_clock_seconds),
        "ghost_pads_injected": 0,
        "benders_iterations": int(result.benders_iterations),
        "drc_errors": int(result.drc_errors),
        "drc_warnings": int(result.drc_warnings),
        "stages_exercised": int(result.stages_exercised),
        "passed": bool(result.passed),
        "closure_summary": result.summary(),
    }

    # Truth-gate: refuse to report a "measurement" when the pipeline
    # produced no placement AND no routing.  The promotion gate
    # relies on this signal to fail loudly instead of silently
    # passing a zero-results run.
    if (
        result.benders_iterations <= 0
        and result.router_completion_pct <= 0.0
    ):
        raise RuntimeError(
            f"closure pipeline produced zero results: "
            f"benders_iterations={result.benders_iterations}, "
            f"router_completion_pct={result.router_completion_pct:.1f}%, "
            f"stages_exercised={result.stages_exercised}, "
            f"errors={result.errors!r}"
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: measure closure and emit JSON to stdout."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the closure pipeline on a KiCad PCB and emit a JSON "
            "measurement to stdout.  Exit non-zero on zero-results."
        )
    )
    parser.add_argument(
        "pcb_path",
        type=Path,
        help="Path to a parseable .kicad_pcb file",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (for drc_ceiling.json lookup)",
    )
    parser.add_argument(
        "--strategy",
        default="template",
        help="Placement strategy name (default: template)",
    )
    args = parser.parse_args(argv)

    try:
        payload = measure_closure(
            pcb_path=args.pcb_path,
            repo_root=args.repo_root,
            strategy=args.strategy,
        )
    except Exception as e:  # noqa: BLE001 — CLI must surface every error
        sys.stderr.write(f"measure_closure failed: {e}\n")
        return 2

    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
