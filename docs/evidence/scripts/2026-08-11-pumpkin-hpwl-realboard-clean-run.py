#!/usr/bin/env python3
"""Follow-up to 2026-08-11-pumpkin-hpwl-realboard-run.py: isolates whether
"infeasible" at real (169-component) scale is caused by the drift between
``temper_induction_cooker.yaml``'s zone/adjacency assumptions and the real,
current ``pcb/temper.kicad_pcb`` geometry (confirmed independently -- the
real board's own as-placed positions violate several of that config's own
constraints, see the companion .md doc Sec 4.0) -- or by the courtyard-
clearance packing problem itself.

Board bounds + courtyard SEPARATED only, NO PCL zone/adjacency/enclosing/
keepout constraints. This is THE real-scale, apples-to-apples measurement
the spike's verdict rests on (its .md doc Sec 4.2).

Usage:
    (cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release)
    uv run --no-sync python docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-clean-run.py

Writes ``docs/evidence/2026-08-11-pumpkin-hpwl-realboard-clean-summary.json``.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_RUN_PATH = _THIS_DIR / "2026-08-11-pumpkin-hpwl-realboard-run.py"
_run_spec = importlib.util.spec_from_file_location("pumpkin_hpwl_realboard_run", _RUN_PATH)
assert _run_spec is not None and _run_spec.loader is not None
m = importlib.util.module_from_spec(_run_spec)
sys.modules["pumpkin_hpwl_realboard_run"] = m
_run_spec.loader.exec_module(m)

OUT_PATH = _THIS_DIR / "2026-08-11-pumpkin-hpwl-realboard-clean-summary.json"


def main() -> None:
    corpus_full = m.build_real_board_corpus()
    netlist = corpus_full.netlist
    board = corpus_full.board
    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}

    tau = m.courtyard_clearance_mm(m.default_clearance_mm())
    courtyard_only = m.build_courtyard_constraints(list(refs_sizes), [], tau)  # NO PCL constraints
    vmodel = m.PlacementModel(
        board_w_mm=float(board.width), board_h_mm=float(board.height), sizes_mm=refs_sizes,
        constraints=courtyard_only, zones={}, zone_components={}, loop_components={},
    )
    corpus = m.CorpusModel(
        name="real-board-169-courtyard-only", netlist=netlist, board=board, extra_constraints=[],
        zones={}, zone_components={}, loop_components={}, minimize_displacement_to=None,
        verification_model=vmodel,
    )
    print(f"courtyard-only corpus: components={len(refs_sizes)} constraints={len(courtyard_only)} "
          f"board={board.width}x{board.height}mm", flush=True)

    hpwl_nets = m.build_hpwl_nets(netlist)
    seeds = [0, 1, 7]
    results = []

    for seed in seeds:
        r = m.run_ortools(corpus, seed, 30_000, 1, hpwl_nets=None)
        print(f"[ortools feasibility-clean] seed={seed} timeout=30000 status={r['status']} solve_ms={r['solve_time_ms']:.0f}", flush=True)
        results.append({"engine": "ortools", "mode": "feasibility-clean", "seed": seed, "timeout_ms": 30_000,
                         "status": r["status"], "solve_time_ms": r["solve_time_ms"]})

        rp = m.run_pumpkin(vmodel, None, seed, 30_000)
        print(f"[pumpkin feasibility-clean] seed={seed} timeout=30000 status={rp.get('status')} solve_ms={rp.get('solve_time_ms', 0):.0f}", flush=True)
        results.append({"engine": "pumpkin", "mode": "feasibility-clean", "seed": seed, "timeout_ms": 30_000,
                         "status": rp.get("status"), "solve_time_ms": rp.get("solve_time_ms")})

    # Independently re-verify one Pumpkin "optimal" claim from scratch
    # (never accept an engine's own say-so, per this repo's own established
    # discipline) -- re-solve seed 0 and check with the harness's own
    # IndependentVerifier.
    rp0 = m.run_pumpkin(vmodel, None, seed=0, timeout_ms=30_000)
    positions0 = {k: tuple(v) for k, v in rp0.get("positions", {}).items()}
    rotations0 = dict(rp0.get("rotations", {}))
    verifier = m.IndependentVerifier()
    vresult = verifier.verify(vmodel, positions0, rotations0)
    print(f"[independent verification] pumpkin seed=0 status={rp0.get('status')} verify_ok={vresult.ok} {vresult.summary()}", flush=True)
    results.append({"check": "independent_verification", "engine": "pumpkin", "seed": 0,
                     "status": rp0.get("status"), "verify_ok": vresult.ok, "summary": vresult.summary()})

    for timeout_ms in (5_000, 30_000):
        for seed in seeds:
            r = m.run_ortools(corpus, seed, timeout_ms, 1, hpwl_nets=hpwl_nets)
            hpwl_check = m.compute_hpwl(r["positions"], hpwl_nets)
            print(f"[ortools hpwl-clean] seed={seed} timeout={timeout_ms} status={r['status']} obj={r['objective_value']} recomputed={hpwl_check} solve_ms={r['solve_time_ms']:.0f}", flush=True)
            results.append({"engine": "ortools", "mode": "hpwl-clean", "seed": seed, "timeout_ms": timeout_ms,
                             "status": r["status"], "objective_value": r["objective_value"],
                             "recomputed_hpwl_mm": hpwl_check, "solve_time_ms": r["solve_time_ms"]})

            rp = m.run_pumpkin(vmodel, hpwl_nets, seed, timeout_ms, safety_margin_s=150.0)
            rp_positions = {k: tuple(v) for k, v in rp.get("positions", {}).items()}
            hpwl_check_p = m.compute_hpwl(rp_positions, hpwl_nets)
            print(f"[pumpkin hpwl-clean] seed={seed} timeout={timeout_ms} status={rp.get('status')} obj={rp.get('objective_value')} recomputed={hpwl_check_p} solve_ms={rp.get('solve_time_ms', 0):.0f}", flush=True)
            results.append({"engine": "pumpkin", "mode": "hpwl-clean", "seed": seed, "timeout_ms": timeout_ms,
                             "status": rp.get("status"), "objective_value": rp.get("objective_value"),
                             "recomputed_hpwl_mm": hpwl_check_p, "solve_time_ms": rp.get("solve_time_ms")})

    OUT_PATH.write_text(json.dumps({
        "n_components": len(refs_sizes), "n_constraints": len(courtyard_only), "n_hpwl_nets": len(hpwl_nets),
        "board_w_mm": board.width, "board_h_mm": board.height, "seeds": seeds, "results": results,
    }, indent=2, default=str))
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
