# Addendum to the TEA construction decision

The NXP reference Gerber was inspected after the original decision. Its copper
aperture is 2.000 × 0.630 mm and its solder-mask aperture is 2.203 × 0.833 mm
(see [README](README.md) for the byte-level declarations and conversion).
The current candidate uses 1.95 × 0.60 mm copper pads, so the NXP reference is
slightly wider and does not offer a narrower-pad escape. The nominal adjacent
gap is about 0.640 mm for the reference geometry versus 0.670 mm for the
candidate; neither is a guaranteed assembled clearance.

The Gerber has no net names or source netlist. Although its repeated pattern is
consistent with an SO16, this archive alone cannot bind a flash to pin 4, 11,
or 15. It consequently cannot prove whether the reference board soldered or
omitted those NC lands. The NXP PDF schematic and official archive establish
the design identity, not an insulation approval.

Result: the reference pattern does not resolve the construction gate. The
no-land idea remains an external package/assembly question, and the status is
still **BLOCKED_EXTERNAL**. No CAD or footprint change is authorized from this
artifact.
