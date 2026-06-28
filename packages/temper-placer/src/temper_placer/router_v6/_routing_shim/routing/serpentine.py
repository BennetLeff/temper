"""
Phase 3: Length Matching Utilities

Functions for measuring path lengths and generating serpentine patterns
to equalize differential pair trace lengths.
"""

from typing import List, Tuple
import math


def measure_path_length(cells: List[Tuple[int, int, int]], cell_size_mm: float) -> float:
    """
    Measure the physical length of a routed path in mm.
    
    Args:
        cells: List of (x, y, layer) grid cells
        cell_size_mm: Size of each grid cell
        
    Returns:
        Total path length in mm
    """
    if len(cells) < 2:
        return 0.0
    
    total_length = 0.0
    for i in range(len(cells) - 1):
        x1, y1, l1 = cells[i]
        x2, y2, l2 = cells[i + 1]
        
        # Manhattan distance in grid cells
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        # Convert to mm
        segment_length = (dx + dy) * cell_size_mm
        
        # Add via penalty if layer changes
        if l1 != l2:
            segment_length += 0.5  # Via adds ~0.5mm equivalent length
        
        total_length += segment_length
    
    return total_length


def generate_serpentine_pattern(
    amplitude_mm: float,
    frequency: int,
    insertion_index: int,
    trace_cells: List[Tuple[int, int, int]],
    cell_size_mm: float,
    perpendicular_direction: Tuple[int, int],
) -> List[Tuple[int, int, int]]:
    """
    Generate a serpentine (zigzag) pattern to add length to a trace.
    
    Args:
        amplitude_mm: Peak-to-peak amplitude of serpentine in mm
        frequency: Number of zigzag cycles
        insertion_index: Index in trace_cells where to insert pattern
        trace_cells: Original trace path
        cell_size_mm: Grid cell size
        perpendicular_direction: (dx, dy) perpendicular to trace direction
        
    Returns:
        New trace with serpentine pattern inserted
    """
    # Convert amplitude to grid cells
    amplitude_cells = int(amplitude_mm / cell_size_mm)
    if amplitude_cells < 1:
        return trace_cells.copy()  # Too small to insert
    
    # Get insertion point
    if insertion_index >= len(trace_cells):
        insertion_index = len(trace_cells) // 2  # Default to middle
    
    base_x, base_y, layer = trace_cells[insertion_index]
    perp_dx, perp_dy = perpendicular_direction
    
    # Generate zigzag pattern
    pattern = []
    for cycle in range(frequency):
        # Zigzag: go perpendicular, then back
        for step in range(amplitude_cells):
            pattern.append((
                base_x + perp_dx * step,
                base_y + perp_dy * step,
                layer
            ))
        
        # Return to centerline
        for step in range(amplitude_cells, 0, -1):
            pattern.append((
                base_x + perp_dx * step,
                base_y + perp_dy * step,
                layer
            ))
    
    # Insert pattern into trace
    new_trace = trace_cells[:insertion_index] + pattern + trace_cells[insertion_index:]
    
    return new_trace


def calculate_serpentine_params(
    length_deficit_mm: float,
    available_space_mm: float,
    cell_size_mm: float,
) -> Tuple[float, int]:
    """
    Calculate serpentine amplitude and frequency to add desired length.
    
    Geometric formula: Added length ≈ 4 × amplitude × frequency
    (Each zigzag cycle adds 4 × amplitude)
    
    Args:
        length_deficit_mm: How much length to add
        available_space_mm: Available perpendicular space
        cell_size_mm: Grid cell size
        
    Returns:
        (amplitude_mm, frequency) tuple
    """
    # Use 50% of available space for amplitude (leave clearance)
    amplitude_mm = min(available_space_mm * 0.5, 1.0)  # Max 1mm amplitude
    
    if amplitude_mm < cell_size_mm:
        # Not enough space for serpentine
        return (0.0, 0)
    
    # Calculate required frequency
    # length_added ≈ 4 × amplitude × frequency
    frequency = int(length_deficit_mm / (4 * amplitude_mm))
    
    # Clamp frequency (avoid excessive zigzags)
    frequency = max(1, min(frequency, 10))
    
    return (amplitude_mm, frequency)


