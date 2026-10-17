# Standalone current-sense unit contract

This contract describes an independently useful current-sensing and primary
overcurrent unit. It is a source proposal only; it does not modify
`elec/src/modules.ato`, place a PCB, or claim physical qualification.

## Boundary

| Pin/net | Direction at unit | Meaning | Required condition |
|---|---|---|---|
| `PRIMARY_IN` | input | HV/tank current conductor into CT primary P1 | one-turn conductor; source insulation is host-owned |
| `PRIMARY_OUT` | output | same conductor after CT primary P2 | series continuation; no branch or sense return |
| `+3V3` | input | comparator/bias supply | design envelope 3.135–3.465 V; TLV3201 device range 2.7–5.5 V |
| `GND` | return | SELV comparator reference | host return; never connect to either CT primary pin |
| `OCP_FAULT` | output | active-high primary overcurrent result | high for either current polarity; host supplies latch |
| `SENSE_MON` | output | biased analog CT waveform | 0.33–2.97 V nominal for 0–88 A peak into a ≥10 MΩ host monitor (or requalify); not an ADC accuracy claim |

Low-voltage host connector `J2` is the existing JST `B4B-XH-A(LF)(SN)`:
pin 1=`+3V3`, pin 2=`GND`, pin 3=`OCP_FAULT`, pin 4=`SENSE_MON`. It is not
used for the primary conductor. `PRIMARY_IN` and `PRIMARY_OUT` terminate at
a single `J1` / `LitzPad_15A` bare solder-land component in the source graph. The footprint is
a 15 mm OD / 3 mm drill / 25 mm pitch land intended for a wire or busbar;
`NON_PURCHASED_BARE_LAND` is a construction marker, not a purchased
connector or a production ampacity certificate. Root must still qualify the
actual conductor, solder joint, thermal rise, and terminal construction.

`PRIMARY_IN` and `PRIMARY_OUT` are the only high-current connections. This
proposal assigns no trace width, copper weight, connector rating, or current
rating. The coordinator must select a terminal, busbar, or qualified copper
construction before production claims.

The CT secondary is galvanically isolated from the primary. Secondary S2 is
DC-connected to the SELV bias midpoint and AC-bypassed to `GND`; the primary
has no DC path into the comparator circuit.

## Adopted topology

The burden is a floating 1.50 ohm resistor directly across CST3015 S1–S2.
S2 is tied to a 1.65 V midpoint made by independent 1 kΩ/1 kΩ, 0.1% divider parts
and bypassed by 100 nF;
therefore S1 is `VBIAS ± Vburden` without loading the burden with the bias
divider. A 1 kΩ series resistor feeds `SENSE_MON` and two BAT54 clamps bound
input transients. The TLV3201 inputs are high impedance, so the series resistor
does not materially attenuate the operating waveform.

Two TLV3201 comparators cover both primary-current polarities:

* `U_POS`: `IN+ = SENSE_MON`, `IN- = REF_HI` (positive peak).
* `U_NEG`: `IN+ = REF_LO`, `IN- = SENSE_MON` (negative peak).

`REF_HI` is a 3.74 kΩ/10 kΩ divider from `+3V3` to `GND`; `REF_LO` is the
reversed divider. The active `CD74HC4075M96` gate ORs the two push-pull outputs.

## Declared analytical envelope

| Quantity | Envelope or condition | Status |
|---|---|---|
| Primary current | 0–88 A peak, either polarity; OCP threshold target 45–55 A peak | Rust analytical check |
| Source frequency | 20–100 kHz requirements window; source point about 47 kHz | CT data-sheet range contains it |
| SENSE_MON waveform | 0.33–2.97 V at ±88 A peak, nominal 3.3 V rail | Rust analytical check |
| Comparator supply | 3.135–3.465 V host rail; TLV3201 device range 2.7–5.5 V | interface constraint |
| Leakage model | BAT54H total reverse leakage ≤4 µA and TLV3201 input bias ≤5 nA/input at 25 °C | Rust analytical check; 25 °C scope |
| Transient protection | 1 kΩ source resistor plus high/low BAT54H clamps | dynamic pulse qualification pending |

The 88 A value is the Coilcraft 40 °C-rise reference, not a continuous
unconditional conductor rating. Currents, temperature, clamp pulses, startup
and board parasitics outside this table require separate qualification.

## Nominal model

At nominal 3.3 V:

```
VBIAS = 3.3 * 1k/(1k+1k) = 1.650 V
VHI  = 3.3 * 10k/(3.74k+10k) = 2.40203 V
VLO  = 3.3 * 3.74k/(10k+3.74k) = 0.89797 V
delta = VHI - VBIAS = VBIAS - VLO = 0.75203 V
Vburden_peak = Iprimary * 1.50/100
Itrip = delta * 100/1.50 = 50.14 A
```

The Rust model's resulting conditional bounded DC trip band is 46.175–54.157 A
across enumerated corners. It sweeps independent 0.1% threshold and bias-divider corners, a
1% burden corner, a ±5% rail, TLV3201 input-bias loading, a ≥10 MΩ host
monitor load, the BAT54H reverse-leakage bound, TLV3201 VOS up to 4 mV, and a
conservative CMRR error derived from 56 dB. The rail largely cancels because
all three dividers use the same supply, but it remains in the model. The
leakage bound is the Nexperia 25 °C data-sheet condition; the analytical claim
is therefore limited to 25 °C until a hot leakage value is qualified. VOS is
specified at VCM=VCC/2 and CMRR is a minimum at 2.7 V; their use at 3.3 V and
the non-midpoint waveform is conditional. The model does not claim CT
saturation, winding parasitics, clamp dynamic behavior, comparator recovery,
or timing through the host latch. This bounded calculation does not establish
the overall 45–55 A requirement: CT ratio/magnetizing-current/frequency
behavior, hysteresis, and unspecified component tolerances remain outside it.

