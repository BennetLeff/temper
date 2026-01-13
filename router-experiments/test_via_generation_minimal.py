
import numpy as np
import logging
from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_via_generation():
    """Minimal test case for via generation.
    
    Setup:
    - 4 layer board
    - Source pin at (10, 10) on L1 (Top)
    - Target pin at (20, 20) on L4 (Bottom)
    - No obstacles
    
    Expected:
    - Path found spanning multiple layers
    - via_count >= 1
    """
    grid_size = (40, 40)
    cell_size = 0.5 # mm
    num_layers = 4
    
    # High via cost to simulate production settings
    via_cost = 25.0
    
    router = MazeRouter(
        grid_size=grid_size,
        cell_size_mm=cell_size,
        num_layers=num_layers,
        via_cost=via_cost
    )
    
    start = (10, 10)
    end = (20, 20)
    
    # Net assignment: Allow all layers
    assignment = LayerAssignment(
        net="TEST_NET",
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT]
    )
    
    # We want to route from Layer 0 to Layer 3
    logger.info("Starting route search from (10,10,0) to (20,20,3)")
    
    # We use find_path_rrr directly
    path = router.find_path_rrr(
        start, 
        end, 
        layer=0, 
        allow_layer_change=True,
        end_layer=3, # Target layer L4
        allowed_layers=[0, 1, 2, 3]
    )
    
    if path:
        logger.info(f"SUCCESS: Path found with length={len(path)}")
        layers_used = set(c.layer for c in path)
        logger.info(f"Layers used: {layers_used}")
        
        via_count = 0
        for i in range(1, len(path)):
            if path[i].layer != path[i-1].layer:
                via_count += 1
        
        logger.info(f"Via count: {via_count}")
        
        if via_count > 0:
            print("TEST_RESULT: PASS (Vias generated)")
        else:
            print("TEST_RESULT: FAIL (No vias generated despite layer change requirement)")
    else:
        logger.error("FAILURE: No path found")
        print("TEST_RESULT: FAIL (No path found)")

if __name__ == "__main__":
    test_via_generation()
