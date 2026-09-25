# Zapote RTD circuit/interface audit

Audit input is the dirty WIP checkout `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`; the audited file bytes are identified in [rtd_contract.json](rtd_contract.json). This artifact is a source review and bounded model result; PCB placement/routing and physical evidence remain **NOT RUN**.

## Findings sent to source owner

The existing MAX31865 pin declarations match the Analog Devices SSOP-20 pin table. The authored 4-wire topology is also correct: `BIAS~REFIN_P`, RREF 430 Ω between `REFIN_P` and `REFIN_N`, `ISENSOR~REFIN_N`, `FORCE2~GND`, and four separate external conductors `FORCE+`, `RTDIN+`, `RTDIN-`, `FORCE-`. The current Top wiring maps those four nets to connector pins 1–4 as Bias+, Sense+, Sense−, Bias−. The source corrections in `rtd_analog_source.patch` and `rtd_window_protection.patch` move MAX31865 DVDD to upstream +3V3 with its own bypass, observe `RTDIN_P` through a shared 100 kΩ comparator branch, and tie the LOW divider bottom to `RTDIN_N`, so the four conductor opens have a concrete local analogue detector.

The accuracy requirement used here is the product criterion of ±2 °C steady-state at 100 °C, with ±1 °C stability at 60 °C as a separate dynamic/thermal criterion. The older 0–250 °C range remains a bounded extended-range calculation, not the product accuracy requirement.

The source corrections retained for schematic freeze are:

1. Add a differential capacitor across `RTDIN_P` and `RTDIN_N`. MAX31865 Figure 4 shows 100 nF as a typical 100 Ω application value, but that value is incompatible with a high-value diagnostic pullup and the 100 ms service bound (`tau` about 1 s). The selected exact part is KEMET `C0603C102J5GACTU`, 1 nF C0G, 50 V, 0603. With a 200 pF harness/PCB parasitic budget, ±5% capacitor tolerance, and 100 ppm/°C pullup TCR over a 60 °C span, its worst selected `tau` is 1.373 ms; 10.5 tau is 14.414 ms. C0G avoids the DC-bias derating of an X7R filter. EMC/noise acceptance remains a physical check.
2. Add paired 1 MΩ diagnostic resistors from each `RTDIN_P` and `RTDIN_N` to `BIAS`. MAX explicitly recommends the RTDIN+ pullup; the matched RTDIN− pullup is the concrete extension needed to classify a broken Sense− lead as a negative differential/low-code fault. Use two Yageo `RC0603JR-071ML`, 0603, 1 MΩ, ±5%, 0.1 W. The smaller pullup keeps the 10.5τ timing bound below 14 ms. Its healthy-path loading error is included in the normal 100 °C accuracy ledger (0.22 °C allocation).
3. Protect both TLV3201 inputs with one shared 100 kΩ branch from `RTDIN_P`, exact `RC0603FR-07100KL`, 0603, ±1%. The unit's allowed passive probe transient is −0.2…+2.5 V, source impedance ≥1 kΩ, edge ≥10 µs, pulse ≤1 ms, and repetition ≤1 Hz. That 2.7 V span fits the TLV3201 minimum supply without input clamp; the MAX's ±45 V RTDIN limit is a device limit only. The RTDIN_N LOW-divider path is bounded separately, including its TLV input-clamp path, and local-off operation is owned by the rail monitor/HW fault protocol.

Top currently gives the one physical REF2025 `VREF` output two override names, `OVP_VREF_2V5` and `OCP2_VREF_2V5`. Both downstream consumers must share one electrical net identity, `SHARED_REF_2V5`; the patch proposal changes only those names and comments.

The RTD safety document's property-test paths under `packages/temper-placer/tests/validation/` are stale in this checkout. The existing runnable tests are under `elec/validation/`: `test_rtd_window_selected_values_spice.py`, `test_rtd_window_ported_models_spice.py`, `test_rtd_hw_fault_spice.py`, and `test_rtd_fault_latch_transient_spice.py`. The old document also says the thresholds must be derived from a measured constant bias current. For this circuit the correct quantity is the MAX31865 series network:

