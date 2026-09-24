# Service coupon construction receipt

Status: **routed SELV lab candidate, not standalone digital acceptance and
not product service approval**. KiCad 10.0.4 DRC reports **0 errors, 0
unconnected**, and **2 `lib_footprint_mismatch` warnings** on J1/J2. ERC
reports **0 errors and 18 warnings**: empty generated symbol library IDs,
off-grid generated pin endpoints and library-resolution warnings. The board
and schematic cannot be described as clean while those warnings remain.

## Reproduction

From `zapote/programming-ui/source-build-01/`:

```sh
uvx --from atopile==0.2.69 ato build
```

From the repository root (set `KICAD10_FOOTPRINT_DIR` to the official KiCad
footprint root for this host):

```sh
python3 scripts/gen_schematics.py \
  --netlist zapote/programming-ui/source-build-01/build/default.net \
  --bom-csv zapote/programming-ui/source-build-01/build/default.csv \
  --output-dir zapote/programming-ui/evidence/service-board-01/native \
  --layout-config zapote/programming-ui/evidence/service-board-01/schematic_layout.json \
  --no-oracle
KICAD10_FOOTPRINT_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints \
  uv run --no-project --with kiutils python \
  zapote/programming-ui/evidence/service-board-01/build_board.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
  zapote/programming-ui/evidence/service-board-01/route_board.py
kicad-cli sch erc zapote/programming-ui/evidence/service-board-01/native/service_coupon.kicad_sch \
  --output zapote/programming-ui/evidence/service-board-01/native/erc.rpt
kicad-cli pcb drc zapote/programming-ui/evidence/service-board-01/native/service_coupon.kicad_pcb \
  --all-track-errors --output zapote/programming-ui/evidence/service-board-01/native/drc-routed.rpt
```

The generated board's every numbered pad was checked against the exact
Atopile net. Exporting the KiCad schematic netlist and comparing `(net,
reference, pin)` tuples returned the same 7 nets and 22 pad claims. The
Tag-Connect footprint uses KiCad's `connect` pad type, so `build_board.py`
assigns those six nets after the shared strict generator creates the board;
it then reloads the board and rejects any pad-net mismatch. KiCad DRC found
zero unconnected pads after routing. The DRC command required normal macOS
configuration access in this environment; under the filesystem sandbox it
crashed with `Swift/SwiftNativeNSArray.swift:78: Array index out of range`
even on the existing accepted current-sense board.

## Exact parts and remaining mechanical checks

- J1: [Tag-Connect TC2030-IDC-NL footprint drawing](https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/2019/12/TC2030-IDC-NL-Datasheet-Rev-B.pdf), `TC2030-IDC-NL-FP` pad pattern; contact pins map 1–6 to IDC 1–6. The six numbered pads and three asymmetric alignment holes in the KiCad footprint match the generated board. No solder paste belongs on the contact pads. Cable access and clip clearance have not been checked against an enclosure.
- J2: [Samtec TSW-106-07-G-S](https://www.samtec.com/products/tsw-106-07-g-s), six-pin 2.54 mm vertical through-hole candidate. KiCad's pad 1 is rectangular. It is **unkeyed**, and a mating harness has not been selected.
- D1–D4: [TI TPD1E05U06DYAR datasheet](https://www.ti.com/lit/ds/symlink/tpd1e05u06.pdf), DYA/SOT-5X3 SOD-523, pin 1 I/O and pin 2 GND. KiCad `D_SOD-523` has pads 1/2 at ±0.7 mm, each 0.6 × 0.7 mm. Pin numbering and nominal package family match; TI's example land pattern has not been independently reconciled to KiCad's land pattern and needs assembler review before fab. The ESD parts are **not** powered-off I/O isolation.
- R1: [Yageo RC0603FR-07499RL](https://yageogroup.com/component-documentation/download/specsheet/RC0603FR-07499RL), 499 R ±1%, 0603, 0.1 W. It implements Espressif's [UART0 TX series-resistor recommendation](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html).

The two remaining DRC footprint mismatch warnings come from the locally
generated footprint copies; an independent `pcbnew.FootprintLoad` comparison
found equal numbered pad geometry for J1 (9 pads including three NPTH holes)
and J2 (6 pads) against the installed KiCad libraries. The metadata mismatch
still requires resolution before digital construction acceptance.

## Source identities and limits

SHA-256 source `420220b46fce45f0814acfd509e21b05642f32c3085aa30fb8bed1c192ca9c8a`,
Atopile netlist `95ca061f2dc5bf0369ae3e49d05271bcfe213a858803f16ce57592510bdcf373`,
KiCad schematic `36abc2f5306e8a38d01a64d5c2ea2e593de6676d8c7cfd8b6e8940a18b748741`,
routed PCB `0699ecf1ccfc1db6fa9d55880bab786999bb9d614736642129b484fb6641a9aa`.
The source netlist and compiler BOM are copied here because `source-build-01/build/`
is ignored. `placed-board-receipt.json` binds the **unrouted** input to the
router; its board hash is not the final PCB hash above.

This coupon is strictly SELV. It has no HOT0, VD, VB, coil, fan or PFC
connection. Pin 5 is a direct pass-through conductor: the **reference-only**
use is a lab rule, not hardware-enforced power-injection protection. A service
reset is a power-stage event on the cooker and cannot
be permitted from this coupon until the actual integrated board proves both
stages stop and remain disarmed. No physical article or service-access test
has been performed.
