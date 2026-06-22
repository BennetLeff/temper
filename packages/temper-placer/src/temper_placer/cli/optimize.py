"""optimize command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
import signal
from pathlib import Path
from ._io import console
from ._io import Panel
from ._io import Progress

@click.command()
@click.argument("input_pcb", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Constraint configuration YAML file.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output .kicad_pcb file path.",
)
@click.option(
    "--epochs",
    "-n",
    type=int,
    default=8000,
    help="Number of optimization epochs (default: 8000).",
)
@click.option(
    "--weight-overlap",
    type=float,
    default=None,
    help="Override overlap loss weight.",
)
@click.option(
    "--weight-wirelength",
    type=float,
    default=None,
    help="Override wirelength loss weight.",
)
@click.option(
    "--visualize",
    "-v",
    is_flag=True,
    default=False,
    help="Enable live browser visualization (not yet implemented).",
)
@click.option(
    "--port",
    type=int,
    default=8080,
    help="Port for visualization server.",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducibility.",
)
@click.option(
    "--checkpoint",
    type=click.Path(path_type=Path),
    help="Save checkpoint file (JSON format).",
)
@click.option(
    "--curriculum/--no-curriculum",
    default=True,
    help="Use curriculum learning (default: enabled).",
)
@click.option(
    "--placements-json",
    type=click.Path(path_type=Path),
    help="Also save placements as JSON file.",
)
@click.option(
    "--heuristics/--no-heuristics",
    default=True,
    help="Use smart heuristic initialization (default: enabled).",
)
@click.option(
    "--auto-group/--no-auto-group",
    default=True,
    help="Automatically detect and cluster functional blocks (default: enabled).",
)
@click.option(
    "--centrality/--no-centrality",
    default=False,
    help="Use graph centrality to prioritize hub components (default: disabled).",
)
@click.option(
    "--profile-dir",
    type=click.Path(path_type=Path),
    help="Save JAX profiler trace to this directory.",
)
@click.option(
    "--grad-norm/--no-grad-norm",
    default=False,
    help="Use GradNorm adaptive loss weighting (default: disabled).",
)
@click.option(
    "--grad-norm-alpha",
    type=float,
    default=1.5,
    help="GradNorm asymmetry parameter (default: 1.5).",
)
@click.option(
    "--grad-norm-lr",
    type=float,
    default=0.025,
    help="GradNorm weight update learning rate (default: 0.025).",
)
@click.option(
    "--loss-history",
    type=click.Path(path_type=Path),
    help="Save full loss history to JSON file.",
)
@click.option(
    "--log-all-epochs",
    is_flag=True,
    default=False,
    help="Record metrics for every epoch (warning: increases file size).",
)
@click.option(
    "--verbose-losses",
    is_flag=True,
    default=False,
    help="Show detailed loss breakdown in console during optimization.",
)
@click.option(
    "--parallel-seeds",
    type=int,
    default=1,
    help="Number of random seeds to run in parallel (default: 1).",
)
@click.option(
    "--skip-topological",
    is_flag=True,
    default=False,
    help="Skip topological initialization heuristic (default: enabled).",
)
@click.option(
    "--track-metrics",
    type=click.Path(path_type=Path),
    help="Enable metrics tracking, save to this directory.",
)
@click.option(
    "--spice-validate/--no-spice-validate",
    default=False,
    help="Run SPICE simulation for electrical validation after optimization.",
)
@click.option(
    "--spice-penalty-weight",
    type=float,
    default=100.0,
    help="Weight for SPICE validation penalty in loss function (if enabled).",
)
@click.option(
    "--weight-channel-capacity",
    type=float,
    default=None,
    help="Override channel capacity loss weight.",
)
@click.option(
    "--compact/--no-compact",
    default=False,
    help="Use the consolidated Core 8 loss set (default: False).",
)
def optimize(
    input_pcb: Path,
    config: Path,
    output: Path,
    epochs: int,
    weight_overlap: float | None,
    weight_wirelength: float | None,
    visualize: bool,
    port: int,
    seed: int,
    checkpoint: Path | None,
    curriculum: bool,
    placements_json: Path | None,
    heuristics: bool,
    auto_group: bool,
    centrality: bool,
    profile_dir: Path | None,
    grad_norm: bool,
    grad_norm_alpha: float,
    grad_norm_lr: float,
    loss_history: Path | None,
    log_all_epochs: bool,
    verbose_losses: bool,
    parallel_seeds: int,
    skip_topological: bool,
    track_metrics: Path | None,
    spice_validate: bool,
    spice_penalty_weight: float,
    weight_channel_capacity: float | None,
    compact: bool,
) -> None:
    """
    Optimize component placement for a KiCad PCB.

    Reads INPUT_PCB and constraint CONFIG, runs gradient-based optimization,
    and writes the result to OUTPUT.

    Example:
        temper-placer optimize temper.kicad_pcb -c constraints.yaml -o optimized.kicad_pcb
    """
    console.print(
        Panel.fit(
            f"[bold blue]temper-placer[/] v{__version__}\nJAX-based PCB placement optimizer",
            border_style="blue",
        )
    )

    console.print(f"\n[bold]Input:[/] {input_pcb}")
    console.print(f"[bold]Config:[/] {config}")
    console.print(f"[bold]Output:[/] {output}")
    console.print(f"[bold]Epochs:[/] {epochs}")
    console.print(f"[bold]Seed:[/] {seed}")
    console.print(f"[bold]Curriculum:[/] {'enabled' if curriculum else 'disabled'}")
    console.print(f"[bold]Heuristics:[/] {'enabled' if heuristics else 'disabled'}")
    console.print(f"[bold]Centrality:[/] {'enabled' if centrality else 'disabled'}")
    console.print(f"[bold]Loss Set:[/] {'[bold cyan]Compact (Core 8)[/]' if compact else 'Standard (Legacy)'}")

    # Import heavy dependencies only when needed
    console.print("\n[dim]Loading JAX and optimizer modules...[/]")

    try:
        import jax
        import jax.numpy as jnp

        from temper_placer.core.community import detect_communities
        from temper_placer.core.state import PlacementState
        from temper_placer.heuristics import PlacementContext, create_default_pipeline
        from temper_placer.io.config_loader import (
            apply_fixed_components_to_netlist,
            apply_zones_to_netlist,
            create_board_from_constraints,
            load_constraints,
        )
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.kicad_writer import (
            export_placements,
            placements_to_json,
            state_to_placements,
        )
        from temper_placer.losses import (
            BoundaryLoss,
            ChannelCapacityLoss,
            CompositeLoss,
            GroupClusterLoss,
            GroupConfig,
            OverlapLoss,
            RoutabilityLoss,
            SpreadLoss,
            WeightedLoss,
            WirelengthLoss,
        )
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.compact import create_compact_loss_set
        from temper_placer.optimizer import OptimizerConfig, train, train_multiphase
        from temper_placer.optimizer.curriculum import create_default_phases, create_fast_phases
    except ImportError as e:
        console.print(f"[red]Failed to import required modules: {e}[/]")
        console.print("Please ensure JAX and all dependencies are installed:")
        console.print("  pip install temper-placer")
        sys.exit(1)

    # Step 1: Parse KiCad PCB
    console.print("\n[bold cyan]Step 1/5:[/] Parsing KiCad PCB...")
    try:
        parse_result = parse_kicad_pcb(input_pcb)
        netlist = parse_result.netlist
        board_from_pcb = parse_result.board

        if parse_result.has_warnings:
            for w in parse_result.warnings:
                console.print(f"  [yellow]Warning:[/] {w}")

        console.print(
            f"  [green]✓[/] Loaded {netlist.n_components} components, {netlist.n_nets} nets"
        )
    except Exception as e:
        console.print(f"[red]Failed to parse PCB: {e}[/]")
        sys.exit(1)

    # Step 2: Load constraints
    console.print("\n[bold cyan]Step 2/5:[/] Loading constraints...")
    try:
        constraints = load_constraints(config)
        board = create_board_from_constraints(constraints)

        # Apply fixed_components to netlist
        apply_fixed_components_to_netlist(netlist, constraints)

        # Apply zone assignments from groups to components
        apply_zones_to_netlist(netlist, constraints)

        console.print(f"  [green]✓[/] Board: {board.width:.1f}mm x {board.height:.1f}mm")
        console.print(f"  [green]✓[/] Zones: {len(board.zones)}")
        console.print(f"  [green]✓[/] HV clearance: {constraints.hv_clearance_mm}mm")
    except Exception as e:
        console.print(f"[red]Failed to load constraints: {e}[/]")
        sys.exit(1)

    # Step 2b: Run heuristic initialization (if enabled)
    initial_state: PlacementState | None = None
    if heuristics:
        console.print("\n[bold cyan]Step 2b/5:[/] Running smart initialization heuristics...")
        try:
            # Skip topological if requested
            # Choose pipeline based on config
            # If placement_priority is defined, use priority pipeline (professional workflow)
            if constraints.placement_priority:
                from temper_placer.heuristics.pipeline import create_priority_pipeline

                pipeline = create_priority_pipeline()
                console.print("  [dim]Using priority-based pipeline (power stage template)[/]")
            else:
                # Skip topological if requested
                include_topological = not skip_topological
                pipeline = create_default_pipeline(include_topological=include_topological)
                if skip_topological:
                    console.print("  [dim]Topological initialization: skipped[/]")
            heuristic_key = jax.random.PRNGKey(seed)

            pipeline_result = pipeline.run(
                board=board,
                netlist=netlist,
                constraints=constraints,
                key=heuristic_key,
            )
            initial_state = pipeline_result.state

            # Report heuristic results
            total_placed = sum(
                stats.get("placed", 0) for stats in pipeline_result.heuristic_stats.values()
            )
            console.print(f"  [green]✓[/] Placed {total_placed}/{netlist.n_components} components")

            # Show per-heuristic stats
            for name, stats in pipeline_result.heuristic_stats.items():
                if stats.get("placed", 0) > 0:
                    console.print(f"    - {name}: {stats['placed']} placed")

            if pipeline_result.unplaced:
                console.print(
                    f"  [yellow]Warning:[/] {len(pipeline_result.unplaced)} components unplaced"
                )

            if pipeline_result.conflicts:
                console.print(f"  [dim]Resolved {len(pipeline_result.conflicts)} conflicts[/]")

        except Exception as e:
            console.print(f"[yellow]Warning:[/] Heuristics failed, using random init: {e}")
            initial_state = None

    # Step 3: Create loss functions
    console.print("\n[bold cyan]Step 3/5:[/] Creating loss functions...")

    # Run auto-grouping if requested AND no manual groups defined
    detected_communities = []
    if auto_group:
        # Skip auto-detect if user has defined manual groups (trust their design)
        if constraints.component_groups:
            console.print(
                f"  [dim]Skipping auto-detection ({len(constraints.component_groups)} manual groups defined)[/]"
            )
        else:
            console.print("  [dim]Detecting functional communities (Louvain)...[/]")
            detected_communities = detect_communities(netlist)
            if detected_communities:
                console.print(
                    f"  [green]✓[/] Detected {len(detected_communities)} functional blocks"
                )
                for comm in detected_communities:
                    console.print(f"    - {comm.name}: {len(comm.component_refs)} components")

    # Build composite loss with curriculum-aware weights
    def make_loss(weights: dict) -> CompositeLoss:
        """Create composite loss function from weights."""
        if compact:
            return create_compact_loss_set(weights, context, constraints)

        losses = []

        # Core feasibility losses
        if "overlap" in weights:
            # Use margin=1.0mm for DRC safety (KiCad default clearance is 0.2mm)
            # The 1.0mm margin provides headroom for:
            # - 0.2mm KiCad clearance
            # - Pad extensions beyond bounding box (~0.3-0.5mm)
            # - Solder mask aperture bridges
            # rotation_invariant=True ensures overlap is detected regardless of rotation
            losses.append(
                WeightedLoss(
                    OverlapLoss(margin=2.0, rotation_invariant=True, inflation_ramp=0.3),
                    weight=weights["overlap"],
                )
            )
        
        # Pin accessibility loss (fine-grained clearance)
        if "pin_accessibility" in weights:
            from temper_placer.losses.pin_accessibility import PinAccessibilityLoss
            losses.append(
                WeightedLoss(
                    PinAccessibilityLoss(pin_pin_margin=0.5, pin_body_margin=0.8),
                    weight=weights["pin_accessibility"],
                )
            )
        elif "overlap" in weights:
            # Add with default weight if overlap is enabled but pin_accessibility is not explicitly set
            from temper_placer.losses.pin_accessibility import PinAccessibilityLoss
            losses.append(
                WeightedLoss(
                    PinAccessibilityLoss(pin_pin_margin=0.5, pin_body_margin=0.8),
                    weight=weights["overlap"] * 0.1,  # 10% of overlap weight by default
                )
            )

        if "boundary" in weights:
            losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))

        # Performance losses
        if "wirelength" in weights:
            losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
        if "spread" in weights:
            losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

        if "routability" in weights:
            losses.append(WeightedLoss(RoutabilityLoss(), weight=weights["routability"]))
        elif "congestion" in weights:
            # Map congestion to the new layer-aware routability loss
            losses.append(WeightedLoss(RoutabilityLoss(), weight=weights["congestion"]))

        # Channel capacity (routing bottlenecks)
        if "channel_capacity" in weights:
            losses.append(
                WeightedLoss(
                    ChannelCapacityLoss(trace_width=0.15, trace_spacing=0.15, min_margin=0.2),
                    weight=weights["channel_capacity"],
                )
            )
        elif "routability" in weights or "congestion" in weights:
            # Enable by default if routability is requested
            losses.append(
                WeightedLoss(
                    ChannelCapacityLoss(trace_width=0.15, trace_spacing=0.15, min_margin=0.2),
                    weight=weights.get("routability", weights.get("congestion", 10.0)) * 0.5,
                )
            )

        # Regularization losses
        if "edge_avoidance" in weights and weights["edge_avoidance"] > 0:
            from temper_placer.losses.regularization import EdgeAvoidanceLoss

            losses.append(WeightedLoss(EdgeAvoidanceLoss(), weight=weights["edge_avoidance"]))

        # Decoupling capacitor proximity loss
        if "decoupling" in weights:
            from temper_placer.losses.decoupling import (
                DecouplingRule,
                create_decoupling_loss,
            )

            # Auto-detect decoupling rules from MCU caps
            decoupling_rules = []
            mcu_refs = [
                c.ref for c in netlist.components if c.ref.startswith("U_MCU") or c.ref == "U_MCU"
            ]
            cap_refs = [c.ref for c in netlist.components if c.ref.startswith("C_MCU")]

            for mcu in mcu_refs:
                for cap in cap_refs:
                    decoupling_rules.append(
                        DecouplingRule(
                            cap_ref=cap,
                            ic_ref=mcu,
                            max_distance_mm=5.0,  # 5mm max for decoupling
                        )
                    )

            if decoupling_rules:
                decoupling_loss = create_decoupling_loss(netlist, decoupling_rules)
                losses.append(WeightedLoss(decoupling_loss, weight=weights["decoupling"]))

        # Power path loss (high-current path optimization)
        if "power_path" in weights:
            from temper_placer.losses.power_path import (
                HighCurrentPathConfig,
                SwitchingLoopConfig,
                create_power_path_loss,
            )

            # Configure power paths based on common high-current nets
            power_paths = []
            power_nets = ["+340V_BUS", "DC_BUS_RTN", "SW_NODE", "+15V", "PGND"]
            for net in power_nets:
                if any(net in n.name for n in netlist.nets):
                    power_paths.append(
                        HighCurrentPathConfig(
                            name=f"path_{net}",
                            nets=[net],
                            current_a=10.0,  # Default
                            weight=1.0,
                        )
                    )

            # Configure switching loops
            switching_loops = [
                SwitchingLoopConfig(
                    name="half_bridge_commutation",
                    components=["Q1", "Q2", "C_BUS1"],
                    weight=2.0,  # High priority
                ),
            ]

            if power_paths or switching_loops:
                power_loss = create_power_path_loss(
                    netlist,
                    power_paths,
                    [
                        loop
                        for loop in switching_loops
                        if all(
                            any(c.ref == comp for c in netlist.components)
                            for comp in loop.components
                        )
                    ],
                )
                losses.append(WeightedLoss(power_loss, weight=weights["power_path"]))

        # Auto-grouping clusters
        if auto_group and (detected_communities or constraints.component_groups):
            group_configs = []

            # Add auto-detected communities
            if detected_communities:
                for comm in detected_communities:
                    # Resolve refs to indices
                    indices = [netlist.get_component_index(ref) for ref in comm.component_refs]
                    group_configs.append(
                        GroupConfig(
                            name=f"auto_{comm.name}",
                            component_indices=jnp.array(indices, dtype=jnp.int32),
                            max_diameter_mm=30.0,  # Default 30mm cluster size
                            weight=1.0,
                        )
                    )

            # Add explicit YAML-defined groups
            if constraints.component_groups:
                for group in constraints.component_groups:
                    # Filter components that actually exist in the netlist
                    valid_refs = [
                        ref for ref in group.components if ref in netlist._component_index
                    ]
                    if not valid_refs:
                        continue

                    indices = [netlist.get_component_index(ref) for ref in valid_refs]
                    group_configs.append(
                        GroupConfig(
                            name=group.name,
                            component_indices=jnp.array(indices, dtype=jnp.int32),
                            max_diameter_mm=group.max_spread_mm,
                            weight=2.0,  # Give higher weight to explicit groups
                        )
                    )

            if group_configs:
                # Use weight from config if provided, otherwise default
                grouping_weight = weights.get("grouping", 10.0)
                losses.append(WeightedLoss(GroupClusterLoss(group_configs), weight=grouping_weight))

        # Loop area loss (PowerSynth: critical for switching loops)
        if "loop_area" in weights:
            from temper_placer.losses.loop_area import LoopAreaLoss

            # Use pre-configured loop definitions from constraints
            # For Temper: commutation loop (Q1-Q2-C_BUS), gate loops
            losses.append(WeightedLoss(LoopAreaLoss(), weight=weights["loop_area"]))

        # Thermal spread loss (PowerSynth: force IGBT spacing)
        if "thermal_spread" in weights:
            from temper_placer.losses.thermal import ThermalSpreadLoss

            # Force minimum spacing between heat-generating components
            losses.append(
                WeightedLoss(
                    ThermalSpreadLoss(min_spacing_mm=12.0), weight=weights["thermal_spread"]
                )
            )

        # Thermal edge loss (PowerSynth: heatsink mounting)
        if "thermal" in weights:
            from temper_placer.losses.thermal import ThermalLoss

            # Penalize components far from required board edges
            losses.append(WeightedLoss(ThermalLoss(), weight=weights["thermal"]))

        # Add more losses based on constraints
        # (clearance, thermal, zone, loop_area, etc. can be added here)
        if "star_point" in weights or (constraints.star_grounds):
            from temper_placer.losses.star_point import StarPointLoss

            weight = weights.get("star_point", 1.0)
            # Default internal weights, could be configured via kwargs if needed
            losses.append(WeightedLoss(StarPointLoss(), weight=weight))

        # Add zone membership loss if zones are defined
        if board.zones:
            from temper_placer.losses.zone import ZoneMembershipLoss

            # Zone assignments come from component.zone (set by apply_zones_to_netlist)
            # ZoneMembershipLoss will use zone.components from board definition
            # Check both 'zone_membership' (YAML) and 'zone' (legacy) keys
            zone_weight = weights.get("zone_membership", weights.get("zone", 100.0))
            losses.append(WeightedLoss(ZoneMembershipLoss(), weight=zone_weight))

        # Add aesthetic losses
        from temper_placer.losses.aesthetic import create_aesthetic_losses

        aes_losses = create_aesthetic_losses(netlist, constraints)
        losses.extend(aes_losses)

        # Add manufacturing losses
        from temper_placer.losses.manufacturing_margin import create_manufacturing_margin_loss

        mfg_loss_fn = create_manufacturing_margin_loss()
        if mfg_loss_fn:
            losses.append(WeightedLoss(mfg_loss_fn, weight=5.0))

        return CompositeLoss(losses)

    # Build weights from config, CLI overrides, or defaults
    # Priority: CLI flags > config file > hardcoded defaults
    if constraints.losses is not None:
        # Use config-specified losses
        config_weights = constraints.losses.get_weights()
        console.print(f"  [dim]Using losses from config: {list(config_weights.keys())}[/]")

        # Apply CLI overrides if specified
        if weight_overlap is not None:
            config_weights["overlap"] = weight_overlap
        if weight_wirelength is not None:
            config_weights["wirelength"] = weight_wirelength
        if weight_channel_capacity is not None:
            config_weights["channel_capacity"] = weight_channel_capacity

        weights = config_weights
    else:
        # Fall back to hardcoded defaults (legacy behavior)
        console.print("  [dim]No losses in config, using defaults[/]")
        weights = {
            "overlap": weight_overlap if weight_overlap is not None else 100.0,
            "boundary": 50.0,
            "wirelength": weight_wirelength if weight_wirelength is not None else 10.0,
            "spread": 5.0,
        }

    # Step 4: Create optimizer context
    console.print("\n[bold cyan]Step 4/5:[/] Initializing context...")

    context = LossContext.from_netlist_and_board(
        netlist, board, use_centrality_weighting=centrality
    )

    composite_loss = make_loss(weights)
    console.print(f"  [green]✓[/] Created {len(composite_loss.losses)} loss functions")

    # Configure optimizer

    # Configure optimizer
    from temper_placer.optimizer.config import GradNormConfig

    gn_cfg = GradNormConfig(alpha=grad_norm_alpha, learning_rate=grad_norm_lr)

    log_interval = 1 if log_all_epochs else max(1, epochs // 100)

    if curriculum:
        phases = create_default_phases(epochs)
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=log_interval,
            curriculum_phases=phases,
            use_centrality_weighting=centrality,
            use_grad_norm=grad_norm,
            grad_norm=gn_cfg,
        )
        console.print(f"  [green]✓[/] Curriculum: {len(phases)} phases")
    else:
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=log_interval,
            use_centrality_weighting=centrality,
            use_grad_norm=grad_norm,
            grad_norm=gn_cfg,
        )

    console.print(
        f"  [green]✓[/] Temperature: {cfg.temperature.start:.1f} → {cfg.temperature.end:.2f}"
    )
    console.print(f"  [green]✓[/] Learning rate: {cfg.learning_rate.initial:.4f}")
    if log_all_epochs:
        console.print("  [green]✓[/] Logging: all epochs")

    # Step 5: Run optimization
    console.print("\n[bold cyan]Step 5/5:[/] Running optimization...")
    if profile_dir:
        console.print(f"  [dim]JAX profiler enabled, saving to: {profile_dir}[/]")
    if track_metrics:
        console.print(f"  [dim]Metrics tracking enabled, saving to: {track_metrics}[/]")

    # Setup Ctrl+C handler for graceful interruption
    interrupted = False

    def signal_handler(sig, frame):
        nonlocal interrupted
        interrupted = True
        console.print("\n[yellow]Interrupted! Saving current best state...[/]")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    # Progress callback
    last_printed_epoch = -1

    def progress_callback(metrics):
        nonlocal last_printed_epoch
        if interrupted:
            raise KeyboardInterrupt()

        # Print every 10% of epochs (unless verbose)
        print_interval = 10 if verbose_losses else max(1, epochs // 10)
        if metrics.epoch % print_interval == 0 or metrics.epoch == epochs - 1:
            phase_name = ""
            if curriculum and cfg.curriculum_phases:
                for p in cfg.curriculum_phases:
                    if p.start_epoch <= metrics.epoch < p.end_epoch:
                        phase_name = f" [[bold]{p.name}[/]]"
                        break

            # Format total loss line
            console.print(
                f"  Epoch {metrics.epoch:5d}/{epochs}: "
                f"loss={metrics.loss:8.2f}, "
                f"T={metrics.temperature:.3f}, "
                f"lr={metrics.learning_rate:.5f}"
                f"{phase_name}"
            )

            # Format breakdown if verbose
            if verbose_losses and metrics.loss_breakdown:
                # Group by major categories
                sorted_keys = sorted(metrics.loss_breakdown.keys())
                breakdown_str = "    "
                for i, k in enumerate(sorted_keys):
                    val = metrics.loss_breakdown[k]
                    if val > 0.01:  # Hide near-zero losses
                        breakdown_str += f"{k}={val:6.2f}  "
                        if (i + 1) % 4 == 0:
                            breakdown_str += "\n    "
                if breakdown_str.strip():
                    console.print(f"[dim]{breakdown_str}[/]")

    try:
        profile_dir_str = str(profile_dir) if profile_dir else None

        if parallel_seeds > 1:
            from temper_placer.optimizer.train import train_parallel

            parallel_result = train_parallel(
                netlist,
                board,
                composite_loss,
                context,
                cfg,
                n_seeds=parallel_seeds,
                callback=progress_callback,
            )
            result = parallel_result.best_result

            console.print("\n[bold cyan]Parallel Optimization Summary:[/]")
            console.print(f"  Confidence Score: {parallel_result.confidence_score:.2%}")

            tax_color = (
                "red"
                if parallel_result.aesthetic_tax > constraints.aesthetics.max_wirelength_tax
                else "green"
            )
            console.print(
                f"  Aesthetic Tax: [{tax_color}]{parallel_result.aesthetic_tax:.2f}x[/] wirelength"
            )

            if parallel_result.aesthetic_tax > constraints.aesthetics.max_wirelength_tax:
                console.print(
                    f"\n[bold red]Warning:[/] Aesthetic tax exceeds threshold of {constraints.aesthetics.max_wirelength_tax}x."
                )
                if not click.confirm("Do you want to proceed with this high-cost layout?"):
                    sys.exit(0)

        elif curriculum and cfg.curriculum_phases:
            result = train_multiphase(
                netlist,
                board,
                make_loss,
                context,
                cfg,
                initial_state=initial_state,
                callback=progress_callback,
                profile_dir=profile_dir_str,
            )
        else:
            result = train(
                netlist,
                board,
                composite_loss,
                context,
                cfg,
                initial_state=initial_state,
                callback=progress_callback,
                profile_dir=profile_dir_str,
            )

        # Restore signal handler
        signal.signal(signal.SIGINT, original_handler)

        console.print("\n  [green]✓[/] Optimization complete!")
        console.print(f"    Final loss: {result.final_loss:.4f}")
        console.print(f"    Best loss: {result.best_loss:.4f}")
        console.print(f"    Epochs: {result.total_epochs}")
        console.print(f"    Converged: {'yes' if result.converged else 'no'}")
        console.print(f"    Time: {result.elapsed_seconds:.1f}s")

    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, original_handler)
        console.print("[yellow]Optimization interrupted.[/]")
        # Use best state found so far
        if "result" not in locals():
            console.print("[red]No results available yet.[/]")
            sys.exit(1)
    except Exception as e:
        signal.signal(signal.SIGINT, original_handler)
        console.print(f"[red]Optimization failed: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Export results
    console.print("\n[bold cyan]Exporting results...[/]")

    # Save loss history if requested
    if loss_history:
        try:
            from temper_placer.visualization.model import (
                LossDataPoint,
                LossHistory,
            )

            history_obj = LossHistory()
            for m in result.history:
                # Convert JAX arrays to lists for JSON serialization
                positions_list = m.positions.tolist() if m.positions is not None else None
                # rotations are logits in TrainingMetrics? No, they are soft one-hot or discrete.
                # In train.py, they were 'rotations' which is soft one-hot (N, 4).
                # For visualization, we might want degrees.
                # But let's just save whatever is in the metrics for now.
                rotations_list = m.rotations.tolist() if m.rotations is not None else None

                history_obj.add_point(
                    LossDataPoint(
                        epoch=m.epoch,
                        total_loss=m.loss,
                        breakdown=m.loss_breakdown,
                        temperature=m.temperature,
                        learning_rate=m.learning_rate,
                        positions=positions_list,
                        rotations=rotations_list,
                    )
                )

            # Add phase boundaries
            if curriculum and cfg.curriculum_phases:
                history_obj.phase_boundaries = [p.start_epoch for p in cfg.curriculum_phases]
                history_obj.phase_names = [p.name for p in cfg.curriculum_phases]

            loss_history.parent.mkdir(parents=True, exist_ok=True)
            with open(loss_history, "w") as f:
                json.dump(history_obj.to_dict(), f, indent=2)

            console.print(f"  [green]✓[/] Wrote {loss_history}")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/] Failed to save loss history: {e}")

    # Save metrics tracking data if requested
    if track_metrics:
        try:
            from temper_placer.experiments import (
                setup_metrics_tracking,
                create_run_metrics,
                record_training_run,
            )

            tracker = setup_metrics_tracking(track_metrics, input_pcb.stem)
            if tracker is not None:
                config_dict = {
                    "epochs": epochs,
                    "seed": seed,
                    "curriculum": curriculum,
                    "weight_overlap": weight_overlap,
                    "weight_wirelength": weight_wirelength,
                }
                run_metrics = create_run_metrics(result, netlist, input_pcb.stem, seed, config_dict)
                tracker.record_run(run_metrics)
                console.print(f"  [green]✓[/] Recorded metrics to {track_metrics}")
        except Exception as e:
            console.print(f"  [yellow]Warning:[/] Failed to record metrics: {e}")

    # Get component refs in order
    component_refs = [c.ref for c in netlist.components]

    # Get board origin
    origin = board_from_pcb.origin if board_from_pcb else (0.0, 0.0)

    # Apply zone legalization for perfect zone compliance
    if board.zones:
        try:
            from temper_placer.optimizer.legalization import clamp_to_zones
            import numpy as np

            console.print("  [dim]Applying zone legalization...[/]")
            # Get positions from best state and apply zone clamping
            legalized_positions = clamp_to_zones(
                np.array(result.best_state.positions),
                netlist,
                board,
                fixed_mask=np.array(context.fixed_mask),
            )
            # Update best_state with legalized positions
            result.best_state = PlacementState.from_positions(
                positions=legalized_positions,
                rotation_logits=result.best_state.rotation_logits,
                net_virtual_nodes=result.best_state.net_virtual_nodes,
            )
            console.print("  [green]✓[/] Applied zone legalization for perfect compliance")
        except Exception as e:
            console.print(f"  [red]✗[/] Zone legalization failed: {e}")
            import traceback

            traceback.print_exc()
            console.print("  [yellow]Warning:[/] Continuing without zone legalization")

        # Apply overlap resolution to fix any overlaps created by zone clamping
        # Use Abacus algorithm for provably optimal legalization (minimal displacement)
        try:
            from temper_placer.optimizer.legalization import (
                legalize_abacus,
                resolve_overlaps_priority,
            )

            console.print(
                "  [dim]Applying Abacus legalization for optimal overlap-free placement...[/]"
            )

            # First try Abacus (optimal 1D legalization per row)
            legalized_state = legalize_abacus(
                result.best_state,
                context,
                n_rows=20,  # More rows for finer control
                spacing=0.5,
            )

            # Then apply priority-based overlap resolution for any remaining 2D overlaps
            from temper_placer.optimizer.legalization import resolve_overlaps_priority

            overlap_free_positions = resolve_overlaps_priority(
                np.array(legalized_state.positions),
                netlist,
                board,
                fixed_mask=np.array(context.fixed_mask),
                max_iterations=1000,  # Increased for stubborn overlaps
                min_separation=2.0,  # Increased for better visual spacing
                damping=0.95,  # Reduced damping for more aggressive separation
            )

            # Update best_state with overlap-free positions
            result.best_state = PlacementState.from_positions(
                positions=overlap_free_positions,
                rotation_logits=result.best_state.rotation_logits,
                net_virtual_nodes=result.best_state.net_virtual_nodes,
            )
            console.print("  [green]✓[/] Applied Abacus + priority overlap resolution")
        except Exception as e:
            console.print(f"  [red]✗[/] Overlap resolution failed: {e}")
            import traceback

            traceback.print_exc()
            console.print("  [yellow]Warning:[/] Continuing with overlaps present")

    try:
        console.print("  [dim]Exporting to KiCad PCB...[/]")
        # Export to KiCad PCB
        write_result = export_placements(
            template_pcb=input_pcb,
            output_pcb=output,
            state=result.best_state,
            component_refs=component_refs,
            origin=origin,
            components=netlist.components,  # Pass components for center offset correction
        )

        console.print(f"  [green]✓[/] Wrote {output}")
        console.print(f"    Updated: {write_result.components_updated} components")
        console.print(f"    Skipped: {write_result.components_skipped} components")

        if write_result.has_warnings:
            for w in write_result.warnings:
                console.print(f"    [yellow]Warning:[/] {w}")

        # Add component bounding boxes for visualization
        try:
            from temper_placer.io.kicad_writer import add_bounding_boxes_to_pcb

            # Function now calculates bounds from actual footprint pads
            boxes_added = add_bounding_boxes_to_pcb(output)
            console.print(f"    [dim]Added {boxes_added} bounding boxes (Dwgs.User layer)[/]")
        except Exception as e:
            console.print(f"    [dim]Could not add bounding boxes: {e}[/]")

        # Add silkscreen labels and F.Fab outlines
        try:
            from temper_placer.io.kicad_writer import add_silkscreen_labels

            label_counts = add_silkscreen_labels(output)
            console.print(
                f"    [dim]Added {label_counts['references']} refs (F.SilkS), "
                f"{label_counts['values']} values, "
                f"{label_counts['outlines']} outlines (F.Fab)[/]"
            )
        except Exception as e:
            console.print(f"    [dim]Could not add silkscreen: {e}[/]")

        # Also save JSON if requested
        if placements_json:
            placements = state_to_placements(result.best_state, component_refs, origin)
            placements_dict = placements_to_json(placements)

            placements_json.parent.mkdir(parents=True, exist_ok=True)
            with open(placements_json, "w") as f:
                json.dump(placements_dict, f, indent=2)

            console.print(f"  [green]✓[/] Wrote {placements_json}")

        # Save checkpoint if requested
        if checkpoint:
            checkpoint_data = {
                "epochs": result.total_epochs,
                "final_loss": result.final_loss,
                "best_loss": result.best_loss,
                "converged": result.converged,
                "elapsed_seconds": result.elapsed_seconds,
                "config": {
                    "seed": seed,
                    "epochs": epochs,
                    "curriculum": curriculum,
                },
            }

            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint, "w") as f:
                json.dump(checkpoint_data, f, indent=2)

            console.print(f"  [green]✓[/] Wrote {checkpoint}")

    except Exception as e:
        console.print(f"[red]Failed to export results: {e}[/]")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Step 6: SPICE Validation (Electrical correctness)
    if spice_validate:
        console.print("\n[bold cyan]Step 6/5 (Optional):[/] Running SPICE electrical validation...")
        try:
            from temper_placer.validation.spice_pipeline import SpiceValidationPipeline
            
            # Load default component names for Temper if not specified in config
            # (In a real scenario, these would come from PCL or auto-discovery)
            spice_config = {
                "gate_loop_components": ["U_GATE", "Q1", "R_GATE1"],
                "bootstrap_loop_components": ["U_GATE", "D_BOOT1", "C_BOOT1"],
                "dc_bus_components": ["C_BUS1", "Q1", "Q2"]
            }
            
            pipeline = SpiceValidationPipeline(config=spice_config)
            spice_results = pipeline.validate_placement(result.best_state, netlist, board)
            
            if spice_results:
                pipeline.print_report(spice_results)
            else:
                console.print("  [yellow]⚠[/] No SPICE results generated (check if ngspice is installed)")
                
        except Exception as e:
            console.print(f"  [red]✗[/] SPICE validation failed: {e}")

    # Print placement summary
    _print_placement_summary(
        console=console,
        netlist=netlist,
        state=result.best_state,
        constraints=constraints,
        min_separation=2.0,
    )

    console.print("\n[bold green]Done![/]")
