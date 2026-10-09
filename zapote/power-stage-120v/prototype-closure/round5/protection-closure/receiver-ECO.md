# Five-channel mirror receiver ECO

**Candidate circuit for K1, K2, KB, KPA and KPB. No powered release.** Preserve existing logical names and high = closed NC/released main contactor. The present 3.3 V excitation and 10 kΩ load do not meet the exact LC1D18BD minimum switching conditions, 17 V and 5 mA. Its NC mirror relationship supports proving the main NO contacts open; an open NC does not prove the power contact closed.

Use **five TI ISO1211DR** receivers and **one TI TPL7407LDR** excitation sink array. This avoids LED/CTR degradation assumptions. Do not implement the earlier explored TLP2361 or RSENSE=200Ω alternative. The following values deliberately match the ISO1211's explicitly bounded 562 Ω table.

## Exact connections

For each contactor Kx:

| Endpoint | Connection |
|---|---|
| External Kx.21 | Fused, qualified AUX_24V (20.4–26.4 V at this connector is a design allocation) |
| External Kx.22 | `Kx_MIRROR_24V`; ISO1211 pin8 SENSE |
| ISO1211 pin7 IN | 562 Ω ±1% from pin8; RTHR=0Ω |
| ISO1211 pin6 FGND | `Kx_FB_SINK`, separate corresponding TPL7407L output |
| Across ISO1211 pin8 to pin6 | 4.7 kΩ ±1%, at least0.5W resistor, and1nF capacitor rated50V or higher |
| ISO1211 pin5 SUB | Floating2×2mm thermal copper island only; do not tie to FGND/GND/another plane |
| ISO1211 pin1 VCC1, pin2 EN | POD_3V3 |
| ISO1211 pin4 GND1 | AUX_0V |
| ISO1211 pin3 OUT | `Kx_MIRROR`, existing MCU input;100kΩ pulldown to AUX_0V |
| ISO1211 bypass | 100nF pin1–pin4, local |
| TPL7407L pin9 COM | AUX_24V with local100nF bypass to AUX_0V; COM powers its gate drive, not an optional unused flyback pin |
| TPL7407L pin8 GND | AUX_0V |
| TPL pins1/2/3/4/5 IN1…IN5 | Existing K1/K2/KB and new KPA/KPB `*_FB_EXC` GPIOs; each100kΩ pulldown |
| TPL pins16/15/14/13/12 OUT1…OUT5 | Corresponding five `*_FB_SINK` nets |
| TPL pins6/7 IN6/IN7 | AUX_0V; outputs11/10 left NC |

GPIO high sinks field current and interrogates that contact. GPIO low releases the sink; the 4.7k resistor collapses the field-side voltage difference and the receiver reports low. The field-side pair floats near AUX24 during an inactive interrogation; **FGND is not a direct ground connection**. Do not short it to a plane or to another channel. No inverter is required. The existing auxiliary domain is already common with the excitation driver; do not claim this assembly adds a new system isolation barrier. An ISO1211 internal substrate pad is not a shield or protective-earth point.

## Bounded selection and explicit allocations

