#!/usr/bin/env python3
"""Run the BLOCKER-ORTOOLS equivalence harness with Pumpkin added as a second
``Engine`` (docs/evidence/2026-08-07-cpsat-equivalence-harness.md Sec 5's
checklist item), alongside the OR-Tools baseline the harness already covers.

# provenance: commit=1e932217b9ee74e4b7b56a48e0f61b2caeaf05c8 dirty=false

This file does NOT modify ``2026-08-07-cpsat-equivalence-harness.py`` --
per the harness doc, ``Engine`` is the only integration point, so this
companion imports the harness module unchanged (verifier, corpus builders,
``run_differential`` all untouched) and adds ``PumpkinEngine``.

``PumpkinEngine.solve()`` shells out to the standalone Rust binary at
``docs/evidence/2026-08-07-pumpkin-engine/`` (built separately with
``cargo build --release``; see that crate's module doc for the model
encoding). The wire format is a single JSON object on stdin / stdout --
see ``ModelSpec`` / the output shape in ``pumpkin_engine/src/main.rs``.

Usage:
    (cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release)
    uv run --no-sync python docs/evidence/2026-08-07-pumpkin-equivalence-run.py [--quick]

Writes ``docs/evidence/2026-08-07-pumpkin-equivalence-summary.json``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = Path(__file__).resolve().parent / "2026-08-07-cpsat-equivalence-harness.py"
PUMPKIN_BIN = REPO_ROOT / "docs" / "evidence" / "2026-08-07-pumpkin-engine" / "target" / "release" / "pumpkin_engine"

spec = importlib.util.spec_from_file_location("cpsat_equivalence_harness", HARNESS_PATH)
assert spec is not None and spec.loader is not None
harness = importlib.util.module_from_spec(spec)
# Register under its own name before exec: the harness module defines
# @dataclass classes, and dataclass's field-type resolution looks up
# `sys.modules[cls.__module__]` -- an unregistered module makes that a
# silent `None`, which crashes instantiation.
sys.modules["cpsat_equivalence_harness"] = harness
sys.path.insert(0, str(HARNESS_PATH.parent))
spec.loader.exec_module(harness)

PLACER_SRC = REPO_ROOT / "packages" / "temper-placer" / "src"
if str(PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(PLACER_SRC))
from temper_placer.placer.cp_sat._encoder_solve import _POLARIZED_REFS  # noqa: E402


def _serialize_model(model: "harness.CorpusModel") -> dict[str, Any]:
    """PlacementModel + minimize_displacement_to -> the pumpkin_engine wire
    format. Built from ``model.verification_model`` -- the SAME independent
    PlacementModel the harness's own IndependentVerifier checks against
    (already includes the auto-generated courtyard-tau SEPARATED pairs via
    ``build_courtyard_constraints``) -- so the Pumpkin model and the
    verifier's ground truth are, by construction, checking the same
    constraint set OR-Tools was given.
    """
    vm = model.verification_model
    components = {
        ref: {
            "w0_mm": w0,
            "h0_mm": h0,
            "rotatable": ref not in _POLARIZED_REFS,
        }
        for ref, (w0, h0) in vm.sizes_mm.items()
    }
    constraints = [c.to_dict() for c in vm.constraints]
    minimize_displacement_to = None
    if model.minimize_displacement_to:
        minimize_displacement_to = {
            ref: [float(x), float(y)] for ref, (x, y) in model.minimize_displacement_to.items()
        }
    return {
        "board_w_mm": vm.board_w_mm,
        "board_h_mm": vm.board_h_mm,
        "edge_margin_mm": vm.edge_margin_mm,
        "components": components,
        "zones": {name: list(bounds) for name, bounds in vm.zones.items()},
        "zone_components": vm.zone_components,
        "loop_components": vm.loop_components,
        "constraints": constraints,
        "minimize_displacement_to": minimize_displacement_to,
    }


class PumpkinEngine:
    """Implements the harness's ``Engine`` protocol (docs/evidence/2026-08-07-
    cpsat-equivalence-harness.py's ``Engine`` Protocol: ``name`` + ``solve()``
    returning a ``SolveOutcome``). The only integration point -- nothing in
    the verifier, corpus, or ``run_differential`` changes.
    """

    name = "pumpkin-solver-0.5.0"

    def __init__(self, binary: Path = PUMPKIN_BIN) -> None:
        if not binary.exists():
            raise FileNotFoundError(
                f"pumpkin_engine binary not found at {binary}; build it first with "
                f"`cargo build --release` in docs/evidence/2026-08-07-pumpkin-engine/"
            )
        self.binary = binary
        # num_workers is meaningless for Pumpkin (single-threaded solver; no
        # analogue of CP-SAT's num_search_workers exists in its public API --
        # verified against pumpkin-core 0.5.0's Solver/SolverOptions surface).
        # It is accepted (the Engine protocol requires the parameter) but has
        # no effect: every (seed, workers) group is therefore a genuine
        # repeated measurement of the SAME configuration, which is honest
        # (not cached/faked) and incidentally gives Tier 4 data for free.

    def solve(self, spec_model: "harness.CorpusModel", *, seed: int, timeout_ms: int, num_workers: int) -> "harness.SolveOutcome":
        payload = _serialize_model(spec_model)
        payload["seed"] = seed
        payload["timeout_ms"] = timeout_ms

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [str(self.binary)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=(timeout_ms / 1000.0) + 15.0,  # generous safety margin over the solver's own TimeBudget
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - t0) * 1000.0
            return harness.SolveOutcome(
                engine=self.name,
                config={"seed": seed, "num_workers": num_workers, "timeout_ms": timeout_ms},
                status="unknown",
                positions={},
                rotations={},
                objective_value=0.0,
                solve_time_ms=elapsed,
            )
        elapsed = (time.monotonic() - t0) * 1000.0
        if proc.returncode != 0:
            raise RuntimeError(
                f"pumpkin_engine exited {proc.returncode} for model={spec_model.name} seed={seed}: "
                f"stderr={proc.stderr[-2000:]!r}"
            )
        out = json.loads(proc.stdout)
        positions = {ref: tuple(xy) for ref, xy in out["positions"].items()}
        return harness.SolveOutcome(
            engine=self.name,
            config={"seed": seed, "num_workers": num_workers, "timeout_ms": timeout_ms},
            status=out["status"],
            positions=positions,
            rotations=dict(out["rotations"]),
            objective_value=float(out["objective_value"]),
            solve_time_ms=elapsed,
        )


def main() -> None:
    quick = "--quick" in sys.argv

    corpora = [harness.build_small_corpus(), harness.build_medium_corpus()]
    full = harness.build_full_board_corpus()
    if full is not None:
        corpora.append(full)
    else:
        print("[warn] corpus-fixture-33c unavailable; skipping", file=sys.stderr)

    engines: list[Any] = [harness.OrToolsEngine(), PumpkinEngine()]
    seeds = [0, 1, 7] if not quick else [0]
    worker_counts = [1, 4, 8] if not quick else [1]
    reports = []
    for model in corpora:
        # Model name updated 2026-08-11 (docs/evidence/2026-08-07-cpsat-equivalence-harness.py's
        # build_full_board_corpus() now names it "corpus-fixture-33c", not
        # "full-board" -- it was never the real board; see that function's
        # own docstring). Matched here so a re-run of this script still
        # picks the right timeout instead of silently falling through to 5s.
        timeout_ms = 30_000 if model.name == "corpus-fixture-33c" else 5_000
        repeats = 2 if not quick else 1
        print(
            f"=== {model.name}: {len(model.verification_model.sizes_mm)} components, "
            f"{len(model.verification_model.constraints)} constraints ==="
        )
        report = harness.run_differential(
            model, engines, seeds, worker_counts, repeats=repeats, timeout_ms=timeout_ms
        )
        reports.append(report)
        print(
            f"  feasibility_parity={report.feasibility_parity} status_set={report.status_set} "
            f"objective_parity={report.objective_parity} spread={report.objective_spread} "
            f"membership_rate={report.membership_rate:.3f} "
            f"determinism_rate={report.determinism_rate} ({report.determinism_groups} groups)"
        )
        if report.membership_fail_examples:
            for ex in report.membership_fail_examples:
                print(f"    MEMBERSHIP FAIL: {ex}")
        # Per-engine breakdown (the harness's own report pools all engines
        # together; this is the part specific to a 2-engine differential --
        # feasibility/status per engine, so a Pumpkin-only failure is
        # distinguishable from an OR-Tools-only one).
        per_engine: dict[str, list[dict]] = {}
        for run in report.runs:
            per_engine.setdefault(run["engine"], []).append(run)
        for eng, runs in per_engine.items():
            statuses = sorted({r["status"] for r in runs})
            verified = [r for r in runs if "verified" in r]
            vrate = (sum(1 for r in verified if r["verified"]) / len(verified)) if verified else float("nan")
            print(f"    [{eng}] n={len(runs)} status_set={statuses} membership_rate={vrate:.3f}")

    out_path = Path(__file__).parent / "2026-08-07-pumpkin-equivalence-summary.json"
    payload = {
        "provenance": {"commit": "1e932217b9ee74e4b7b56a48e0f61b2caeaf05c8", "dirty": False},
        "generated_by": Path(__file__).name,
        "engines": [e.name for e in engines],
        "seeds": seeds,
        "worker_counts": worker_counts,
        "quick": quick,
        "models": [
            {
                "name": r.name,
                "n_components": r.n_components,
                "n_constraints": r.n_constraints,
                "feasibility_parity": r.feasibility_parity,
                "status_set": r.status_set,
                "objective_parity": r.objective_parity,
                "objective_spread": r.objective_spread,
                "membership_rate": r.membership_rate,
                "membership_fail_examples": r.membership_fail_examples,
                "determinism_rate": r.determinism_rate,
                "determinism_groups": r.determinism_groups,
                "runs": r.runs,
            }
            for r in reports
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
