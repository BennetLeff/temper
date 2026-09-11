# Standalone current-sense unit contract

This contract describes an independently useful current-sensing and primary
overcurrent unit. It is a source proposal only; it does not modify
`elec/src/modules.ato`, place a PCB, or claim physical qualification.

## Boundary

| Pin/net | Direction at unit | Meaning | Required condition |
|---|---|---|---|
| `PRIMARY_IN` | input | HV/tank current conductor into CT primary P1 | one-turn conductor, source impedance and insulation owned by host |
| `PRIMARY_OUT` | output | same conductor after CT primary P2 | series continuation; no branch or sense return is allowed |
| `+3V3` | input | comparator/bias supply | 3.135–3.465 V design envelope; 2.7–5.5 V is TLV3201 device range |
| `GND` | return | SELV reference for comparator/OR | host return; do not connect to either CT primary pin |
| `OCP_FAULT` | output | active-high primary overcurrent result | high when either polarity comparator exceeds its threshold; host latches it |
| `SENSE_MON` | output | biased, attenuated analog sense node | 0–3.3 V nominally within the declared 0–88 A envelope; not an ADC accuracy claim |

`PRIMARY_IN` and `PRIMARY_OUT` are the only high-current connections. The
standalone proposal does not assign a trace width, copper weight, connector
rating, or continuous current rating. Those are placement/routing and
mechanical-interface decisions for the coordinator. A terminal, busbar, or
qualified copper construction must be selected before a production claim.

The CT secondary is galvanically isolated from the primary. Its secondary
return is AC-referenced to `GND` through `C_CT_RETURN`; there is no DC path
from either primary terminal to the SELV circuit.

## Adopted topology

The burden is a floating 4.99 ohm resistor directly across CST3015 S1–S2.
`S2` receives a 100 nF AC return capacitor to `GND`; `S1` is AC-coupled by
1 uF, then reduced by a 36.5 kΩ/10 kΩ network into `SENSE_MON`. The 10 kΩ
leg returns through the 47 kΩ/47 kΩ bias divider's 23.5 kΩ Thevenin source
impedance. This makes the burden a real AC termination while keeping its DC
node separate from the bias node.

Two TLV3201 comparators cover both primary-current polarities:

* `U_POS`: `IN+ = SENSE_MON`, `IN- = OCP_REF_HI` (positive peak).
* `U_NEG`: `IN+ = OCP_REF_LO`, `IN- = SENSE_MON` (negative peak).

`OCP_REF_HI` is the 3.24 kΩ/10 kΩ divider from `+3V3` to `GND`; `OCP_REF_LO`
is the reversed 10 kΩ/3.24 kΩ divider. An SN74HC4075 gate ORs the two
push-pull comparator outputs. BAT54 rail clamps at `SENSE_MON` and the
13.3 kΩ source resistor bound input transients; their leakage, dynamic
clamping, and off-board surge behavior remain to be verified.

## Nominal model

At nominal 3.3 V:

```
VBIAS = 3.3 * 47k/(47k+47k) = 1.650 V
VHI  = 3.3 * 10k/(3.24k+10k) = 2.49245 V
VLO  = 3.3 * 3.24k/(10k+3.24k) = 0.80755 V
RBIAS_TH = 47k || 47k = 23.5k
RPATH_TO_BIAS = 10k + RBIAS_TH = 33.5k
attenuation = RBIAS_TH/(36.5k + RPATH_TO_BIAS) = 0.33571
Vburden_peak = Iprimary * 4.99/100
Vmon_peak = Vburden_peak * attenuation
Itrip = (VHI - VBIAS) * 100/(4.99 * attenuation) = 50.2 A
```

The same equation applies to the negative branch because `VBIAS - VLO` is
equal to `VHI - VBIAS` at nominal values. The Rust model sweeps independent
1% resistor corners and a ±5% rail as a bounded analytical result. It does
not model hysteresis, CT saturation, winding parasitics, clamp capacitance,
PCB coupling, or comparator recovery.

## Limits and gates

* Declared source requirement: primary OCP is 45–55 A peak and the full
  cooker chain allocates `<1 us` from current stimulus to latched shutdown.
  This unit has two 55 ns maximum comparator propagation figures at the TI
  datasheet test condition, but no standalone end-to-end timing PASS is
  claimed. The OR gate, host latch, overdrive, load, and wiring are outside
  this unit's proof.
* Declared current-sense source range: the repository's current operating
  point is approximately 28.76 A peak at about 47 kHz; the inherited
  analytical design window is 20–100 kHz. CST3015 is specified 0.78 kHz to
  above 1 MHz and 88 A sensed-current at its 40 °C rise reference condition.
* At 28.76 A peak sinusoidal current, the 4.99 Ω burden dissipates about
  0.206 W. The existing 0.25 W 1206 MPN is below that nameplate value but
  has little thermal margin; no derating or continuous thermal qualification
  is claimed.
* CST3015 is 5000 Vrms winding-to-winding and at least 8 mm creepage/clearance
  per Coilcraft. The whole-cooker PD3 reinforced 12.6 mm barrier is not
  satisfied by the intrinsic CT pad corridor (about 9.1 mm); this standalone
  unit therefore carries an explicit **INDETERMINATE** physical-isolation
  gate. A host-qualified slot, barrier construction, or alternate sensor is
  required before any PD3 claim.
* Physical tests, rail transient tests, current-ramp timing, thermal rise,
  and primary copper/terminal qualification are **NOT RUN**.

## Exact instances and pins

| Ref | Existing component/MPN | Pins used | Role |
|---|---|---|---|
| `T1` | `CST3015_100E` / `CST3015-100ED` | P1=1, P2=2, S1=3, S2=4 | 1:100 current transformer |
| `R1` | `RC1206FR-074R99L` | p1/p2 | 4.99 Ω burden |
| `C1` | `GRM1885C1H104JA01D` | p1/p2 | burden HF filter |
| `C2` | `GRM1885C1H104JA01D` | p1/p2 | secondary AC return to GND |
| `C3` | `GRM188R71C105KA12D` | p1/p2 | AC coupling; existing exact 1 µF X7R donor |
| `R2` | `RC0603FR-0736K5L` | p1/p2 | source attenuation resistor; exact MPN review required |
| `R3` | `RC0603FR-0710KL` | p1/p2 | sense-to-bias resistor |
| `R4,R5` | `RC0603FR-0747KL` | p1/p2 | 1.65 V bias divider; exact MPN review required |
| `R6` | `RC0603FR-073K24L` | p1/p2 | high threshold top |
| `R7` | `RC0603FR-0710KL` | p1/p2 | high threshold bottom |
| `R8` | `RC0603FR-0710KL` | p1/p2 | low threshold top |
| `R9` | `RC0603FR-073K24L` | p1/p2 | low threshold bottom |
| `D1,D2` | `BAT54` | A/K | SENSE_MON high/low rail clamps; exact suffix review required |
| `U1,U2` | `TLV3201AIDBVR` | 1 OUT, 2 GND, 3 IN+, 4 IN−, 5 VCC | polarity comparators |
| `U3` | `SN74HC4075DR` | Y1=9, A1=1, B1=2, C1=8, VCC=14, GND=7 | output OR; unused inputs tied low |

The capacitor/resistor/diode rows marked “exact MPN review required” are
proposal candidates because the legacy component library only declares generic
passives. They must be distributor and datasheet-checked before ordering.