[TI ISO1211 RevG](https://www.ti.com/lit/ds/symlink/iso1211.pdf), pp3,10–11,21–23: with RTHR=0 and RSENSE=562Ω±1%, input current is2.05–2.75mA for VIL<VSENSE<30V. Positive threshold≤8.55V; negative threshold≥6.5V. Recommended VCC1 is2.25–5.5V; at the stated test loads output high≥VCC1−0.4V and output low≤0.4V. At3.3V keep load≤3mA; this input plus100k pulldown is far below that. Table propagation maxima140ns rising/15ns falling apply to10ns stimulus edges, **not** the installed RC waveform.

[TI TPL7407L RevD](https://www.ti.com/lit/ds/symlink/tpl7407l.pdf), pp3–5: COM8.5–40V, output≤40V; input high≥1.5V, low≤0.9V. Its0.32V maximum output low is specified at100mA across−40…125°C; conservatively use that larger-load drop for this<9mA resistive load. Published switching350ns is typical only. Its500nA maximum off leakage is tested at24V, not26.4V. Neither is silently promoted to a complete chain guarantee.

Worst static healthy-contact current using the above drop and1% resistors:

- Minimum:2.05mA+(20.4−0.32)V/4.747kΩ = **6.280mA**, above5mA.
- Maximum:2.75mA+26.4V/4.653kΩ = **8.424mA**.
- Burden dissipation≤26.4²/4653 = **0.150W**. Select the0.5W part with its actual installed-temperature derating still above this figure; do not substitute an ordinary0.1W0603. RSENSE dissipation≤2.75mA²×567.62Ω = **4.30mW**.
- Field voltage≥20.08V while active, over twice the8.55V receiver threshold. Open-contact available voltage remains≥20.4V, above17V. The calculated1.28mA wetting margin does not justify operation outside the allocated rail range.
- At the24V leakage test condition, inactive field voltage≤500nA×4.747kΩ = **2.374mV**. The shunt gives a conservative minimum low-state leakage rejection threshold6.5V/4.747kΩ = **1.369mA**. Verify actual26.4V/hot board leakage below this threshold with margin; do not cite the24V table as a26.4V guarantee.
- With a1nF±10% field capacitor alone, passive open-wire fall26.4V→6.5V takes≤**7.32µs**. Board/harness capacitance is additional. Allocate≤5nF total differential capacitance, yielding≤33.27µs with4.747kΩ. Budget **100µs from commanded excitation edge to sampled validity**, including a50µs driver/receiver allowance; these are requirements for verification, not supplier timing guarantees. No blanket80ns optocoupler or350ns driver claim is used.

The receiver adds no LED aging/CTR failure mechanism. Semiconductor failure, resistor drift, solder faults, receiver supply supervision and wetting-contact durability remain relevant. Duty-cycled diagnostics do not prove end-of-life contact resistance. The source datasheet calls for thermal analysis at elevated ambient;26.4V×2.75mA is a conservative73mW field-power estimate before subtraction of external sense-resistor loss, not an installed junction-temperature measurement.

## Interrogation and static operating mode

The product uses **no FPGA**. During source-isolated diagnostics obtain a complete six-slot scan: all excitation off, then one of five channels on per slot. Allocate100µs settling before acquisition and150µs per slot; check every inactive channel low. Only publish a completed valid five-bit mask. Perform individual contactor mechanical challenges while the source is verified open.

Before START or any mechanical selftest, change to **all five excitation outputs continuously high** and confirm a settled raw snapshot. `feedback_static` must become true before the isolation core accepts START. Maintain this mode throughout all mechanical selftests, CONNECT, PRECHARGE, BYPASS, ISOLATE, REARM, REPROVE, READY and RUN. Do not perform intentional excitation-low diagnostics during a source-present interval. Firmware still timestamps valid static samples with≤2ms age; it does not synthesize a high or hold the last healthy reading after invalidity.

The independent hardware RUN path directly ANDs existing hard permission, raw KPA mirror, raw KPB mirror, KPA excitation, KPB excitation, NOT CMD_KPA, NOT CMD_KPB and receiver supply-good. Loss of either static mirror or its excitation immediately removes the combinational permission, subject to real receiver/gate propagation; there is no FPGA, scanner-state latch or software echo. Native gate part selection and actual command-to-inhibit bounds belong to the board integration receipt. A low mirror during commanded precharge is expected; this gate inhibits RUN, not the separately bounded precharge authorization.

Source-isolated diagnostic coverage:

- Static-high receiver, stuck-on sink, cross-connected outputs or return-to-ground shunt: invalid inactive slot when contact is closed; latch inhibit. If contact is presently open the fault may remain latent, so perform mechanical release/energization checks before source admission.
- Open cable/LED-equivalent input failure, stuck-low receiver or lost24V: low when a released contact should read high; inhibit.
- Short across NC contact: electrical excitation still toggles normally, so detect during the source-isolated mechanical self-test when that contactor is energized and its mirror must go low. Dynamic excitation alone cannot detect this fault.
- False feedback plus a welded associated power contact is two faults; the other independently open series contact still interrupts the precharge route. Shared shorts bridging both contacts, common-cause excitation/logic failures, flashover or two welds are not claimed covered.
- Dropped3.3V, either static RUN mirror, either excitation or watchdog failure must inhibit through the independent static hardware permission path. Firmware also rejects stale samples. This document defines that gate but does not implement its native board circuitry or qualify its latency.

The150µs slots are electrical test excitation; contactors are not mechanically cycled at this rate. On source-isolated START, separately energize/release KPA then KPB with100ms pickup/40ms release deadlines, requiring10ms stable mirror states. Preserve the existing cold POST and fault-reset requirements. Native board and target owners must implement this exact polarity/scan convention before treating the candidate as integrated.

Source-isolated close challenges and final CONNECT require at least73ms energized dwell, independently of the mirror transition. The executable core now requires a fresh loaded bypass proof after both isolation contacts release. A second proof pulse requires verified one-shot rearm and two-pulse resistor qualification; command-low alone does not reset an LTC6993-1.

During static operating mode an output stuck-high or cross-short that arises after the selftest may remain latent. A subsequent associated welded power contact is an additional failure; two independent open power contacts reduce that route, but a common short bridging both contacts or shared logic/receiver failure is not covered by a single-fault claim. Excitation activity is never used as a substitute for actual NC level in the hardware RUN gate.

## Isolation coil authorization before the main attempt

The isolation contactors must move during source-isolated selftest, before the main ATTEMPT timer starts. Their actual drivers therefore cannot be gated by ATTEMPT alone. Each driver uses requested command AND PG3 AND PG5 AND STOP_OK AND LATCH_OK AND (`SOURCE_OFF_PHYSICAL` OR (`ATTEMPT` AND `TOTAL_WINDOW` AND NOT `RUN_PERMIT`)). The source-off term consists of raw K1/K2/KB NC mirrors, their continuously high excitations, all three actual source/bypass driver commands low, and the existing physical bus/catch-discharge comparators. Bind real comparator nets in the native board; a firmware CAPS_SAFE or PRESTART echo is insufficient.

Complete the dynamic electrical challenge first, then hold all five excitations high and settle before any mechanical selftest. Assert the independent ATTEMPT/TOTAL_WINDOW authorization before raising main-source commands so coil permission has no transition gap. The actual KPA/PB commands, not just requested MCU bits, also inhibit the hardware RUN gate. Supply/STOP/latch loss defeats both authorization terms. The complete existing source/coil driver implementation must confirm polarity, hardware latch behavior and command-to-extinction limits.
