# Native-21 F6 source and mains zero-cross ECO

This is the circuit-source handoff for owner layout, based on build commit
`fada4c13c`. There is no native-21 board or routing in this change. The
[qualification report](../validation-results/01-switching-parasitics/round17/delegation/out-D33/README.md)
separates simulation evidence from the physical acceptance checks below.

[PART-CHANGES.md](PART-CHANGES.md) lists every added, removed and replaced
component, reference, exact part, value and footprint. [change-inventory.json](change-inventory.json)
also enumerates every added/deleted net and every changed endpoint on an
existing net. These compare compiler exports against native-20. There are
331 components, versus 142; 195 additions, six bootstrap removals, two part
replacements. Existing references remain fixed, including the removed gaps.

## Supply and gate circuit

PS2 becomes **IRM-20-24**, still fed exclusively from **TCO_L/N_FILT**.
Its negative terminal is **N_LS**, approximately −2 V relative to **LEG_RET**;
its positive terminal is **V24_RAW**, 24 V above N_LS. Do not short N_LS to
LEG_RET: the TLVH431 shunt establishes that midpoint. PS1 remains the SELV
supply and does not supply the bias transformers, gate-output power or HOT5.
SELV still powers the existing driver input side and the isolated monitor
receivers/disable logic.

A TPS7A4700 produces a nominal 17 V span above N_LS; its midpoint is fixed by
TLVH431BQDBZR with 6.12 kΩ / 10 kΩ feedback. This gives approximately +15/−2 V
relative to the low-side source. One SN6507DGQR on V24_RAW/N_LS drives two
750320775 transformers. Each high side has two PMEG10030ELPX **100 V**
rectifiers, a 100 µH 74404064101 filter, the same span regulator and shunt,
and its own SW_A or SW_B midpoint. The high-side transformers are HOT↔HOT
functional barriers; they introduce no new transformer path to PS1/PE.
Their stated 3 pF interwinding capacitance is **typical**, not a maximum.

SN6507: 18.2 kΩ CLK (about 600 kHz from the manufacturer curve), 30.1 kΩ
current-limit resistor, 4.7 µF SS, 4.99 kΩ SR, DC left open. The clock must
measure **500–700 kHz** over operating conditions. Each drain has a
680 Ω / 100 pF series snubber to V24_RAW. The transformer model uses minimum
primary inductance, winding resistance increased 40% over its 25°C maximum,
minimum 80 µH filter inductance, 1 Ω filter resistance and 1 Ω switch RON.
It is a linear engineering model: startup flux, core loss, worst-case leakage,
clock tolerance and actual snubber stress remain physical checks.

At each of the four driver VSS locations, fit:

- 2 × 10 µF, 50 V, 1210; **≥10 µF effective combined**;
- 2 × 1 µF, 25 V, 0603; **≥1 µF effective combined**;
- 4 × 100 nF, 25 V, 0402; **≥320 nF effective combined**;
- 220 µF / 6.3 V 6SVPC220M polymer through **0.68 Ω** series damping;
- 4.99 kΩ bleed from the positive rail to the MOSFET-source midpoint.

These effective minima include tolerance, DC bias and temperature; they are
**acceptance conditions**, not a claim that nominal capacitance or a typical
vendor curve guarantees them. Obtain the selected MLCC curves and verify the
assembled bank over its declared temperature range before release. The rail
model includes a 140.8–316.8 µF polymer sensitivity range, leakage and ESR.
The bulk cap's positive terminal goes through the damping resistor to source;
its negative terminal goes to VSS. Do not remove the damping resistor.

Retain the 3.9 Ω turn-on gate resistors and 10 kΩ gate-source hold-offs.
Add 1 nF C0G gate-to-source and the **1 Ω + PMEG6030EP** turn-off branch at
each gate. PMEG6030EP anode faces the gate; cathode faces the 1 Ω resistor
and driver output. These 60 V gate diodes are different from the 100 V
transformer rectifiers. Delete D1/D2, C10/C11/C17/C18; no bootstrap remains.

HOT5 uses TPS70950DBVR. IN and EN use V15_LS; GND goes to **R5.2
(OCP_KELVIN_P)**. TPS3700 remains powered by V15_LS, independently of HOT5.
Do not return any bias recharge or shunt current through the Kelvin island.

## Mandatory rail monitor

