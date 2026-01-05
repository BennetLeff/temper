"""
Standalone runner for MVP-3 deterministic placement and routing pipeline.

This module provides a simplified interface for running the zone-based
deterministic pipeline without the template-based orchestrator.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import logging

from temper_placer.deterministic import DeterministicPipeline, BoardState
from temper_placer.deterministic.stages import (
    ZoneGeometryStage,
    ZoneAssignmentStage,
    SlotGenerationStage,
    ComponentAssignmentStage,
    ApplyPlacementsStage,
    ClearanceGridStage,
    LayerAssignmentStage,
    NetOrderingStage,
    SequentialRoutingStage,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules

logger = logging.getLogger(__name__)


@dataclass
class MVP3Config:
    """Configuration for MVP-3 pipeline execution."""
    
    layer_count: int = 4
    cell_size_mm: float = 0.25  # Finer grid for better DRC compliance
    slot_spacing_mm: float = 5.0
    deterministic_seed: int = 42


@dataclass
class MVP3Result:
    """Result of MVP-3 pipeline execution."""
    
    success: bool
    nets_routed: int
    total_nets: int
    components_placed: int
    total_components: int
    error: Optional[str] = None


class MVP3Runner:
    """
    Runs the MVP-3 deterministic placement and routing pipeline.
    
    This is a standalone runner that bypasses the template-based
    orchestrator and directly executes the zone-based deterministic
    pipeline stages.
    """
    
    def __init__(
        self,
        pcb_path: Path,
        config_path: Path,
        output_path: Path,
        mvp3_config: Optional[MVP3Config] = None,
    ):
        """
        Initialize the MVP3Runner.
        
        Args:
            pcb_path: Path to input KiCad PCB file
            config_path: Path to YAML configuration file
            output_path: Path for output KiCad PCB file
            mvp3_config: Optional MVP3-specific configuration
        """
        self.pcb_path = pcb_path
        self.config_path = config_path
        self.output_path = output_path
        self.mvp3_config = mvp3_config or MVP3Config()
        
    def run(self) -> MVP3Result:
        """
        Execute the MVP-3 pipeline.
        
        Returns:
            MVP3Result with execution summary
        """
        try:
            # Step 1: Load PCB
            logger.info(f"Loading PCB from {self.pcb_path}")
            parse_result = parse_kicad_pcb(self.pcb_path)
            netlist = parse_result.netlist
            
            logger.info(f"Loaded {len(netlist.nets)} nets, {len(netlist.components)} components")
            
            # Step 2: Load constraints
            logger.info(f"Loading constraints from {self.config_path}")
            constraints = load_constraints(self.config_path)
            
            logger.info(f"Zones: {[z.name for z in constraints.zones]}")
            logger.info(f"Net classes: {set(constraints.net_classes.values())}")
            
            # Step 3: Create board
            board = Board(
                width=constraints.board_width_mm,
                height=constraints.board_height_mm,
                zones=constraints.zones,
            )
            
            # Step 4: Create design rules
            design_rules = self._create_design_rules(constraints)
            logger.info(f"Design rules: {list(design_rules.net_classes.keys())}")
            
            # Step 5: Build pipeline
            logger.info("Building MVP-3 pipeline...")
            pipeline = self._build_pipeline(design_rules)
            
            # Step 6: Run pipeline
            logger.info("Running deterministic pipeline...")
            initial_state = BoardState(board=board, netlist=netlist)
            final_state = pipeline.run(initial_state)
            
            # Step 7: Collect results
            placements = dict(final_state.placements) if final_state.placements else {}
            routes = list(final_state.routes) if final_state.routes else []
            
            logger.info(f"Placement: {len(placements)}/{len(netlist.components)} components")
            logger.info(f"Routing: {len(routes)}/{len(netlist.nets)} nets")
            
            # Step 8: Export to KiCad
            logger.info(f"Exporting to {self.output_path}")
            self._export_to_kicad(final_state, parse_result)
            
            return MVP3Result(
                success=True,
                nets_routed=len(routes),
                total_nets=len(netlist.nets),
                components_placed=len(placements),
                total_components=len(netlist.components),
            )
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return MVP3Result(
                success=False,
                nets_routed=0,
                total_nets=0,
                components_placed=0,
                total_components=0,
                error=str(e),
            )
    
    def _create_design_rules(self, constraints) -> DesignRules:
        """Convert constraints net class rules to DesignRules object."""
        design_rules = DesignRules()
        design_rules.net_classes = {}
        
        for name, rule in constraints.net_class_rules.items():
            design_rules.net_classes[name] = NetClassRules(
                name=name,
                trace_width=rule.trace_width_mm,
                clearance=rule.clearance_mm,
                via_diameter=rule.via_size_mm,
                via_drill=rule.via_drill_mm,
            )
        
        return design_rules
    
    def _build_pipeline(self, design_rules: DesignRules) -> DeterministicPipeline:
        """Construct the MVP-3 pipeline with all stages."""
        return DeterministicPipeline(stages=[
            # Phase 1-4: Placement
            ZoneGeometryStage(),
            ZoneAssignmentStage(),
            SlotGenerationStage(slot_spacing_mm=self.mvp3_config.slot_spacing_mm),
            ComponentAssignmentStage(),
            ApplyPlacementsStage(),
            # Phase 5: Routing
            ClearanceGridStage(
                cell_size_mm=self.mvp3_config.cell_size_mm,
                layer_count=self.mvp3_config.layer_count,
            ),
            LayerAssignmentStage(),
            NetOrderingStage(),
            SequentialRoutingStage(design_rules=design_rules),
        ])
    
    def _export_to_kicad(self, final_state: BoardState, parse_result) -> None:
        """Export the final state to a KiCad PCB file."""
        from temper_placer.io.kicad_writer import (
            write_placements_to_pcb,
            write_routes_to_pcb,
            build_net_name_to_index_map,
            PlacementUpdate,
        )
        
        # Step 1: Convert placements to KiCad format
        placements_dict = {}
        if final_state.placements:
            for ref, (x, y) in final_state.placements:
                placements_dict[ref] = PlacementUpdate(
                    ref=ref,
                    x=x,
                    y=y,
                    rotation=0.0  # TODO: Get actual rotation from state
                )
        
        # Step 2: Write placements to output PCB
        logger.info(f"Writing {len(placements_dict)} placements to {self.output_path}")
        placement_result = write_placements_to_pcb(
            template_pcb=self.pcb_path,
            output_pcb=self.output_path,
            placements=placements_dict,
            preserve_unmatched=True,
        )
        
        logger.info(f"Placement export: {placement_result.components_updated} components updated")
        
        if placement_result.has_warnings:
            for warning in placement_result.warnings:
                logger.warning(warning)
        
        # Step 3: Add routes to the PCB (if any were generated)
        if final_state.routes and len(final_state.routes) > 0:
            logger.info(f"Writing {len(final_state.routes)} routes to {self.output_path}")
            
            # Build net name → index mapping from the PCB
            net_map = build_net_name_to_index_map(self.output_path)
            
            # Write routes (traces) to the same file
            route_result = write_routes_to_pcb(
                template_pcb=self.output_path,  # Use the file we just wrote
                output_pcb=self.output_path,     # Overwrite with routes added
                routes=final_state.routes,
                net_name_to_index=net_map,
                clear_existing=False,  # Keep any existing traces
            )
            
            logger.info(f"Route export: {route_result.components_updated} traces added")
            
            if route_result.has_warnings:
                for warning in route_result.warnings:
                    logger.warning(warning)
        else:
            logger.info("No routes to export")

