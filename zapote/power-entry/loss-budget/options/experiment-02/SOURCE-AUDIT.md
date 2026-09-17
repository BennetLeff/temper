# C7 / UCC27624 12 V drive-contract source audit

Scope: read-only audit of the retained primary PDFs at commit `c27abe974`.
No CAD, code, builds, or procurement changes were made.

## Source identity

| Source | SHA-256 | Relevant printed pages |
|---|---|---|
| TI UCC27624, SLUSE44E, Rev E, revised March 2026 | `b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51` | 4–7, 16–17, 20–25 |
| TI UCC28180, SLUSBQ5D, Rev D, revised July 2016 | `e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be` | 4–7, 17, 36 |
| Infineon IPW65R045C7, Rev 2.1, 2013-04-30 | `7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a` | 3–6, 9–11 |

## What a 12 V ±5% UCC27624-port contract can mean

A regulated **UCC27624 VDD pin** contract of 11.4–12.6 V is a useful
hypothetical test condition for the C7 experiment. It is inside the driver's
recommended 4.5–26 V VDD range (UCC27624 p. 5), well above its UVLO rising
threshold (3.8 V minimum, 4.1 V typical, 4.4 V maximum) and below the 26 V
recommended ceiling / 30 V absolute maximum. The contract must be measured at
the driver pins, with the requested 0.2 V load-droop allowance allocated within
that 11.4–12.6 V pin-voltage band (plus separately recorded ripple/transient
behavior). This is an experiment contract, not a datasheet guarantee.

This does **not** define the UCC28180 controller's supply or GATE waveform.
If the same 12 V ±5% source is used for UCC28180 VCC, startup is not
guaranteed: UCC28180 VCC turn-on is 10.8 V minimum / 11.5 V typical / 12.1 V
maximum, while turn-off is 9.1/9.5/10.3 V (UCC28180 p. 6). The recommended
VCC range is VCCOFF + 1 V through 21 V (p. 5). At the 11.4 V low end, the
controller may remain in UVLO; require a separately qualified controller bias
rail or test startup across the full tolerance and temperature range.

The UCC28180 GATE table is only a test point at VCC = 12.2 V and CGATE =
4.7 nF: 10.8 V minimum, 11.2 V typical, 12.0 V maximum (p. 7). It gives no
guaranteed GATE-high value for an 11.4–12.6 V rail, no GATE output I–V curve,
and no dynamic output resistance. The peak source/sink figures are 1.5 A
source and 2 A sink with CGATE = 4.7 nF (p. 7); they are peak capabilities,
not plateau-current guarantees. GATE rise/fall are 40/25 ns typical (8–60 ns
and 8–40 ns limits) under that same 4.7 nF timing setup. The internal 15.2 V
clamp is typical only (p. 17), and GATE is held off below controller UVLO.

Therefore the port contract is useful for testing the **buffered driver** but
must leave controller-to-driver logic amplitude, edge shape, startup/fault
behavior, and effective source impedance as measured inputs. UCC27624 INA's
specified high threshold is 1.8 V minimum / 2.0 V typical / 2.3 V maximum,
and low threshold is 0.8/1.0/1.2 V, with 1 V typical hysteresis (UCC27624
p. 6). Those thresholds are VDD-independent, but a passing logic threshold
does not prove the UCC28180 GATE pulse is valid under all VCC/load/fault
conditions.

## UCC27624 output facts and what cannot be treated as impedance

The recommended UCC27624 output range is 0 to VDD (p. 5). The 5 A source and
5 A sink numbers are typical peak tests at VDD = 12 V, CVDD = 10 µF,
CL = 0.1 µF, 1 kHz; the table marks them “not tested in production” (p. 6).
They cannot be used as a guaranteed continuous or plateau current at 129 kHz.

The table's `ROH = 5 Ω typ, 8.5 Ω max` is a **DC** measurement at IOUT =
−50 mA, and `ROL = 0.6 Ω typ, 1.1 Ω max` is a DC measurement at +50 mA (p. 6).
Section 6.3.4 (pp. 16–17) explicitly says ROH represents only the P-channel
device because the N-channel boost device is off in DC. During the brief
turn-on assist pulse, the N-channel is enabled and its resistance is about
1.04 Ω; the assist duration and current-vs-voltage/temperature behavior are
not specified. The effective turn-on resistance is therefore lower than ROH,
but neither `ROH`, `ROL`, nor the 1.04 Ω approximate value is a guaranteed
dynamic Miller-plateau impedance. Any model using `(1.04 || 5) Ω` with assist
or `5 Ω` without assist is a conditional hypothesis; the 8.5/1.1 Ω values are
only DC max anchors, not dynamic bounds.