```text
I(RTD) = VBIAS / (RREF + RRTD)
V(REFIN-) = I(RTD) * RRTD = VBIAS * RRTD / (RREF + RRTD)
```

The bias current is resistance-dependent; using one guessed constant current would be the wrong model. The current selected-value deck has the correct passive equation but still uses behavioral comparators.

## Standalone unit boundary and conductor window

The source-ready standalone wrapper is [standalone_interface_source_proposal.ato](standalone_interface_source_proposal.ato), with an equivalent patch in [standalone_interface_source.patch](standalone_interface_source.patch). It instantiates the existing module as `rtd_pan` and the proposed Samtec `FTSH-105-01-F-D` as `unit_io`. Pin order is `1:+3V3`, `2:GND_A`, `3:GND_B`, `4:RTD_SCK`, `5:RTD_SDI`, `6:RTD_SDO`, `7:RTD_CS_N`, `8:RTD_DRDY`, `9:RTD_HW_FAULT`, `10:SHARED_REF_2V5`. The two ground contacts are the same unit ground net. No MCU, buck, or host harness endpoint is declared.

The exact Samtec product is a plain double-row header; its silkscreen dot marks pin 1 but there is no keyed shroud. The proposed footprint uses the Samtec DTH print's 0.71 mm finished hole and 1.05 mm copper pads. `kicad-cli pcb render` completed for the connector and for the TPS389001DSER DSE footprint; the receipt records the expected no-outline warning from the minimal test boards. The final vendor drawing check of body keepout, plating, and host-side orientation remains a mechanical acceptance item.

The companion [rtd_window_protection.patch](rtd_window_protection.patch) adds the shared protected RTDIN_P comparator branch after the direct-window topology. The executable [rtdin_comparator_model.py](rtdin_comparator_model.py) and [rtdin_comparator_model_results.txt](rtdin_comparator_model_results.txt) solve the explicit external resistor network with 65536 independent corners per row (including independent diagnostic-pullup mismatch), including MAX ±14 nA leakage, TLV3201 ±5 nA per input, combined window-node bias, board leakage, resistor TCR, and reference tolerance. At 1 Ω per force/sense lead (the adopted 500 mm harness accuracy case), healthy 100–194.1 Ω has positive LOW/HIGH margins and each individual FORCE+, FORCE−, SENSE+, SENSE− open has the expected negative margin. A separate 50 Ω per-lead robustness sweep also retains those polarity verdicts. The runtime [rtdin_transient_model.py](rtdin_transient_model.py) uses the actual 1.10 nF/200 pF RC network and reports all four crossings within 0.329 ms at a conservative 20 mV comparator overdrive (the analytic maximum-RC envelope bounds the detector at 1.321292 ms), including the sourced 55 ns TLV3201 propagation maximum and conservative 10 ns logic bound; the worst SENSE+ crossing is 0.329 ms because the capacitance is located at the RTDIN pins. The allowed passive probe envelope is −0.2…+2.5 V with ≥1 kΩ source, so clamp sum is zero; the device-only MAX ±45 V limit is not a unit immunity claim. The RTDIN_N LOW-divider path remains included in the model as a bounded comparator-input path.

## Official device evidence

The [MAX31865 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf) gives the SSOP pin functions on pp. 7–8: BIAS pin 4, REFIN+ pin 5, REFIN− pin 6, ISENSOR pin 7, FORCE+ pin 8, FORCE2 pin 9, RTDIN+ pin 10, RTDIN− pin 11, FORCE− pin 12, grounds pins 13/18/19, SDI/SCLK/CS/SDO pins 14–17, DRDY pin 1, DVDD pin 2, VDD pin 3, and NC pin 20. It specifies 1.95–2.06 V BIAS, 5.75 mA maximum BIAS output current, 3.5 mA maximum active supply current excluding BIAS load, 10 ms maximum BIAS startup, 600 µs maximum automatic fault cycle, 55 ms maximum single conversion with 60 Hz filtering, 3.0–3.6 V supplies, and 5 MHz maximum SCLK. The source now powers DVDD from upstream +3V3 with a separate 100 nF bypass while VDD remains post-ferrite; this is a partial-power host contract, not a claim that an unpowered MAX may be driven. It explicitly says a broken RTDIN+ lead can be unpredictable and recommends 10 MΩ from RTDIN+ to BIAS; its typical circuits show 100 nF across the RTD inputs for a 100 Ω RTD. It states that the high threshold sets the open fault when conversion result is greater than or equal to the threshold.

