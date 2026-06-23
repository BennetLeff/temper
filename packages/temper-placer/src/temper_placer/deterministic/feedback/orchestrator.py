import logging
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING
from ..pipeline import DeterministicPipeline
from ..state import BoardState
from .violation_mapper import ViolationComponentMapper, DRCViolation
from .zone_adjuster import ZoneAdjuster, ZoneAdjustment, AdjustmentResult
from .drc_parser import parse_kicad_drc

if TYPE_CHECKING:
    from temper_placer.io.config_loader import PlacementConstraints

logger = logging.getLogger(__name__)


class AutomatedZeroDRC:
    """
    Orchestrates the feedback loop between pipeline execution and DRC results.
    """

    def __init__(
        self,
        pipeline: DeterministicPipeline,
        netlist: Any,
        initial_config: "Dict[str, Any] | PlacementConstraints",
        drc_runner: Callable[[], str],  # Returns path to DRC JSON report
        max_iterations: Optional[int] = None,
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

    def _get_zone_config(self) -> Dict[str, Any]:
        """Convert config to dict for mapper/adjuster."""
        zone_dict = {}

        if hasattr(self.config, "zones"):
            # PlacementConstraints
            for z in self.config.zones:
                zone_dict[z.name] = {
                    "bounds": ((z.bounds[0], z.bounds[1]), (z.bounds[2], z.bounds[3])),
                    "max_size": z.max_size
                    or (self.config.board_width_mm, self.config.board_height_mm),
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

    def run(self, initial_state: Optional[BoardState] = None) -> BoardState:
        """
        Execute the feedback loop.

        Args:
            initial_state: Optional starting state.

        Returns:
            The final BoardState after iterations.
        """
        state = initial_state

        for i in range(self.max_iterations):
            logger.info(f"--- Feedback Iteration {i + 1}/{self.max_iterations} ---")

            # 1. Run Pipeline
            # Note: The pipeline needs to be aware of the updated config
            # This might require re-initializing the pipeline or passing config to stages
            state = self.pipeline.run(state)

            # 2. Run DRC
            logger.info("Running DRC...")
            report_path = self.drc_runner()
            raw_violations = parse_kicad_drc(report_path)

            if not raw_violations:
                logger.info("Zero DRC violations achieved!")
                break

            logger.info(f"Found {len(raw_violations)} raw DRC violations")

            # 3. Map Violations
            self.mapper.zone_config = self._get_zone_config()
            mapped_violations = [self.mapper.map_violation(v) for v in raw_violations]

            # 4. Compute Adjustments
            self.adjuster.zone_config = self._get_zone_config()
            adjustment = self.adjuster.compute_adjustments(mapped_violations)

            if not adjustment.adjustments:
                logger.info("No further zone adjustments possible.")
                break

            # 5. Update Config
            self._update_config(adjustment)

            # Reset state for next iteration (re-placement needed with new zones)
            # We preserve core objects but clear derived state
            # EXP-5: Preserve locked_routes so successfully routed nets aren't re-routed
            # feat/hv-lv-guard-strip: Preserve config so HvLvPartitionStage and
            # any other config-reading stages still find their block.
            if state:
                logger.info(
                    f"EXP-5: Preserving {len(state.locked_routes)} locked routes for next iteration"
                )
                state = BoardState(
                    board=state.board,
                    netlist=state.netlist,
                    locked_routes=state.locked_routes,  # EXP-5: Preserve locks
                    config=state.config,  # feat/hv-lv-guard-strip: Preserve config
                )

        return state
