# TPS3431 DRB0008A footprint review

Local footprint: `TPS3431_DRB0008A.pretty/TPS3431_DRB0008A_VSON-8-1EP_3x3mm_P0.65mm_EP1.75x1.5mm.kicad_mod`.

The source is TI's TPS3431 datasheet, package drawing DRB0008A revision A, outline page 27 and board land pattern page 28 (printed page numbers 27–28; PDF pages 28–29). The 3.00 mm body has an eight-lead, 0.65 mm-pitch arrangement. The recommended land pattern specifies eight 0.60 mm radial-by-0.31 mm tangential pads; the pad columns are 2.80 mm apart and each column has four centers at 0.65 mm pitch. Coordinates in the footprint are therefore X = ±1.40 mm and Y = −0.975, −0.325, +0.325, +0.975 mm. Pin 1 is upper-left in top view, pins 1–4 descend the left side, pins 5–8 ascend the right side.

The exposed thermal land is centered, 1.75 × 1.50 mm, numbered 9 to match the schematic symbol, and intended to connect to GND. Four unnumbered paste apertures are 0.725 × 0.725 mm with 0.05 mm webs, giving 80.2% nominal paste coverage over the land. TI's sample stencil design calls for approximately 84%; these apertures are a deliberate, conservative split approximation and should be reviewed with the board assembler before fabrication. No thermal vias are included because those depend on board construction.

The courtyard is a 3.60 × 3.60 mm square around the 3.00 mm nominal body. Silkscreen stays outside the package and identifies pin 1. The footprint uses TI's example copper geometry; the fab outline and courtyard are library conventions around TI's package dimensions.

## Verification

- `python3 check_footprint.py` checks all pad numbers, coordinates, sizes, exposed land, and split paste geometry against the documented drawing interpretation.
- `kicad-cli fp export svg ...` successfully parsed and rendered the footprint to `render/`. This validates KiCad syntax and provides a visual artifact for review.
- The rendered SVG contains copper, mask, paste, fab, silkscreen, and courtyard layers. A PCB DRC cannot be claimed here because this footprint is not yet placed on a board.

Reference: [TI TPS3431 datasheet](https://www.ti.com/lit/ds/symlink/tps3431.pdf), package outline and land-pattern drawing DRB0008A. No 3D model is included because the exact TI package model was not validated in this review.
