# Serpentine Necessity Audit

**Date**: 2026-06-28

## Finding: Not needed for this design

The Temper induction cooker PCB contains exactly one signal differential pair:
**USB_D+/USB_D-** (USB 2.0 Full Speed, 12 Mbps, driven by ESP32-S3 which has no HS PHY).

`DC_BUS+/DC_BUS-` is a power rail, not a differential signal — length matching is irrelevant.

## Physical analysis

| Parameter | Value |
|-----------|-------|
| MCU USB_D+ position | ~83.5, 100 mm |
| MCU USB_D- position | ~83.5, 100.4 mm |
| Connector USB_D+ position | ~95, 130 mm |
| Connector USB_D- position | ~95.4, 130 mm |
| Straight-line D+ path | ~32.1 mm |
| Straight-line D- path | ~31.9 mm |
| Straight-line mismatch | ~0.2 mm |
| Worst-case routed mismatch estimate | <2 mm |

## Timing analysis

| Parameter | Value |
|-----------|-------|
| FR4 propagation | ~150 mm/ns |
| 1 mm skew | 6.7 ps |
| 10 mm worst-case skew | 67 ps |
| USB FS bit period (12 Mbps) | 83.3 ns |
| USB FS receiver skew spec | ±2 ns |
| Margin (worst-case vs spec) | 30× |

## Skew budget

The 0.1mm skew budget in `length_group_inference.py:70` (0.5 ps at FR4
propagation speed) is over-specified by 3-4 orders of magnitude for the
only signal diff pair on this board.

## Verdict

Serpentine length matching (Idea #3 from `docs/ideation/2026-06-24-router-v6-feature-completeness-ideation.html`) adds zero electrical benefit to this design. It would matter for designs with:

- USB High Speed (480 Mbps)
- PCIe (>2.5 Gbps)
- HDMI/DVI (>1.65 Gbps)
- Multiple board-spanning diff pairs with significant path divergence

None of which apply to an induction cooker with a single USB Full Speed pair.

The `length_matching.py` module, `serpentine.py`, and `length_matcher.py` are
kept in the tree as future infrastructure.

## Code cleanup

Removed the dead `length_matching=None` call site from `pipeline.py` and
the unused parameter from `compile_routing_results()` in `routing_results.py`.
Removed dead `LengthMatchingResult`/`LengthMatchingResults`/`apply_length_matching`
exports from `router_v6/__init__.py`.
