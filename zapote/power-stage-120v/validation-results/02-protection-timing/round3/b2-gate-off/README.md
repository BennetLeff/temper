# B2 — gate-off and returned-energy handoff

- Board: native-15, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Source: `44417ae1489fd00e2d652fd3b2c1582b76d17630`; 2026-09-27, Codex coordinator.
- Verdict: **BLOCKED** for F2 current at actual gate-off and dynamic F3.
- Evidence: source review and arithmetic on the completed A3/A5 models.

## Findings

[A3](../README.md) completed the ideal CT grid but did not establish a
comparator delay guarantee for arbitrary ramps. Its 20 mV plus 55 ns
estimates are conditional. Adding an assumed gate-discharge delay to them
would not produce a guaranteed fault-current limit. A first gate-threshold
crossing also does not establish persistent turn-off when the switch can
turn on again during its partner's transition.

[A5](../../../05-resonant-tank-envelope/round3/README.md) starts its trip
from the same-time maximum-capacitor-voltage state of an unconstrained tank
trajectory. Its minimum-bank bus result is 273.747 V, compared with A3's
272.087 V minimum static OVP threshold and D3's 295 V stand-off. The latter
leaves 21.253 V in that model. The gates are already off in this experiment;
crossing the OVP threshold cannot prevent the stored energy from returning
through the body diodes. This is not a simulation of when the real chain
would initiate shutdown.

`comparison.json` records all three capacitance cases and a lossless energy
ceiling for each **fixed initial state in an isolated lumped model**. It
does not bound other trip phases, ongoing mains replenishment, delayed
switching, or local inductive voltage overshoot. It does not establish D3
hot pulse/repetition qualification.

## Why the historical bus script was not run unchanged

`tools/bus_voltage_sim.py` explicitly retains a historical 4.5 µF bank,
crest-start trajectory, ideal current detector and 300 ns assumed delay.
Its own header says these are illustrative. The present bank is 5.49–6.11 µF
and the real sensing/filter/interlock timing remains incomplete. Running
the default script would replace missing evidence with obsolete assumptions.
A5's finite-bank diode simulation supplies the relevant partial F3 result.

## Inputs required to finish

Measure or qualify the actual ramp-dependent comparator, interlock and
PERMIT timing. Capture MOSFET gate, current, tank-capacitor voltage and bus
voltage together at the final turn-off instant, including any gate rebound.
Use that simultaneous state, the actual bank/ESL and clamp-loop parasitics
for the returned-energy simulation. Check the current pulse against the
MOSFET's specified conditions; T1's 88 A thermal reference is not an
absolute instantaneous limit. Follow `DC-LINK-CLAMP.md` for hot clamp pulse
duration, repetition and terminal-versus-board voltage assessment.

## Reproduce

Run `assess_handoff.py` with Python from any directory. It hashes the
integrated A3/A5 inputs and writes `comparison.json`; no simulator or
invented downstream delay is used.
