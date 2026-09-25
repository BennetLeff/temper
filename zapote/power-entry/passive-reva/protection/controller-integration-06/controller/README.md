# Controller-coupled switching witness

This is a **nominal functional model and a precharged switching witness**, not a
qualified UCC28180 macro-model or a settled operating point. It replaces the old
fixed100kHz/55% PWM stimulus with live VB/ISENSE feedback, an external compensated
voltage amplifier, current averaging, nonlinear M1/M2 gain, and leading-edge PWM.
The intended next use is a conditional line/load study after the remaining model
and interface gaps below are resolved.

## Source and independent checks

TI publishes SLUM528 (TINA transient) and SLUM423 (PSpice average) at
https://www.ti.com/product/UCC28180 . Both downloaded archives are retained in
`sources/`; their controller libraries are encrypted and cannot be evaluated by
ngspice. `ucc28180.inc` is host-authored from the retained TI RevD datasheet.
It is not a decrypted, converted or manufacturer-certified model.

- Pin-forced functional fixtures test UVLO11.5/9.5V hysteresis, OVP5.45/5.10V
  hysteresis, VSENSE standby/recovery, ISENSE open-pin, ICOMP short, PCL blanking
  from the actual leading gate request and retention for the rest of the cycle,
  EDR source current, and SOC sink current. They test model functions, not silicon
  propagation maxima. Nominal digital-state delay is an explicit1ns assumption.
- `current-loop.cir` reproduces TI's worked example: M1=.538 at VCOMP3V,
  M2=1.387634615V/µs at118kHz. Its physical2.7nF compensation capacitor follows
  the independently predicted36.979µs pole and DC gain (TIeq100). Measured PWM
  period is checked as well. This tests the actual SPICE current loop, not just
  arithmetic that never controls PWM.
- `soft-start.cir` uses the retained40.2kΩ/4.7µF/220nF compensation network.
  Pin stimuli exercise charging, SOC discharge/recovery, standby and retry.
  This is not cold startup of the2240µF power bank.
- The coupled fixture includes four bridge diodes, AC source work/current,
  rectifier-return10mΩ shunt,220Ω/1nF sense filter,180µH inductor/20mΩ winding,
  two SiC legs, finite MOS/channel/body/capacitance model, local19.8µF reservoir,
  ideal F2,2240µF bank and220Ω load. The actual VSENSE ratio and compensation
  values are preserved. RevB's separate VD/VB detectors, rail qualification,
  fresh-arm latch and default-off driver are copied into `protection.inc`.
- Negative controls disable PCL or bypass independent external protection;
  the same full-trace checker must reject each for its specific intended reason.
- The coupled witness is repeated at10ns and5ns maximum timesteps. Both must
  pass independently, with peak differences≤50mV/50mA and latch-time difference
  ≤50ns. This is numerical convergence, not a tolerance or physical limit proof.

Run `./run_checks.sh`. Rust rejects malformed, nonfinite, unordered, gapped or
truncated traces. Full precision `numdgt=17` avoids duplicate rounded event times.
Generated positive/negative outputs and logs are retained beside the fixtures.

## Applicability and remaining work

The witness starts with VD/VB389.615V, VCOMP3V, ICOMP3V and qualified protection
rail timers. ARM rises at20µs, F2 opens at600µs and the run ends at900µs. The
controller runs during the first25µs while the driver waits for ARM; afterward a
logical standby clamp follows the local latch. This explicitly prequalified
initialization is a fixture boundary. It is not a source of real precharge,
continuity, isolated ARM or load-permit sequencing. Cold start and long-duration
regulation remain unverified.

The final standby clamp is a proposed logical connection, not an already compiled
physical addition to the retained power source. AUX15/LOGIC5 remain ideal port
stimuli in this fast switching witness. The separate supply candidate is tested
separately; no dynamic regulator/shutdown co-simulation is claimed.

Source resistance0.25Ω and bridge diode parameters (including100pF junction
capacitance) are model assumptions. The bridge model is not an exact GBJ2510
loss/commutation model. Winding resistance is a room-temperature datum; constant
L does not establish L(I,T). The04 MOS/SiC surrogates retain their original
limitations. Body-diode recovery, capacitance curves, wiring L, reservoir ESR/ESL,
fuse arc/clearing and temperature corners remain unqualified.

Controller frequency uses the source calculation's129.107kHz at16.2kΩ; the fitted
RFREQ law is not a guaranteed oscillator transfer over the entire frequency
range. Amplifier saturation at±50µA is an authored approximation of the stated
linear range. Powered OLP discharge uses80Ω from the nominal0.04V at0.5mA datum;
bias-absent discharge uses5.405kΩ from0.37mA at2V. Neither is a maximum response
bound. The nominal gate output and protection driver do not reproduce every
internal transistor, supply transient, temperature corner or propagation delay.

**Existing source defect:** the retained BAT54H clamp connects its anode to the
negative bridge-return shunt node and cathode to HOT0. It therefore does not
clamp the negative ISENSE excursion required by TI§8.3.14. The coupled model does
not invent an effective clamp in its place. The accepted witness remains within
the sense-pin range; negative inrush/short qualification is open. A correction
must also preserve the −0.438V PCL threshold: blindly reversing the Schottky is
insufficient. See the host review disposition for the reference-design follow-up.
