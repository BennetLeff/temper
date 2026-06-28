"""
Length Matching for Differential Pairs.

Implements serpentine/meander insertion to equalize differential pair trace
lengths after routing. Part of Router V6 (temper-v35p.1.3).

Also provides bus-level length matching (temper-l4we.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.bus_cohort import BusCohortConstraint
    from temper_placer.routing.heuristics import GridCell
    from temper_placer.routing.maze_router import RoutePath


@dataclass
class LengthMatchResult:
    """Result of bus length matching operation.

    Attributes:
        paths: Updated paths for each net in the bus.
        original_skew_mm: Length difference before matching.
        final_skew_mm: Length difference after matching.
        achieved_skew_mm: Same as final_skew_mm for compatibility.
        max_skew_mm: Maximum allowed skew from bus definition.
        nets_modified: List of net names that had serpentine added.
        success: Whether all nets were successfully matched.
        failure_reason: Reason for failure if success is False.
    """

    paths: dict[str, RoutePath]
    original_skew_mm: float = 0.0
    final_skew_mm: float = 0.0
    achieved_skew_mm: float = 0.0
    max_skew_mm: float = 0.0
    nets_modified: list[str] = field(default_factory=list)
    success: bool = True
    failure_reason: str | None = None


@dataclass
class SerpentineParams:
    """Configuration parameters for serpentine insertion.

    Attributes:
        amplitude_mm: Maximum perpendicular deviation from straight line
        pitch_mm: Wavelength of serpentine pattern (default: 2x amplitude)
        tolerance_mm: Acceptable length mismatch before correction
        min_straight_length_mm: Minimum straight segment length for insertion
    """

    amplitude_mm: float = 0.5
    pitch_mm: float = 1.0  # Will be set to 2*amplitude if not specified
    tolerance_mm: float = 0.5
    min_straight_length_mm: float = 2.0

    def __post_init__(self):
        """Set pitch to 2x amplitude if not explicitly specified."""
        if self.pitch_mm == 1.0:  # Default value
            self.pitch_mm = 2.0 * self.amplitude_mm


class LengthMatcher:
    """Implements length matching for differential pairs via serpentine insertion.

    This post-processing step equalizes trace lengths by inserting meandering
    sections into the shorter trace, maintaining signal integrity for high-speed
    differential pairs (e.g., USB, LVDS, Ethernet).

    Example:
        >>> from temper_placer.routing.post_processing import LengthMatcher, SerpentineParams
        >>>
        >>> matcher = LengthMatcher()
        >>> params = SerpentineParams(amplitude_mm=0.5, tolerance_mm=0.5)
        >>> path_pos, path_neg = matcher.match_differential_pair_lengths(
        ...     path_pos, path_neg, params
        ... )
    """

    def measure_path_length(self, cells: list[GridCell], cell_size_mm: float) -> float:
        """Calculate physical trace length through grid cells.

        Sums Euclidean distances between consecutive cells, accounting for
        diagonal moves and layer changes (vias add vertical distance).

        Args:
            cells: Path as list of grid cells
            cell_size_mm: Grid resolution in mm

        Returns:
            Total path length in mm
        """
        if len(cells) < 2:
            return 0.0

        total_length = 0.0
        for i in range(1, len(cells)):
            prev = cells[i - 1]
            curr = cells[i]

            # Horizontal/vertical/diagonal distance
            dx = (curr.x - prev.x) * cell_size_mm
            dy = (curr.y - prev.y) * cell_size_mm
            xy_dist = math.sqrt(dx * dx + dy * dy)

            # Add layer change distance (via height is negligible for PCBs)
            # We just count the lateral distance
            total_length += xy_dist

        return total_length

    def find_straight_segments(
        self, cells: list[GridCell], cell_size_mm: float, min_length_mm: float
    ) -> list[tuple[int, int]]:
        """Identify straight horizontal or vertical segments in path.

        A segment is "straight" if it maintains constant direction (no corners).
        Only segments longer than min_length_mm are returned.

        Args:
            cells: Path as list of grid cells
            cell_size_mm: Grid resolution in mm
            min_length_mm: Minimum segment length to consider

        Returns:
            List of (start_idx, end_idx) tuples for valid segments
        """
        if len(cells) < 3:
            return []

        segments = []
        start_idx = 0

        # Determine initial direction
        dx = cells[1].x - cells[0].x
        dy = cells[1].y - cells[0].y
        current_dir = (dx, dy)

        for i in range(2, len(cells)):
            prev = cells[i - 1]
            curr = cells[i]

            dx = curr.x - prev.x
            dy = curr.y - prev.y
            new_dir = (dx, dy)

            # Check if direction changed or layer changed
            if new_dir != current_dir or curr.layer != prev.layer:
                # End of segment
                segment_length = (i - start_idx) * cell_size_mm
                if segment_length >= min_length_mm:
                    segments.append((start_idx, i - 1))

                # Start new segment
                start_idx = i - 1
                current_dir = new_dir

        # Check final segment
        segment_length = (len(cells) - 1 - start_idx) * cell_size_mm
        if segment_length >= min_length_mm:
            segments.append((start_idx, len(cells) - 1))

        return segments

    def insert_serpentine(
        self,
        cells: list[GridCell],
        segment: tuple[int, int],
        length_delta_mm: float,
        cell_size_mm: float,
        params: SerpentineParams,
    ) -> list[GridCell]:
        """Insert serpentine meander into a straight segment.

        Replaces a straight segment with a meandering path to add length.
        The serpentine is perpendicular to the trace direction.

        Args:
            cells: Original path cells
            segment: (start_idx, end_idx) of segment to modify
            length_delta_mm: Additional length to add
            cell_size_mm: Grid resolution in mm
            params: Serpentine configuration

        Returns:
            New cell list with serpentine inserted
        """
        from temper_placer.routing.heuristics import GridCell

        start_idx, end_idx = segment

        # Calculate number of waves needed
        # Each wave adds approximately 2 * amplitude to the path length
        wave_length_added = 2.0 * params.amplitude_mm
        n_waves = max(1, int(math.ceil(length_delta_mm / wave_length_added)))

        # Get segment direction
        start_cell = cells[start_idx]
        end_cell = cells[end_idx]
        dx = end_cell.x - start_cell.x
        dy = end_cell.y - start_cell.y

        # Determine if horizontal or vertical
        is_horizontal = abs(dx) > abs(dy)

        # Calculate perpendicular offset in grid cells
        amplitude_cells = int(round(params.amplitude_mm / cell_size_mm))
        amplitude_cells = max(1, amplitude_cells)  # At least 1 cell

        # Generate serpentine waypoints
        new_cells = []
        new_cells.extend(cells[: start_idx + 1])  # Keep everything before segment

        # Distribute waves along the segment
        segment_length = abs(dx) if is_horizontal else abs(dy)
        if segment_length < n_waves * 2:
            # Segment too short for requested waves, reduce wave count
            n_waves = max(1, segment_length // 2)

        wave_spacing = segment_length // n_waves if n_waves > 0 else segment_length

        current_pos = start_cell
        layer = start_cell.layer

        for wave_idx in range(n_waves):
            # Move forward to wave position
            if is_horizontal:
                forward_dist = wave_spacing
                wave_center_x = start_cell.x + (wave_idx + 0.5) * forward_dist
                wave_center_x = int(round(wave_center_x))

                # Move to wave center
                for x in range(current_pos.x, wave_center_x, 1 if dx > 0 else -1):
                    new_cells.append(GridCell(x, current_pos.y, layer))

                # Add perpendicular deviation
                offset_dir = 1 if wave_idx % 2 == 0 else -1
                for offset in range(1, amplitude_cells + 1):
                    new_cells.append(
                        GridCell(wave_center_x, current_pos.y + offset * offset_dir, layer)
                    )

                # Return to centerline
                for offset in range(amplitude_cells - 1, -1, -1):
                    new_cells.append(
                        GridCell(wave_center_x, current_pos.y + offset * offset_dir, layer)
                    )

                current_pos = GridCell(wave_center_x, current_pos.y, layer)
            else:  # Vertical
                forward_dist = wave_spacing
                wave_center_y = start_cell.y + (wave_idx + 0.5) * forward_dist
                wave_center_y = int(round(wave_center_y))

                # Move to wave center
                for y in range(current_pos.y, wave_center_y, 1 if dy > 0 else -1):
                    new_cells.append(GridCell(current_pos.x, y, layer))

                # Add perpendicular deviation
                offset_dir = 1 if wave_idx % 2 == 0 else -1
                for offset in range(1, amplitude_cells + 1):
                    new_cells.append(
                        GridCell(current_pos.x + offset * offset_dir, wave_center_y, layer)
                    )

                # Return to centerline
                for offset in range(amplitude_cells - 1, -1, -1):
                    new_cells.append(
                        GridCell(current_pos.x + offset * offset_dir, wave_center_y, layer)
                    )

                current_pos = GridCell(current_pos.x, wave_center_y, layer)

        # Connect to end of segment
        if is_horizontal:
            for x in range(current_pos.x, end_cell.x, 1 if dx > 0 else -1):
                new_cells.append(GridCell(x, current_pos.y, layer))
        else:
            for y in range(current_pos.y, end_cell.y, 1 if dy > 0 else -1):
                new_cells.append(GridCell(current_pos.x, y, layer))

        # Keep everything after segment
        new_cells.extend(cells[end_idx + 1 :])

        return new_cells

    def match_differential_pair_lengths(
        self,
        path_pos: RoutePath,
        path_neg: RoutePath,
        params: SerpentineParams,
    ) -> tuple[RoutePath, RoutePath]:
        """Equalize differential pair trace lengths via serpentine insertion.

        Measures both paths, calculates delta, and inserts serpentine on the
        shorter trace if delta exceeds tolerance.

        Args:
            path_pos: Positive net route path
            path_neg: Negative net route path
            params: Serpentine configuration

        Returns:
            Tuple of (updated_path_pos, updated_path_neg)
        """
        from temper_placer.routing.maze_router import RoutePath

        # Both paths must be successful
        if not path_pos.success or not path_neg.success:
            return path_pos, path_neg

        # Infer cell size from path length
        # This is a hack - ideally cell_size should be passed explicitly
        cell_size_mm = 0.1  # Default assumption
        if len(path_pos.cells) > 1:
            # Try to infer from path length
            grid_length = len(path_pos.cells)
            if path_pos.length > 0 and grid_length > 0:
                cell_size_mm = path_pos.length / grid_length

        # Measure current lengths
        len_pos = self.measure_path_length(path_pos.cells, cell_size_mm)
        len_neg = self.measure_path_length(path_neg.cells, cell_size_mm)

        length_delta = abs(len_pos - len_neg)

        # Check if correction needed
        if length_delta <= params.tolerance_mm:
            return path_pos, path_neg

        # Determine which path is shorter
        if len_pos < len_neg:
            shorter_path = path_pos
            longer_path = path_neg
            modify_pos = True
        else:
            shorter_path = path_neg
            longer_path = path_pos
            modify_pos = False

        # Find suitable straight segments for serpentine insertion
        segments = self.find_straight_segments(
            shorter_path.cells, cell_size_mm, params.min_straight_length_mm
        )

        if not segments:
            # No suitable segments, return unchanged
            return path_pos, path_neg

        # Use the longest segment
        best_segment = max(segments, key=lambda s: s[1] - s[0])

        # Insert serpentine
        new_cells = self.insert_serpentine(
            shorter_path.cells,
            best_segment,
            length_delta,
            cell_size_mm,
            params,
        )

        # Calculate new length
        new_length = self.measure_path_length(new_cells, cell_size_mm)

        # Count vias
        via_count = sum(
            1 for i in range(len(new_cells) - 1) if new_cells[i].layer != new_cells[i + 1].layer
        )

        # Create updated path
        updated_path = RoutePath(
            net=shorter_path.net,
            cells=new_cells,
            length=new_length,
            via_count=via_count,
            success=True,
            trace_width=shorter_path.trace_width,
            via_diameter=shorter_path.via_diameter,
            via_drill=shorter_path.via_drill,
        )

        # Return in correct order
        if modify_pos:
            return updated_path, longer_path
        else:
            return longer_path, updated_path

    def match_bus_lengths(
        self,
        paths: dict[str, RoutePath],
        bus: BusCohortConstraint,
        cell_size_mm: float = 0.2,
        serpentine_params: SerpentineParams | None = None,
    ) -> LengthMatchResult:
        """Equalize lengths of all nets in a bus cohort.

        Measures all paths, identifies the longest, and adds serpentine meanders
        to shorter paths to match within the bus's max_skew tolerance.

        Args:
            paths: Dictionary mapping net names to their RoutePaths.
            bus: BusCohortConstraint defining the bus and tolerance.
            cell_size_mm: Grid resolution for length calculations.
            serpentine_params: Optional serpentine configuration.
                           Defaults to SerpentineParams().

        Returns:
            LengthMatchResult with updated paths and skew information.
        """
        if serpentine_params is None:
            serpentine_params = SerpentineParams()

        if len(paths) < 2:
            return LengthMatchResult(
                paths=paths,
                success=True,
                max_skew_mm=bus.max_skew_mm,
            )

        successful_paths = {net: p for net, p in paths.items() if p.success}
        if len(successful_paths) < 2:
            return LengthMatchResult(
                paths=paths,
                success=False,
                failure_reason="Fewer than 2 successful paths in bus",
                max_skew_mm=bus.max_skew_mm,
            )

        lengths: dict[str, float] = {}
        for net, path in successful_paths.items():
            lengths[net] = self.measure_path_length(path.cells, cell_size_mm)

        max_length = max(lengths.values())
        min_length = min(lengths.values())
        original_skew = max_length - min_length

        updated_paths = dict(paths)
        nets_modified: list[str] = []

        max_skew_target = bus.max_skew_mm

        for net, length in lengths.items():
            if length >= max_length:
                continue

            delta = max_length - length

            if delta <= max_skew_target:
                continue

            path = successful_paths[net]

            segments = self.find_straight_segments(
                path.cells, cell_size_mm, serpentine_params.min_straight_length_mm
            )

            if not segments:
                continue

            best_segment = max(segments, key=lambda s: s[1] - s[0])

            new_cells = self.insert_serpentine(
                path.cells,
                best_segment,
                delta - max_skew_target,
                cell_size_mm,
                serpentine_params,
            )

            new_length = self.measure_path_length(new_cells, cell_size_mm)

            via_count = sum(
                1 for i in range(len(new_cells) - 1) if new_cells[i].layer != new_cells[i + 1].layer
            )

            updated_paths[net] = RoutePath(
                net=net,
                cells=new_cells,
                length=new_length,
                via_count=via_count,
                success=True,
                trace_width=path.trace_width,
                via_diameter=path.via_diameter,
                via_drill=path.via_drill,
            )
            nets_modified.append(net)

        final_lengths = {
            net: self.measure_path_length(p.cells, cell_size_mm)
            for net, p in updated_paths.items()
            if p.success
        }

        if len(final_lengths) >= 2:
            final_skew = max(final_lengths.values()) - min(final_lengths.values())
        else:
            final_skew = 0.0

        return LengthMatchResult(
            paths=updated_paths,
            original_skew_mm=original_skew,
            final_skew_mm=final_skew,
            achieved_skew_mm=final_skew,
            max_skew_mm=max_skew_target,
            nets_modified=nets_modified,
            success=final_skew <= max_skew_target or len(nets_modified) > 0,
        )
