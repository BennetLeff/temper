# F2-open: a smaller sensing circuit and a shutdown requirement

2026-09-19. **Scoped circuit experiment; protection qualification INDETERMINATE.**
The new `elec/src/power_entry_f2_sense.ato:PowerEntryF2Sense` compiles to 21
components. It replaces the equivalent 31-part sensing portion of the rejected
supervisor, saving ten components without discarding either voltage observation
or either direction of voltage difference. This is not a 21-part complete
protection system. The canonical 54-part power board remains unchanged.

## Circuit decision

Keep F2 between boost diode and bank. Keep the proposed diode-side reservoir,
independent absolute OV observation, hardware gate disable and a retained fault
latch. Replace the buffered fixed-difference detector with two tapped dividers:

```text
VD -- 200k -- 200k -- 200k -- 200k -- 187k -- DH -- 200R -- DL -- 5.62k -- return
VB -- 200k -- 200k -- 200k -- 200k -- 187k -- BH -- 200R -- BL -- 5.62k -- return
                                                    |                   
                               100pF from each H node to return

Quad comparator (open-collector outputs joined to FAULT_N_RAW):
  A: pulls low when DH > 2.5V       independent diode-side overvoltage
  B: pulls low when BH > 2.5V       independent bank-side overvoltage
  C: pulls low when DL > BH        diode side pulling ahead of bank
  D: pulls low when BL > DH        bank side pulling ahead of diode

FAULT_N_RAW --> hardware fault latch --> driver enable LOW and UCC standby
                                            |
                                  remove downstream permission
```

All returns are the controller-side HOT bus minus, not rectifier negative or
SELV ground. The drawing's latch/driver/interface is a required next integration;
it is not present in this isolated sensing entry. Raw FAULT_N must never be
used directly as RUN permission. Its pullup requires a regulated logic rail.

Nominal relative trip is `VD/VB > 5820/5620 = 1.035587`, or the reverse ratio.
The approximately 3.56% dead band comes from two 200-ohm divider segments.
No op-amp or buffered reference offset is needed. The two absolute OV channels
still use the shared LM4040 reference; nominal OV is 426.469 V. Its full threshold
budget has not been requalified here.

Count: 16 divider/filter components, one TLV1704, its bypass capacitor, one
LM4040, its bias resistor, and one output pullup = 21. The comparator's input
loads are included in the static calculation: two pins on each H tap and one
on each L tap. Exact candidate MPNs and physical pin connections are retained
in the compiled export. Stock availability and purchasing qualification are
not established by compilation.

## What happens when the fuse opens

For a healthy diode and controllable switch, current already in U8 cannot
vanish when F2 opens. Once U9 turns off, the path is rectifier positive → U8 →
U10 → diode-side capacitor → controller return → U12 → rectifier negative.
The main bank is outside that path. The mains can add energy during this
commutation; an inductor-energy-only calculation would miss it.

For the ideal constant-input case:

`Vpeak = Vin + sqrt((Vtrip - Vin)^2 + (L/C) * Itrip^2)`.

After current reaches zero, the healthy diode blocks reverse flow. With U9
held off, there is no commanded boost action. At high local capacitor voltage
the lower rectified line cannot keep charging it through the diode. As the
bleeder discharges it, passive mains recharge remains possible; gate-off is not
mains isolation or discharge-to-safe-voltage. The bleeder and service procedure
remain necessary.

If U9 is failed short, gate shutdown is ineffective: line-fed current needs
F1 coordination. If U10 is also short, F2 is the proposed bulk-bank interrupter.
The local capacitor remains outside F2 and can dump into those shorts. None of
these failed-device interruption/containment cases is qualified by this work.

## Static trip results and controller restart

The Rust screen enumerates 2,048 paired divider/bias/offset corners per bank
voltage. Budgets: each resistor ±0.35% (0.1% initial plus 25 ppm/K over 100 K),
each input bias ±20 nA, and comparator differential error ±8 mV. The last is an
authored allowance, not a complete installed-device bound. PCB leakage, common-mode
behavior, ageing, additional parasitics and actual temperatures remain open.
An additional 0.1% resistor-drift sensitivity is separately printed.

| Bank voltage | Earliest diode-side trip | Latest diode-side trip |
|---:|---:|---:|
| 120 V | 121.030 V | 127.556 V |
| 150 V | 151.668 V | 159.059 V |
| 390 V | 396.774 V | 411.084 V |
| 410 V | 417.199 V | 432.086 V |

These are static, conditional results. In particular, the earliest-trip margin
at 120 V is small; installed ripple/noise must fit it. They are not response-time
measurements. Swapping VD/VB gives the reverse detector case.

