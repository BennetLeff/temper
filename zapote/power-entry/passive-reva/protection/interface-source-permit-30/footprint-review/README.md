# TPS389001DSER DSE0006A footprint review

This local KiCad footprint represents the TI TPS3890 DSE0006A, six-pin WSON
package. It is based on the package outline and example land pattern in the
[TI TPS3890 Rev A datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
package drawing 4220552/B (datasheet pages 23–25). The geometry was compared
with the drawing callouts and checked in KiCad's footprint exporter.

## Land geometry

| Feature | Value |
| --- | ---: |
| Body outline | 1.50 × 1.50 mm nominal |
| Copper pad width | 0.25 mm |
| Pad 1 copper length | 0.80 mm |
| Pads 2–6 copper length | 0.70 mm |
| Pin pitch | 0.50 mm |
| Pad row center X | -0.60 mm / +0.60 mm |
| Pad row Y positions | -0.50 mm, 0.00 mm, +0.50 mm |
| Pin 1 center | (-0.55, -0.50) mm |
| Pin 1 outer copper edge | X = -0.95 mm, aligned with pads 2–3 |
| Pad corner radius | 0.05 mm nominal |
| Thermal/exposed pad | None |

Pad 1 is deliberately asymmetric: it is 0.80 mm long and shifted 0.05 mm
toward the body from the other left-side pads, keeping the three left outer
copper edges aligned. Pads 1–3 use a -0.05 mm solder-mask margin (mask-defined
lands); pads 4–6 use +0.05 mm (non-mask-defined lands). Do not replace these
with six identical pads or add an exposed pad. The datasheet drawing shows
six perimeter lands only.

The pin numbering follows the DSE top view: pads 1, 2, 3 from upper-left to
lower-left; pads 4, 5, 6 from lower-right to upper-right. Pins are SENSE,
GND, MR, VDD, CT, RESET respectively.

## Validation

`kicad-cli fp export svg` parsed and exported the local footprint. The
generated SVG elements and source pad definitions were checked to confirm six
separate lands, pin-1 marking, the longer and offset pad 1, and no center pad.
The numeric pad geometry above was checked against the drawing's 0.25 mm
width, 0.80/0.70 mm lengths, 0.50 mm pitch, and asymmetric solder-mask notes.

This establishes a drawing-matched footprint proposal. It does not verify
fabrication-library conventions, paste release, stencil behavior, or a
manufactured assembly. The library is not yet bound in fixture 30's KiCad
project configuration, so `RailSupervisor` deliberately retains its
`TBD_REVIEW_ONLY` source footprint. Do not use the candidate for fabrication
until the local library is bound and the compiled footprint reference is
verified.