The [TLV3201 datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf), Rev. C (SBOS561C), gives SOT-23 pinout OUT=1, GND=2, IN+=3, IN−=4, VCC=5, 2.7–5.5 V supply, ±4 mV maximum input offset over temperature for TLV3201, 5 nA maximum input bias per input, functional common-mode from VEE−0.2 V to VCC+0.2 V, ±10 mA input-current absolute maximum, 55 ns maximum propagation delay over temperature, and push-pull outputs. The source's `TLV3201AIDBVR` and SOT-23-5 footprint match that device. The bounded model uses ±4 mV and ±5 nA per input as conservative corners; the 100 kΩ RTDIN_P branch limits the declared transient clamp current.

The [REF20xx/REF2025 TI page](https://www.ti.com/product/REF2025) specifies the dual VREF/VBIAS outputs, ±0.05% initial accuracy, 8 ppm/°C maximum drift, 3 ppm/V line regulation, 8 ppm/mA load regulation, less than 430 µA quiescent current, ±20 mA output capability, 2.52–5.5 V input, and SOT-23-5 package. The source's `REF2025AIDDCR` pin declaration matches the TI pin order. Its VBIAS is the 1.25 V divider source; its 2.5 V VREF is shared with OVP and OCP2. The protected-window model bounds the VREF divider load at 96.242 µA and separately records the two downstream comparator input-bias contributions.

The selected [TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf), Rev. A, specifies 1.5–5.5 V operation, 1% maximum adjustable threshold accuracy, maximum 0.825% hysteresis, and an open-drain active-low RESET. The DSE top-view pin map is SENSE=1, GND=2, MR=3, VDD=4, CT=5, RESET=6. The exact selected part is `TPS389001DSER`; CT is left open, and RESET has the existing 10 kΩ upstream pullup. Its no-capacitor delay is approximately 25 µs minimum. The monitor is a bounded source/model correction; RESET behavior during rail ramp and loss remains a physical acceptance item.

The [Panasonic ERA6AEB6983V product page](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA6AEB6983V) identifies the exact 698 kΩ monitor-divider part as 0805, 0.1%, 0.125 W, ±25 ppm/°C, −55…155 °C. The [Susumu RG-series ordering table](https://www.susumu.co.jp/common/pdf/RG_LL_Data_Sheet.pdf) defines `V` as ±5 ppm/°C and `W` as ±0.05% tolerance for the RG2012 0805 family; the exact `RG2012V-431-W-T1` 430 Ω option is independently listed with those values by [DigiKey](https://www.digikey.com/en/products/detail/susumu/RG2012V-431-W-T1/602808). These parts retain the existing 0805 land pattern; procurement must verify the exact reel/lot.

The [JST XH drawing](https://jst.es/wp-content/uploads/2025/06/xh-connector.pdf) lists B4B-XH-A and XHP-4 at 2.5 mm pitch and identifies the No. 1 circuit. It does not prove the assembled harness orientation, color order, or continuity; those are bench checks.

## Threshold and bounded window result

Firmware's inclusive boundaries are `R <= 10 Ω` for short and `R >= 300 Ω` for open. With 430 Ω RREF, the 15-bit ADC code is `floor(32768*R/RREF)`. The low comparator is a strict `<` comparison, so its threshold must be `floor(32768*10/430)+1 = 763`, word `0x05F6` (1526), including the exact-integer case. The high comparator is `>=`, so its threshold is `floor(32768*300/430) = 22861`, word `0xB29A` (45722). The effective nominal register boundaries are 10.0125 Ω and 299.9948 Ω, while firmware retains the inclusive floating-point guard. Configuration `0x84` is `1000_0100`: VBIAS on, normally-off conversion mode, automatic fault detection D3:D2=01, no status clear, and 60 Hz filter (D0=0); it does not start an ADC conversion or provide conversion DRDY. Continuous conversion is `0xC0` (`VBIAS|D6|60Hz`).

The current direct hardware window uses the REF2025 1.25 V VBIAS divider values already in source, with LOW returned to RTDIN_N and HIGH observing protected RTDIN_P. The old table that called `REFIN−` the comparator input was stale after this topology correction; the authoritative current values are in `rtdin_comparator_model_results.txt`.

| Quantity | 1 Ω harness nominal/corner result |
|---|---:|
| Healthy RTDIN_P, 100 Ω | 0.370107–0.391511 V |
| Healthy RTDIN_P, 194.1 Ω | 0.607492–0.642496 V |
| Healthy LOW margin, 194.1 Ω | +0.423960…+0.472730 V |
| Healthy HIGH margin, 194.1 Ω | +0.135419…+0.186921 V |
| FORCE+ open LOW margin | −0.180477…−0.166474 V |
| SENSE+ open HIGH margin | −1.317987…−1.119682 V |
| SENSE− open LOW margin | −0.693525…−0.643604 V |
| FORCE− open HIGH margin | −1.277307…−1.151397 V |

The 65,536-corner sweep independently varies MAX BIAS, precision RREF, REF2025 initial/drift/line/load terms, divider tolerance/TCR, each diagnostic pullup independently, MAX and TLV input leakage, board leakage, and comparator offset. The 50 Ω harness robustness sweep remains separate. The HIGH comparator's passive threshold is earlier than the firmware's 300 Ω digital threshold: it is guaranteed clear through the modeled lower transition, corner dependent through the transition band, and guaranteed fault by 300 Ω. The contract therefore accepts early hardware FAULT in that transition band; it does not claim no-false-trip throughout 194.1–300 Ω.

The RTD_AVDD monitor is a separate supply guard. The prior TPS3700/698 kΩ/100 kΩ choice was fail-safe for trip but could not guarantee release at the declared valid local floor. The source correction in [rail_monitor_tps3890.patch](rail_monitor_tps3890.patch) selects exact TI `TPS389001DSER` (WSON-6 DSE, 1.5 mm × 1.5 mm) with Panasonic `ERA-3AEB1652V`, 16.5 kΩ ±0.1%, ±25 ppm/°C, 0603, over `ERA-3AEB103V`, 10 kΩ ±0.1%, ±25 ppm/°C, 0603. Exhaustive independent corners using ±1% threshold, 0.825% maximum hysteresis, ±100 nA SENSE current, resistor tolerance, and opposing TCR over 60 °C give 3.006010–3.089236 V falling and 3.092085–3.114708 V rising thresholds. The falling minimum is 6.010 mV above the MAX31865 3.0 V minimum. The authoritative buck contract is 3.135–3.465 V; allowing 10 mA RTD-branch current and the ferrite's 0.18 Ω maximum DCR gives a bounded local minimum of 3.1332 V, 18.492 mV above the worst rising clear. This closes the deterministic valid-low release corner in the source/model envelope. Divider current is about 118.2 µA at that rail, over 100× the 100 nA SENSE-current bound. RESET transients, rail ramp, and physical loss behavior still require physical validation. See `rail_monitor_bounds.txt` for the reproducible calculation and official links.

This result is a bounded calculation, not a PVT proof, vendor macro-model result, or physical safety claim.

The exact TI `TPS3808G01DBVR` alternative was checked against the same rail
contract. It is a 6-pin SOT-23 adjustable supervisor (DBV pin map RESET=1,
GND=2, MR=3, CT=4, SENSE=5, VDD=6; open-drain active-low RESET), with 0.405 V
reference, -2/+2% adjustable threshold accuracy, 1.5–3% hysteresis, and
20 ms delay with CT open. Guaranteeing a falling trip above 3.0 V would require
nominal VIT ≥3.0612 V; its worst rising release is then ≥3.155 V before divider
error, above the 3.1332 V valid local floor. It is therefore recorded as a
rejected replacement rather than a source patch. A lower-impedance precision
comparator/supervisor with an explicitly bounded threshold and hysteresis, or
a higher valid-rail floor, is still required if guaranteed release at 3.135 V
is a product requirement. See `rail_monitor_bounds.txt` for the calculation and
official TI links.

## Firmware conversion protocol correction

The current driver writes `0x84`, waits for DRDY, and reads only fault status. This conflates the automatic fault cycle with a conversion. The proposed sequence is: write `0x80` during initialization to enable BIAS; wait two 10 ms control ticks (covering the MAX31865 10 ms BIAS-start maximum); write `0x84` for the one-time automatic fault detection cycle with the 60 Hz filter; wait one control tick (covering its 600 us maximum); write `0xC0` (`VBIAS|CONVERSION_AUTOMATIC|60HZ`) to enable continuous conversion; wait for falling-edge DRDY; read RTD registers 01h/02h first to release DRDY; then read latched fault status 07h. Do not repeat `0x84` every sample because that interrupts continuous conversion. With control-tick alignment, the first startup-open result is accepted by the next 10 ms tick at or before 90 ms, leaving 5 ms for fault-sink/control handoff. For an arbitrary runtime break, [rtd_sinc_phase_model.txt](rtd_sinc_phase_model.txt) uses an explicit third-order boxcar assumption: 40.8998 ms threshold crossing, up to one additional 17.6 ms continuous sample period, 10 ms poll including phase/jitter, 5 ms sink, and 14.4144 ms conservative RC accounting, totaling 87.9142 ms using the vendor continuous-period maximum; the 55 ms single-conversion bound applies to startup only. The force/RREF path remains intact during isolated SENSE opens, so this model uses the ratiometric `(300/RREF)*(REFIN+ - REFIN-)` threshold and actual healthy reference voltage. This timing is conditional engineering evidence, not a vendor guarantee. The service publishes a fresh resistance only after the RTD data and fault-status reads both succeed; readiness remains false until that first validated sample. The selected 1 nF C0G/1 MΩ paired network settles for 14.414 ms worst case including 200 pF parasitic budget and temperature coefficients, before the 30 ms continuous-conversion launch.

The proposal adds mock coverage for the `0x80 -> 0x84 -> 0xC0` writes, right-aligned 15-bit RTD data reads, repeated DRDY servicing without restarting the fault cycle, and fail-closed read/write errors. It is a source proposal only; the canonical firmware and tests were not edited in this checkout.

## Independent expected fault verdicts

| Fault | Digital MAX31865 path | Local hardware path | Expected overall verdict |
|---|---|---|---|
| RTD element short, 0–10 Ω | Low threshold, latched status | RTDIN_P below RTDIN_N-referenced LOW threshold | FAULT |
| RTD element valid, 100–194.1 Ω | Valid conversion | Both permissions high | CLEAR |
| Analogue transition, 194.1–262.7 Ω | Firmware still valid below 300 Ω | Guaranteed inside high window under declared corners | CLEAR |
| Analogue transition, 262.7–293.6 Ω | Firmware still valid below 300 Ω | High comparator result depends on VBIAS, reference, divider, and offset corner | Contract must accept either CLEAR or FAULT |
| Analogue transition, 293.6–300 Ω | Firmware still valid below 300 Ω | High comparator guaranteed fault in the bounded model | Contract must accept early hardware FAULT |
| RTD element open, ≥300 Ω | High threshold, latched status | RTDIN_P above HIGH threshold | FAULT |
| FORCE+ open | MAX Table 12 lists the analogue-path fault condition; “indeterminate” describes resulting conversion data | Bounded open-loop model drives RTDIN_P near ground, below LOW threshold | FAULT expected from local comparator; numeric MAX conversion result requires physical acceptance |
| RTDIN+ / SENSE+ open | MAX recommends 10 MΩ to BIAS; selected 1 MΩ gives faster bounded pullup | RTDIN_P rises near VBIAS and exceeds HIGH threshold | FAULT expected from local comparator; MAX SPI data is supplementary |
| RTDIN− / SENSE− open | Proposed matched 1 MΩ pullup drives the open RTDIN− input toward BIAS, making a negative differential and low conversion code | RTDIN_N rises and the LOW divider threshold exceeds RTDIN_P | FAULT expected from local comparator; MAX code is supplementary |
| FORCE− open | MAX Table 12 lists the analogue-path fault condition; “indeterminate” describes resulting conversion data | Bounded open-loop model drives RTDIN_P near VBIAS, above HIGH threshold | FAULT expected from local comparator; numeric MAX conversion result requires physical acceptance |
| RTD_AVDD brownout/loss | MAX31865 unavailable | TPS389001 withdraws rail permission; upstream-powered open-drain NAND releases upstream pull-up | FAULT |
| Upstream SAFETY_3V3 loss | Digital path unpowered | RTD_HW_FAULT pullup disappears; system DIS disable behavior belongs to milestone 3 | System disable obligation; no high-level RTD_HW_FAULT claim |

The four individual conductor rows are deliberately separate. An RTD-element-open test does not cover a cable conductor open. The RTDIN comparator patch gives FORCE+ and SENSE− a LOW path and FORCE− and SENSE+ a HIGH path; MAX31865 Table 12 still classifies unconnected FORCE conductors' conversion data as indeterminate, so the local analogue result is the independent detector. The MAX SPI state machine remains responsible for a fresh resistance/status sample, while comparator propagation and sink timing require separate acceptance.

## Exact inventory and risks

The current RTDSensing module has 33 physical component instances, excluding interface objects, after the paired diagnostics, differential filter, separate DVDD bypass, and protected comparator branch are included. The standalone interface adds one connector instance; interface objects are not counted as electrical components.

| Qty | Function | Exact MPN | Package/footprint | Pin or procurement risk |
|---:|---|---|---|---|
| 1 | RTD converter | MAX31865AAP+ | SSOP-20, `Package_SO:SSOP-20_3.9x8.7mm_P0.635mm` | Verify symbol pin 20 NC and grounds against generated netlist |
| 1 | RREF | RG2012V-431-W-T1 | 0805 | Susumu thin-film 430 Ω ±0.05%, ±5 ppm/°C, 1/8 W, −55…155 °C, AEC-Q200; exact lot/availability and solder stress need procurement check |
| 1 | VDD bypass | C0603C104K5RACTU | 0603 | 100 nF on post-ferrite VDD; source declares 10 V, verify DC-bias derating |
| 1 | DVDD bypass | C0603C104K5RACTU | 0603 | Separate 100 nF on upstream +3V3 DVDD; host partial-power sequencing remains required |
| 4 | SPI/CS series | RC0603FR-0733RL | 0603 | 33 Ω ±1%; edge/trace reflection not measured |
| 1 | Supply ferrite | BLM18AG121SN1D | 0603 inductor land pattern | Source models it as generic Resistor; impedance versus DC/current is not represented |
| 6 | Local IC bypass | C0603C104K5RACTU | 0603 | One each at REF2025, comparators, AND, TPS3890, NAND; placement not run |
| 1 | Dual reference | REF2025AIDDCR | SOT-23-5 | VREF is shared with OVP and OCP2; the source documents this shared identity |
| 2 | Window comparators | TLV3201AIDBVR | SOT-23-5 | Push-pull outputs; do not use as wired-OR sinks |
| 1 | Window AND | SN74LVC1G08DBVR | SOT-23-5 | Partial-power-down and input state during RTD_AVDD loss need board validation |
| 1 | RTD rail monitor | TPS389001DSER | WSON-6 DSE, `Temper_RTD:TPS389001DSER_WSON-6_DSE` | SENSE=1/GND=2/MR=3/VDD=4/CT=5/RESET=6; RESET open-drain active-low; six-pad no-EP land pattern rendered; solder/ramp behavior require validation |
| 1 | Fault NAND | SN74LVC1G38DBVR | SOT-23-5 | Open-drain/Ioff behavior and downstream latch input need integrated validation |
| 1 | Low divider top | ERA-3AEB6192V | 0603 | 61.9 kΩ ±0.1%; exact stocking evidence inherited from source doc |
| 2 | Low/high divider bottoms | ERA-3AEB103V | 0603 | 10 kΩ ±0.1%; resistor identity must remain separate instances |
| 1 | High divider top | ERA-3AEB5901V | 0603 | 5.9 kΩ ±0.1%; exact stocking evidence inherited from source doc |
| 1 | Window pulldown | RC0603FR-07100KL | 0603 | 100 kΩ ±1%; unpowered AND output behavior depends on input leakage |
| 1 | Protected RTDIN_P branch | RC0603FR-07100KL | 0603 | 100 kΩ ±1% shared by both TLV3201 inputs; allowed unit envelope is −0.2…+2.5 V, ≥1 kΩ source |
| 1 | Rail monitor top | ERA-3AEB1652V | 0603 | 16.5 kΩ ±0.1%, ±25 ppm/°C; exact Panasonic part used for the TPS389001 3.006–3.115 V bounded window |
| 1 | Rail monitor bottom | ERA-3AEB103V | 0603 | 10 kΩ ±0.1%, ±25 ppm/°C |
| 2 | Upstream fault/rail pullups | RC0603FR-0710KL | 0603 | 10 kΩ ±1%; pullup ownership is upstream SAFETY_3V3 |
| 1 | Probe header | B4B-XH-A(LF)(SN) | JST XH 2.5 mm vertical THT | Pin 1/mating orientation, crimp contact, cable shield, and creepage need bench/assembly evidence |
| 1 (proposed) | RTDIN differential filter | C0603C102J5GACTU | 0603 | 1 nF, C0G, 50 V across RTDIN+/−; selected with 200 pF parasitic budget to meet the 1 MΩ diagnostic RC bound; EMC/noise remains untested |
| 2 (proposed) | RTDIN+/RTDIN− diagnostic pullups | RC0603JR-071ML | 0603 | 1 MΩ ±5%, 0.1 W each; matched bias makes both sense opens produce bounded ADC polarity |
| 1 (proposed) | Standalone host interface | FTSH-105-01-F-D | THT 2×5, 1.27 mm, `Temper_RTD:FTSH-105-01-F-D_2x5_P1.27mm` | Samtec DTH print: 0.71 mm finished hole; proposal uses 1.05 mm pads; plain `-D` has no keyed shroud; pin-1 dot only |

## Shared reference contract

`REF2025AIDDCR.VBIAS` is the 1.25 V source for the RTD low/high threshold dividers. `REF2025AIDDCR.VREF` is a single 2.5 V source consumed by both `SafetyInterlock.ovp.vref_ext` and `SafetyInterlock.ocp2.vref_ext`. The source's two names (`OVP_VREF_2V5` and `OCP2_VREF_2V5`) are an identity error, not two independent references. The patch proposal assigns `SHARED_REF_2V5` to both. The two comparator inputs are high impedance, but the final load budget must include input bias/leakage, reference decoupling, and any later consumers; TI's ±20 mA rating is not a substitute for that budget.

## Model and validation status

The companion [rtd_window_bounded.cir](rtd_window_bounded.cir) is a portable ngspice passive/Boolean model. It sweeps representative short, valid, open, RTD_AVDD brownout, and RTD_AVDD loss states; its component model is intentionally limited to the source's voltage divider, series RREF/RTD, comparator permissions, and open-drain pullup. It does not model MAX31865 internal switch fault sequencing, cable parasitics, vendor transistor behavior, temperature/noise distributions, PCB geometry, or latch timing.

The machine-readable observed output is generated by [rtd_observed_faults.py](rtd_observed_faults.py) into [rtd_observed_faults.json](rtd_observed_faults.json), separate from the expected fault contract. It records the four transient conductor-open observations, healthy-window no-fault corners, the nominal 10 Ω ngspice short, startup masking, the TPS389001/upstream-NAND local-rail fault owner, passive local-off collapse as a separate non-detector observation, and the explicitly unmodeled upstream-loss owner, with source hashes and timing/current/reference budgets.

The standalone connector contract bounds the external `SHARED_REF_2V5` load to 100 µA and 10 nF; the REF2025 ±20 mA rating is a device capability, not the unit boundary. `RTD_HW_FAULT` reserves a 10 kΩ pullup and <=100 pF host load, giving a calculated 1.205 µs rise to 70% VCC; the downstream safety sink retains a separate 15 ms handoff allocation. These are interface assumptions pending system integration.

The protected comparator deck ran with ngspice 45.2; its current budget output bounds RTD_AVDD at 7.529050 mA total (MAX active 3.500 mA + MAX BIAS 3.874686 mA + diagnostics 4.364 µA + two TLV3201 65 µA limits + two logic 10 µA limits), leaving 2.470950 mA below the 10 mA source contract. The all-state RTD short bound removes the healthy 100 Ω load and is 8.448898 mA (MAX BIAS 4.794533 mA), leaving 1.551102 mA. The internal REF2025 VBIAS divider load is 96.242 µA; the separate J2 SHARED_REF_2V5 boundary is limited to 100 µA external load and 10 nF external capacitance, with future OVP/OCP2 consumers required to fit that budget. Its separate case decks produced 100 Ω clear, each FORCE+/SENSE+/SENSE−/FORCE− open fault, and post-ferrite local-off fault. The executable corner generator covers 65536 independent corners per row (including independent diagnostic-pullup mismatch): VBIAS, exact 0.05%/5 ppm/°C RREF, REF2025 initial tolerance, divider TCR/tolerance, 1 MΩ diagnostic tolerance/TCR, MAX ±14 nA input leakage, TLV3201 ±5 nA input bias, combined shared-node bias, board leakage, and ±4 mV comparator offset. At the accepted 1 Ω harness, healthy minimum margins are +186.10 mV LOW and +135.42 mV HIGH at 194.1 Ω; the four open maxima are −166.47 mV (FORCE+ LOW), −1.120 V (SENSE+ HIGH), −643.60 mV (SENSE− LOW), and −1.151 V (FORCE− HIGH). The independent 50 Ω robustness sweep retains the same verdicts, with healthy 194.1 Ω HIGH margin +82.25 mV. The runtime [rtdin_transient_model.py](rtdin_transient_model.py) simulates each open from healthy 100/194.1 Ω and reports FORCE+/FORCE− crossings in 1 µs and worst SENSE+ crossing in 0.329 ms at 20 mV comparator overdrive; the analytic maximum-RC envelope bounds total detector time at 1.323576 ms with Rdiag 1.057 MΩ/Rwindow 102 kΩ, plus sourced 55 ns TLV3201 propagation and conservative 10 ns logic delay. The same model steps healthy 100/194.1 Ω to 10/0 Ω and observes all four short transitions at 0.001065 ms; the passive bound applies to those transitions as well. The allowed passive envelope is −0.2…+2.5 V, ≥1 kΩ source, ≥10 µs edge, ≤1 ms pulse, ≤1 Hz repetition; it fits the TLV3201 minimum supply, so clamp sum is zero. The 4.7385 nJ stored-energy bound is evaluated against a post-ferrite capacitance acceptance minimum of 180 nF (four nominal 100 nF bypasses, each characterized >=45 nF at voltage and temperature), giving <=0.229456 V rail rise. Device-only MAX ±45 V is recorded separately. During local post-ferrite loss, external source drive is forbidden, BIAS collapses to zero, and the rail monitor/HW fault protocol owns shutdown; the powered TLV window is not asserted. The adopted [`fault_nand_upstream_power_and_bypass.patch`](fault_nand_upstream_power_and_bypass.patch) powers the SN74LVC1G38 and its bypass from upstream +3V3 (the equivalent split patches are retained), so the RESET input is evaluated in a valid VCC domain instead of an intermediate local brownout; the SN74LVC1G38 Ioff guarantee is used only for VCC=0 partial power down. The 100 °C accuracy ledger remains 1.46 °C (Class A probe 0.35 + ADC 0.50 + RREF initial 0.18 + RREF drift 0.11 + network 0.22 + self-heating/contact 0.10). The separate [rtdin_spice_receipt.txt](rtdin_spice_receipt.txt) records case outputs.

Physical probe continuity, open-each-conductor injection, oscilloscope timing, low-voltage rail-loss behavior, EMC/noise, and full shutdown-chain captures remain **NOT RUN**.
