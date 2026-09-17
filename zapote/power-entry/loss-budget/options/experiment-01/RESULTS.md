# Existing-drive MOSFET comparison: experiment 01

The IPW65R045C7 merits the next gate-drive experiment. It has the lowest nominal
partial loss in this model, but the independent device sensitivities overlap.
This is a research priority, not an approved substitution. The authored circuit,
PCB, BOM and production loss-budget adapter retain STW65N65DM2AG.

## Conditional result

At 120 Vrms input, 15 A input RMS, 400 V bus, 129.107 kHz, 10 V gate bias,
10 Ω external gate resistance and no additional driver resistance:

| Device | Switching overlap | Eoss | Conduction | Gate network | Partial total |
| --- | ---: | ---: | ---: | ---: | ---: |
| STW65N65DM2AG | 129.90 W | 2.26 W | 7.20 W | 0.155 W | **139.51 W** |
| IPW65R045C7 | 60.24 W | 1.51 W | 6.48 W | 0.120 W | **68.35 W** |
| IPW65R041CFD7 | 79.04 W | 1.81 W | 5.90 W | 0.132 W | **86.88 W** |

These totals cover the modeled MOSFET and gate network only. They are neither
measured heat nor whole-board loss, efficiency or delivered output. The model's
input power here is 1,796.31 W. The 400 V comparison was chosen for the candidates'
numeric Eoss points; the earlier incumbent result near 136 W used the authored
approximately 389.615 V bus. Those are different operating points.

Switching overlap dominates the conditional difference. The C7's lower Miller
charge, lower internal gate resistance and plateau point shorten the modeled
transition. Its small conduction advantage explains little of the difference.
Both transition currents and duty-weighted RMS are retained separately.

## What uncertainty changes

Adding hypothetical symmetric driver resistance while holding the other nominal
inputs fixed produces these partial totals:

| Device | +0 Ω | +5 Ω | +10 Ω |
| --- | ---: | ---: | ---: |
| STW65N65DM2AG | 139.51 W | 188.35 W | 237.18 W |
| IPW65R045C7 | 68.35 W | 96.11 W | 123.87 W |
| IPW65R041CFD7 | 86.88 W | 115.52 W | 144.16 W |

This resistance is an assumed driver characteristic lumped into the solver's
resistance input, not a changed PCB resistor or measured driver I–V curve.
The separate 1.5 A source and 2 A sink peak limits are retained.

Independently varying each device's Qgd by 0.5–1.5× and plateau by ±0.5 V at
the otherwise nominal point gives ST **82.07–204.73 W**, C7 **45.76–92.18 W**,
and CFD7 **56.68–119.83 W**. Every pair overlaps. These are hypothetical
sensitivity ranges, not confidence intervals or guaranteed bounds. Matching
the same multiplier across parts would hide possible reversals in their ranking.

ST charge is specified at 520 V/60 A; the candidates' charge points are at
400 V/about 25 A. Actual event currents here average about 11.93/15.03 A.
The sensitivity grid does not establish a valid transfer between those points.
The ST plateau is assumed. Rds multiplier 2 is not a hot-temperature model.
Temperature feedback, real driver behavior, diode/commutation behavior and
installed cooling remain unresolved. Typical Eoss is not a guaranteed bound;
ST's ±0.6 µJ digitization uncertainty is metadata, not a swept axis.

## Evidence and decision

All **4,374 scenarios** passed numerical/source/configuration checks. The
standalone continuous-phase and triangle-energy audit agreed on all cases;
maximum relative discrepancy was **1.035e-11 or less**. It calls neither the
production moment function nor the switching solver. This verifies the
conditional arithmetic, not whether the waveform assumptions describe hardware.
The overall result remains **INDETERMINATE**, with CLI exit 2.

The next discriminating experiment should compare the C7 with an explicitly
specified gate supply and applicable source/sink drive characteristics, including
turn-on/off resistance and commutation/overshoot constraints. Keep the current
part as the control. If those inputs cannot be established from source evidence,
record the gap and define the required waveform measurement instead of selecting
a nominal resistance. A stronger-driver comparison needs an actual bias/UVLO
contract; it must not silently borrow the controller's peak-current rating.

Do not size cooling from the 68 W nominal point or select a replacement yet.
The present result prioritizes reducing switching loss and resolving the drive
uncertainty before developing an installed-cooling model.

See [PLAN.md](PLAN.md), [SOURCE-AUDIT.md](SOURCE-AUDIT.md),
[raw results](evidence/report.json), [audit result](evidence/audit-result.json),
and [verification](evidence/VALIDATION.md) for scope and reproducibility.