UCC28180 disables PWM at its upper OVP threshold and permits it again after
voltage falls. Its specified threshold spans 107–111% of VREF, with reset at
100–104%; this is not a retained fault latch. [TI UCC28180 Rev D](https://www.ti.com/lit/ds/symlink/ucc28180.pdf),
§§7.5, 8.3.4. This is why the external latch remains necessary.

At VB=390 V, the latest static relative trip is 1.05406 × VB. It precedes the
107% controller threshold only if the initial bank is below about 1.01512 × that
same controller's regulation target. This comparison assumes settled sensing
and no intervening dynamics. Bank ripple, controller response and detector delay
must satisfy it; it is not a proof that the detector always beats controller OVP.
In particular, preceding a voltage crossing does not establish output timing.

## Energy turns into a concrete timing requirement

Use a provisional local ceiling of 500 V, 132 Vac crest input, nominal 180 µH,
19.8 µF (22 µF minus its stated 10% initial tolerance), and the latest static
trip for an initial 410 V bank. During a still-switching delay the screen uses
`Imax = Itrip + Vin/L * delay`, and pessimistically permits simultaneous maximum
current and capacitor-voltage growth, then commutates the stored energy.

| Assumed current at static trip | Immediate-off peak | Peak with 5 µs delay | Maximum delay to 500 V in this screen |
|---:|---:|---:|---:|
| 20 A | 439.39 V | 449.65 V | 20.38 µs |
| 40 A | 460.12 V | 477.40 V | 10.66 µs |
| 60 A | 491.56 V | 514.10 V | 1.93 µs |

**These are design requirements conditional on assumed current and plant
parameters, not deadlines the hardware has demonstrated.** Delay starts at the
unfiltered static trip condition and must include sensing/filter lag, comparator
response, latch/logic, driver and actual switch current cessation. Saturation,
L(I,T), capacitor temperature/bias, wiring inductance, diode/switch transients,
fuse arcing and surge are not modeled. The 500 V ceiling is an engineering
screen, not a newly established capacitor or semiconductor rating.

The retained TLV1704 has full-temperature input-offset/bias specifications,
but its published propagation delays are typical values at a stated overdrive.
Those typical values cannot certify the required total delay on a slow-ramping
input. [TI TLV1704 Rev D](https://www.ti.com/lit/ds/symlink/tlv1704.pdf), §§7.6–7.7.
The next component decision is to establish that delay at the actual input ramp,
or replace this comparator with a part whose applicable guarantee suffices.
Do not simply substitute the typical delay into the safety budget.

## Startup and fault cases

| State when F2 is open | What the detector can establish | Required surrounding behavior |
|---|---|---|
| Both sides initially at zero | Nothing about continuity; offset determines raw state | Default-off until precharge and independent continuity check |
| Only VD charged | Forward mismatch asserts once the offset is exceeded | Hold off; no arm into an open bank path |
| Only VB charged | Reverse mismatch asserts | Hold off; residual charge does not authorize startup |
| Both sides equally charged, no energy transfer | Open and closed fuse are indistinguishable | Never report continuity from voltage equality |
| Opening during startup, VD subsequently rises | Relative mismatch can assert well below full bank voltage | Latch fault and stop; startup sequencing remains external |
| Opening during run | Relative mismatch or absolute OV can assert as nodes separate | Direct gate disable, retained fault, revoke load permission |
| Fault clears or AUX returns | A healthy-looking detector output is not a start event | Fresh deliberate arm edge after rail validity; held arm/permit cannot restart |
| U9 failed short | Detector cannot turn a failed switch off | Separate line-fuse/containment coordination |

A voltage monitor cannot guarantee detection of every open fuse at the instant
of opening. The claim is detection of hazardous voltage separation/OV within a
budget still to be proven. An automatic continuity-test mechanism is not added
or credited here.

## Checks actually run

- Atopile 0.2.69 compiled and exported the isolated source to `source-02`:
  21 components. `source-01` retains the failed sandbox-cache attempt.
- Three Rust compiled-graph checks passed: current source snapshot/count,
  comparator polarity/tap wiring, and divider component values.
- Ten Rust screen checks passed, including the independent ngspice comparisons.
- The existing canonical passive source/native binding test passed.
- ngspice 45.2 independently solved the resistor network. A nominal 390→450 V
  ramp at 3 V/µs crossed the assumed +8 mV decision at 15.67598 µs, including
  the 100 pF filter. This is a prescribed ramp, not UCC controller behavior.
- The healthy-off idealized commutation case gave 460.0342 V in ngspice versus
  460.1198 V in the loss-free calculation. The small difference is consistent
  with diode and bleeder losses. Synthetic diode/ideal OFF switch only; this
  does not establish STW/C3D switching performance.

Full traces, netlists, compiler output and test logs are retained here. An early
Rust build had a bitmask type error, corrected before successful compilation;
one SPICE invocation used the wrong working-directory-relative path, retained
as `divider-attempt-01.log`. Neither produced a numerical result used above.
No new PCB, native schematic, ERC/DRC result, installed measurement or qualified
full-controller transient model is claimed.

Reproduce from the repo root (SPICE runs from this directory):

```sh
rustc --edition=2021 -O zapote/power-entry/passive-reva/protection/f2-open-01/window_screen.rs -o /tmp/temper-f2-window-screen
/tmp/temper-f2-window-screen
rustc --edition=2021 --test zapote/power-entry/passive-reva/protection/f2-open-01/window_screen.rs -o /tmp/temper-f2-window-tests
/tmp/temper-f2-window-tests
cargo test --locked --offline --manifest-path zapote/Cargo.toml -p zapote-erc --test f2_sense --test passive_reva
```