## Limits and gates

* Source requirement: primary OCP is 45–55 A peak and the complete cooker
  chain allocates `<1 us` from current stimulus to latched shutdown. TI's
  TLV3201 datasheet gives 55 ns maximum propagation at its stated test
  condition over temperature. The selected active `CD74HC4075M96` is
  specified as a 2–6 V, 14-pin SOIC triple 3-input OR, but its published
  propagation figures are characterized at 2/4.5/6 V (not this 3.3 V rail)
  and 50 pF. This unit claims no end-to-end timing PASS; root must measure the
  comparator-to-OR-to-latch path at the actual rail and load.
* Source operating point is approximately 28.76 A peak at about 47 kHz. The
  inherited analytical frequency window is 20–100 kHz. CST3015 is specified
  0.78 kHz to above 1 MHz and 88 A sensed current at its 40 °C rise reference.
* At 28.76 A peak sinusoidal primary current, the 1.50 Ω burden dissipates
  about 0.062 W (`(28.76/100/√2)^2*1.50`). At 25 A RMS it dissipates 0.094 W.
  Its exact part and thermal derating remain an ordering and physical-
  qualification item.
* The 100 nF bias bypass with the 1 kΩ/1 kΩ divider has a nominal 50 µs
  Thevenin startup time constant. The host must allow at least 5 ms after
  `+3V3` becomes valid before treating `OCP_FAULT` or `SENSE_MON` as settled;
  startup sequencing and fault masking are host-owned.
* CST3015 is 5000 Vrms winding-to-winding and at least 8 mm creepage/clearance
  per Coilcraft. The source selects the corrected local
  `temper:CST3015_Datasheet2025` footprint. Native readback records primary
  pads at x=±5.58 mm, y=-11.55 mm (4.8 x 9.0 mm) and secondary pads at
  x=±6.88 mm, y=13.75 mm (3.0 x 4.6 mm), giving 18.5 mm copper edge gap
  between the two rows. This is evidence that the footprint matches the
  reviewed drawing; it is not a routed-board PD3 proof. The 12.6 mm PD3
  barrier remains **INDETERMINATE** until root measures the completed board,
  including any slot, solder mask exclusion, wire lands, and enclosure.
* Physical tests, rail transient tests, current-ramp timing, thermal rise,
  and primary copper/terminal qualification are **NOT RUN**.

## Exact instances and pins

| Ref | Existing component/MPN | Pins used | Role |
|---|---|---|---|
| `T1` | `CST3015_100E` / `CST3015-100ED`, `temper:CST3015_Datasheet2025` | P1=1, P2=2, S1=3, S2=4 | 1:100 current transformer; corrected official land pattern |
| `J1` | `NON_PURCHASED_BARE_LANDS`, `lib:LitzPad_15A` | p1=1, p2=2 | single two-pad primary wire/busbar solder interface; no ampacity claim |
| `R1` | `RC1206FR-071R5L` | p1/p2 | 1.50 Ω burden; 0.25 W 1206, thermal review required |
| `C1` | `GRM31C5C1H104JA01L` | p1/p2 | burden HF filter; 1206, 50 V, C0G |
| `C2` | `GRM31C5C1H104JA01L` | p1/p2 | bias midpoint bypass; 1206, 50 V, C0G |
| `R2` | `ERA3AEB102V` | p1/p2 | bias-divider top; 1 kΩ, 0.1%, 0603 |
| `R3` | `ERA3AEB102V` | p1/p2 | bias-divider bottom; 1 kΩ, 0.1%, 0603 |
| `R4` | `RC1206FR-071KL` | p1/p2 | comparator input protection resistor; 1 kΩ, 1%, 1206 |
| `R5,R6` | `ERA3AEB3741V` / `ERA3AEB103V` | p1/p2 | high threshold, independent 0.1% divider parts |
| `R7,R8` | `ERA3AEB103V` / `ERA3AEB3741V` | p1/p2 | low threshold, independent 0.1% divider parts |
| `D1,D2` | `BAT54H,115` | A/K | SOD-123F 30 V/200 mA SENSE_MON clamps; 25 °C leakage bound only |
| `U1,U2` | `TLV3201AIDBVR` | 1 OUT, 2 GND, 3 IN+, 4 IN−, 5 VCC | polarity comparators |
| `U3` | `CD74HC4075M96` (active TI 14-pin SOIC) | Y1=9, A1=1, B1=2, C1=8, VCC=14, GND=7 | output OR; unused gates tied low; drop-in pin map |
| `C3,C4,C5` | `C0603C104K5RACTU` | p1/p2 | local 100 nF X7R supply bypass, one per IC |
| `J2` | `B4B-XH-A(LF)(SN)` | 1..4 | low-voltage host boundary |

Rows marked candidate are source proposals, not procurement approval. The
coordinator must verify each exact orderable, footprint, power rating, and
surge condition before BOM release.
