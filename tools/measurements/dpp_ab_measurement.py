#!/usr/bin/env python3
"""
DPP multi-seed A/B measurement script.

Runs A/B variants (baseline single-seed, random K-from-N, DPP selection)
N times per board and outputs JSON + markdown summary.

Variant A: Single seed via train_multiphase
Variant B: Random K-from-N selection with triage
Variant C: DPP-selected K-from-N with triage
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add repo root to path if running as standalone script
reporoot = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(reporoot / "packages" / "temper-placer" / "src"))


def run_ab_measurements(
    pcb_files: list[Path],
    constraint_files: list[Path],
    n_runs: int = 10,
    n_generate: int = 50,
    n_select: int = 4,
    master_seed: int = 42,
    output_json: Path | None = None,
    output_md: Path | None = None,
) -> dict:
    """
    Run A/B measurements across specified boards.

    Returns:
        Dict with board_name -> {variant -> [list of best_loss values]}.
    """
    results: dict = {}

    for pcb_file, constraint_file in zip(pcb_files, constraint_files):
        board_name = pcb_file.stem
        results[board_name] = {
            "baseline_single": [],
            "random_selection": [],
            "dpp_selection": [],
        }

        # Import inside loop for isolation
        from temper_placer.io import load_pcb

        netlist, board = load_pcb(pcb_file)
        logger.info("Loaded %s: %d components", board_name, netlist.n_components)

        for run_idx in range(n_runs):
            seed = master_seed + run_idx

            # Variant A: Single seed
            result_a = _run_baseline(netlist, board, seed)
            results[board_name]["baseline_single"].append(result_a)

            # Variant B: Random K-from-N
            result_b = _run_random_multiseed(netlist, board, seed, n_generate, n_select)
            results[board_name]["random_selection"].append(result_b)

            # Variant C: DPP selection
            result_c = _run_dpp_multiseed(netlist, board, seed, n_generate, n_select)
            results[board_name]["dpp_selection"].append(result_c)

            logger.info(
                "Board %s run %d: baseline=%.3f random=%.3f dpp=%.3f",
                board_name, run_idx, result_a, result_b, result_c,
            )

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(results, indent=2))

    if output_md:
        _write_markdown_summary(results, output_md)

    return results


def _run_baseline(netlist, board, seed):
    """Run single-seed baseline via train_multiphase."""
    import jax
    import jax.numpy as jnp
    from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
    from temper_placer.losses.boundary import BoundaryLoss
    from temper_placer.losses.overlap import OverlapLoss
    from temper_placer.optimizer.config import OptimizerConfig
    from temper_placer.optimizer.train import train_multiphase

    context = LossContext.from_netlist_and_board(netlist, board)
    config = OptimizerConfig.fast_test()

    def factory(weights):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
            WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        ])

    result = train_multiphase(netlist, board, factory, context, config)
    return result.best_loss


def _run_random_multiseed(netlist, board, seed, n_generate, n_select):
    """Run random K-from-N selection with triage."""
    import jax
    from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
    from temper_placer.losses.boundary import BoundaryLoss
    from temper_placer.losses.overlap import OverlapLoss
    from temper_placer.optimizer.config import MultiSeedConfig, OptimizerConfig
    from temper_placer.optimizer.seed_generation import _generate_diverse_seeds
    from temper_placer.optimizer.train import train_multiphase
    from temper_placer.optimizer.triage import _triage_evaluate
    from temper_placer.core.state import PlacementState

    context = LossContext.from_netlist_and_board(netlist, board)
    config = MultiSeedConfig(n_generate=n_generate, n_select=n_select, n_triage_iters=30)
    key = jax.random.PRNGKey(seed)
    seeds = _generate_diverse_seeds(netlist, board, config, key)

    # Random K-from-N
    import random
    rng = random.Random(seed + 1000)
    selected = rng.sample(range(len(seeds)), min(n_select, len(seeds)))

    # Triage evaluation on selected
    best_loss = float("inf")
    best_positions = None
    for idx in selected:
        triage_loss = _triage_evaluate(
            seeds[idx][0], netlist, board, context=context, n_iters=30,
        )
        if triage_loss < best_loss:
            best_loss = triage_loss
            best_positions = seeds[idx][0]

    if best_positions is None:
        return float("inf")

    # Full optimization
    opt_config = OptimizerConfig.fast_test()

    def factory(weights):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
            WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        ])

    result = train_multiphase(
        netlist, board, factory, context, opt_config,
        initial_state=PlacementState(
            positions=best_positions,
            rotation_logits=jax.numpy.zeros((netlist.n_components, 4)),
        ),
    )
    return result.best_loss


def _run_dpp_multiseed(netlist, board, seed, n_generate, n_select):
    """Run DPP-selected multi-seed with triage (via train_dpp_multiseed)."""
    from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
    from temper_placer.losses.boundary import BoundaryLoss
    from temper_placer.losses.overlap import OverlapLoss
    from temper_placer.optimizer.config import MultiSeedConfig, OptimizerConfig
    from temper_placer.optimizer.train import train_dpp_multiseed

    context = LossContext.from_netlist_and_board(netlist, board)
    opt_config = OptimizerConfig(
        epochs=100,
        multi_seed=MultiSeedConfig(
            enabled=True, n_generate=n_generate, n_select=n_select, n_triage_iters=30,
        ),
    )

    def factory(weights):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
            WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        ])

    result = train_dpp_multiseed(
        netlist, board,
        loss_factory=factory,
        context=context,
        config=opt_config,
    )
    return result.best_result.best_loss


def _write_markdown_summary(results: dict, output_md: Path) -> None:
    """Write markdown summary of A/B results."""
    lines = ["# DPP Multi-Seed A/B Test Results", ""]
    lines.append(f"**Date:** {_today()}")
    lines.append(f"**Variants:** Baseline (single), Random K-from-N, DPP selection")
    lines.append("")

    for board_name, variant_data in results.items():
        lines.append(f"## {board_name}")
        lines.append("")
        lines.append("| Variant | Mean Best Loss | Std Dev | Min | Max |")
        lines.append("|---------|---------------|---------|-----|-----|")

        for variant, losses in variant_data.items():
            if not losses:
                continue
            import statistics
            mean_loss = statistics.mean(losses)
            std_loss = statistics.stdev(losses) if len(losses) > 1 else 0.0
            min_loss = min(losses)
            max_loss = max(losses)
            lines.append(
                f"| {variant} | {mean_loss:.3f} | {std_loss:.3f} | "
                f"{min_loss:.3f} | {max_loss:.3f} |"
            )
        lines.append("")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines))


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("A/B measurement script placeholder — use from Python API.")
    sys.exit(0)
