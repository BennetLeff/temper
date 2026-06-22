"""benchmark command for temper-placer CLI."""

from __future__ import annotations

import click
import json
from pathlib import Path
from ._io import console
from ._io import Panel

@click.command()
@click.option(
    "--pcbs",
    type=str,
    default="all",
    help="Comma-separated list of PCBs to benchmark (default: all).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output report file (default: stdout).",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Report format (default: text).",
)
@click.option(
    "--epochs",
    type=int,
    default=2000,
    help="Optimization epochs (default: 2000).",
)
@click.option(
    "--auto-group/--no-auto-group",
    default=False,
    help="Enable automatic functional grouping (default: disabled).",
)
def benchmark(
    pcbs: str,
    output: Path | None,
    format: str,
    epochs: int,
    auto_group: bool,
) -> None:
    """
    Run placement benchmarks against human baselines.

    Compares the optimizer's placement quality (wirelength, overlap, etc.)
    against production-quality human designs.

    Example:
        temper-placer benchmark --pcbs piantor_left,bitaxe_ultra
    """
    import jax.numpy as jnp

    from temper_placer.core.community import detect_communities
    from temper_placer.io.config_loader import create_board_from_constraints, load_constraints
    from temper_placer.io.reference_loader import load_reference_pcb
    from temper_placer.losses import (
        BoundaryLoss,
        CompositeLoss,
        GroupClusterLoss,
        GroupConfig,
        OverlapLoss,
        SpreadLoss,
        WeightedLoss,
        WirelengthLoss,
    )
    from temper_placer.losses.base import LossContext
    from temper_placer.optimizer import OptimizerConfig, train
    from temper_placer.report.generator import (
        BenchmarkSummary,
        calculate_benchmark_result,
        generate_json_report,
        generate_text_report,
    )

    console.print(
        Panel.fit(
            "[bold blue]temper-placer benchmark[/]\nComparing optimizer to human ground truth",
            border_style="blue",
        )
    )

    # 1. Identify PCBs
    design_dir = Path("tests/fixtures/external/.cache")
    all_designs = []
    seen_names = set()

    if design_dir.exists():
        for p in design_dir.iterdir():
            if p.is_dir() and p.name not in seen_names:
                for pcb in p.glob("*.kicad_pcb"):
                    all_designs.append({"name": p.name, "path": str(pcb)})
                    seen_names.add(p.name)
                    break  # Only one PCB per project for now

    selected_names = [] if pcbs == "all" else [n.strip() for n in pcbs.split(",")]
    targets = []
    for d in all_designs:
        if pcbs == "all" or d["name"] in selected_names:
            targets.append(d)

    if not targets:
        console.print(f"[red]No matching PCBs found in {design_dir}[/]")
        return

    console.print(f"Found {len(targets)} benchmark targets.\n")

    # 2. Setup Loss Factory
    def make_benchmark_loss(weights, netlist=None, detected_communities=None):
        losses = []
        losses.append(
            WeightedLoss(
                OverlapLoss(margin=2.0, rotation_invariant=True, inflation_ramp=0.3),
                weight=weights["overlap"],
            )
        )
        losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))
        losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
        losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

        if auto_group and detected_communities and netlist:
            group_configs = []
            for comm in detected_communities:
                indices = [netlist.get_component_index(ref) for ref in comm.component_refs]
                group_configs.append(
                    GroupConfig(
                        name=comm.name,
                        component_indices=jnp.array(indices, dtype=jnp.int32),
                        max_diameter_mm=30.0,
                        weight=1.0,
                    )
                )
            losses.append(WeightedLoss(GroupClusterLoss(group_configs), weight=10.0))

        return CompositeLoss(losses)

    default_weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 10.0, "spread": 5.0}

    # 3. Run Benchmarks
    summary = BenchmarkSummary(total_pcbs=len(targets), passed=0, failed=0, better_than_human=0)

    for target in targets:
        name = target["name"]
        pcb_path = Path(target["path"])
        console.print(f"Benchmarking [cyan]{name}[/]...")

        try:
            # 1. Load Human Baseline
            baseline_path = pcb_path.parent / f"{name}_benchmark.yaml"
            if not baseline_path.exists():
                # Try legacy name just in case
                legacy_path = pcb_path.parent / f"{name}_baseline.yaml"
                if legacy_path.exists():
                    baseline_path = legacy_path
                else:
                    console.print(
                        f"  [yellow]Warning:[/] Benchmark baseline not found for {name}. Run generate_unrouted_benchmarks.py first."
                    )
                    continue

            with open(baseline_path) as f:
                import yaml as yaml_module

                baseline = yaml_module.safe_load(f)

            # 2. Setup Optimizer Data
            ref_design = load_reference_pcb(pcb_path)

            # Load constraints
            config_path = pcb_path.parent / f"{name}_constraints.yaml"
            if config_path.exists():
                constraints = load_constraints(config_path)
            else:
                from temper_placer.io.config_loader import PlacementConstraints

                constraints = PlacementConstraints()

            board = create_board_from_constraints(constraints)
            context = LossContext.from_netlist_and_board(ref_design.netlist, board)

            # Community detection for auto-grouping
            detected = []
            if auto_group:
                detected = detect_communities(ref_design.netlist)

            # Create loss for this specific board
            composite_loss = make_benchmark_loss(default_weights, ref_design.netlist, detected)

            # 3. Run Optimizer
            cfg = OptimizerConfig(epochs=epochs, seed=42, log_interval=max(1, epochs // 10))
            opt_result = train(ref_design.netlist, board, composite_loss, context, cfg)

            # 4. Compute Real Score
            res = calculate_benchmark_result(name, opt_result, baseline, context)

            summary.results.append(res)
            if res.status == "FAIL":
                summary.failed += 1
            else:
                summary.passed += 1
                if res.status == "BETTER":
                    summary.better_than_human += 1

            console.print(f"  [green]✓[/] Result: {res.status} (WL: {res.wirelength_ratio:.2f}x)")

        except Exception as e:
            console.print(f"  [red]Failed to benchmark {name}: {e}[/]")
            summary.failed += 1
            import traceback

            console.print(traceback.format_exc())

    # 4. Generate Report
    if format == "text":
        report_text = generate_text_report(summary)
        if output:
            output.write_text(report_text)
            console.print(f"\n[green]✓[/] Report written to {output}")
        else:
            print(report_text)
    else:
        if output:
            generate_json_report(summary, output)
            console.print(f"\n[green]✓[/] JSON report written to {output}")
        else:
            console.print(json.dumps(summary.to_dict(), indent=2))
