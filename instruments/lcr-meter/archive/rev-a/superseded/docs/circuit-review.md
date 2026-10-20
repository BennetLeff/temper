# Circuit review and operating envelope

## Selected implementation

This board uses the AD5933 integrated DDS/ADC/DFT with an external AD8606 dual amplifier, following the low-impedance topology in [ADI CN0217](https://www.analog.com/en/resources/reference-designs/circuits-from-the-lab/cn0217.html). CN0217 demonstrates low-ohm loads with approximately 20 Ω feedback/calibration around 30 kHz. The source series resistor, feedback compensation, USB bridge and calibration model here are deliberate changes; published reference-design accuracy does not transfer automatically.

U2's VOUT drives C11 (1 µF) and the R8/R9 47 kΩ midpoint. U3A follows this bias and AC signal. R12 adds 10 Ω source isolation before J2 pin1, DUT_HI. The DUT returns through J2 pin2, DUT_LO, to U3B's inverting input. Its noninverting input is biased by R10/R11, 47 kΩ each, filtered by C12 1 µF. U3B output is TIA_OUT. R13/R14, 20 kΩ each, form the AD5933 internal unity-gain receiver stage through VIN/RFB. This is a current-sensitive path with calibrated source behavior; no separate voltage-sense converter exists.

The range feedback is R16/20 Ω + C15/100 nF, R17/200 Ω + C16/10 nF, R18/2 kΩ + C17/1 nF, or R19/20 kΩ + C18/100 pF. Each resistor is parallel to its capacitor; exactly one header jumper connects that branch to DUT_LO. All four selected branches have nominal RC=2 µs (79.6 kHz pole). R15 1 MΩ and C14 22 pF permanently close feedback. Effective impedance is `(1/Rrange + 1/1M + jω(Crange+22pF))^-1`. The software fits empirical complex scale rather than assuming an ideal resistor gain.

The AD5933 is fixed to range4 (~0.198 Vpp unloaded), PGA×1, external16 MHz clock; control high byte lower configuration bits are 0x03. Nominal drive amplitude is 99 mV peak before source impedance. Ideal purely resistive current at a 5 Ω DUT is 99mV/(10+5)≈6.6mA peak; at a hard short it would be9.9mA. Actual op-amp output impedance and frequency dependence add to10 Ω. These calculations set a design target, not a current-limit specification. Do not excite shorts or charged capacitors.

## Power and control

USB-C J1 uses both CC pull-downs, R1/R2 5.1 kΩ. D1 USBLC6-2SC6 protects the data interface; it is not DUT overvoltage protection. U4 AP2112 supplies3V3D continuously from5V VBUS; U1 MCP2221A VDD/VUSB use3V3D, with 100nF/470nF decoupling. U5 AP2112 supplies3V3A when factory MCP2221A GP2/USBCFG is high after USB enumeration. Analog power turns off during USB suspend. R4 pulls enable low if the bridge is unpowered. SDA/SCL pull-ups are on3V3A. No USB power delivery negotiation is needed. Keep factory pin configuration; some Linux kernel driver configurations repurpose GP2, as documented in the host README.

The external YXC16 MHz oscillator is powered by3V3A and feeds MCLK through33 Ω. The AD5933 synthesizer and DFT share this clock. The host transfers frequency words and four DFT bytes per point over100 kHz I²C; no high-rate raw ADC streaming or SPI bus is required. Factory USB firmware is already in the MCP2221A. The included Rust application performs acquisition and calculation.

The four-layer PCB has top/bottom signals, continuous In1 ground, and separated digital/analog supply pours on In2. Ground is common, including USB shield. This is not isolation. Local bypass capacitors and ground vias sit adjacent to IC supply pins. The USB full-speed connection has short board traces but is not a controlled-impedance/high-speed-certified interface. Data eye, enumeration and power suspend behavior need physical checks.

## Calibration and limits

At each exact frequency/range/drive/clock/fixture setting, normalize DFT registers as **real−i·imaginary**. This conjugation follows AD5933 revisionF pp19–20's impedance-phase convention. Fit `d=o+k/(Z+zs)` from an open fixture and two known resistive loads, then compute `Z=k/(d-o)-zs`. Open removes an additive term; two loads fit complex gain and additive source/lead impedance. This assumes linear, repeatable behavior and known AC standards. A third independent load must validate the result. A DC-accurate resistor with unknown parasitics is not automatically a suitable standard at 100 kHz.

For JP1, suggested first standards are measured10 Ω and40 Ω, with a separate20 Ω check. Do not use an excited hard short for calibration. Use standards of roughly the same impedance scale for other ranges. Recalibrate after changing jumper, temperature, amplitude, frequency grid, lead geometry or USB power. The host binds calibration metadata and rejects mismatches; it cannot sense which physical jumper is fitted.

Series `R=Re(Z)`, `L=Im(Z)/(2πf)` when positive, and `C=-1/(2πf Im(Z))` when negative are equivalent-circuit values at that frequency. Parallel networks, resonance, core loss and distributed capacitance may make a single L/C number misleading. There is no specified 0.1% accuracy, ESR floor, milliohm capability, live-circuit capability, four-wire sense, DC bias source or high-voltage insulation test. The 5 Ω lower target is pending bench verification. All CSV points remain flagged prototype_unqualified.

## Verification evidence

Native KiCad10.0.4 ERC/DRC and source↔schematic↔PCB pin mapping pass; independent parent checks use severity-all and schematic parity. These are topology/manufacturability checks, not analog performance measurements. `validation/analog-review.md` documents96 generic two-pole op-amp cases, within-rail responses and up to1.423× source peaking. That model is explicitly not the AD8606 manufacturer macromodel and cannot establish phase margin, accuracy, noise or stability of the assembled instrument. Scope the real source and receiver with capacitive loads before relying on measurements.

## Physical footprint audit

Exact package pinouts were checked against manufacturer documents: MCP2221A-I/ST=TSSOP14, AD5933YRSZ=SSOP16 5.3×6.2mm, AD8606ARZ=SOIC8, AP2112K=SOT23-5, USBLC6-2SC6=SOT23-6. Genuine ADI AD8606 C26360 is specified; similarly named UMW parts are not approved substitutes.

The HRO2020 USB drawing in `sources/usb-c.pdf` overrides the older stock KiCad land pattern: signal/power lands1.14mm long, centrey−3.67; ground/power x±3.2/±2.4; signal pitch0.5; locatingholesØ0.60 at±2.89,y−2.6; shellcentresx±4.325,y−3.1/+1.08; slots0.60×1.70/1.40. Frontslot copper is1.0×1.8 for0.20mm end annulus. The drawing's1.64mm is padtop-to-locatinghole, and0.50mm is padbottom-to-hole, so landlength=1.14mm. J1 centre(60,53.19),rotation180, places the recommended localPCBedgey3.19 atglobaly50. YXC3225 lands1.4×1.2mm centred±1.1,±0.85 follow its family drawing. Manufacturer pin1 and native pad positions are recorded; vendor assembly zero angles still require preview review.

## Primary references

- [AD5933 revisionF datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD5933.pdf)
- [AD8605/AD8606/AD8608 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD8605_8606_8608.pdf)
- [ADI CN0217](https://www.analog.com/en/resources/reference-designs/circuits-from-the-lab/cn0217.html) and [AN1252](https://www.analog.com/en/resources/app-notes/an-1252.html)
- [MCP2221A DS20005565D](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP2221A-Data-Sheet-DS20005565D.pdf); olderB local copy is not the authority for the corrected GP2 configuration table.
- [TI TIDA-060029](https://www.ti.com/tool/TIDA-060029), original analog-front-end inspiration, not the selected implementation.
