# Temper LCR meter — revision C, based on TI TIDA-060029

A single **140 × 100 mm, four-layer PCB** for small-signal bench measurements of isolated, discharged stage53 components. It retains the TI OPA2810 source buffer, voltage-sense followers and transimpedance circuit, including matched 100 Ω / 5 kΩ / 100 kΩ source and feedback resistors. Revision C uses one short, local 100 pF feedback capacitor on every range and corrects the ADC-driver compensation using TI’s evaluation-board circuit. Excitation, simultaneous acquisition, power and USB control are integrated on the same board.

**Engineering prototype — design and manufacturing files complete.** Native KiCad ERC/DRC, connectivity, schematic parity and BOM/placement checks pass. No board has been fabricated, calibrated or physically validated. TI's reference accuracy does not transfer automatically to this implementation. No files have been uploaded to a manufacturer and no order has been placed.

- [Circuit PDF](previews/schematic.pdf) and [native KiCad project](cad/temper-lcr.kicad_pro).
- [TI reference conformance](docs/reference-conformance.md): retained, changed and added circuits, and physical layout review evidence.
- [Bring-up procedure](docs/bring-up.md), [full-chain simulation evidence](docs/analog-validation-rev-c.md), [cost estimate](docs/cost-estimate.md).
- [Firmware](firmware/README.md) and [Rust host CLI](host/README.md), including prebuilt RP2040 UF2 and macOS ARM64 host binary.
- [Complete revision C package](temper-lcr-rev-c-package.zip), [Gerber/drill ZIP](manufacturing/temper-lcr-gerbers.zip), [fabrication instructions](manufacturing/FABRICATION.md), and [verification receipt](validation/README.md). The BOM and CPL reside in `manufacturing/`.

The board requires **filled, copper-capped, planarized via-in-pad fabrication**. Budget approximately **$320–450 for the minimum prototype assembly batch, plus the vendor's unquoted four-layer via-in-pad surcharge**; fitted components alone are about $76 per board. JLC's minimum batch is five bare boards and two assembled boards, even when only one working instrument is needed. See the cost estimate for inclusions and limits.

## Circuit and operation

AD9833 sine generator → two-stage RC reconstruction → AC coupling and OPA810 gain 6 → retained TIDA-060029 analog core → two THS4551 differential drivers → ADS9224R simultaneous 16-bit ADC → RP2040 USB CDC. The 24 MHz DDS clock derives from the MCU; acquisition uses two serial data lanes at 1 MSPS, and the firmware boxcar-sums 1–20 consecutive conversions per output sample at low frequencies instead of undersampling. The Rust host fits both waveforms at the actual DDS frequency, applies complex feedback impedance and fixture calibration, and reports complex impedance and equivalent series L/C/R.

A regulated **5 V ±5%, 1 A, center-positive external supply** powers the board. USB carries data and ground. A forced-PWM TPS65131 and low-noise positive/negative postregulators supply approximately ±12 V. The instrument is ground referenced; it has no mains isolation. Neither DUT terminal should be connected to an external powered circuit.

With power removed, fit exactly one matched pair of removable jumpers:

| Range | Source selection | Feedback selection | Feedback impedance |
|---|---|---|---|
| Low | JP1 | JP4 | 100 Ω with local 100 pF |
| Medium | JP2 | JP5 | 5 kΩ with local 100 pF |
| High | JP3 | JP6 | 100 kΩ with local 100 pF |

The first qualification targets are 35–60 kHz stage53 coil and resonant-capacitor measurements, plus a 1 kHz bus-capacitor check. The firmware permits 100 Hz–100 kHz excitation, but usable accuracy and impedance limits must be established with standards at each frequency and range. Maximum nominal source is approximately 3.6 Vpp; the 100 Ω source resistor limits short-circuit current to approximately 18 mA peak. This justifies omitting TI's optional BUF634A stages for this small-signal use.

## Stage53 measurements

| Component | Intended check | Practical limit |
|---|---|---|
| Coil, with and without pan | Complex impedance and equivalent series L/R at 35–60 kHz, roughly 5–30 Ω | Small-signal only; does not predict power-level loss, heating or saturation |
| Five 100 nF capacitors / 0.5 µF bank | Individual values, bank impedance and relative loss comparisons | Calibrated ESR uncertainty must be measured; no milliohm claim |
| 9 µF bus capacitors | Capacitance around 1 kHz, approximately 17.7 Ω | Discharge and isolate first; no high-voltage or high-frequency ESR qualification |
| Chokes, snubber/gate capacitors | Value comparison and gross faults within qualified ranges | Parallel circuit paths require disconnection or lifting a lead |
| 1 mΩ current shunt | Unsupported | Requires a separate four-wire low-resistance measurement architecture |

Stage53 source: `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, SHA256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`. The LCR project does not modify or release the Temper power-stage board.

## Reproduction and qualification

Explicit component/pin/placement records are in `cad/design.json`; routed segments, vias, plane and keepouts are in `cad/routing.json`. The existing Python adapter calls native pcbnew and serializes KiCad sources. Host measurement logic is Rust; RP2040 firmware uses the official Pico SDK. `cad/rebuild.sh` regenerates native CAD, fills zones, fails on ERC/DRC findings, exports fabrication data and verifies source/schematic/PCB/BOM/placement parity. KiCad 10.0.4 was used; project-local symbols and footprints are included.

Hardware qualification remains essential: inspect rails and oscillation, check source settling, acquire a source-off noise sweep, calibrate with known standards and verify a third independent standard. The full coupled amplifier models now converge at a checked true DC operating point. Bilateral loop measurements, independent controlled-source cuts, two FDA models, tolerance/load sweeps and local fast disturbances support the revised compensation. These typical-model checks do not establish physical-board stability or calibrated accuracy; all three ranges still require scope qualification. Revision C-local100p firmware and host reject revision B and earlier per-range-capacitor calibration files. The high range favors frequencies up to 10 kHz for sensitivity; its 100 pF feedback pole is 15.9 kHz. Final JLCPCB placement preview and assembler DFM remain outstanding.

Revision A’s AD5933 implementation and revision B’s uncompensated TI derivative are preserved under `archive/rev-a/` and `archive/rev-b/`. Both are superseded. Order only from the revision C package and its current BOM/CPL. Historical simulation files are labelled separately and are not the manufacturing target.
