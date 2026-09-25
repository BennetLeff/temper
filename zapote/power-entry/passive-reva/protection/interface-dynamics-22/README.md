# Revision 22: protected-AUX load-envelope screen

Date: 2026-09-22. This bounded LTspice experiment asks how much **sustained
additional current** the Revision 19 clamp fixture tolerates after its output
rises past an approximate buck-enable point. It is a sensitivity screen, not
a TPS54202 startup model, an IRM-10-15 fault model, or a qualification of the
power-entry assembly. Revision 11 remains the latest compiled candidate.

## Why this screen

The [Revision 20 fixture](../interface-dynamics-20/README.md) used a fixed
130 Ω load; its nominal 15 V current is about 115 mA. The [Revision 14 load
audit](../interface-physical-14/load-audit.md) gives 114.473684 mA only under
historical 75 mA direct-AUX and 75 mA logic5 allocations and assumed 70%
buck efficiency. Neither is a measured maximum. [Revision 21](../interface-dynamics-21/README.md)
found that TI's TPS54202 ZIP cannot be parsed by LTspice, so no physical
converter-current transient is available from that attempt.

The [LT4363 Rev C data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf)
gives a 50 mV typical current-limit sense voltage and 45–55 mV at its stated
12 V VCC / 3–12 V OUT conditions. Across the fixture's 0.22 Ω sense resistor,
those are 227.3 mA typical and 204.5–250.0 mA at those stated conditions,
before sense-resistor error. The same table gives a lower foldback threshold
for OUT below 1 V. These specified test points are not a guaranteed 15 V
startup-current limit for this assembly. They explain why extra load near
100 mA merits a circuit sensitivity test. The proposed direct [Mean Well
IRM-10-15](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF) has a
0.67 A nameplate rating, but the clamp's own current limit can act first; its
rating alone cannot establish protected-rail startup.

## Declared fixture

The three [LTspice decks](load-step-screen.cir) copy the Revision 20
`startup-6s.cir` LT4363-1/FDB33N25 circuit, source and component values,
including the **synthetic 15 V source through 0.5 Ω** and the 130 Ω load. The
only electrical addition is a behavioral current sink that rises smoothly
over 0.15 V around **10.6 V protected output** and then remains on:

```text
Iextra × 0.5 × [1 + tanh((Vprotected − 10.6 V)/0.15 V)]
```

The 10.6 V center comes from the [Revision 17 nominal enable-divider
illustration](../interface-integration-17/README.md), not a guaranteed buck
enable voltage. The added current is **above** the 130 Ω baseline. It is not
the entire buck input current, a timed inrush pulse, or the actual new circuit
load. Real enable threshold, capacitor charging, switching pulses, driver and
relay states, source droop and temperature remain unbound. Solver nominal
temperature is 27 °C. The 1N4148 model remains a surrogate for 1N4148W.

## Results

All three decks completed in official ADI LTspice 26.0.2. The [coarse
screen](load-step-screen.log) used 100 µs maximum step; [refinement](load-step-refined.log)
used the same settings; [convergence](load-step-convergence.log) repeated
110 and 120 mA with a 20 µs maximum step. Output values below are at 6 s.

| Added sustained current | Maximum step | Output at 6 s | TMR peak | Result in this fixture |
| ---: | ---: | ---: | ---: | --- |
| 0 mA | 100 µs | 14.908 V | 0.500 V | Recovers |
| 50 mA | 100 µs | 14.869 V | 0.500 V | Recovers |
| 100 mA | 100 µs | 14.830 V | 0.500 V | Recovers |
| 110 mA | 100 / 20 µs | 14.822 / 14.822 V | 0.613 / 0.614 V | Recovers; modeled pass-current peak 227.52 mA |
| 120 mA | 100 / 20 µs | ~0.00065 / ~0.00065 V | 4.310 / 4.310 V | Reaches 13.5 V briefly, then latches off; peak 228.07 mA |
| 130, 140, 150 mA | 100 µs | ~0.00065 V | 4.310 V | Latches off before reaching 13.5 V |

The matched 110/120 mA outcomes survive the five-times smaller maximum
step. This brackets a **fixture-specific** transition between these sampled
loads. It does not locate a general part threshold or prove that a short
120 mA pulse would latch. The current source's persistent behavior matters:
timer accumulation occurs while the demanded current remains above what this
modeled clamp can deliver. At 120 mA, the transient's momentary crossing of
13.5 V is not successful startup; the rail has collapsed by 3 s.

## Decision and next measurement

The immediate engineering target is a current-versus-time capture at the
**protected rail** during cold startup and enable, not another nominal DC
budget. Use the selected source, actual 5 V converter and its input/output
capacitors, driver circuit, supervisor, relay and permitted state sequencing.
Measure `AUX_RAW`, `AUX_PROTECTED` at the consumer pins, clamp FET current or
sense voltage, TMR, buck VIN/input current, 5 V output and enable. Record
source impedance/current limit and repeat after full/partial discharge and
over temperature. Compare the measured waveform with the [Revision 19
transient matrix](../interface-dynamics-19/transient-matrix.md) and the
[Revision 15/16 bench worksheet](../interface-active-15/bench-plan.md).

The Rev 20 35 V / 50 ms stimulus still latches the LT4363-1 and removes AUX
in its fixture. The product must explicitly decide whether a safe latched
stop is acceptable or AUX continuity is required; this screen cannot decide
that requirement. No bench run or compiled source integration occurred here.

## Reproduction and artifacts

Run each `.cir` deck with the same official LTspice executable and bundled
libraries identified by [Revision 20](../interface-dynamics-20/README.md).
The [solver logs](load-step-convergence.log), deck files, process output and
compressed raw traces are retained here. `raw-uncompressed.sha256` records
the digest of each raw trace before compression; `artifact-hashes.sha256`
records the retained files. The latter excludes itself. A solver completion
is evidence for the stated fixture only.
