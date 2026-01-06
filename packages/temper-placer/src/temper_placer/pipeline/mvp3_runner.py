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
from temper_placer.deterministic.feedback import AutomatedZeroDRC
from temper_placer.deterministic.stages import (
    ZoneGeometryStage,
    ZoneAssignmentStage,
    SlotGenerationStage,
    ComponentAssignmentStage,
    ApplyPlacementsStage,
    CourtyardCheckStage,
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
    cell_size_mm: float = 0.25  # Optimal grid for DRC compliance and performance
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
            
            # Extract pad sizes from KiCad board for accurate valid blocking
            # We need to load raw KiCad board because parse_result.board is a simplified Core object
            from kiutils.board import Board as KiBoard
            raw_board = KiBoard.from_file(str(self.pcb_path))
            
            self.pad_sizes_map = {}
            if raw_board.footprints:
                 for fp in raw_board.footprints:
                    for pad in fp.pads:
                        key = (fp.properties.get('Reference', ''), pad.number)
                        self.pad_sizes_map[key] = pad
            logger.info(f"Extracted sizes for {len(self.pad_sizes_map)} pads")

            # Extract Courtyards
            from temper_placer.deterministic.geometry.courtyard import Courtyard
            self.courtyards_map = {}
            if raw_board.footprints:
                for fp in raw_board.footprints:
                    ref = fp.properties.get('Reference', '')
                    if not ref: continue
                    
                    if ref == 'J_AC_IN':
                        print(f"DEBUG J_AC_IN attrs: {dir(fp)}")
                        print(f"DEBUG J_AC_IN graphicItems count: {len(fp.graphicItems) if hasattr(fp, 'graphicItems') else 'N/A'}")
                    
                    points = []
                    # Try to find CrtYd items
                    if fp.graphicItems:
                        for item in fp.graphicItems:
                            if True: 
                                print(f"DEBUG item: ref={ref} type={type(item)} layer={getattr(item, 'layer', 'N/A')}")
                            
                            if hasattr(item, 'layer') and item.layer in ('F.CrtYd', 'B.CrtYd'):
                                # Handle Polygon/Polyline
                                pts = []
                                if hasattr(item, 'points'): # kiutils ~1.0
                                    pts = item.points
                                elif hasattr(item, 'coordinates'):
                                    pts = item.coordinates
                                
                                if pts:
                                    points = [(p.X, p.Y) for p in pts]
                                    break # Found one
                    
                    # Fallback: Generate courtyard from pads if no graphic items found
                    if not points and fp.pads:
                        # Find bounding box of all pads
                        min_x, min_y = float('inf'), float('inf')
                        max_x, max_y = float('-inf'), float('-inf')
                        has_pads = False
                        
                        for pad in fp.pads:
                            # Pad position is relative to footprint center
                            px, py = pad.position.X, pad.position.Y
                            w, h = pad.size.X, pad.size.Y
                            
                            # Expand by half size + large margin for safety
                            margin = 0.5
                            min_x = min(min_x, px - w/2 - margin)
                            min_y = min(min_y, py - h/2 - margin)
                            max_x = max(max_x, px + w/2 + margin)
                            max_y = max(max_y, py + h/2 + margin)
                            has_pads = True
                        
                        if has_pads:
                            # Calculate geometric center of the bounds
                            center_x = (min_x + max_x) / 2.0
                            center_y = (min_y + max_y) / 2.0
                            
                            # Create rectangular polygon CENTERED at (0,0)
                            # This matches state.placements which tracks geometric center
                            half_w = (max_x - min_x) / 2.0
                            half_h = (max_y - min_y) / 2.0
                            
                            points = [
                                (-half_w, -half_h),
                                (half_w, -half_h),
                                (half_w, half_h),
                                (-half_w, half_h)
                            ]
                            # logger.info(f"Generated fallback courtyard for {ref}")

                    self.courtyards_map[ref] = Courtyard(
                        component_ref=ref, 
                        points=points if points else [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)] # Ultimate fallback
                    )
            logger.info(f"Extracted {len(self.courtyards_map)} courtyards")
            if len(self.courtyards_map) > 0:
                print(f"DEBUG: Extracted {len(self.courtyards_map)} courtyards. Keys: {list(self.courtyards_map.keys())[:5]}")
                sample = list(self.courtyards_map.values())[0]
                print(f"DEBUG: Sample Courtyard {sample.component_ref}: {sample.points}")
            else:
                print("DEBUG: No courtyards extracted!")
            
            # Step 5: Build pipeline
            logger.info("Building MVP-3 pipeline...")
            pipeline = self._build_pipeline(
                design_rules, 
                constraints.net_classes,
                fixed_placements=constraints.fixed_positions
            )
            
            # Step 6: Run pipeline
            logger.info("Running deterministic pipeline...")
            initial_state = BoardState(board=board, netlist=netlist)
            
            # Check if feedback loop is requested
            if hasattr(constraints, 'feedback') and constraints.feedback.max_iterations > 1:
                logger.info(f"Enabling Automated Zero-DRC Feedback Loop (max_iterations={constraints.feedback.max_iterations})")
                
                # We need a DRC runner. For now, we use a simple placeholder or 
                # a callback that could eventually call KiCad-CLI.
                # Since MVP3Runner is often used in headless/CI, we might just 
                # use internal validation or a provided callback.
                
                def drc_callback() -> str:
                    # Placeholder for actual KiCad DRC execution
                    # In a real environment, this would run 'kicad-cli pcb drc'
                    # For this milestone, we might rely on the internal DRCOracle 
                    # but AutomatedZeroDRC expects a JSON report file.
                    report_path = Path("drc_report.json")
                    # If we don't have a real runner yet, we could generate a mock
                    # or skip if not in a KiCad-enabled environment.
                    return str(report_path)

                orchestrator = AutomatedZeroDRC(
                    pipeline=pipeline,
                    netlist=netlist,
                    initial_config=constraints,
                    drc_runner=drc_callback
                )
                final_state = orchestrator.run(initial_state)
            else:
                final_state = pipeline.run(initial_state)
            
            # Step 7: Collect results
            placements = dict(final_state.placements) if final_state.placements else {}
            routes = list(final_state.routes) if final_state.routes else []
            
            # Count unique routed nets (routes contains segments, we need unique nets)
            routed_net_names = {route.net for route in routes if route.net}
            if final_state.vias:
                routed_net_names.update({via.net for via in final_state.vias if via.net})
            num_routed_nets = len(routed_net_names)
            
            logger.info(f"Placement: {len(placements)}/{len(netlist.components)} components")
            logger.info(f"Routing: {num_routed_nets}/{len(netlist.nets)} nets")
            
            # Step 8: Export to KiCad
            logger.info(f"Exporting to {self.output_path}")
            self._export_to_kicad(final_state, parse_result)
            
            return MVP3Result(
                success=True,
                nets_routed=num_routed_nets,
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
        
        # NEW: Populate net class assignments from config
        design_rules.net_class_assignments = constraints.net_classes
        
        return design_rules
    
    def _build_pipeline(self, 
                        design_rules: DesignRules, 
                        net_classes: dict[str, str] = None,
                        fixed_placements: dict = None) -> DeterministicPipeline:
        """Construct the MVP-3 pipeline with all stages."""
        from temper_placer.deterministic.stages import (
            SetupStage, 
            DRCValidationStage, 
            ConnectivityValidationStage
        )
        
        # Build net class clearance mapping for the grid
        net_class_clearances = {
            name: rules.clearance 
            for name, rules in design_rules.net_classes.items()
        }
        
        return DeterministicPipeline(stages=[
            # Phase 0: Setup
            SetupStage(),
            # Phase 1-4: Placement
            ZoneGeometryStage(),
            ZoneAssignmentStage(),
            SlotGenerationStage(slot_spacing_mm=self.mvp3_config.slot_spacing_mm),
            ComponentAssignmentStage(
                slot_spacing=self.mvp3_config.slot_spacing_mm,
                fixed_placements=fixed_placements
            ),
            ApplyPlacementsStage(),
            # Resolution: Resolve physical overlaps
            CourtyardCheckStage(courtyards=self.courtyards_map),
            # Phase 5: Routing
            ClearanceGridStage(
                cell_size_mm=self.mvp3_config.cell_size_mm,
                layer_count=self.mvp3_config.layer_count,
                pad_sizes=self.pad_sizes_map,  # Inject pad sizes
                net_class_clearances=net_class_clearances,
            ),
            LayerAssignmentStage(net_classes=net_classes),
            NetOrderingStage(),
            SequentialRoutingStage(
                design_rules=design_rules,
                pad_sizes=self.pad_sizes_map
            ),
            # Phase 6: Validation
            DRCValidationStage(),
            ConnectivityValidationStage(),
        ])
    
    def _export_to_kicad(self, final_state: BoardState, parse_result) -> None:
        """Export the final state to a KiCad PCB file."""
        from temper_placer.io.kicad_writer import (
            write_placements_to_pcb,
            write_routes_to_pcb,
            write_zones_to_pcb,
            build_net_name_to_index_map,
            PlacementUpdate,
            strip_routing,
        )
        
        # Step 1: Strip existing routing from template to create a clean slate
        logger.info(f"Stripping legacy routing from {self.pcb_path}")
        strip_result = strip_routing(
            input_pcb=self.pcb_path,
            output_pcb=self.output_path,
            keep_zones=True,
            keep_fills=False
        )
        logger.info(f"Stripped {strip_result.traces_removed} traces and {strip_result.vias_removed} vias")

        # Step 2: Convert placements to KiCad format
        placements_dict = {}
        if final_state.placements:
            for ref, (x, y) in final_state.placements:
                placements_dict[ref] = PlacementUpdate(
                    ref=ref,
                    x=x,
                    y=y,
                    rotation=0.0  # TODO: Get actual rotation from state
                )
        
        # Step 3: Write placements to the already-stripped output PCB
        logger.info(f"Writing {len(placements_dict)} placements to {self.output_path}")
        placement_result = write_placements_to_pcb(
            template_pcb=self.output_path,  # Use the stripped board as template
            output_pcb=self.output_path,
            placements=placements_dict,
            preserve_unmatched=True,
        )
        
        logger.info(f"Placement export: {placement_result.components_updated} components updated")
        
        if placement_result.has_warnings:
            for warning in placement_result.warnings:
                logger.warning(warning)
        
        # Step 4: Add routes to the PCB (if any were generated)
        if final_state.routes and len(final_state.routes) > 0:
            logger.info(f"Writing {len(final_state.routes)} routes to {self.output_path}")
            
            # Build net name → index mapping from the PCB
            net_map = build_net_name_to_index_map(self.output_path)
            
            # Write routes (traces) and vias to the same file
            route_result = write_routes_to_pcb(
                template_pcb=self.output_path,  # Use the file we just wrote
                output_pcb=self.output_path,     # Overwrite with routes added
                routes=final_state.routes,
                vias=final_state.vias,
                net_name_to_index=net_map,
                clear_existing=True,  # Clear any remaining traces just in case
            )
            
            logger.info(f"Route export: {route_result.components_updated} traces added")
            
            if route_result.has_warnings:
                for warning in route_result.warnings:
                    logger.warning(warning)
        else:
            logger.info("No routes to export")

        # Step 5: Write zones for power planes
        zones_to_create = []
        if final_state.layer_assignments and final_state.board:
            # Determine board polygon
            if final_state.board.outline_polygon:
                poly_pts = final_state.board.outline_polygon
            else:
                w, h = final_state.board.width, final_state.board.height
                ox, oy = final_state.board.origin
                poly_pts = [(ox, oy), (ox+w, oy), (ox+w, oy+h), (ox, oy+h)]
            
            layer_idx_to_name = {1: "In1.Cu", 2: "In2.Cu"}
            
            for assignment in final_state.layer_assignments:
                if hasattr(assignment, 'is_plane') and assignment.is_plane:
                    layer_name = layer_idx_to_name.get(assignment.layer)
                    if layer_name:
                        zones_to_create.append({
                            'net_name': assignment.net_name,
                            'layer': layer_name,
                            'polygon_pts': poly_pts
                        })
        
        if zones_to_create:
            logger.info(f"Writing {len(zones_to_create)} zones to {self.output_path}")
            net_map = build_net_name_to_index_map(self.output_path)
            
            zone_result = write_zones_to_pcb(
                template_pcb=self.output_path,
                output_pcb=self.output_path,
                zones=zones_to_create,
                net_name_to_index=net_map
            )
            logger.info(f"Zone export: {zone_result.components_updated} zones added")
            if zone_result.has_warnings:
                for warning in zone_result.warnings:
                    logger.warning(warning)
        else:
            logger.info("No power plane zones to export")
