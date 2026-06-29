"""Routability gradient signal validation experiment.
Answers: do CaDiCaL solver statistics predict routing failures?
Run:  uv run python packages/temper-placer/src/temper_placer/experiments/routability_signal_validation.py --pcb <path>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class ComponentOutcome:
    component_idx: int
    ref: str
    routability_score: float
    nets_connected: int
    nets_failed: int
    any_failed: bool
    position: tuple[float, float]
    solver_time_ms: float


@dataclass
class BoardResult:
    board_id: str
    n_components: int
    n_nets: int
    solver_status: str
    outcomes: list[ComponentOutcome] = field(default_factory=list)
    spearman_rho: float = 0
    spearman_p: float = 1
    point_biserial_r: float = 0
    point_biserial_p: float = 1
    auc_roc: float | None = None
    auc_ci: tuple[float | None, float | None] = (None, None)
    top_k_precision: float = 0
    cohens_d: float = 0
    gradient_chi2_p: float | None = None
    gradient_odds_ratio: float | None = None
    score_mean_failed: float = 0
    score_mean_routed: float = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class ExperimentReport:
    board_results: list[BoardResult]
    total_components: int
    total_boards: int
    pooled_spearman_rho: float = 0
    pooled_spearman_ci: tuple[float, float] = (0, 0)
    pooled_auc_roc: float | None = None
    verdict: str = "DO_NOT_WIRE"
    verdict_detail: str = ""


def _scipy():
    try:
        from scipy import stats
        return stats
    except ImportError:
        return None


def _numpy_auc(scores, binary):
    desc = np.argsort(scores)[::-1]
    sl = binary[desc]
    pos = int(np.sum(binary))
    neg = len(binary) - pos
    if pos == 0 or neg == 0:
        return 0.5
    return float(np.trapz(np.cumsum(sl) / pos, np.cumsum(1 - sl) / neg))


def extract_stats(rust_result):
    s = rust_result.get("solver_stats", {})
    if s:
        return dict(s)
    return {
        "conflicts": 0,
        "decisions": 0,
        "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "cpu_solve_time_ms": rust_result.get("solver_time_ms", 0),
        "clause_to_var_ratio": rust_result.get("num_clauses", 0) / max(rust_result.get("num_vars", 1), 1),
        "variable_count": rust_result.get("num_vars", 0),
    }


def compute_scores(stats, var_to_net, n_components, unsat_core=None, solver_status="unknown"):
    if n_components == 0:
        return np.zeros(0)
    n_nets = max((n for n in var_to_net if n != 0xFFFFFFFFFFFFFFFF), default=0) + 1 if var_to_net else n_components
    if solver_status == "unsat" and unsat_core:
        pn = np.zeros(n_nets)
        for idx in unsat_core:
            if idx < len(var_to_net) and var_to_net[idx] < n_nets:
                pn[var_to_net[idx]] = 1.0
    elif solver_status == "unsat" and not unsat_core:
        pn = np.ones(n_nets)
    elif stats.get("conflicts", 0) > 0 or stats.get("decisions", 0) > 0:
        counts = np.bincount([n for n in var_to_net if 0 <= n < n_nets], minlength=n_nets).astype(float)
        pn = np.clip(0.3 * counts / max(n_nets, 1) + 0.2 * counts / max(np.max(counts), 1), 0, 1)
    else:
        ratio = stats.get("clause_to_var_ratio", 0)
        t = stats.get("cpu_solve_time_ms", 0)
        counts = np.bincount([n for n in var_to_net if 0 <= n < n_nets], minlength=n_nets).astype(float)
        pn = np.clip((ratio / 10.0) * counts / max(stats.get("variable_count", 1), 1), 0, 1) * min(t / 500.0, 1)
    pc = pn[:n_components] if len(pn) >= n_components else np.pad(pn, (0, n_components - len(pn)))
    return np.clip(pc, 0, 1)


def _spearman(scores, target):
    s = _scipy()
    if not s or len(scores) < 3 or np.all(scores == scores[0]) or np.all(target == target[0]):
        return (0.0, 1.0)
    return tuple(map(float, s.spearmanr(scores, target)))


def _point_biserial(scores, binary):
    s = _scipy()
    if not s or len(scores) < 3 or np.all(scores == scores[0]) or np.all(binary == binary[0]):
        return (0.0, 1.0)
    return tuple(map(float, s.pointbiserialr(binary, scores)))


def _auc(scores, binary):
    if len(scores) < 5:
        return None, None, None
    pos = int(np.sum(binary))
    neg = len(binary) - pos
    if pos == 0 or neg == 0:
        return None, None, None
    auc = _numpy_auc(scores, binary)
    q1 = auc / (2 - auc) if auc < 1 else 1.0
    q2 = 2 * auc * auc / (1 + auc) if auc > 0 else 0
    se = np.sqrt((auc * (1 - auc) + (pos - 1) * (q1 - auc * auc) + (neg - 1) * (q2 - auc * auc)) / (pos * neg))
    se = max(se, 1e-10)
    return auc, max(0, auc - 1.96 * se), min(1, auc + 1.96 * se)


def _fisher_z(rs, ns):
    v = [(r, n) for r, n in zip(rs, ns) if n > 3 and -1 < r < 1]
    if not v:
        return 0.0, (0.0, 0.0)
    zs = [np.arctanh(r) for r, _ in v]
    ws = [n for _, n in v]
    pz = np.average(zs, weights=ws)
    pr = np.tanh(pz)
    se = 1.0 / np.sqrt(sum(ws) - 3 * len(v))
    return float(pr), (float(pr - 1.96 * se), float(pr + 1.96 * se))


def run_single_board(pcb_path, repo_root, score_threshold=0.5, proximity_mm=5.0):  # noqa: ARG001
    bid = pcb_path.stem
    try:
        from temper_rust_router import solve_topology_rust

        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.router_v6.constraint_model import ModelBuilder
        from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
    except Exception as e:
        return BoardResult(board_id=bid, n_components=0, notes=[f"Import: {e}"])
    try:
        parsed = parse_kicad_pcb_v6(str(pcb_path))
        if not parsed or not hasattr(parsed, "components"):
            return None
    except Exception:
        return None
    pcb = parsed
    nc = len(pcb.components)
    if nc == 0:
        return None
    refs = [c.name if hasattr(c, "name") else f"C{i}" for i, c in enumerate(pcb.components)]
    positions = np.array([
        (c.initial_position or (0, 0)) if hasattr(c, "initial_position") else (0, 0)
        for c in pcb.components
    ])
    net_names = [n.name for n in pcb.nets]
    try:
        dp = infer_differential_pairs(net_names)
        mb = ModelBuilder(
            skeletons={},
            nets=pcb.nets,
            channel_widths={},
            design_rules=getattr(pcb, "design_rules", None),
            diff_pairs=dp,
            pcb=pcb,
        )
        cm = mb.build()
        rr = solve_topology_rust(list(cm.variables), list(cm.constraints), net_names)
        st = rr.get("status", "unknown")
    except Exception:
        rr = {"status": "unknown", "solver_time_ms": 0}
    stats = extract_stats(rr)
    vtn = rr.get("var_to_net") or [0] * len(net_names)
    scores = compute_scores(stats, vtn, nc, unsat_core=rr.get("unsat_core", []), solver_status=st)
    outcomes = []
    try:
        pipe = RouterV6Pipeline(verbose=False, skip_stage3=False, max_sat_nets=None)
        pipeline_result = pipe.run(str(pcb_path))
        if hasattr(pipeline_result, "routing_outcomes"):
            routing_outcomes = pipeline_result.routing_outcomes
        elif hasattr(pipeline_result, "stage4_result"):
            routing_outcomes = getattr(pipeline_result.stage4_result, "routing_outcomes", {})
        else:
            routing_outcomes = {}
    except Exception:
        routing_outcomes = {}
    for i, comp in enumerate(pcb.components):
        nets = [p.net for p in getattr(comp, "pins", []) if hasattr(p, "net") and p.net]
        nf = sum(1 for n in nets if not routing_outcomes.get(n, True))
        outcomes.append(ComponentOutcome(
            component_idx=i,
            ref=refs[i] if i < len(refs) else f"C{i}",
            routability_score=float(scores[i]) if i < len(scores) else 0,
            nets_connected=len(nets),
            nets_failed=nf,
            any_failed=nf > 0,
            position=tuple(positions[i].tolist()),
            solver_time_ms=stats.get("cpu_solve_time_ms", 0),
        ))
    sa = np.array([o.routability_score for o in outcomes])
    ba = np.array([o.any_failed for o in outcomes]).astype(float)
    fa = np.array([o.nets_failed / max(o.nets_connected, 1) for o in outcomes])
    sr, sp = _spearman(sa, fa)
    pb, pp = _point_biserial(sa, ba)
    auc, alo, ahi = _auc(sa, ba)
    tk = float(np.mean(ba[np.argsort(sa)[-5:]])) if len(sa) >= 5 and np.sum(ba) > 0 else 0.0
    fv = sa[ba > 0]
    rv = sa[ba == 0]
    cd = float((np.mean(fv) - np.mean(rv)) / max(np.std(sa, ddof=1), 1e-10)) if len(fv) > 1 and len(rv) > 1 else 0
    mf = float(np.mean(fv)) if len(fv) > 0 else 0
    mr = float(np.mean(rv)) if len(rv) > 0 else 0
    return BoardResult(
        board_id=bid,
        n_components=nc,
        n_nets=len(net_names),
        solver_status=st,
        outcomes=outcomes,
        spearman_rho=sr,
        spearman_p=sp,
        point_biserial_r=pb,
        point_biserial_p=pp,
        auc_roc=auc,
        auc_ci=(alo, ahi),
        top_k_precision=tk,
        cohens_d=cd,
        score_mean_failed=mf,
        score_mean_routed=mr,
    )


def run_experiment(pcb_paths, repo_root, score_threshold=0.5, proximity_mm=5.0):
    results = []
    for p in pcb_paths:
        if not p.exists():
            continue
        print(f"  {p.name} ...", end=" ", flush=True)
        br = run_single_board(p, repo_root, score_threshold, proximity_mm)
        if br is None:
            print("SKIP")
            continue
        results.append(br)
        print(f"{br.n_components}c, rho={br.spearman_rho:.3f} (p={br.spearman_p:.3f}) {'OK' if br.spearman_p < 0.05 else 'X'}")
    if not results:
        return ExperimentReport(board_results=[], total_components=0, total_boards=0)
    pr, pci = _fisher_z([r.spearman_rho for r in results], [r.n_components for r in results])
    ars = [(r.auc_roc, r.n_components) for r in results if r.auc_roc is not None]
    if ars:
        para, paci = _fisher_z([a for a, _ in ars], [n for _, n in ars])
    else:
        para, paci = None, (None, None)
    gates = {
        "predictive": pr >= 0.30 and pci[0] > 0,
        "discriminative": para is not None and para >= 0.65 and (paci[0] or 0) > 0.50,
    }
    passed = sum(gates.values())
    v = "WIRE" if passed == 2 else ("BORDERLINE" if passed == 1 else "DO_NOT_WIRE")

    def fm(x):
        return f"{x:.3f}" if x is not None else "N/A"

    return ExperimentReport(
        board_results=results,
        total_components=sum(r.n_components for r in results),
        total_boards=len(results),
        pooled_spearman_rho=pr,
        pooled_spearman_ci=pci,
        pooled_auc_roc=para,
        verdict=v,
        verdict_detail=f"rho={fm(pr)} CI=({fm(pci[0])},{fm(pci[1])}), AUC={fm(para)}, gates={gates}",
    )


def cli_main():
    ap = argparse.ArgumentParser(description="Routability gradient signal validation")
    ap.add_argument("--pcb", type=str, action="append", default=[], help="PCB file (repeatable)")
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--score-threshold", type=float, default=0.5)
    ap.add_argument("--proximity-mm", type=float, default=5.0)
    ap.add_argument("--output", type=str, default=None)
    ap.add_argument("--repo-root", type=str, default=None)
    args = ap.parse_args()
    repo = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[4]
    paths = [Path(p) for p in args.pcb]
    if args.corpus:
        m = repo / "power_pcb_dataset" / "manifest.yaml"
        if m.exists():
            import yaml
            with open(m) as f:
                data = yaml.safe_load(f) or {}
            for e in data.get("entries", data.get("boards", [])):
                paths.append(repo / "power_pcb_dataset" / e.get("pcb", ""))
    if args.golden:
        gm = repo / "power_pcb_dataset" / "golden_manifest.yaml"
        if gm.exists():
            import yaml
            with open(gm) as f:
                data = yaml.safe_load(f) or {}
            for e in data.get("boards", []):
                if e.get("path"):
                    paths.append(repo / e["path"])
    if not paths:
        ap.error("Provide --pcb, --corpus, or --golden")
    print(f"Routability signal validation -- {len(paths)} board(s)")
    report = run_experiment(paths, repo, args.score_threshold, args.proximity_mm)
    print(f"\nVerdict: {report.verdict}\n  {report.verdict_detail}")
    if args.output:
        out = {
            "verdict": report.verdict,
            "verdict_detail": report.verdict_detail,
            "pooled_spearman_rho": report.pooled_spearman_rho,
            "pooled_spearman_ci": list(report.pooled_spearman_ci),
            "pooled_auc_roc": report.pooled_auc_roc,
            "total_components": report.total_components,
            "total_boards": report.total_boards,
            "board_results": [
                {
                    "board_id": r.board_id,
                    "n_components": r.n_components,
                    "spearman_rho": r.spearman_rho,
                    "spearman_p": r.spearman_p,
                    "auc_roc": r.auc_roc,
                    "top_k_precision": r.top_k_precision,
                    "score_mean_failed": r.score_mean_failed,
                    "score_mean_routed": r.score_mean_routed,
                    "notes": r.notes,
                }
                for r in report.board_results
            ],
        }
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2)
        print(f"Report: {args.output}")


if __name__ == "__main__":
    cli_main()