UCC27624 propagation and rise/fall numbers are likewise test-specific:
6/10 ns typical (10/14 ns max) rise/fall at 1.8 nF with VDD = VEN = 12 V;
17/27 ns propagation at CLOAD = 1.8 nF, Vin = 0–3.3 V, 500 kHz, 50% duty,
and TJ = 125 °C (p. 7). They do not establish C7 gate transition times in the
assembled loop.

## Startup, enable, UVLO, and bypass requirements

UCC27624 INA/INB have internal 120 kΩ pulldowns; ENA/ENB have internal 200 kΩ
pullups, so a floating EN defaults **enabled** while a floating IN defaults
low (p. 4 and p. 6). EN is active high. Hold EN low with an external,
defined reset/interlock until both driver VDD and UCC28180 GATE behavior are
known; do not rely on a floating input or EN to guarantee fail-off. Outputs
are held low below UCC27624 UVLO and during VDD ramp (pp. 20, 24), but this
does not suppress a controller-generated pulse after the buffer has enabled.

TI requires two local low-ESR ceramic bypass capacitors: 0.1 µF less than
1 mm from VDD/GND and another ≥1 µF in parallel (UCC27624 pp. 4, 20, 24–25),
with the driver close to C7 and a short, low-inductance driver–gate–source
loop. Add the explicitly requested VDD droop/transient requirement to the
bench contract; the datasheet's capacitance recommendation does not prove
the rail meets 12 V ±5% under real gate current.

## C7 source facts and applicability limits

The IPW65R045C7 is 650 V, with static VGS −20…+20 V and dynamic VGS
−30…+30 V (C7 p. 3). Its 45 mΩ maximum RDS(on) is specified at VGS = 10 V,
ID = 24.9 A, Tj = 25 °C; the typical 150 °C curve point is 96 mΩ at that
test current (p. 4). Gate resistance is 0.85 Ω typical at 1 MHz/open drain.

Qg = 93 nC, Qgd = 30 nC, Qgs = 23 nC, and plateau = 5.4 V are typical
gate-charge values at VDD = 400 V, ID = 24.9 A, VGS = 0–10 V (p. 6). The
datasheet's timing test instead uses VGS = 13 V, VDD = 400 V, ID = 24.9 A,
and RG = 3.3 Ω (p. 5). None of these values is a guaranteed C7 Qgd,
plateau, or switching-energy value at the approximately 390 V PFC bus,
actual phase current, 12 V buffer output, 10 Ω network, temperature, or
assembled parasitics. A 12 V buffer supply is compatible with the C7's 10 V
RDS(on) test class in principle, but the actual VGS waveform and plateau
current remain unresolved.

## Bounded conditional sweep and mandatory measurements

Use the 12 V-port experiment only as a sensitivity envelope:

1. Test the assumed UCC27624 VDD port at 11.4, 12.0, and 12.6 V at the pins;
   allocate the 0.2 V load-droop allowance within that band and record local
   ripple/overshoot. Keep the
   UCC28180 VCC rail as a separate variable and prove it clears its UVLO
   thresholds at startup, shutdown, and faults.
2. For each VDD, run three output-drive hypotheses: (a) hybrid-assist
   turn-on using the approximate 1.04 Ω N-MOS assist in parallel with the
   5 Ω P-MOS typical value, (b) assist absent with 5 Ω, and (c) DC max
   anchors 8.5 Ω pull-up / 1.1 Ω pull-down. Label all three as model
   assumptions; none is a guaranteed dynamic bound. Sweep the external C7
   gate resistor and measure driver output current with a calibrated shunt.
3. Require scope captures at the UCC28180 GATE, UCC27624 INA/OUT, and C7
   gate/source pins: high/low levels, edge timing, plateau voltage/current,
   ringing, negative undershoot, and EN/VDD sequencing. Check UCC27624 input
   against 1.8–2.3 V high and 0.8–1.2 V low thresholds and its −10…+26 V
   recommended input range / −10…+30 V absolute range.
4. On a representative ~390 V double-pulse fixture, measure instantaneous
   drain current, VDS, VGS, Eon/Eoff, overshoot, and temperature. Do not
   substitute UCC peak-current ratings, C7 Qg/Qgd, RMS switch current, or
   4.7 nF controller timing for these measurements. Separate any measured
   Eon/Coss contribution before adding an Eoss term.
5. Verify EN is held low before UCC27624 VDD is valid and that UCC28180
   UVLO/OVP/PCL/fault transitions cannot create an unintended buffer output
   pulse. Confirm the actual AUX source, impedance, current limit, and
   startup sequencing; the PDFs do not provide those system-level facts.

Conclusion: 12 V ±5% at UCC27624 pins is a useful hypothetical driver-port
contract for a bounded C7 experiment, with explicit droop and interlock
requirements. It is not a qualified gate-drive contract and cannot supply a
guaranteed plateau impedance or switching-loss prediction without the
measurements above.
