import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import temper_orchestration as _to

from .. import DeterministicPipeline
from ..state import BoardState
from .drc_parser import parse_kicad_drc
from .violation_mapper import ViolationComponentMapper
from .zone_adjuster import AdjustmentResult, ZoneAdjuster

if TYPE_CHECKING:
    from temper_placer.io.config_loader import PlacementConstraints

logger = logging.getLogger(__name__)


class AutomatedZeroDRC:
    """
    Orchestrates the feedback loop between pipeline execution and DRC results.

    Orchestration-port unit U-F (Rust Orchestration Engine plan
    2026-08-09-001): the iterate-until-clean LOOP of ``run()`` is implemented
    in Rust (``temper-orchestration``'s ``run_automated_zero_drc``
    pyfunction), which drives the per-iteration call-backs (``pipeline.run``,
    the DRC runner, the report parser, the violation mapper, the zone
    adjuster and the config update) through the Rust
    ``PipelineRunner<BoardState>`` in the oracle's order and terminates on
    the oracle's conditions (clean parse, empty adjustments, iteration cap).
    The construction/marshalling (config parsing, mapper/adjuster wiring,
    ``_get_zone_config`` / ``_inject_zone_config`` / ``_update_config``) and
    the subprocess DRC invocation (``drc_runner``) stay Python; the leaf
    mapping/adjustment compute is the already-landed design-bundle kernels.
    """

    def __init__(
        self,
        pipeline: DeterministicPipeline,
        netlist: Any,
        initial_config: "dict[str, Any] | PlacementConstraints",
        drc_runner: Callable[[], str],  # Returns path to DRC JSON report
        max_iterations: int | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            pipeline: The deterministic pipeline to execute.
            netlist: The netlist containing components.
            initial_config: The initial configuration dictionary or PlacementConstraints object.
            drc_runner: A callback that executes DRC and returns the report file path.
            max_iterations: Maximum number of feedback iterations (overrides config).
        """
        self.pipeline = pipeline
        self.netlist = netlist
        self.config = initial_config
        self.drc_runner = drc_runner

        # Load feedback settings from config
        if hasattr(initial_config, "feedback"):
            # Handling PlacementConstraints object
            feedback_config = initial_config.feedback
            self.max_iterations = max_iterations or feedback_config.max_iterations
            violation_threshold = feedback_config.violation_threshold
            expansion_per_violation = feedback_config.expansion_per_violation
        else:
            # Handling raw dict
            feedback_config = initial_config.get("feedback", {})
            self.max_iterations = max_iterations or feedback_config.get("max_iterations", 5)
            violation_threshold = feedback_config.get("violation_threshold", 5)
            expansion_per_violation = feedback_config.get("expansion_per_violation", 0.5)

        # Initialize sub-components
        self.mapper = ViolationComponentMapper(netlist, self._get_zone_config())
        self.adjuster = ZoneAdjuster(
            self._get_zone_config(),
            violation_threshold=violation_threshold,
            expansion_per_violation=expansion_per_violation,
        )

        # Inject zone config into the pipeline's ZoneGeometryStage if it exists
        self._inject_zone_config()

    def _inject_zone_config(self):
        """Inject zone config into pipeline stages."""
        zones = []
        if hasattr(self.config, "zones"):
            # PlacementConstraints
            for z in self.config.zones:
                zones.append(
                    {
                        "name": z.name,
                        "bounds_ratio": [
                            z.bounds[0] / self.config.board_width_mm,
                            z.bounds[1] / self.config.board_height_mm,
                            z.bounds[2] / self.config.board_width_mm,
                            z.bounds[3] / self.config.board_height_mm,
                        ],
                    }
                )
        else:
            # Raw dict
            zones = self.config.get("zones")

        for stage in self.pipeline.stages:
            if stage.name == "zone_geometry" and hasattr(stage, "zone_config"):
                stage.zone_config = zones

    def _get_zone_config(self) -> dict[str, Any]:
        """Convert config to dict for mapper/adjuster."""
        zone_dict = {}

        if hasattr(self.config, "zones"):
            # PlacementConstraints
            for z in self.config.zones:
                zone_dict[z.name] = {
                    "bounds": ((z.bounds[0], z.bounds[1]), (z.bounds[2], z.bounds[3])),
                    "max_size": z.max_size
                    or (self.config.board_width_mm, self.config.board_height_mm),  # type: ignore[union-attr]
                    "can_expand": z.can_expand,
                }
        else:
            # Raw dict
            board_w = self.config["board"]["width_mm"]
            board_h = self.config["board"]["height_mm"]

            for zone in self.config.get("zones", []):
                name = zone["name"]
                ratio = zone.get("bounds_ratio", [0, 0, 1, 1])
                bounds = (
                    (ratio[0] * board_w, ratio[1] * board_h),
                    (ratio[2] * board_w, ratio[3] * board_h),
                )
                zone_dict[name] = {
                    "bounds": bounds,
                    "max_size": zone.get("max_size", (board_w, board_h)),
                    "can_expand": zone.get("can_expand", ["right", "left", "up", "down"]),
                }
        return zone_dict

    def _update_config(self, adjustment: AdjustmentResult):
        """Update the configuration with new zone bounds."""
        if hasattr(self.config, "zones"):
            # Update PlacementConstraints
            for zone_name, adj in adjustment.adjustments.items():
                zone = next((z for z in self.config.zones if z.name == zone_name), None)
                if not zone:
                    continue

                # For simplicity in stripe layout, we expand to the right and shift others
                # In a more general case, we'd need a 2D packer
                idx = self.config.zones.index(zone)

                # Shift right boundary
                new_bounds = list(zone.bounds)
                new_bounds[2] += adj.delta_width
                zone.bounds = tuple(new_bounds)

                # Shift all subsequent zones
                for next_idx in range(idx + 1, len(self.config.zones)):
                    nz = self.config.zones[next_idx]
                    nb = list(nz.bounds)
                    nb[0] += adj.delta_width
                    nb[2] += adj.delta_width
                    nz.bounds = tuple(nb)

            # Re-inject updated config
            self._inject_zone_config()
        else:
            # Update raw dict
            board_w = self.config["board"]["width_mm"]
            zone_map = {z["name"]: i for i, z in enumerate(self.config["zones"])}

            for zone_name, adj in adjustment.adjustments.items():
                if zone_name not in zone_map:
                    continue

                idx = zone_map[zone_name]
                dr = adj.delta_width / board_w

                if dr > 0:
                    self.config["zones"][idx]["bounds_ratio"][2] += dr
                    for next_idx in range(idx + 1, len(self.config["zones"])):
                        self.config["zones"][next_idx]["bounds_ratio"][0] += dr
                        self.config["zones"][next_idx]["bounds_ratio"][2] += dr

    def run(self, initial_state: BoardState | None = None) -> BoardState | None:
        """
        Execute the feedback loop.

        Orchestration-port unit U-F: the iterate-until-clean LOOP is
        implemented in Rust (``temper-orchestration.run_automated_zero_drc``),
        which sequences the per-iteration call-backs through the Rust
        ``PipelineRunner<BoardState>``. The call-backs cross the FFI as
        arguments: the pipeline object, the DRC runner (subprocess boundary,
        stays Python), the report parser (file read, stays Python), the
        mapper/adjuster instances (leaf compute already Rust), and the
        config-marshalling bound methods ``_get_zone_config`` /
        ``_update_config`` (stay Python). The Rust loop preserves the
        oracle's call order, break conditions, iteration cap, EXP-5 state
        reset and log messages.

        Args:
            initial_state: Optional starting state.

        Returns:
            The final BoardState after iterations.
        """
        return _to.run_automated_zero_drc(
            pipeline=self.pipeline,
            drc_runner=self.drc_runner,
            parse_kicad_drc=parse_kicad_drc,
            mapper=self.mapper,
            adjuster=self.adjuster,
            get_zone_config=self._get_zone_config,
            update_config=self._update_config,
            max_iterations=self.max_iterations,
            initial_state=initial_state,
        )
