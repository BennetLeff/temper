#!/usr/bin/env python3
"""
Extract baseline metrics for all corpus boards.

Runs the optimizer once per board with a fixed seed/config and writes
the resulting baseline.json file. Used for initial corpus assembly and
after intentional placement quality improvements (via bless_baselines.py).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jax
import yaml


def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent.parent
    return p


def load_corpus_manifest(repo_root: Path) -> dict:
    manifest_path = repo_root / "power_pcb_dataset" / "corpus" / "manifest.yaml"
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)
    with open(manifest_path) as f:
        return yaml.safe_load(f)


def optimize_board(
    repo_root: Path,
    board_id: str,
    pcb_rel: str,
    constraints_rel: str,
    seed: int,
    epochs: int,
) -> dict | None:
    """Run optimizer on a single board and return metrics dict."""
    pcb_path = repo_root / "power_pcb_dataset" / "corpus" / pcb_rel
    constraints_path = repo_root / "power_pcb_dataset" / "corpus" / constraints_rel

    if not pcb_path.exists():
        print(f"  SKIP: PCB not found: {pcb_path}")
        return None
    if not constraints_path.exists():
        print(f"  SKIP: Constraints not found: {constraints_path}")
        return None

    print(f"  Parsing {pcb_path}...")
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.config_loader import load_constraints, create_board_from_constraints

    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    constraints = load_constraints(constraints_path)
    board = create_board_from_constraints(constraints)

    print(f"    {netlist.n_components} components, {netlist.n_nets} nets")

    from temper_placer.losses.base import LossContext, CompositeLoss, WeightedLoss
    from temper_placer.losses.overlap import OverlapLoss
    from temper_placer.losses.wirelength import WirelengthLoss, compute_total_hpwl
    from temper_placer.losses.boundary import BoundaryLoss
    from temper_placer.losses.regularization import SpreadLoss

    weights = {
        "overlap": 200.0,
        "boundary": 100.0,
        "wirelength": 20.0,
        "spread": 5.0,
    }

    # Use config weights if present
    if constraints.losses is not None:
        config_weights = constraints.losses.get_weights()
        for k, v in config_weights.items():
            if k in weights:
                weights[k] = v

    def make_loss(w: dict):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), w["overlap"]),
            WeightedLoss(BoundaryLoss(), w["boundary"]),
            WeightedLoss(WirelengthLoss(), w["wirelength"]),
            WeightedLoss(SpreadLoss(), w.get("spread", 5.0)),
        ])

    context = LossContext.from_netlist_and_board(netlist, board)

    from temper_placer.optimizer.config import OptimizerConfig
    from temper_placer.optimizer.curriculum import create_default_phases
    from temper_placer.optimizer.train import train_multiphase
    from temper_placer.heuristics.pipeline import create_default_pipeline

    pipeline = create_default_pipeline()
    rng = jax.random.PRNGKey(seed)
    preset = pipeline.run(board, netlist, constraints, rng)
    initial_state = preset.state

    phases = create_default_phases(epochs)
    cfg = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        log_interval=max(1, epochs // 100),
        curriculum_phases=phases,
        use_centrality_weighting=False,
    )

    # Pin to CPU for deterministic results
    jax.config.update("jax_platform_name", "cpu")

    print(f"    Optimizing {epochs} epochs (seed={seed})...")
    result = train_multiphase(netlist, board, make_loss, context, cfg, initial_state=initial_state)

    # Compute individual loss values from the composite breakdown.
    # Rotations must be softmax'd --- passing raw logits to loss functions
    # (which expect soft one-hot rotations) produces garbage metrics.
    rotations = jax.nn.softmax(result.final_state.rotation_logits, axis=-1)
    loss_result = make_loss(weights)(
        result.final_state.positions, rotations, context
    )
    breakdown = loss_result.breakdown if loss_result.breakdown else {}

    # Compute HPWL from final positions using the correct function signature.
    hpwl_val = float(
        compute_total_hpwl(result.final_state.positions, rotations, context)
    )

    return {
        "wirelength_final": {
            "mean": float(breakdown.get("wirelength", 0.0)),
            "margin_rel": 0.10,
            "margin_abs": 100.0,
        },
        "overlap_loss_final": {
            "mean": float(breakdown.get("overlap", 0.0)),
            "margin_rel": 0.10,
            "margin_abs": 12.0,
        },
        "boundary_loss_final": {
            "mean": float(breakdown.get("boundary", 0.0)),
            "margin_rel": 0.10,
            "margin_abs": 5.0,
        },
        "final_loss": {
            "mean": float(result.final_loss),
            "margin_rel": 0.05,
            "margin_abs": 20.0,
        },
        "hpwl_final": {
            "mean": hpwl_val,
            "margin_rel": 0.05,
            "margin_abs": 100.0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Extract baseline metrics for corpus boards")
    parser.add_argument("--board", type=str, default=None, help="Extract baseline for a specific board")
    parser.add_argument("--all", action="store_true", help="Extract baselines for all boards")
    args = parser.parse_args()

    repo_root = find_repo_root()
    manifest = load_corpus_manifest(repo_root)

    boards_to_run = manifest["boards"]
    if args.board:
        boards_to_run = [b for b in boards_to_run if b["id"] == args.board]
        if not boards_to_run:
            print(f"Board '{args.board}' not found in manifest", file=sys.stderr)
            sys.exit(1)

    git_hash = "unknown"
    try:
        import subprocess
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        if result.returncode == 0:
            git_hash = result.stdout.strip()[:8]
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()

    for entry in boards_to_run:
        board_id = entry["id"]
        print(f"\n[{board_id}] Extracting baseline...")
        metrics = optimize_board(
            repo_root,
            board_id,
            entry["pcb"],
            entry["constraints"],
            entry["seed"],
            entry["epochs"],
        )

        if metrics is None:
            print(f"  FAILED: Could not extract metrics for {board_id}")
            continue

        baseline = {
            "board_id": board_id,
            "extracted_at": now,
            "git_hash": git_hash,
            "config": {
                "seed": entry["seed"],
                "epochs": entry["epochs"],
                "curriculum": True,
                "heuristics": True,
                "compact": False,
            },
            "metrics": metrics,
        }

        baseline_path = repo_root / "power_pcb_dataset" / "corpus" / entry["baseline"]
        with open(baseline_path, "w") as f:
            json.dump(baseline, f, indent=2)
        print(f"  Wrote {baseline_path}")


if __name__ == "__main__":
    main()
