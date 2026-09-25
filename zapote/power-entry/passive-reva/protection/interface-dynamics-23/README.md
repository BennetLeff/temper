# Revision 23: duration sensitivity of an added startup-current pulse

Date: 2026-09-22. This is a bounded follow-up to the [Revision 22
sustained-load screen](../interface-dynamics-22/README.md). It asks whether
the vendor-model clamp fixture treats a short added-current pulse differently
from a sustained load near the modeled limit. It does **not** model the actual
TPS54202 converter, IRM-10-15 source, or complete power-entry assembly.
Revision 11 remains the latest compiled candidate.

## Source, timing and load identity

All decks use the Revision 20/22 LT4363-1 and FDB33N25 circuit, 15 V source
through a declared 0.5 Ω resistor, 130 Ω baseline output load, 1.5 µF gate
capacitor and 330 µF output capacitor. The official ADI LTspice 26.0.2 model
and library identities are recorded in [Revision 20](../interface-dynamics-20/README.md).
In a [new baseline timing run](baseline-enable-time.log), the protected output
first crosses **10.6 V at 2.4890909 s** and **13.5 V at 2.7117722 s**. The
10.6 V level is the [Revision 17 nominal divider illustration](../interface-integration-17/README.md),
not a guaranteed TPS54202 enable threshold.

The pulse decks add a **rectangular 150 mA current request** starting at
2.4891 s, on top of the 130 Ω load. Durations are 5, 20, 100 and 500 ms.
The magnitude and rectangle are arbitrary sensitivity inputs. TI specifies a
[5 ms *typical* internal soft-start](https://www.ti.com/lit/ds/symlink/tps54202.pdf);
that is an output-control timing datum, **not** a rectangular 150 mA VIN
current waveform or a guaranteed current/duration limit. The fixed-time pulse
also ignores the actual converter's enable hysteresis, input/output capacitor
charging, switching current and interaction with a slowing protected rail.

The first [ideal-sink deck](pulse-150mA.cir) remained on even after the output
collapsed. Its 500 ms case drove the simulated rail below −5 V around 2.7 s,
which is a fixture artifact and must not be used as a circuit result. The
[revised deck](pulse-150mA-vin-gated.cir) multiplies the current request by a
smooth voltage gate centered at 4 V with a 0.2 V scale, so the artificial load
vanishes as its input collapses. This is only a cutoff surrogate. TI's actual
[TPS54202 VIN UVLO](https://www.ti.com/lit/ds/symlink/tps54202.pdf) has
specified rising and falling threshold ranges and hysteresis; the gate does
not implement that behavior. Both decks and logs remain to show why the
revision was needed.

## Corrected-fixture results

The [voltage-gated sweep log](pulse-150mA-vin-gated.log) used a 100 µs maximum
step. The [5/20 ms convergence log](pulse-150mA-convergence.log) used 20 µs.
All solver processes exited 0 and reached the 6 s endpoint.

| 150 mA pulse | Maximum step | TMR peak | 13.5 V reached? | Protected output at 6 s | Modeled outcome |
| ---: | ---: | ---: | --- | ---: | --- |
| 5 ms | 100 / 20 µs | 1.1199 / 1.1270 V | Yes, ~2.7175 s | 14.908 V | Recovers |
| 20 ms | 100 / 20 µs | 4.310 / 4.310 V | No | ~0.00065 V | LT4363-1 latches off |
| 100 ms | 100 µs | 4.310 V | No | ~0.00065 V | Latches off |
| 500 ms | 100 µs | 4.310 V | No | ~0.00065 V | Latches off |

The 5-versus-20 ms distinction survives a five-times smaller step and removal
of the negative-voltage load artifact. It establishes duration sensitivity for
**this declared pulse and model**. It is not an allowed inrush envelope: the
actual buck input-current pulse may have another amplitude, shape, onset,
repetition pattern or undervoltage response, while source and component
corners are not represented. A real current pulse that causes current limiting
also needs the FET's time-dependent electrical and thermal stress evaluated.

## Practical next step

Capture the selected assembly's startup at the **protected rail** with enough
time resolution to resolve the first tens of milliseconds after buck enable,
and retain a longer record through AUX settling and any LT4363 timer event.
Record converter VIN current, protected-rail voltage at its consumers, 5 V
output, buck EN, LT4363 sense voltage, TMR, FET VDS/current and source voltage
simultaneously. Include cold and partially charged starts, relay/PWM inhibited
and enabled states, load steps, temperature and source-current-limit behavior.
The [Revision 15/16 bench worksheet](../interface-active-15/bench-plan.md)
states the broader fixture and fault cases. The model's 5 ms pass is not a
substitute for that measurement.

Neither the direct IRM-10-15 nor the historical IRM-10-24→LDO proposal is
integrated into Revision 11, and no hardware or manufacturer fault waveform
was obtained here. The product's AUX continuity requirement during a fault
also remains a separate decision.

## Reproduction

Run the four `.cir` decks in this directory with the official LTspice package
and bundled models identified by Revision 20. Each deck declares its circuit,
stimulus, solver maximum step and measurements. `raw-uncompressed.sha256`
records precompression SHA-256 for all raw traces; `artifact-hashes.sha256`
checks the retained decks, logs, compressed traces and this report, excluding
itself. A completed simulation is a fixture result, not product acceptance.
