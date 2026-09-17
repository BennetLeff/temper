# Evidence needed before selecting the buffered gate drive

This contract identifies the unresolved inputs to experiment 02. It records no
completed bench measurements and does not authorize energizing a prototype.
Use the existing power-entry bring-up/protection requirements for any hardware
work. Numerical agreement alone cannot close the items below.

## Supply and enable interface

The proposed controller supply is 15 V ±5% at UCC28180 VCC. The separate
UCC27624 supply is 12 V ±5% **at its pins under load**, including regulation,
ripple and switching transients. Its 0.2 V local droop budget is an allocation
within 11.4–12.6 V, not permission to fall below 11.4 V.

Do not reuse the 12 V band for controller startup: its 11.4 V low end is below
the UCC28180's 12.1 V maximum turn-on threshold. Recommended controller VCC
minimum is VCCOFF+1 V; using the 10.3 V maximum turn-off threshold gives
11.3 V for that operating constraint, which is distinct from startup.

The driver needs a local 100 nF ceramic and at least 1 µF ceramic, with the
effective capacitance at bias verified for the eventual exact parts. Qg/C
screens neglect ESR, ESL, supply replenishment and charge variation. The 10 V
datasheet charge cannot establish a 12 V upper bound or a supply current limit.

Both EN pins default enabled internally. The proposed implementation must hold
the used channel disabled until both supplies are valid, no fault is present,
and a low controller PWM state has been observed. Any rail-invalid or fault
condition must force disable independently of firmware. The unused channel is
explicitly disabled. This requirement has no implemented supervisor circuit in
the current PCB and is not a verified state machine.

## Driver characterization

Record exact parts, source revisions, fixture revision, supply impedances,
effective bypass capacitance, gate resistor, probe setup and temperatures.
First verify the supply/input/enable interface with a controlled low-energy
fixture. A capacitive load can characterize the driver, but cannot reproduce
drain-voltage Miller charge or establish switching energy.

The decisive unknown is the source-current profile while the C7 traverses its
plateau. Capture controller GATE, driver IN/OUT, VDD, EN and VGS referenced at
the MOSFET's source. Extract source/sink current with a characterized measurement
path and quantify its loading. Determine whether the transient NMOS assist
persists through the relevant transition; do not infer its duration from a
5 A peak rating or from the PMOS-only DC resistance.

Repeat for 11.4/12/12.6 V and the candidate gate resistors across the intended
temperature range. Retain input/enable sequencing during startup, brownout,
shutdown and faults. Preserve raw waveforms, bandwidth/timebase, uncertainty,
and pass/fail criteria before measuring. No case is complete from a screenshot
of a single nominal pulse.

## Commutation and installed assembly

Representative switching tests need measured instantaneous drain current and
bus voltage, VGS/VDS waveforms, junction/case temperature evidence and a defined
commutation path. The loss model's mean event currents and duty-weighted RMS
are not peak-current test setpoints. Its 10 nH loop inductance is an assumption,
and the TO-247-3 source lead couples the power and gate paths.

Measure the overshoot/ringing consequences of reducing gate resistance. Record
Eon/Eoff integration windows and whether Eoss is already included; do not add
the same capacitive energy twice. EMI and false-turn-on remain separate checks.
Only source-bound applicable switching evidence can replace the conditional
linear-ramp assumptions. Installed cooling is evaluated with those losses and
the actual assembly afterward.

## Acceptance boundary

The experiment answers which circuit change deserves construction and testing.
It cannot accept the supplies, sequencing, dynamic impedance, device switching
energy, temperature or cooling. Those findings stay INDETERMINATE until the
specified evidence exists and the corresponding validator consumes it.
