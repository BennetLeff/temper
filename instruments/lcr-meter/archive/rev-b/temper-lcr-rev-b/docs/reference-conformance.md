# Revision B reference inheritance and review

Revision B uses **TIDA-060029 as its analog measurement core**. Excitation, acquisition, USB control and power conversion are integrated on the same PCB. This derivative has no established accuracy specification before hardware qualification.

The selected test article is stage53, `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, SHA-256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`, with its adjacent scoped manifest. The separate repository stage15b baseline check passed; that does not make the two boards interchangeable. This instrument does not modify or release either power-stage design.

## Authorities

TI documents are retained under `sources/ti/`:

- [TIDA guide TIDUEU6B](https://www.ti.com/lit/pdf/TIDUEU6): stability, measurement results and layout references.
- [TIDA schematic TIDM635](https://www.ti.com/lit/pdf/TIDM635), analog-core sheet 2; [PCB layers TIDM638](https://www.ti.com/lit/pdf/TIDM638).
- [OPA2810 SBOS789C](https://www.ti.com/lit/gpn/opa2810), section 11.
- [ADS9224R SBAS876C](https://www.ti.com/lit/gpn/ads9224r), Figure 80, reference decoupling, timing and layout.
- [THS4551 SBOS778D](https://www.ti.com/lit/gpn/ths4551), including RGT dedicated feedback pins.
- [TPS65131 SLVS493E](https://www.ti.com/lit/gpn/tps65131), Figure 8-1 and sections 8–9.
- [AD9833 revision G](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9833.pdf) and [RP2040](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) for new source/control circuitry.

## Circuit inheritance

| Block | Revision B | Relationship |
|---|---|---|
| Source buffer | U6A, OPA2810IDGKR; feedback at its own output | Retains TI topology/package; optional booster omitted |
| Ranges | R40–R45; matched RG/RF pairs of 100 Ω, 5 kΩ, 100 kΩ | Retains the topology underlying TI's bounded capacitive noise gain; one matching jumper pair required |
| Auto-balancing amplifier | U7A; grounded noninverting input, DUT low at summing input | Retained; feedback from actual amplifier output |
| High-range compensation | C41, nominal 5 pF across 100 kΩ RF branch | Retained; complex feedback included in software |
| Voltage sensing | U6B senses DUT high; U7B senses DUT low | Retains both followers; low follower does not sense TIA output |
| BUF634A | Omitted | Deliberate change at intended approximately 20 mA peak current ceiling; other loads require review |
| Acquisition | U8/U9 THS4551, U10 ADS9224R | Same device types as TI's test setup; added on this board using ADC application circuit |
| ADC network | Four 1 kΩ resistors per FDA; 4.02 Ω isolation per output, 330 pF per input to ground, 3.3 nF differential | ADS9224R Figure 80 derivative; sourced 4.02 Ω replaces nominal 4 Ω |
| FDA package | THS4551IRGTR QFN16 | Sourcing change; RF connects FB+ to IN− and FB− to IN+; EP grounded |
| Excitation | AD9833, reconstruction filter, AC coupling, OPA810 gain stage | New integration outside TIDA validation |
| Control | Bare RP2040, QSPI flash, USB CDC, burst DMA | New integration; compiled digital tests do not validate analog behavior |
| Power | TPS65131 raw bipolar rails; TPS7A49/30 approximately ±12 V postregulation | New supply preserves intended OPA operating rails, not TI bench supplies |
| Fixture | Two-pin contact plane | Custom two-terminal fixture; not remote Kelvin sensing |

TI's unused VCA and evaluation connectors are omitted. Its source and ADC were outside the TIDA PCB boundary. Those additions make a complete one-PCB instrument and require separate qualification.

## Signal/software agreement

Channel A is `HIGH_BUF − LOW_BUF`; channel B is `LOW_BUF − TIA_OUT`, including TIA inversion. With nominally equal FDA gains:

```text
Zf(f) = RF / (1 + j·2π·f·RF·CF)
Zdut(f) = Zf(f) · A(f) / B(f)
CF = 5 pF on 100 kΩ range; nominally zero otherwise.
```

This circuit relation is not a complete error model. At 100 kHz, nominal high-range compensation alone contributes approximately −17.4° to Zf. The host applies a frequency-specific short/two-resistor correction; an independent standard must validate it.

Firmware reads two simultaneous 16-bit lanes, rather than a single 32-clock stream. The 120 MHz MCU also supplies DDS MCLK at 24 MHz. Fitting uses the tuning-word frequency; crystal tolerance remains an absolute frequency uncertainty.

## Layout acceptance

Electrical review passed for AFE topology, feedback signs, acquisition/source pin maps, reverse-polarity FET and supply topology. The source was updated with per-pin 1 µF ADC supply bypass and supplemental 10 nF OPA2810 bypass. Filter placement is checked against actual ADC pad positions during routing. Firmware settling increased to 1000 ms for the source coupling network.

The [analog simulation report](analog-validation-rev-b.md) records successful bounded checks, approximately 30° modeled TIA margin for the 5 kΩ/5 kΩ case, and failure of the complete coupled manufacturer-model circuit to converge. Circuit review is not a full stability or accuracy qualification.

The final CAD checkpoint is board SHA-256 `15546293b47b16b7edba8a79bdc3feafe582b2b85618be469d930ba27e1816d9`. Native KiCad 10.0.4 ERC, DRC with all track errors, schematic parity and an independent repeat passed with zero findings. The selected stage53 hash and the separate 69-input repository baseline were rechecked unchanged.

| Requirement | Final CAD evidence |
|---|---|
| OPA signal parasitics | All twelve U6/U7 signal-pin centers lie in deliberate relief on In1/In2/B; actual Gerber plane windows reviewed. Added source-output pocket covers U6 pin1. |
| Feedback | Direct adjacent-pin follower feedback; RF/C41 beside TIA; summing-node relief retained and digital routing kept outside that area. Manual-range connector parasitics still need fixture calibration. |
| Bypass | C50–C53 10 nF supply-pad centers are 2.031–2.050 mm from their OPA supply pads, within the 2.54 mm placement recommendation. Ground vias are 1.000–1.025 mm from those capacitor ground pads and outside the plane windows. TI's 100 nF + 1 µF per-rail bypass remains fitted. |
| ADC kickback | Output-isolation/filter network placed beside ADC inputs; C62/C63/C68/C69 ground pads use filled/capped vias directly into the ground return. Copper and paste plots reviewed. |
| Reference | REFby2 C74 pad-center distance 1.847 mm; REFOUT C75 4.894 mm; separate 22 µF REFP reservoirs C72/C73 each 2.600 mm from their ADC reference pads. FDA common mode is REFby2. These distances are geometry, not settling measurements. |
| Switcher | Hand-routed switching-current loops, shielded inductors, forced PWM, local ground vias and separation from the analog input cluster. Converter placement/top copper reviewed against its application guidance. |
| Digital | Zero non-ground track segments on In1; actual ground Gerber shows a continuous plane outside deliberate amplifier relief and ordinary pad/via clearances. Crystal relocated beside MCU with local clock routes. |
| Manufacturing | 167 source/schematic/PCB components and pin maps agree; 156 SMT placements across 52 BOM lines. Exact-part footprint/rotation audit, native DRC and printed control/range labels reviewed. Thirteen intentional SMT-land vias require four-layer resin-filled, copper-capped, planarized POFV; no unexpected drill/SMT overlap. |

Independent native and geometry receipts are retained in `validation/independent-erc-final.json`, `independent-drc-final.json` and `independent-layout-final.json`. The geometry receipt uses native pad positions and rectangular relief bounds; visual Gerber review supplements its pin-center coverage checks. The assembly, mask, paste, copper, plane and outline exports belong to the same frozen PCB. The package manifest identifies their exact bytes.

This closes the circuit/layout **CAD review**. Vendor process/stackup acceptance, final JLC component-orientation preview and first-board measurements remain outstanding. The required POFV process and its unquoted surcharge are stated in the manufacturing instructions and cost estimate. These checks do not certify physical stability, calibrated accuracy or mains safety.

## Limits of inherited evidence

TI's measured results used an external stimulus, separate acquisition board and Keysight E4980A comparison. Errors vary by range, frequency and component; advertised best accuracy does not transfer as a 0.1% system specification.

Stage53 qualification targets are coil/pan and resonant capacitance at 35–60 kHz, plus 9 µF checks near 1 kHz. Neither these references nor the generated files establish milliohm-shunt accuracy, high-current saturation/loss, voltage withstand or energized-stage suitability. Waveform, source-off noise and independent-standard checks remain necessary.
