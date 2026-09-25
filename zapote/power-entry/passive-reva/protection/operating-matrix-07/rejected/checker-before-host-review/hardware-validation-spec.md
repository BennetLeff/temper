# Hardware validation specification after the normal-point screen

This is an observation and comparison specification. It is intentionally not
an energized step-by-step procedure. Hardware remains unavailable for this
matrix and no simulation pass authorizes energization.

## Required observations

At each accepted simulated normal point, retain synchronized records of line
voltage/current at the defined input port, bridge/inductor/shunt current,
VD and VB, MOSFET VDS and VGS (referenced to the actual source), gate-enable,
ARM/PERMIT/fault, controller state, load voltage/current, and all 15-V/5-V
rail voltages. Record ambient and inlet temperature, component case
temperatures, board copper temperatures at the shunt/bridge/switch/diode,
and the duration and settled-cycle count. Capture raw traces and instrument
settings with the source revision, PCB/BOM identity, probe serials, bandwidth
limits, sample rate, attenuation and calibration date.

## Instruments and independent checks

Use a safety-rated isolated differential voltage probe for each floating hot
node, a calibrated current probe or shunt Kelvin measurement for the line and
inductor currents, and a power analyser capable of true-RMS, real-power and
PF measurements over the switching bandwidth. Use a separate oscilloscope
for event timing and gate/fault correlation. Use thermocouples or calibrated
RTDs for case/board/inlet observations and an infrared camera only as a
cross-check with emissivity documented. Verify probes against a known source
and verify current polarity before the run.

For every point, compare instrument-integrated cycle metrics against the
checker using the same defined port and integer-cycle window: Vrms, Irms,
real power, PF, load power, VB mean/ripple/drift, IL peak, VD/VDS/VGS peaks,
and ARM/on fraction. Differences require an uncertainty budget and raw-trace
review; they are not fixed by changing the screen. Compare the authored
controller model against controller-pin observations (PCL, OVP, standby,
soft-start and retry) and compare magnetic loss/current behavior against
vendor curves at the measured temperature. Compare thermal observations
against a separately bound thermal model; a loss estimate alone is not
thermal qualification.

## Fault scenarios, only after a normal point is accepted

Fault work is a separate gate. Execute only the scenarios whose fixtures,
interlocks, current limits and recovery criteria have been reviewed:

* F2 open during an established run and during startup, including charged,
  discharged and residual-charge restart states;
* controller OVP-before-external-latch and repeated mains input;
* healthy switch, switch-short, diode-short and both-short graph states;
* loss of ARM/PERMIT, rail undervoltage/overvoltage and controller standby;
* adverse line/PWM phase, current-limit delay, minimum effective capacitance,
  hot magnetic/device parameters, ESR/ESL and interconnect inductance.

Observe the same node set plus latch timing, source work, local energy and
whether any gate command receives unjustified current-interruption credit.
Stop on an unbounded fuse arc, magnetic curve, parasitic ringing, supply
producer, partial-power or thermal input. A fault trace with an aliased
switching current, missing settled reference, unknown averaging semantics or
disabled/unstable loop is indeterminate and cannot be relabelled as pass.
