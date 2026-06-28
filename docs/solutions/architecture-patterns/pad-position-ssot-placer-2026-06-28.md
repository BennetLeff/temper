---
title: "Pad-Position Single Source of Truth in the Placer"
date: "2026-06-28"
category: architecture-patterns
module: core/pin_geometry
problem_type: architecture_pattern
component: core
severity: high
applies_when:
  - Computing a pin's world position anywhere in the placer
  - Adding new pad-position math to any module
  - Seeing inline `comp_pos + pin.position` or `Pin.absolute_position` in code
tags: [pad-position, pin-geometry, rotation, side-mirror, ssot, consolidation]
---

# Pad-Position Single Source of Truth in the Placer

## Context

The placer had two divergent ways to compute a pin's world (board-relative)
position, and a third broken pattern scattered across ~40 call sites:

1. **`Pin.absolute_position(comp_pos, rotation, side)`** — a JAX-dependent method
   on the `Pin` dataclass. Correctly applied rotation and side-mirror transforms.
   Used by ~11 call sites.

2. **`pin_world_position(pin, comp)`** — a pure-Python free function in
   `core/pin_geometry.py`. Semantically identical to `Pin.absolute_position`,
   but read rotation/side from the `Component` object directly. D2 canonical surface.

3. **`comp_pos + pin.position`** (inlined) — broken. Ignored component rotation
   and bottom-side mirroring entirely. Used by ~40 call sites across ~25 files.
   Gave wrong results for any rotated or bottom-side-mounted component.

Three implementations meant three opportunities for drift. The broken inline pattern
was particularly dangerous because it produced silent wrong answers — pins on rotated
components appeared at incorrect board positions, which cascaded into routing failures.

## Guidance

### Canonical surface

**Module:** `core/pin_geometry.py`

```python
from temper_placer.core.pin_geometry import (
    pin_world_position,
    pin_world_position_at,
    pin_world_layer,
    pin_world_radius,
)
```

- **`pin_world_position(pin, comp)`** — the primary SSOT. Computes world (x, y) by
  applying the component's `initial_rotation` and `initial_side` to the pin's offset,
  then adding `comp.initial_position`. Pure Python, no JAX dependency.

- **`pin_world_position_at(pin, comp, pos_override)`** — variant that accepts an
  explicit `pos_override` tuple replacing `comp.initial_position`. Used when the
  component's board position comes from a placement dict rather than the component
  object (e.g., `drc_sweep.py`, `fine_pitch_escape.py`).

- **`pin_world_layer(pin)`** — returns the pin's layer name, defaulting to `"F.Cu"`.

- **`pin_world_radius(pin)`** — returns effective pad radius as
  `max(width, height) / 2.0`, with a 0.5 mm fallback for zero-sized pads.

### What was removed

**`Pin.absolute_position(comp_pos, rotation, side)`** — the JAX-dependent method on
`Pin` was fully decommissioned (PR #38, commit `f4c1fc9d`). It required callers to
manually extract rotation/side from the component, duplicating the logic that
`pin_world_position` handles internally.

### Migration pattern

**Before** (JAX-dependent, manual parameter extraction):
```python
import jax.numpy as jnp
x, y = pin.absolute_position(
    (comp.initial_position[0], comp.initial_position[1]),
    jnp.deg2rad(comp.initial_rotation * 90),
    side=comp.initial_side,
)
```

**After** (pure Python, reads from component directly):
```python
from temper_placer.core.pin_geometry import pin_world_position
x, y = pin_world_position(pin, comp)
```

**With position override** (when placement comes from a dict):
```python
comp_pos = placements.get(comp.ref, comp.initial_position)
x, y = pin_world_position_at(pin, comp, comp_pos)
```

## Why This Matters

**Before**: Three implementations, one silently wrong. The rotation-and-side math was
duplicated in `Pin.absolute_position` (JAX trig), `pin_world_position` (Python `math`),
and missing entirely from ~40 inlined `comp_pos + pin.position` sites. Adding a new
pin-position computation required deciding which implementation was "correct" and
whether JAX was available in that module.

**After**: One canonical implementation. All call sites use the same pure-Python
free function. Rotation and side are read from the `Component` object (no manual
parameter extraction). The JAX dependency is gone from the pad-position path.

## When to Apply

- **When computing a pin's position anywhere**: use `pin_world_position` or
  `pin_world_position_at`. Never inline `comp_pos + pin.position` — rotation and
  side transforms are not optional.
- **When you see `Pin.absolute_position` in code**: it's removed. The import will
  fail. Migrate to `pin_world_position`.
- **When adding a new call site** that needs position-override semantics (e.g.,
  reading component positions from a placement dict): use `pin_world_position_at`.

## Examples

### Before (broken inline pattern — ~40 sites)

```python
# Wrong: ignores component rotation and bottom-side mirroring
pin_x = comp_pos[0] + pin.position[0]
pin_y = comp_pos[1] + pin.position[1]
```

### After (canonical)

```python
from temper_placer.core.pin_geometry import pin_world_position_at
pin_x, pin_y = pin_world_position_at(pin, comp, comp_pos)
```

## Related Documents

- [Layer Index SSOT](layer-index-ssot-placer-2026-06-23.md)
- [Net Classification SSOT](net-classification-ssot-placer-2026-06-23.md)
- [A* Primitives SSOT](a-star-primitives-ssot-placer-2026-06-24.md)
- [Pad-Position Requirements](../../brainstorms/2026-06-23-pad-position-consolidation-requirements.md)
- [Pad-Position Plan](../../plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md)