Three HOT-powered monitor circuits cover LS, HS-A and HS-B. Each uses an
LM339B, TL431 reference, and VO617A isolated healthy indication. The negative
window is nominally **−2.198 to −1.799 V**; the total-span window is nominally
**16.218 to 17.839 V**. The combination supervises the positive rail too
(approximately +14.02 to +16.04 V at nominal thresholds). It does not claim a
precise +15 V window independent of negative-rail voltage. Divider/reference
and comparator errors must be included when measuring enable thresholds.

The four open-collector comparator outputs wire together as healthy-AND.
A silicon diode plus NPN prevents the comparator's low output from keeping
the optocoupler LED on. LED off, monitor unpowered or an open isolated
connection gives BAD through a 10 kΩ SELV pullup. All three BADs OR together;
a local two-input OR combines BAD with each existing PERMIT-derived DIS.
Each final DIS has a 10 kΩ pullup. A monitor cannot override an asserted DIS.
The 1 nF input filters reject switching-edge excursions; they are not a
substitute for reservoir qualification or a safety latch.

Startup, TCO removal, each missing rail, brownout, optocoupler open, and rail
recovery must be captured with both DIS and driver outputs. There is no
hardware latch in this new monitor: the controller's existing fault/reset
policy still owns deliberate restart. Establish the allowed startup wait
from measured settling (the negative bulk reservoir may take hundreds of
milliseconds). Added DIS OR propagation also requires the native-21 B4 check:
**comparator → driver output** is the timing endpoint; report gate discharge
separately. Do not silently reuse a native-20 timing certificate.

## Isolated line zero crossing and J4 returns

VOL628A-3X001T is the AC-input optocoupler, with the VDE option and an LSOP4
package specified for ≥8 mm clearance/creepage. Two 16.5 kΩ 1206 resistors
on each LED side give 66 kΩ between L_FILT and N_FILT. Its SELV collector
has a 33 kΩ pullup and SN74LVC1G17 Schmitt buffer. **J4.16 = LINE_ZC**,
high near zero or when the line/detector is absent; the other header signals
are unchanged. Do not connect J4.16 to an old harness ground contact.

At 140 V RMS the resistor string dissipates approximately 0.297 W total,
0.074 W per resistor, with a conservative peak LED current of 3.00 mA.
The source therefore covers 120 V +10% and the campaign's 140 V condition.
The optocoupler CTR bin is specified at 1 mA; extrapolated sub-mA CTR is not
a timing guarantee. Raw transitions can be about a millisecond from the
actual voltage zero. Firmware must use a continuously observed line phase,
qualify both pulse edges/period and timeout, and calibrate the inferred zero.
**Bursts stay disabled until firmware uses LINE_ZC and the bench demonstrates
±250 µs timing.** A single raw transition is not a proven crossing.

D-20 R20/O04 did not close the original four-contact return allocation.
The proposed three-return assignment is J4.2 for the 15 V power return,
J4.4 for 3.3 V/PWM return, J4.15 for analog/LINE_ZC reference next to pin16.
All are the same SELV_GND electrical net; this is a harness allocation, not
three isolated grounds. The added receiver/pullup DC allocation is 2 mA
above native-20's 41.657 mA power-board 3.3 V subtotal. No bias conversion
load is charged to PS1.

The source connectivity check passes with three returns, but current sharing,
contact resistance, missing-contact operation, allowable ground offset and
PE/USB/instrument bonds remain **D-20 harness gates**. There is no evidence
here to declare three contacts physically sufficient, or to force an
18-position connector. Grow to 18 if that measured allocation fails; update
both ends together. Do not interpret this source export as harness approval.

## Layout acceptance and L1–L7

| Rule | Source status and owner-layout obligation |
|---|---|
| L1 | All F6 parts and mandatory DIS monitoring are present. Place each reservoir directly at its VSS/source loop; do not share a narrow neck between banks. Rail model maximum additional local branch ESL is 0.5 nH (10 µF and 1 µF branches), and **0.1 nH aggregate** for the parallel 0402 bank; ESR maxima are 40/100/50 mΩ respectively. Extract/measure these conditions; they are not measurements of the new layout. Keep transformer capacitance/dv/dt and monitor barriers out of sensitive Kelvin routes. |
| L2 | R34 = RT0603BRD0710K6L / 10.6 kΩ; R8/R16 = 330 Ω retained by reference and identity tests. |
| L3 | R9/R17 = 49.9 kΩ ±0.1% retained. |
| L3a | Reinforced VOL628A detector reaches J4.16; resistor chain stays HOT. Check D5 clearance around the whole barrier and qualify D-20 returns as above. |
| L4 | TPS709 GND and HOT protection returns remain on R5.2; bias currents return through LEG_RET/N_LS. Re-extract Kelvin resistance, aim ≤50 mΩ or separate stars, and require the revised OCP minimum ≥44 A. |
| L5 | Preserve or improve native-19 gate/power loop geometry; the 0.1 nH reservoir requirement is additional to the existing FEM board matrix. Keep each diode/1 Ω branch inside the gate loop. Re-extract changed legs and rerun switching grids. |
| L6 | C38–C41 and their bus-pad connections retained. |
| L7 | No stackup, MOSFET footprint or board file changed here. Recheck geometry if the layout changes them. |

