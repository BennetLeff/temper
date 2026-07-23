#!/usr/bin/env python3
"""CP-SAT Benchmark Runner — reads scenario YAML, runs placement, outputs JSONL."""
from __future__ import annotations
import argparse, json, sys, time
from dataclasses import dataclass, field
from pathlib import Path
import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_PLACER_ROOT = _REPO_ROOT / "packages" / "temper-placer"
_src = str(_PLACER_ROOT / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

@dataclass
class ScenarioConfig:
    name: str; description: str = ""; type: str = "synthetic"
    n_components: int = 10; board_width_mm: float = 100.0
    board_height_mm: float = 100.0; timeout_ms: int = 2000
    seeds: list[int] = field(default_factory=lambda: [42, 123, 456, 789, 1011])
    pcl_config: str = ""; components: dict = field(default_factory=dict)
    zones: dict = field(default_factory=dict)
    zone_components: dict = field(default_factory=dict)
    loop_components: dict = field(default_factory=dict)

@dataclass
class BenchmarkRecord:
    scenario: str; seed: int; status: str; solve_time_s: float
    objective_value: float = 0.0; n_components: int = 0
    placed_count: int = 0; rounds: int = 1; drc_errors: int = 0
    board_width_mm: float = 0.0; board_height_mm: float = 0.0
    timeout_ms: int = 0

def load_scenarios(d: Path) -> list[ScenarioConfig]:
    return [ScenarioConfig(**yaml.safe_load(open(f))) for f in sorted(d.glob("*.yaml"))]

class BenchmarkRunner:
    def __init__(self, scenarios_dir=None, output_dir=None, seeds=None, scenario_filter=None):
        self._scenarios_dir = scenarios_dir or (_HERE / "scenarios")
        self._output_dir = output_dir or (_HERE / "results")
        self._seeds = seeds; self._scenario_filter = scenario_filter

    def run(self) -> list[BenchmarkRecord]:
        scenarios = load_scenarios(self._scenarios_dir)
        if self._scenario_filter:
            scenarios = [s for s in scenarios if s.name == self._scenario_filter]
        records: list[BenchmarkRecord] = []
        for cfg in scenarios:
            seeds = self._seeds or cfg.seeds
            for seed in seeds:
                t0 = time.monotonic()
                try:
                    from tests.fixtures.generators.synthetic_netlist import generate_netlist
                    from temper_placer.placer.cp_sat.encoder import solve_placement
                    netlist = generate_netlist(n_components=cfg.n_components, seed=seed)
                    board = type("Board", (), {"width": cfg.board_width_mm, "height": cfg.board_height_mm, "zones": [], "constraints": None})()
                    result = solve_placement(netlist=netlist, board=board, timeout_ms=cfg.timeout_ms, seed=seed)
                    records.append(BenchmarkRecord(
                        scenario=cfg.name, seed=seed, status=result.status,
                        solve_time_s=round(time.monotonic()-t0, 4),
                        objective_value=round(result.objective_value, 4),
                        n_components=netlist.n_components,
                        placed_count=len(result.placed_refs),
                        board_width_mm=cfg.board_width_mm,
                        board_height_mm=cfg.board_height_mm, timeout_ms=cfg.timeout_ms,
                    ))
                except Exception as e:
                    records.append(BenchmarkRecord(scenario=cfg.name, seed=seed, status=f"error: {e}", solve_time_s=0.0))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out = self._output_dir / "cp_sat_metrics.jsonl"
        with open(out, "w") as f:
            for r in records:
                f.write(json.dumps({k: v for k, v in r.__dict__.items()}) + "\n")
        print(f"Wrote {len(records)} records to {out}")
        return records

def compare_baseline(pr_path, baseline_path, time_tolerance=2.0):
    if not baseline_path.exists(): return []
    baseline = {}
    with open(baseline_path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line); baseline[(r["scenario"], r["seed"])] = r
    regressions = []
    with open(pr_path) as f:
        for line in f:
            if not line.strip(): continue
            pr = json.loads(line)
            key = (pr["scenario"], pr["seed"])
            base = baseline.get(key)
            if not base: continue
            reasons = []
            rank = {"optimal": 0, "feasible": 1, "infeasible": 2, "unknown": 3}
            if rank.get(pr["status"], 3) > rank.get(base["status"], 3):
                reasons.append(f"status: {base['status']} -> {pr['status']}")
            bt, pt = float(base.get("solve_time_s", 0)), float(pr.get("solve_time_s", 0))
            if bt > 0 and pt > bt * time_tolerance:
                reasons.append(f"time: {bt:.3f}s -> {pt:.3f}s")
            bd, pd = int(base.get("drc_errors", 0)), int(pr.get("drc_errors", 0))
            if pd > bd:
                reasons.append(f"DRC: {bd} -> {pd}")
            if reasons:
                regressions.append({"scenario": pr["scenario"], "seed": pr["seed"], "reasons": reasons})
    return regressions

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario"); p.add_argument("--seeds", type=int, nargs="+")
    p.add_argument("--output", type=Path); p.add_argument("--compare", type=Path)
    args = p.parse_args()
    runner = BenchmarkRunner(output_dir=args.output, seeds=args.seeds, scenario_filter=args.scenario)
    runner.run()
    if args.compare:
        out = (args.output or _HERE / "results") / "cp_sat_metrics.jsonl"
        regs = compare_baseline(out, args.compare)
        if regs:
            for r in regs:
                print(f"  REGRESSION {r['scenario']} seed={r['seed']}: {'; '.join(r['reasons'])}")
            sys.exit(1)
        print("No regressions.")

if __name__ == "__main__":
    main()
