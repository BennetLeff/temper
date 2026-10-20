# Revision C reference inheritance and review

Revision C uses **TIDA-060029 as its analog measurement core**. Excitation, acquisition, USB control and power conversion are integrated on the same PCB. Full-chain simulation exposed insufficient stability margin in the derivative's low and middle ranges; a fixed local C104 = 100 pF now bypasses the range headers, and the host accounts for it. Earlier range-specific feedback capacitors C105/C41 are removed: placing compensation behind the header caused a sensitive inductive resonance. The ADC drivers also use the complete EVM feedback/filter topology with increased inside-feedback output resistance. This derivative has no established accuracy specification before hardware qualification.

The selected test article is stage53, `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, SHA-256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`, with its adjacent scoped manifest. The separate repository stage15b baseline check passed; that does not make the two boards interchangeable. This instrument does not modify or release either power-stage design.

## Authorities

TI documents are retained under `sources/ti/`:

- [TIDA guide TIDUEU6B](https://www.ti.com/lit/pdf/TIDUEU6): stability, measurement results and layout references.
- [TIDA schematic TIDM635](https://www.ti.com/lit/pdf/TIDM635), analog-core sheet 2; [PCB layers TIDM638](https://www.ti.com/lit/pdf/TIDM638).
- [OPA2810 SBOS789C](https://www.ti.com/lit/gpn/opa2810), section 11.
- [ADS9224R SBAS876C](https://www.ti.com/lit/gpn/ads9224r), Figure 80, reference decoupling, timing and layout.
- [ADS9224REVM SBAU315B](https://www.ti.com/lit/pdf/SBAU315), printed pages 6 and 26: complete feedback/output filter circuit.
- [THS4551 SBOS778D](https://www.ti.com/lit/gpn/ths4551), including RGT dedicated feedback pins.
- [TPS65131 SLVS493E](https://www.ti.com/lit/gpn/tps65131), Figure 8-1 and sections 8–9.
- [AD9833 revision G](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9833.pdf) and [RP2040](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) for new source/control circuitry.

## Circuit inheritance

| Block | Revision C | Relationship |
|---|---|---|
| Source buffer | U6A, OPA2810IDGKR; feedback at its own output | Retains TI topology/package; optional booster omitted |
| Ranges | R40–R45; matched RG/RF pairs of 100 Ω, 5 kΩ, 100 kΩ | Retains the topology underlying TI's bounded capacitive noise gain; one matching jumper pair required |
| Auto-balancing amplifier | U7A; grounded noninverting input, DUT low at summing input | Retained; feedback from actual amplifier output |
| TIA compensation | C104 = 100 pF directly between U7A output and summing input, common to all ranges; C41/C105 removed | Deliberate stability change. Keeps capacitor feedback local and independent of the selected RF header’s inductance; lowers high-range bandwidth and is included in software |
| Voltage sensing | U6B senses DUT high; U7B senses DUT low | Retains both followers; low follower does not sense TIA output |
| BUF634A | Omitted | Deliberate change at intended approximately 20 mA peak current ceiling; other loads require review |
| Acquisition | U8/U9 THS4551, U10 ADS9224R | Same device types as TI's test setup; added on this board using ADC application circuit |
| ADC network | Four 1 kΩ resistors per FDA; C106–C109 = 100 pF across RF; R90–R93 = 22 Ω before the feedback takeoff; R64/R65/R70/R71 = 4.32 Ω after the takeoff; 330 pF per ADC input to ground and 3.3 nF differential | Complete ADS9224REVM page 26 topology, with inside-feedback resistance increased from 10 Ω to 22 Ω for modelled stability margin |
| FDA package | THS4551IRGTR QFN16; dedicated FB pads 1/4 NC | External feedback originates after the 22 Ω resistors driven by main OUT pads 10/11; RGT internal 3.3 Ω FB branches are unused; EP grounded |
| FDA common-mode reference | REFby2 directly drives both VOCM inputs with C74 = 1 µF | EVM per-driver 100 Ω / 100 nF VOCM filters omitted; modelled reference is ideal and hardware qualification remains required |
| Excitation | AD9833, reconstruction filter, AC coupling, OPA810 gain stage | New integration outside TIDA validation |
| Control | Bare RP2040, QSPI flash, USB CDC, burst DMA | New integration; compiled digital tests do not validate analog behavior |
| Power | TPS65131 raw bipolar rails; TPS7A49/30 approximately ±12 V postregulation | New supply preserves intended OPA operating rails, not TI bench supplies |
| Fixture | Two-pin contact plane | Custom two-terminal fixture; not remote Kelvin sensing |

TI's unused VCA and evaluation connectors are omitted. Its source and ADC were outside the TIDA PCB boundary. Those additions make a complete one-PCB instrument and require separate qualification.

JP4 uses a project-local footprint with unchanged 2.54 mm pitch, pads and drill, and a 0.28 mm courtyard allowance around the nominal 2.54 mm body. The [Samtec TSW drawing/catalog](https://suddendocs.samtec.com/catalog_english/tsw_th.pdf) and [specified SNT shunt drawing](https://suddendocs.samtec.com/prints/snt-100-xx-x-x-mkt.pdf) define the physical envelope. Use TSW-102-07-G-S with SNT-100-BK-G, fully seated; a shorter post is not automatically compatible. The local capacitor removes the need to assume a 20 nH bound for that header.

## Signal/software agreement

Channel A is `HIGH_BUF − LOW_BUF`; channel B is `LOW_BUF − TIA_OUT`, including TIA inversion. With nominally equal FDA gains:

```text
Zf(f) = RF / (1 + j·2π·f·RF·CF)
Zdut(f) = Zf(f) · A(f) / B(f)
CF = 100 pF directly across U7A in every range.
```

This circuit relation is not a complete error model. At 100 kHz, nominal feedback compensation contributes approximately −0.36°, −17.44° and −80.96° to Zf on the three respective ranges. These are measurement-band feedback phases, not loop phase margins. The 100 kΩ feedback pole moves to about 15.9 kHz and |Zf| falls to about 15.7 kΩ at 100 kHz, reducing high-frequency resistive sensitivity about 6.4×. Qualify that range’s practical bandwidth and noise on hardware; stage53 coil and resonant-capacitor checks use the 100 Ω range. The host applies a frequency-specific short/two-resistor correction; an independent standard must validate it. Revision C software and fresh calibration are required for the changed feedback network.

Firmware reads two simultaneous 16-bit lanes, rather than a single 32-clock stream. The 120 MHz MCU also supplies DDS MCLK at 24 MHz. Fitting uses the tuning-word frequency; crystal tolerance remains an absolute frequency uncertainty.

## Layout acceptance

Electrical review passed for AFE topology, feedback signs, acquisition/source pin maps, reverse-polarity FET and supply topology. The source was updated with per-pin 1 µF ADC supply bypass and supplemental 10 nF OPA2810 bypass. Filter placement is checked against actual ADC pad positions during routing. Firmware settling increased to 1000 ms for the source coupling network.

The [Rev C analog report](analog-validation-rev-c.md) supersedes the earlier bounded Rev B analysis. It uses the complete coupled amplifier chain, real FDA DC loading, explicit internal model-bias checks and a bilateral loop calculation. The test bridge is mathematically removed from that calculation. KLU and reproducible initial guesses resolve the numerical failure without changing TI's model libraries. An [independent FDA audit](../validation/fda-independent/README.md) cross-checks its compensation in both original 2016 and current GWL TI models, with 64 combined tolerance corners per model. The report defines the actual simulated cases and limitations; circuit review and typical macro models do not establish physical accuracy or every possible DUT/fixture condition.

The final Rev C CAD checkpoint is identified by `validation/independent-verification-rev-c.json` and the package manifest. Native KiCad ERC, DRC with all track errors, schematic parity and independent geometry results are recorded in the Rev C receipts below. The selected stage53 hash and the separate repository baseline must match their pinned inputs; they are not revised by this instrument work.

| Requirement | Final CAD evidence |
|---|---|
| OPA signal parasitics | All twelve U6/U7 signal-pin centers and sixteen FDA input/feedback pad centers lie in deliberate relief on In1/In2/B; actual Gerber plane windows reviewed. Added source-output pocket covers U6 pin1. |
| Feedback | Direct adjacent-pin follower feedback; RF range connections and the fixed local C104 feedback path reviewed with the TIA; summing-node relief retained and digital routing kept outside that area. RF header/trace inductance is stressed separately from the short local-capacitor path; these lumped assumptions require first-board waveform qualification. Calibration cannot repair an unstable amplifier. |
| Bypass | C50–C53 10 nF supply-pad centers are 2.031–2.050 mm from their OPA supply pads, within the 2.54 mm placement recommendation. Ground vias are 1.000–1.025 mm from those capacitor ground pads and outside the plane windows. TI's 100 nF + 1 µF per-rail bypass remains fitted. |
| ADC kickback | Output-isolation/filter network placed beside ADC inputs; C62/C63/C68/C69 ground pads use filled/capped vias directly into the ground return. Copper and paste plots reviewed. |
| Reference | REFby2 C74 pad-center distance 1.847 mm; REFOUT C75 4.894 mm; separate 22 µF REFP reservoirs C72/C73 each 2.600 mm from their ADC reference pads. FDA common mode is REFby2. These distances are geometry, not settling measurements. |
| Switcher | Hand-routed switching-current loops, shielded inductors, forced PWM, local ground vias and separation from the analog input cluster. Converter placement/top copper reviewed against its application guidance. |
| Digital | Zero non-ground track segments on In1; actual ground Gerber shows a continuous plane outside deliberate amplifier relief and ordinary pad/via clearances. Crystal relocated beside MCU with local clock routes. |
| Manufacturing | 175 electrical source/schematic/PCB components and pin maps agree (179 footprints including four mounting holes); 164 SMT placements across 53 BOM lines. Exact-part footprint/rotation audit, native DRC and printed control/range labels reviewed. Fifteen intentional SMT-land vias require four-layer resin-filled, copper-capped, planarized POFV; no unexpected drill/SMT overlap. |

Independent native and geometry receipts are retained in `validation/independent-erc-rev-c.json`, `independent-drc-rev-c.json` and `independent-layout-rev-c.json`. Earlier `*-final.json` files describe Rev B and do not qualify Rev C. `independent-verification-rev-c.json` ties these native results, the 558-pin independent netlist comparison and the source files to exact SHA-256 values. The geometry receipt uses native pad positions and rectangular relief bounds; visual Gerber review supplements its pin-center coverage checks. The assembly, mask, paste, copper, plane and outline exports belong to the same frozen PCB. The package manifest identifies their exact bytes.

The native/geometry receipts describe the candidate’s **CAD review**; the analog report separately records simulation acceptance. Vendor process/stackup acceptance, final JLC component-orientation preview and first-board measurements remain outstanding. The required POFV process and its unquoted surcharge are stated in the manufacturing instructions and cost estimate. These checks do not certify physical stability, calibrated accuracy or mains safety.

## Limits of inherited evidence

TI's measured results used an external stimulus, separate acquisition board and Keysight E4980A comparison. Errors vary by range, frequency and component; advertised best accuracy does not transfer as a 0.1% system specification.

Stage53 qualification targets are coil/pan and resonant capacitance at 35–60 kHz, plus 9 µF checks near 1 kHz. Neither these references nor the generated files establish milliohm-shunt accuracy, high-current saturation/loss, voltage withstand or energized-stage suitability. Waveform, source-off noise and independent-standard checks remain necessary.
