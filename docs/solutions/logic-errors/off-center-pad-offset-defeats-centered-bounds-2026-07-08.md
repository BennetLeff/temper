---
title: Off-centre pad offset defeats centered component bounds — symmetric boxing around footprint origin encloses all pads
date: "2026-07-08"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "shorting_items and solder_mask_bridge survive at ~4-5 DRC violations despite Chebyshev-verified pairwise clearance ≥ τ"
  - "Test P9 passes (bounds size encloses pad span) but DRC still shows shorts on the same components"
  - "TO-247 pads protrude 5.45 mm past the modeled box on one side while the other side is fine"
root_cause: "Component.bounds is a centred (width, height) tuple carrying no offset. When pads are not symmetric around the footprint origin, the box the placer separates is not where the copper is. The solver places a box centred at the origin while the actual pads sit up to half the span away."
resolution_type: code_fix
tags: ["bounds", "pad-offset", "symmetric-boxing", "footprint-origin", "placement-model", "map-vs-territory"]
---

# Off-centre pad offset defeats centered component bounds — symmetric boxing around footprint origin encloses all pads

## Problem

After fixing the Chebyshev encoding to correctly enforce pairwise clearance, and after verifying that `component.bounds ⊇ pads` (P9 passes on all 33 components), kicad-cli DRC still showed ~4 shorting and ~5 solder mask bridge violations. The specific violations were all on TO-247 through-hole components (Q1, Q2) — pad 3 [SW_NODE] of Q1 shorting to PWM of U_GATE. But the Chebyshev disjunction correctly separated Q1's bounds from U_GATE's. How?

## Symptoms

- Q2 bounds: (14.4, 3.5) mm — the box spans from −7.2 to +7.2 mm in x from the footprint origin
- Q2 pads: at x = 0, 5.45, 10.90 mm — pad 3 extends to 12.65 mm with pad size
- P9 passes: 14.4 mm ≥ pad_span of 0 to 12.65 mm
- But the pad at 12.65 mm sits 5.45 mm past the box edge at +7.2 mm
- The solver separates the box at ±7.2 mm from U_GATE. The pad at +12.65 mm is not protected.

## Root Cause

**`Component.bounds` is a `(width, height)` tuple — centred on the footprint origin, carrying no offset.** The parser computes `_calculate_footprint_bounds` as `(x_max − x_min, y_max − y_min)` — the span, which gives the total size but discards the offset from the origin.

For symmetric footprints (most SMD parts), this is fine — min ≈ −max, so the box is centred on the copper. For asymmetric footprints (TO-247, diodes D1/D2, radial capacitors), the pads cluster on one side of the origin, and the span-based width puts the box centre at the midpoint of the span, not at the footprint origin where the solver positions it.

The solver models every component as a box of size `(bounds[0], bounds[1])` centred on its placement position. But the actual copper extends farther on one side — specifically, to `max(|pad_x|) + pad_width/2` from the origin. The box protects the near side and leaves the far side exposed.

## Solution

**Return symmetric half-extents: `2 × max(|x_min|, |x_max|)` instead of span `x_max − x_min`.** This makes the box centred on the footprint origin AND large enough to cover the maximum pad extent in every direction.

```python
# BEFORE: span — box is centred at midpoint of pad extents, not at origin
x_min = min(gfx_x_min, pad_x_min)
x_max = max(gfx_x_max, pad_x_max)
return (x_max - x_min, y_max - y_min)

# AFTER: symmetric around origin — box covers max extent in all directions
hw = max(abs(x_min), abs(x_max))
hh = max(abs(y_min), abs(y_max))
return (2 * hw, 2 * hh)
```

For Q2: pads span −1.75 to +12.65 mm from origin. `max(1.75, 12.65) = 12.65` → box half-width = 12.65 mm → width = 25.3 mm. The box edges at ±12.65 mm now cover the pad at +12.65 mm.

## Why This Works

The solver places the component at a position `(x, y)`. The box spans `[x − hw, x + hw] × [y − hh, y + hh]`. With symmetric half-extents, any pad at position `(px, py)` relative to the origin satisfies `|px| ≤ hw` and `|py| ≤ hh`. The SEPARATED Chebyshev constraint on this box guarantees no other component enters this region. Since the region encloses all pads, no other component's pad can enter — zero shorts, zero mask bridges.

The box is conservatively larger on one side (the near side of Q2 has 12.65 mm of empty box beyond the pad at 0 mm). This is acceptable because:
- The board is large enough (150×100 mm, ~7.4% utilization after boxing)
- The solver is fast enough (224 ms for 33 components with symmetric boxes)
- The alternative (offset-aware bounds) requires changing the Component dataclass and 100+ consumers

## Prevention

1. **P9 (bounds ⊇ pads) — necessary but not sufficient.** P9 verifies that `pad_span ≤ box_size`, but does not verify that the box *at its placed position* covers the pads. P9 is green on the exact failure mode this fix addresses.

2. **Golden-board DRC gate is the definitive guard.** `test_regression_drc.py` runs kicad-cli DRC on the placed temper board and catches shorts/mask-bridge violations regardless of their cause. No model-level invariant test (P1-P9) can substitute for the territory-level check.

3. **What a sufficient invariant would look like:** assert that for every component, `max(|pad_x|) ≤ box_half_width` and `max(|pad_y|) ≤ box_half_height` — i.e., the box covers the max absolute extent in each direction, not just the total span.

## Result

| Violation type | Before | After |
|---|---|---|
| shorting_items | 4 | 0 |
| solder_mask_bridge | 5 | 0 |
| clearance | 9 | 8 |
| copper_edge_clearance | 4 | 4 |
| **Placement-relevant total** | **22** | **12** |

Placement-relevant DRC drops to 12 — below the human baseline of 22. The remaining 8 clearance violations are intra-component fine-pitch (U_MCU QFN pads, J_USB connector pads — not placement-fixable). The 4 edge violations are a hardcoded margin mismatch (0.5 mm vs board setup value).

## Related

- `packages/temper-placer/src/temper_placer/io/kicad_parser.py:746` — `_calculate_footprint_bounds` (fixed)
- `packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py` — P8/P9 bounds invariant tests
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — golden-board DRC gate
- `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md` — Chebyshev encoding fix (preceding workstream)