def apply_length_matching(
    diff_pair_path: 'DiffPairPath',
    cell_size_mm: float,
    max_skew_mm: float,
) -> 'DiffPairPath':
    """
    Apply length matching to differential pair by inserting serpentine.
    
    Measures lengths of P and N traces. If mismatch exceeds max_skew_mm,
    inserts serpentine pattern on the shorter trace.
    
    Args:
        diff_pair_path: Original routed pair
        cell_size_mm: Grid cell size
        max_skew_mm: Maximum allowed skew
        
    Returns:
        Updated DiffPairPath with length matching applied
    """
    if not diff_pair_path.success:
        return diff_pair_path  # Don't modify failed routes
    
    # Measure current lengths
    pos_length = measure_path_length(diff_pair_path.pos_cells, cell_size_mm)
    neg_length = measure_path_length(diff_pair_path.neg_cells, cell_size_mm)
    
    skew = abs(pos_length - neg_length)
    
    if skew <= max_skew_mm:
        # Already within tolerance
        return diff_pair_path
    
    # Determine which trace is shorter
    if pos_length < neg_length:
        shorter_cells = diff_pair_path.pos_cells
        longer_cells = diff_pair_path.neg_cells
        deficit_mm = neg_length - pos_length
        is_pos_shorter = True
    else:
        shorter_cells = diff_pair_path.neg_cells
        longer_cells = diff_pair_path.pos_cells
        deficit_mm = pos_length - neg_length
        is_pos_shorter = False
    
    # Calculate serpentine parameters
    # Assume 2mm available space (conservative for differential pairs)
    amplitude_mm, frequency = calculate_serpentine_params(
        deficit_mm, available_space_mm=2.0, cell_size_mm=cell_size_mm
    )
    
    if frequency == 0:
        # Can't add serpentine (not enough space or deficit too small)
        return diff_pair_path
    
    # Insert serpentine on shorter trace
    # Use perpendicular direction (assume horizontal trace → vertical serpentine)
    insertion_index = len(shorter_cells) // 2
    new_shorter = generate_serpentine_pattern(
        amplitude_mm=amplitude_mm,
        frequency=frequency,
        insertion_index=insertion_index,
        trace_cells=shorter_cells,
        cell_size_mm=cell_size_mm,
        perpendicular_direction=(0, 1),  # Vertical zigzag
    )
    
    # Update path
    if is_pos_shorter:
        new_pos_cells = new_shorter
        new_neg_cells = longer_cells
    else:
        new_pos_cells = longer_cells
        new_neg_cells = new_shorter
    
    # Recalculate metrics
    new_pos_length = measure_path_length(new_pos_cells, cell_size_mm)
    new_neg_length = measure_path_length(new_neg_cells, cell_size_mm)
    new_skew = abs(new_pos_length - new_neg_length)
    
    # Return updated path
    from temper_placer.routing.diff_pair_router import DiffPairPath
    return DiffPairPath(
        pos_cells=new_pos_cells,
        neg_cells=new_neg_cells,
        coupling_ratio=diff_pair_path.coupling_ratio,  # Unchanged
        max_skew_mm=new_skew,
        avg_separation_mm=diff_pair_path.avg_separation_mm,
        success=True
    )


# Phase 3 TODO:
# [x] Implement measure_path_length()
# [x] Implement calculate_serpentine_params()
# [x] Implement generate_serpentine_pattern()
# [x] Implement apply_length_matching()
# [ ] Unit tests for length measurement
# [ ] Unit tests for serpentine generation
# [ ] Integrate into route_pair() as post-processing