Three new land patterns are explicitly **ReviewOnly**: WE750320775 EP7HV,
WE74404064101 6×6 mm inductor, and VOL628A LSOP4. They name the selected
manufacturer package; they are not fabrication-approved footprints. Build
and review them against the linked package drawings before placing/routing.
All other footprints are in the exact component inventory. The TPS7A4700 EP
needs its specified copper/thermal vias; its approximately 1.36 W LS heat
allocation cannot be evaluated from θJA alone. Keep the polymer caps below
their 105°C rating and the selected TL431AI reference below its 85°C rated
ambient; validate all part temperatures in the enclosure.

## Manufacturer pin/ratings sources

- [TI TLVH431, SLVS555N, June 2024](https://www.ti.com/lit/ds/symlink/tlvh431.pdf): DBZ REF1/K2/A3, BQ temperature limits, recommended 70 mA sink maximum.
- [TI TPS7A47, SBVS204G, May 2026](https://www.ti.com/lit/ds/symlink/tps7a47.pdf): pin table pp3–4, accuracy/dropout p6, ANY-OUT and startup pp12–16. **±1% is 25°C nominal; overall accuracy is ±2.5% at its specified headroom/load**, not ±1% over temperature. Datasheet §7.2.2.2 permits dropout scaling with current; transformer headroom still needs physical validation.
- [TI SN6507, SLLSFM0A](https://www.ti.com/lit/ds/symlink/sn6507.pdf): DGQ pins, 0.5 A recommended switch current, clock/current-limit/SS curves and limits. OCP is disabled during soft start: measure startup, do not rely on the current-limit resistor alone.
- [WE750320775, rev001.002](https://www.we-online.com/components/products/datasheet/750320775.pdf): winding schematic, 1.2:1 ratio, 300 µH minimum, 60 Vµs half-primary, 3 pF typical, working-voltage/frequency rating and EP7HV drawing.
- [WE74404064101, rev002.003](https://www.we-online.com/components/products/datasheet/74404064101.pdf): 100 µH ±20%, DCR/current ratings and land pattern.
- [Mean Well IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF): IRM-20-24 output/ripple/derating and **ACL1, ACN2, VN3, VP4**. These AC pins differ from the removed IRM-05.
- [Panasonic 6SVPC220M](https://industrial.panasonic.com/ww/products/pt/os-con/models/6SVPC220M): 220 µF, 6.3 V, 27 mΩ ESR, 300 µA leakage, 105°C.
- [TI LM339B](https://www.ti.com/lit/ds/symlink/lm339b.pdf), [TL431 SLVS543S](https://www.ti.com/lit/ds/symlink/tl431.pdf): comparator pin table and TL431 DBZ **K1/REF2/A3**, which differs from TLVH431.
- [TI TPS709](https://www.ti.com/lit/ds/symlink/tps709.pdf): DBV IN1/GND2/EN3/NC4/OUT5, voltage and quiescent current.
- [TI SN74LVC1G32](https://www.ti.com/lit/ds/symlink/sn74lvc1g32.pdf), [SN74LVC1G332](https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf), [SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf): exact DBV pin tables and supply requirements.
- [Vishay VOL628A, rev1.9](https://www.vishay.com/docs/82401/vol628a.pdf): AC input1/2, emitter3/collector4, CTR bin/option1 certification and LSOP4 isolation dimensions. [VO617A](https://www.vishay.com/docs/83430/vo617a.pdf): A1/K2/E3/C4 and selected isolation option.
- [Nexperia PMEG6030EP](https://assets.nexperia.com/documents/data-sheet/PMEG6030EP.pdf) and [PMEG10030ELP](https://assets.nexperia.com/documents/data-sheet/PMEG10030ELP.pdf): SOD128 K1/A2 and voltage/current ratings.
