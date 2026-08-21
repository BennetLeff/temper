#!/usr/bin/env python3
"""Measure Stage 3 model size vs net count (2026-08-15 investigation).

Three measurements in one process (Stage 2 runs once, both ModelBuilder
arms share its output):

1. Skeleton edge count on the CURRENT board (origin/main) -- the |nets| x
   |edges| term's E. 20K vs 204K edges is the difference between a
   42M/78M-clause CNF that fits (~7 GB) and a ~770M-clause CNF that needs
   ~182-200 GB (docs/plans/2026-08-12-004, MEASURED per-clause costs).
2. FULL model: ModelBuilder.build() over all nets -- raw (pre-CNF)
   variable/constraint counts and peak RSS. Solve is NOT attempted: the
   full-board CNF does not fit this machine (deliberately).
3. SINGLE-NET model: ModelBuilder.build() + solve_topology_rust over a
   one-net subset -- the handoff's net-filtering hypothesis: if the
   dominant term is |nets| x |edges|, collapsing nets 110->1 must
   collapse the model ~110x and the CNF entirely (Sinz AtMostK fires only
   when max_nets < n_terms; n_terms=1 never fires it).

Caveat: escape_vias=[] (real pipeline feeds Stage-1 escape vias into the
obstacle map). Fine for sizing (10x-scale distinctions), not byte-exact.

Usage:
    .venv/bin/python docs/evidence/scripts/2026-08-15-stage2-skeleton-probe.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6  # noqa: E402
from temper_placer.io.netclass_loader import load_netclass_rules  # noqa: E402
from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs  # noqa: E402
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator  # noqa: E402
from temper_placer.router_v6.constraint_model import ModelBuilder  # noqa: E402


def rss_kb() -> int:
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        return -1
    return -1


def main() -> int:
    t0 = time.perf_counter()
    pcb_path = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    rules = load_netclass_rules(REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml")
    pcb = parse_kicad_pcb_v6(pcb_path)
    nets = pcb.nets
    print(f"[probe] parsed {pcb_path.name}: {len(nets)} nets "
          f"({time.perf_counter() - t0:.1f}s, rss_kb={rss_kb():,d})")

    orch = Stage2Orchestrator(verbose=False)
    t1 = time.perf_counter()
    state = orch.run(pcb, [])
    print(f"[probe] stage2 done in {time.perf_counter() - t1:.1f}s, "
          f"rss_kb={rss_kb():,d}")

    total_edges = 0
    total_nodes = 0
    skeletons = state.channel_skeletons or {}
    for layer, sk in sorted(skeletons.items()):
        n_nodes = len(sk.graph.nodes)
        n_edges = len(sk.graph.edges)
        total_edges += n_edges
        total_nodes += n_nodes
        print(f"[probe] skeleton {layer}: {n_nodes:,d} nodes / {n_edges:,d} edges")
    print(f"[probe] TOTAL skeleton edges: {total_edges:,d}")
    print(f"[probe] |nets| x |edges| = {len(nets):,d} x {total_edges:,d} = "
          f"{len(nets) * total_edges:,d} raw NetChannelVars (unpruned, unbundled)")

    channel_widths = state.channel_widths or {}
    design_rules = rules.design_rules
    diff_pairs = infer_differential_pairs([n.name for n in nets])

    # --- ARM 2: full model (build only, no solve) ---
    t2 = time.perf_counter()
    print(f"[probe] ModelBuilder.build() FULL ({len(nets)} nets) ...", flush=True)
    mb_full = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=channel_widths,
        design_rules=design_rules,
        diff_pairs=diff_pairs,
        pcb=pcb,
    )
    model_full = mb_full.build()
    print(f"[probe] FULL model built in {time.perf_counter() - t2:.1f}s: "
          f"vars={model_full.variable_count:,d} cons={model_full.constraint_count:,d} "
          f"rss_kb={rss_kb():,d} (solve NOT attempted)", flush=True)
    del mb_full, model_full

    # --- ARM 3: single-net model (build + solve) ---
    one = nets[0]
    print(f"[probe] ModelBuilder.build() SINGLE-NET ({one.name!r}) ...", flush=True)
    t3 = time.perf_counter()
    mb_one = ModelBuilder(
        skeletons=skeletons,
        nets=[one],
        channel_widths=channel_widths,
        design_rules=design_rules,
        diff_pairs=[d for d in diff_pairs if d.p_net == one.name or d.n_net == one.name],
        pcb=pcb,
    )
    model_one = mb_one.build()
    print(f"[probe] SINGLE model built in {time.perf_counter() - t3:.1f}s: "
          f"vars={model_one.variable_count:,d} cons={model_one.constraint_count:,d} "
          f"rss_kb={rss_kb():,d}", flush=True)

    from temper_rust_router import solve_topology_rust

    py_vars = list(model_one.variables)
    py_cons = list(model_one.constraints)
    t4 = time.perf_counter()
    print(f"[probe] solve_topology_rust SINGLE-NET ENTER "
          f"(py_vars={len(py_vars):,d} py_cons={len(py_cons):,d})", flush=True)
    rust_result = solve_topology_rust(
        py_vars,
        py_cons,
        [one.name],
        conflict_limit=20_000,
        time_limit_ms=None,
    )
    print(f"[probe] solve_topology_rust SINGLE-NET done in "
          f"{time.perf_counter() - t4:.1f}s: status={rust_result.get('status')} "
          f"vars={rust_result.get('num_vars'):,d} clauses={rust_result.get('num_clauses'):,d} "
          f"solver_ms={rust_result.get('solver_time_ms'):.1f} rss_kb={rss_kb():,d}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
