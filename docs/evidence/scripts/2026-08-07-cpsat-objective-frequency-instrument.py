#!/usr/bin/env python3
"""Instrument every real CP-SAT solve invocation and count objective-posting
vs. objective-free solves across a realistic run, for
``docs/evidence/2026-08-07-cpsat-objective-frequency.md``.

# provenance: commit=<filled in at run time, see the doc's Sec 1>

This does NOT change any production module. It monkeypatches three points,
all read-only observation hooks (record-then-call-through), matching the
measurement-hook discipline the equivalence harness already uses (scoped
monkeypatch, restored after the run, changes nothing shipped):

1. ``_encoder_solve.solve_placement`` -- the single production entry point
   ("the single entry point consumed by PlaceRouteLoop and `temper
   optimize`", per its own docstring). Records whether
   ``minimize_displacement_to`` was passed (truthy) for every call, which is
   the only way an objective reaches this path (Sec 2 of the doc traces
   ``apply_objective``/``Minimize`` and finds this is the only producer).
2. ``model.PlacementModel.solve`` -- the lower-level direct-model path used
   by encoder-level unit tests (not by any production caller -- no
   production module calls ``PlacementModel().solve()`` directly; see the
   doc's Sec 1 call-site census). Recorded separately so it is not conflated
   with the production path.
3. ``unsat.py``'s UNSAT-core re-solve (``new_solver.Solve(test_model)``) --
   always objective-free by construction (MUS refinement over a cloned
   proto), counted for completeness so the "total solves" denominator in
   the doc's whole-suite run is exact, not just the two objective-capable
   paths' sum.

Usage (from ``packages/temper-placer/``, needs built pyo3 extensions --
``make extensions`` from repo root first):

    uv run --no-sync python ../../docs/evidence/scripts/2026-08-07-cpsat-objective-frequency-instrument.py [pytest-args...]

With no args, runs the full ``tests/placer/cp_sat/`` + ``tests/cli/`` +
``tests/router_v6/test_phase1_anti_false_zero.py`` suite (every test file
that calls ``solve_placement`` per the doc's Sec 1 grep) -- "whatever CI
exercises" for this module. Prints a summary table and writes
``docs/evidence/2026-08-07-cpsat-objective-frequency-instrument-summary.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACER_SRC = REPO_ROOT / "packages" / "temper-placer" / "src"
if str(PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(PLACER_SRC))

COUNTS = {
    "solve_placement_calls_total": 0,
    "solve_placement_with_objective": 0,
    "solve_placement_without_objective": 0,
    "model_solve_calls_total": 0,
    "model_solve_with_objective": 0,
    "model_solve_without_objective": 0,
    "unsat_resolve_calls_total": 0,
}
CALL_LOG: list[dict] = []


def _install_hooks() -> None:
    import temper_placer.placer.cp_sat as cp_sat_pkg
    from temper_placer.placer.cp_sat import _encoder_solve, encoder, model, unsat

    orig_solve_placement = _encoder_solve.solve_placement

    def patched_solve_placement(*args, **kwargs):
        has_objective = bool(kwargs.get("minimize_displacement_to"))
        COUNTS["solve_placement_calls_total"] += 1
        if has_objective:
            COUNTS["solve_placement_with_objective"] += 1
        else:
            COUNTS["solve_placement_without_objective"] += 1
        t0 = time.monotonic()
        result = orig_solve_placement(*args, **kwargs)
        CALL_LOG.append(
            {
                "path": "solve_placement",
                "has_objective": has_objective,
                "n_components": len(getattr(args[0], "components", []) or [])
                if args
                else None,
                "status": getattr(result, "status", None),
                "wall_s": round(time.monotonic() - t0, 4),
            }
        )
        return result

    _encoder_solve.solve_placement = patched_solve_placement
    # `encoder.py` and the `cp_sat` package `__init__.py` both already did
    # `from ..._encoder_solve import solve_placement` (both transitively
    # imported by the `from temper_placer.placer.cp_sat import ...` line
    # above, itself required to reach `_encoder_solve`) -- that captured the
    # ORIGINAL function object into their own namespaces before the
    # reassignment above ran, so `encoder.solve_placement` and
    # `cp_sat_pkg.solve_placement` are unaffected by patching
    # `_encoder_solve.solve_placement` alone. Every real caller resolves the
    # name through one of these three module namespaces at call time
    # (`encoder.solve_placement` for the CLI's lazy import and most test
    # helpers, `_encoder_solve.solve_placement` for clearance_repair.py's
    # top-level import evaluated AFTER this patch runs, so it needs no
    # separate patch), so all three must be reassigned for the hook to see
    # every call site.
    encoder.solve_placement = patched_solve_placement
    cp_sat_pkg.solve_placement = patched_solve_placement

    orig_model_solve = model.CpSatModel.solve

    def patched_model_solve(self, *args, **kwargs):
        has_objective = bool(self._objective_terms)
        COUNTS["model_solve_calls_total"] += 1
        if has_objective:
            COUNTS["model_solve_with_objective"] += 1
        else:
            COUNTS["model_solve_without_objective"] += 1
        return orig_model_solve(self, *args, **kwargs)

    model.CpSatModel.solve = patched_model_solve

    # unsat.py's re-solve: count via a light source-level counter instead of
    # patching a bound method on a local variable inside the function (it is
    # not a class/module attribute) -- patch cp_model.CpSolver.Solve globally
    # and use call-site attribution via the objective flag already tracked
    # on the enclosing model instead. Simpler and equally accurate: patch
    # unsat.cp.CpSolver.Solve is the same class object as model.cp_model.
    # CpSolver.Solve (both import ortools.sat.python.cp_model), so patching
    # CpSolver.Solve once, globally, at the OR-Tools level, and subtracting
    # the two already-counted paths gives the unsat-resolve count for free.
    from ortools.sat.python import cp_model as cp_model_module

    orig_cpsolver_solve = cp_model_module.CpSolver.Solve
    state = {"total": 0}

    def patched_cpsolver_solve(self, *args, **kwargs):
        state["total"] += 1
        return orig_cpsolver_solve(self, *args, **kwargs)

    cp_model_module.CpSolver.Solve = patched_cpsolver_solve
    COUNTS["_cpsolver_solve_total_ref"] = state  # resolved in main() at the end


def main() -> None:
    _install_hooks()

    import pytest

    default_targets = [
        "tests/placer/cp_sat/",
        "tests/cli/test_cp_sat_flag.py",
        "tests/cli/test_optimize_no_loop.py",
        "tests/router_v6/test_phase1_anti_false_zero.py",
    ]
    args = sys.argv[1:] or default_targets
    placer_root = REPO_ROOT / "packages" / "temper-placer"
    resolved_args = [
        str(placer_root / a) if not a.startswith("-") and not Path(a).is_absolute() else a
        for a in args
    ]

    t0 = time.monotonic()
    exit_code = pytest.main(["-q", "-x" if "-x" in args else "--tb=short", *[
        a for a in resolved_args if a != "-x"
    ]])
    wall_s = time.monotonic() - t0

    total_cpsolver = COUNTS.pop("_cpsolver_solve_total_ref")["total"]
    unsat_resolve = total_cpsolver - (
        COUNTS["solve_placement_calls_total"] + COUNTS["model_solve_calls_total"]
    )
    COUNTS["unsat_resolve_calls_total"] = max(unsat_resolve, 0)
    COUNTS["cpsolver_solve_calls_total"] = total_cpsolver
    COUNTS["pytest_exit_code"] = exit_code
    COUNTS["wall_s"] = round(wall_s, 2)

    print("\n=== objective-frequency instrumentation summary ===")
    for k, v in COUNTS.items():
        print(f"  {k}: {v}")

    total_objective_capable = (
        COUNTS["solve_placement_calls_total"] + COUNTS["model_solve_calls_total"]
    )
    total_with_obj = (
        COUNTS["solve_placement_with_objective"] + COUNTS["model_solve_with_objective"]
    )
    if total_objective_capable:
        ratio = total_with_obj / total_objective_capable
        print(
            f"\n  objective-posting ratio (solve_placement + model.solve): "
            f"{total_with_obj}/{total_objective_capable} = {ratio:.4f} "
            f"({ratio * 100:.2f}%)"
        )

    out_path = Path(__file__).resolve().parent / "2026-08-07-cpsat-objective-frequency-instrument-summary.json"
    out_path.write_text(json.dumps({"counts": COUNTS, "calls": CALL_LOG}, indent=2))
    print(f"\nWrote {out_path}")

    sys.exit(0)  # measurement script: report even if some tests failed


if __name__ == "__main__":
    main()
