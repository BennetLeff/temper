"""Thermal anchoring pipeline stage (Stage 0).

Runs between the ``input`` stage and ``topological`` stage.  Constructs the
thermal potential field, greedily assigns power devices to field minima,
validates safety gates, and writes fixed positions to the constraints object
so the downstream pipeline treats anchored devices as immutable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from temper_placer.pipeline.dag_types import DataContext, StageResult

logger = logging.getLogger(__name__)


class ThermalAnchoringStage:
    """Stage 0: pre-place power devices at thermally optimal positions.

    Reads ``board``, ``netlist``, ``constraints`` from the DataContext.
    When ``initialization.thermal_anchoring`` is True AND at least one
    ``ThermalConstraint`` exists, builds the potential field, assigns
    anchors, validates safety gates, and writes to
    ``constraints.fixed_positions`` / ``constraints.fixed_components``.

    If the gate conditions are not met the stage is a no-op that returns
    ``StageResult.success()``.
    """

    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()

        board = context.get("board")
        netlist = context.get("netlist")
        constraints = context.get("constraints")

        # ------------------------------------------------------------------
        # Gate check (R6)
        # ------------------------------------------------------------------
        if constraints is None:
            logger.info("No constraints object in context; thermal anchoring skipped.")
            return StageResult.success()

        init_cfg = getattr(constraints, "initialization", None)
        if init_cfg is None or not init_cfg.thermal_anchoring:
            logger.info(
                "Thermal anchoring not enabled (initialization.thermal_anchoring=%s).",
                getattr(init_cfg, "thermal_anchoring", None),
            )
            return StageResult.success()

        thermal_constraints = getattr(constraints, "thermal_constraints", [])
        if not thermal_constraints:
            logger.info(
                "No thermal_constraints in PCL; thermal anchoring skipped "
                "despite initialization.thermal_anchoring=True."
            )
            return StageResult.success()

        if board is None or netlist is None:
            logger.warning(
                "Board or netlist missing from DataContext; thermal anchoring skipped."
            )
            return StageResult.success()

        # ------------------------------------------------------------------
        # Gather power device data
        # ------------------------------------------------------------------
        from temper_placer.io.config_loader import infer_rjc
        from temper_placer.physics.thermal_potential import (
            ThermalAnchoringSafetyError,
            ThermalPotentialConfig,
            assign_thermal_anchors,
            validate_heatsink_edge,
            validate_stackup_for_anchoring,
            validate_tj_safety,
        )

        thermal_props = getattr(constraints, "thermal_properties", None)
        if thermal_props is None:
            logger.warning(
                "thermal_properties not found in constraints; "
                "thermal anchoring skipped."
            )
            return StageResult.success()

        high_power_refs = thermal_props.high_power_components
        power_dissipation = getattr(thermal_props, "power_dissipation_w", {})
        rated_tj_max_dict = getattr(thermal_props, "rated_tj_max", {})

        # Filter to devices with power_dissipation_w > 0
        power_devices: list[tuple[str, float]] = []
        for ref in high_power_refs:
            pwr = power_dissipation.get(ref, 0.0)
            if pwr > 0:
                power_devices.append((ref, pwr))

        if not power_devices:
            logger.warning(
                "No high_power_components with power_dissipation_w > 0; "
                "thermal anchoring skipped."
            )
            return StageResult.success()

        # Sort: descending power, alphabetical tie-break (determinism, SC7)
        power_devices.sort(key=lambda x: (-x[1], x[0]))

        # ------------------------------------------------------------------
        # Determine heatsink edge (first ThermalConstraint.edge)
        # ------------------------------------------------------------------
        edge_name = "TOP"  # default
        for tc in thermal_constraints:
            if hasattr(tc, "edge"):
                edge_name = tc.edge
                break
            elif hasattr(tc, "components") and hasattr(tc, "prefer_edge"):
                # Legacy ThermalConstraint from config_loader
                edge_name = "TOP"  # default for legacy format
                break

        # ------------------------------------------------------------------
        # Stackup validation (R5) --- adjust phi_copper weight
        # ------------------------------------------------------------------
        board_bounds = (0.0, 0.0, board.width, board.height)
        n_layers = len(board.layer_stackup.layers) if board.layer_stackup else 4
        stackup_config = validate_stackup_for_anchoring(n_layers)

        # ------------------------------------------------------------------
        # Safety gate: heatsink edge validation (R3) --- HARD ABORT
        # ------------------------------------------------------------------
        try:
            validate_heatsink_edge(board_bounds, edge_name)
        except ThermalAnchoringSafetyError as exc:
            from temper_placer.pipeline.state import PipelineError, PipelinePhase

            raise PipelineError(
                f"Thermal anchoring safety gate FAILED: {exc}",
                phase=PipelinePhase.GEOMETRIC,
            ) from exc

        # ------------------------------------------------------------------
        # Build config, superimpose phi, assign anchors
        # ------------------------------------------------------------------
        grid_res = init_cfg.anchoring_grid_resolution if init_cfg else 50
        config = ThermalPotentialConfig(
            edge_weight=1.0,
            copper_weight=stackup_config.copper_weight,
            coupling_weight=1.0,
            exclusion_weight=1.0,
            convection_weight=1.0 if thermal_props.airflow_vector else 0.0,
            grid_resolution=grid_res,
        )

        # Build zone map for per-component zone containment (R14)
        comp_zones: dict[str, tuple[float, float, float, float]] = {}
        for comp in netlist.components:
            if comp.zone and board._zone_map:
                zone = board._zone_map.get(comp.zone)
                if zone and hasattr(zone, "bounds"):
                    comp_zones[comp.ref] = zone.bounds

        anchors = assign_thermal_anchors(
            board_bounds=board_bounds,
            edge=edge_name,
            power_devices=power_devices,
            zones=comp_zones if comp_zones else None,
            keepouts=board.keepouts if hasattr(board, "keepouts") else None,
            config=config,
            copper_zones=getattr(constraints, "copper_zones", None),
            airflow_vector=thermal_props.airflow_vector,
            min_separation_mm=thermal_props.min_separation_mm,
        )

        if not anchors:
            logger.warning(
                "Thermal anchoring produced no anchors; continuing without fixed positions."
            )
            return StageResult.success()

        # ------------------------------------------------------------------
        # Safety gate: Tj validation (R4) --- HARD ABORT
        # ------------------------------------------------------------------
        for ref, (ax, ay) in anchors.items():
            from temper_placer.losses.thermal import compute_edge_distance

            import jax.numpy as jnp

            pos = jnp.array([ax, ay])
            bounds_arr = jnp.array([0.0, 0.0, board.width, board.height])
            edge_dist = float(compute_edge_distance(pos, bounds_arr, edge_name))

            power_w = power_dissipation.get(ref, 0.0)
            # Find Rjc from component
            rjc: float | None = None
            for comp in netlist.components:
                if comp.ref == ref:
                    rjc = getattr(comp, "Rjc", None)
                    break
            if rjc is None:
                rjc = infer_rjc(
                    next((c.footprint for c in netlist.components if c.ref == ref), None)
                )

            rated_tj = rated_tj_max_dict.get(ref)

            try:
                validate_tj_safety(ref, power_w, rjc, rated_tj, edge_dist)
            except ThermalAnchoringSafetyError as exc:
                from temper_placer.pipeline.state import PipelineError, PipelinePhase

                raise PipelineError(
                    f"Thermal anchoring safety gate FAILED: {exc}",
                    phase=PipelinePhase.GEOMETRIC,
                ) from exc

        # ------------------------------------------------------------------
        # Write anchors to constraints
        # ------------------------------------------------------------------
        from temper_placer.io.config_loader import apply_fixed_components_to_netlist

        for ref, (x, y) in anchors.items():
            constraints.fixed_positions[ref] = (x, y)
            if ref not in constraints.fixed_components:
                constraints.fixed_components.append(ref)

        apply_fixed_components_to_netlist(netlist, constraints)

        # ------------------------------------------------------------------
        # Mark state for downstream use (U6: curriculum weight adjustment)
        # ------------------------------------------------------------------
        state.thermal_anchoring_applied = True

        elapsed = time.time() - start
        logger.info(
            "Thermal anchoring placed %d devices in %.2f ms. "
            "Anchors: %s",
            len(anchors),
            elapsed * 1000,
            {ref: f"({x:.1f}, {y:.1f})" for ref, (x, y) in anchors.items()},
        )

        if elapsed > 0.500:
            logger.warning(
                "Thermal anchoring took %.0f ms (>500 ms budget for R17).",
                elapsed * 1000,
            )

        return StageResult(outputs={}, duration_s=elapsed)
