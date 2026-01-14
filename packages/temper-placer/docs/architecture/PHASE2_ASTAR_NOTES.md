# Phase 2: A* Integration Notes

## Challenge

The current A* implementation uses binary free/blocked checks:
- `is_free()` returns True if cell == 0
- `is_blocked()` returns True if cell != 0

For differential pairs, we need distance-based checking:
- USB_D- should be able to route within 0.127mm of USB_D+ (pair gap)
- OTHER_NET should NOT be able to route within 0.2mm of USB_D+ (normal clearance)

## Approach

Instead of changing the binary free/blocked model (which works well for most cases), we'll:

1. **Keep existing is_free() behavior** for initial feasibility
2. **Add clearance validation during neighbor expansion** using check_clearance()
3. **Allow routing through pair mate's occupied cells** if within pair gap

## Implementation

The A* algorithm will:
1. Check if neighbor is generally routable (not a static obstacle)
2. If occupied by another net, check required clearance using `grid.check_clearance()`
3. Calculate distance to nearest obstacle boundary
4. Allow move if distance >= required_clearance, otherwise skip

## Key Insight

The differential pair gap (0.127mm) is SMALLER than trace_width + clearance (0.35mm).

When USB_D+ is marked blocked with radius 0.35mm:
- Cells within 0.35mm are marked with net_id=1
- USB_D- wants to route within 0.127mm + 0.075mm = 0.202mm (center-to-edge)
- These cells are currently blocked!

So USB_D- needs special permission to route through cells marked as USB_D+ if it's within the pair gap.

## Modified Algorithm

```python
# In A* neighbor expansion:
for dx, dy in moves:
    neighbor = (x + dx, y + dy)

    # Check if totally blocked (static obstacle)
    if grid.grid[neighbor[1], neighbor[0]] == -1:
        continue

    # Check if occupied by another net
    blocking_net_id = grid.grid[neighbor[1], neighbor[0]]
    if blocking_net_id > 0 and blocking_net_id != net_id:
        # Get required clearance (pair-aware)
        required_clearance = grid.check_clearance(neighbor[0], neighbor[1], net_id)

        # TODO: Calculate distance to obstacle boundary
        # For now, assume cell center is the check point
        # This is conservative - actual impl would compute edge distance

        # Skip if violates clearance
        # (Simplified: assume if cell is occupied, we're at the boundary)
        # Real impl: compute distance from cell center to obstacle edge
        continue

    # Proceed with normal A* logic
    ...
```

## Simplified Implementation for Phase 2

For the initial Phase 2 implementation, we'll use a simplified approach:

1. When a cell is occupied by the pair mate, treat it as "high cost" rather than blocked
2. This allows routing through it with penalty
3. Post-routing, verify clearances are satisfied

Actually, even simpler: Just reduce the blocking radius when marking differential pairs!

## Actual Fix (Simplest)

The blocking radius is currently calculated as `trace_width + clearance`.

For differential pairs routing:
1. When marking USB_D+ blocked, use `trace_width + pair_gap` instead of `trace_width + clearance`
2. This makes the blocking radius 0.15 + 0.127 = 0.277mm instead of 0.35mm
3. USB_D- can now route within 0.277mm of USB_D+ centerline
4. Post-routing spacing will be ~0.127mm (pair gap) ✓

But wait, this means OTHER_NET can ALSO route within 0.277mm, which violates clearance!

Ugh, we really do need per-net clearance checking...

## Final Approach

Modify `is_free()` to be clearance-aware:

```python
def is_free_for_net(self, x: int, y: int, net_id: int) -> bool:
    """Check if cell is free for specific net (clearance-aware)."""
    cell_value = self.grid[y, x]

    if cell_value == -1:
        return False  # Static obstacle

    if cell_value == 0:
        return True  # Free

    if cell_value == net_id:
        return True  # Own net

    # Occupied by different net - check clearance
    required_clearance = self.check_clearance(x, y, net_id)

    # SIMPLIFIED: If required clearance is less than normal, allow (pair mate)
    # This assumes the cell is at the boundary of the obstacle
    # TODO: Calculate actual distance to obstacle edge

    # For now, disallow routing through other nets' cells
    # Phase 2.1 will add proper distance calculation
    return False
```

Then update A* to call `is_free_for_net(x, y, net_id)` instead of `is_free(x, y)`.
