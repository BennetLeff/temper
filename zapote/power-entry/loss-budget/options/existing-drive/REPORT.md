# Existing STW65N65DM2AG with UCC28180D drive — engineering report

Investigation revision: `80ae56830d9cc679b280736fde62461573bcafdd`.
Retrieved-source date: 2026-09-17. No powered test was performed.

The existing gate network is electrically identified, but its operating point
is not. U11's UCC28180D VCC pin is tied directly to the external
`AUX_15V_IN` connector. The source manifest contains no regulator, clamp or
other producer that establishes 15 V. The GATE pin drives the boost MOSFET
through one authored 10 ohm resistor; a 10 kohm pulldown is at the MOSFET
gate. There is no anti-parallel turn-off diode. Therefore 9–11 V in the
current loss model is an assumption, not a measurement or a schematic-derived
gate bias.

## Source identity and retained evidence

| Item | Exact revision / condition | Retained bytes and URL |
|---|---|---|
| TI UCC28180D | SLUSBQ5D Rev D, revised July 2016; printed pp. 3, 7, 17, 26 | `../../../shunt-repair/sources/TI-UCC28180.pdf`, SHA-256 `e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`; [TI datasheet](https://www.ti.com/lit/ds/symlink/ucc28180.pdf), [TI product/tools](https://www.ti.com/product/UCC28180), retrieved 2026-09-17 |
| STW65N65DM2AG | DocID028164 Rev 1, August 2015; printed pp. 4 and 7 | `../../sources/STW65N65DM2AG.pdf` (from this option directory), SHA-256 `6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322`; [ST datasheet](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf), retrieved 2026-09-17 |
| Unit schematic | Candidate section, source-manifest at this revision | `../../../shunt-repair/candidate/section.kicad_sch`, SHA-256 `49db3ee4e2d79f08d524b92457764098f9dc051b17746729cfb1460bbde4d3a9`; manifest SHA-256 `136c94c36af498285c731e6cd43877eb5cc2e2b2289de21fbd8d531bc7d18ef2` |

Exact source excerpts and pin/net bindings are retained in
[`evidence/driver-excerpts.txt`](evidence/driver-excerpts.txt). TI's product
page also lists a UCC28180 PSpice average model (SLUM423) and TINA transient
model (SLUM528); neither model was downloaded or used, so no manufacturer
SPICE result is implied here.

## Driver facts and what they do not establish

TI specifies a push-pull output with typical peak capability of 1.5 A source
and 2 A sink, but these are peak ratings under `CGATE=4.7 nF`, not a complete
output I–V curve. The same table gives 40 ns typical rise (2–8 V) and 25 ns
typical fall (8–2 V) for that test load. The output high is specified as
11.2 V typical (10.8–12 V) at VCC=12.2 V and 15.2 V typical (14.5–16.1 V)
at VCC=20 V, with a 15.2 V typical internal clamp. There is no output-high
specification at VCC=15 V. Interpolating those two test points to 15 V would
be an estimate only; it is not used as a fixed candidate input.

If a future isolated measurement proves 15 V at U11 pin 7 under load, a
9–11 V sweep can remain a deliberately conservative sensitivity range, but it
still cannot be promoted to the actual gate bias without observing U11 pin 8
and the MOSFET gate.

TI recommends VCC from VCCOFF + 1 V to 21 V (printed p.5); 10.5 V uses the
typical VCCOFF, while its 10.3 V maximum gives an 11.3 V operating minimum.
UVLO turns the controller on at 11.5 V typical (12.1 V maximum) and off at
9.5 V typical (10.3 V maximum), per the printed p.6 table. Those
thresholds constrain an external supply but do not establish its nominal
voltage, ripple or source impedance at U11.

Experiment 02 corrected the earlier fixed 10.5 V wording above. Its proposed
12 V ±5% buffer supply is separate from controller VCC: the 11.4 V low end
does not guarantee clearing the controller's maximum startup threshold.

The 10 kohm pulldown draws about 1.1–1.5 mA for a 11–15 V gate and drops only
about 11–15 mV across the 10 ohm series resistor at DC. Dynamic current is
set by the MOSFET charge, the 10 ohm external resistor, 3.3 ohm intrinsic
gate resistance, PCB parasitics and the driver's unknown output impedance.
The TI design example instead uses 3.3 ohm plus an anti-parallel 40 V/1 A
Schottky to bypass that resistor during turn-off. The existing 10 ohm/no-diode
network therefore has no source-backed fast-turn-off path.

For a transparent conditional calculation, let `Rseries=10+3.3=13.3 ohm`,
and retain the model's 6.2 V plateau only as an assumption. The resistive
plateau-current expression is

`Iplateau <= min(Ipeak_rating, (Vdrive - 6.2 V)/13.3 ohm)`.

The inequality is deliberate: any UCC output resistance, PCB resistance or
actual plateau above 6.2 V lowers current. With ST's typical `Qgd=58 nC`, the
corresponding `Qgd/Iplateau` values are optimistic lower bounds on Miller
transition time:

The table is reproducible without a workspace build with:

```sh
rustc gate_calc.rs -O -o /tmp/existing-drive-gate-calc
/tmp/existing-drive-gate-calc
```

`gate_calc.rs` contains only the equations and constants shown here. It is a
calculation receipt, not a replacement for the Rust loss model.

| Assumed driver output (V) | Plateau current upper bound (A) | Qgd-only time lower bound (ns) |
|---:|---:|---:|
| 9.0 | 0.211 | 275.5 |
| 10.0 | 0.286 | 203.0 |
| 11.0 | 0.361 | 160.7 |
| 12.2 (assumed gate output; TI test has 11.2 V typ output at VCC=12.2 V) | 0.451 | 128.6 |
| 15.0 (external-label assumption only) | 0.662 | 87.6 |

Even at 15 V, the 1.5/2 A peak ratings do not bind this 13.3 ohm path at
the assumed plateau. The existing model's 9–11 V cases are useful sensitivity
points but cannot be called the actual gate waveform. `Qgd`, `Qgs` and `Qg`
were measured at 520 V drain, 60 A drain, and 10 V gate; transfer charge at
the ~390 V bus and phase-varying current is unknown. `Qg-Qgd` is not a valid
replacement for the current-transfer charge.

The conditional gate-charge supply-energy expression is `P=Qg*Vdrive*fSW`.
At the model frequency 129107.392 Hz it gives 0.139, 0.155, 0.170, 0.189,
and 0.232 W for 9, 10, 11, 12.2 and 15 V respectively, using the ST typical
120 nC test-point charge. These are driver supply-energy sensitivities, not
MOSFET die loss bounds. The UCC datasheet's 7 mA typical operating current is
specified with a 4.7 nF gate load at VCC=15 V; adding `Qg*V*f` to that number
without separating loaded-gate current would double count. The external
15 V supply current and source impedance are missing.

## Temperature and line operating points

TI's electrical-characteristic conditions cover `-40 .. 125 °C`, but it does
not publish GATE high or output resistance at 25/100/125 °C. Thus driver
voltage/current at those temperatures is **unknown**, not extrapolated. ST's
Figure 10 is a typical normalized `RDS(on)` curve at VGS=10 V. Reading the
plot gives approximately 1.0× at 25 °C, 1.6× near 100 °C and 2.0× near 125 °C
(plot-read estimates, not maxima), so the 50 mOhm 25 °C maximum would become
roughly 80 and 100 mOhm if those typical multipliers applied. This supports a
conditional hot-resistance sensitivity only; it does not qualify junction
temperature or package cooling.

The requested line points keep the common 15 A RMS ceiling. Existing CCM
model anchors are 1,796.416 W ideal input at 120 Vrms/15 A, 1,617.1 W at
108 Vrms/15 A (ceiling binds), and 1,796.416 W at 132 Vrms/13.645 A. These
are fixed-input-model sensitivities, not delivered DC output or efficiency.
No gate-drive evidence changes those power anchors, and switching overlap,
hot RDS(on), auxiliary supply loss, diode/core/capacitor losses and cooling
remain unresolved at all three lines.

## Candidate disposition

Keeping the STW65N65DM2AG and existing 10 ohm network is a valid baseline for
measurement. It is not endorsed: the actual AUX_15V_IN voltage, GATE high,
plateau, output impedance, commutation waveform and hot RDS(on) are absent.
The 10 ohm/no-diode path should not be represented as equivalent to TI's 3.3
ohm plus turn-off-diode reference network. No replacement part is required by
this investigation.

The first decisive bench step is a low-voltage, current-limited driver
characterization with the controller in a valid operating state (VCC, VSENSE,
ISENSE, ICOMP, VCOMP and FREQ all set to valid data-sheet operating conditions).
Do not back-drive the controller GATE output. Use a known
capacitive/resistive gate load and observe U11 GATE and q_boost-g with a
short-ground spring or differential probe; measure high/low levels,
source/sink current (small calibrated series shunt), output loading and
ringing, repeating at 25/100/125 °C fixture temperatures. This does not
characterize a drain-voltage Miller plateau or switching energy. Those require
a representative ~390 V drain commutation/double-pulse fixture with measured
drain current and a stated Eon/Coss partition. No such test was run here.
