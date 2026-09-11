# Buck qualification targets and measurement definitions

Status: design targets adopted in the 2026-09-10 closure wave; component
minima remain unresolved. These targets are not measured performance or
approved engineering evidence.
Prepared from the Luna requirements follow-up and corrected during host review.
Base: `a75ca538d87d6578917d0cb3a50da7f14ebdc210`.

Keep the current 13.5–16.5 V input range, nominal 3.3 V output, 3.135–3.465 V
regulation band, and 0.5 A continuous design budget. The additional 1 A pulse
is design headroom; this audit has not established it as actual load
demand. Adopting a design target and demonstrating performance are separate acts.

## Disposition of the 16 unresolved IDs

| IDs | Proposed resolution |
|---|---|
| `iout_peak`, `iout_peak_duration` | 1 A for 10 ms, starting from 50 mA, pulse start-to-start interval at least 100 ms. Continuous 0.5 A remains a separate operating point. |
| `ripple_amplitude`, `ripple_bandwidth` | Maximum 50 mVpp at 20 MHz measurement bandwidth. Include zero-load PFM, 50 mA and 500 mA steady conditions. Evaluate the 1 A plateau separately from its load-step edges. |
| `startup_ramp` | Output 10–90% rise time at most 8 ms, defined as t90 minus t10, not time from an EN event. |
| `startup_overshoot` | At most 100 mV above final settled output, and never above 3.465 V. The absolute upper bound takes precedence. |
| `startup_settling` | Settle within 1% of final output within 10 ms after VIN enters the 13.5–16.5 V range; remain there through the observation window. The lower 3.135 V regulation bound applies after settling, not while the rail rises from zero. |
| `load_step_endpoints`, `load_step_slew` | Separate 50–500 mA and 50–1,000 mA cases, both directions, at 0.1 A/us. The full linear transitions are 4.5 us and 9.5 us, respectively. |
| `load_step_undershoot`, `load_step_overshoot` | No more than 100 mV departure from the pre-step mean, and always inside 3.135–3.465 V after startup. Neither condition overrides the other. |
| `load_step_recovery` | Reach a band within 1% of the post-step final mean within 1 ms of each current edge ending, then remain in it until the next edge. |
| `thermal_limit` | Proposed U3 junction limit 125°C and L2 hotspot limit 105°C at 0.5 A continuous load through 70°C ambient. Record distinct physical quantities; do not equate case temperature to junction temperature. |
| `efficiency_operating_points` | At each of 13.5, 15 and 16.5 V: at least 80% at 100 mA and at least 85% at 500 mA. Initially qualify this claim at 25°C; thermal-corner efficiency is a separately reported measurement. |
| `capacitor_effective_value` | Resolve through five per-placement evidence entries, each comparing an exact-part, condition-specific effective minimum with its required minimum. Numerical floors remain evidence-dependent, not an arbitrary blanket derating factor. |
| `inductor_current_rating` | Resolve through L2 current/temperature evidence, including normal ripple, transient overshoot, and saturation under fault current. Proposed hot saturation target: 20%-drop current above 8.35 A at 105°C (25% margin over 6.68 A). This is a design criterion, not a proven property. |

## Executable procedure proposal

**Startup.** Cold-start each input corner with VIN and VOUT discharged below
50 mV. EN remains physically tied to VIN. Apply a monotonic 0-to-target VIN
ramp lasting 1 ms; capture actual VIN and output. Let t0 be the first VIN
crossing of 13.5 V. Capture from before the input ramp until t0+20 ms. Define
the final output as the mean during t0+15 to t0+20 ms. Use its 10% and 90%
levels for t10/t90. Independently of the rise-time limit, require recovery into
the final +/-1% band by t0+10 ms and remain there through t0+20 ms. Require the
final mean inside 3.135–3.465 V and the stated upper bound throughout startup;
do not score the lower regulation bound while the output rises from zero.
Repeat at zero and 500 mA load.
Slow input ramps and prebiased restarts require separate procedures if claimed;
these startup targets do not implicitly qualify them.

**Ripple.** Measure differentially at C11/C12 terminals, with the probing
connection documented, 20 MHz bandwidth and at least 100 MS/s for bench
capture. After settling, retain 100 ms at each steady VIN/load point. Score
the maximum peak-to-peak voltage across that complete steady window so slow
PFM envelopes are not hidden by short subwindows. Retain a full-bandwidth
diagnostic separately if available; it is not interchangeable with this
bandwidth-limited acceptance quantity.

**Load transitions.** At each input corner, hold 50 mA for at least 100 ms,
rise to 500 mA or 1 A, hold for 10 ms, and fall to 50 mA. Repeat pulse starts
no faster than every 100 ms. Use three pulses at exactly 100 ms start-to-start
for this procedure, and capture 100 ms after the last falling edge. This
restriction applies to pulse starts; it does
not require 100 ms between the rising and falling edges of a 10 ms pulse.
Record actual current with nominal slew tolerance +/-10% and plateau tolerance
+/-2%. For each edge, compute Vpre over the last 1 ms before the edge and Vfinal
over the last 1 ms before the next edge, or the last 1 ms of the 100 ms capture
after the final falling edge. A window that has not settled is indeterminate.
Throughout the post-edge
plateau, require `max(3.135, Vpre-0.100) <= Vout <= min(3.465, Vpre+0.100)`.
After no more than 1 ms from edge completion, require
`abs(Vout-Vfinal) <= 0.01*Vfinal` continuously until the next edge or the end of
the final capture. Score both
directions; a passing rising edge cannot cover a failing falling edge.

**Efficiency and temperature.** The six efficiency points are (13.5,0.1),
(15,0.1), (16.5,0.1), (13.5,0.5), (15,0.5), (16.5,0.5) in V/A. Establish
thermal stability (less than 1°C drift over 10 minutes), then average input
and output power over the same 10-second window. Use synchronized measurements
or meters with a justified integration/error model. For thermal verification,
repeat the continuous-load input corners at 0, 40 and 70°C ambient in the
declared airflow/enclosure; retain a justified junction-temperature estimate
and L2 hotspot measurement. Physical execution remains deferred.

**Inductor hot-current criterion.** The 6.68 A basis is TI's published maximum
high-side peak-current limit, cited in [components.md](components.md). The
proposed 8.35 A criterion asks for a hot inductance-versus-current curve whose
20% drop point exceeds that value, with its reference inductance and test
conditions explicitly stated. It is not a fault-survival test. Fault duration,
waveform, heating and recovery would need a separate procedure before claiming
fault survival; no such claim is established here.

**Uncertainty.** Upper-bound checks use measured value plus the stated expanded
uncertainty; lower-bound checks use measured value minus it. Time, voltage,
current, efficiency and temperature each need their own uncertainty budget.
Missing bandwidth, timing resolution, calibration or stable final windows
makes the measurement indeterminate rather than a pass. The +/-1% settling
band is in volts (0.01 times Vfinal), not an untyped percentage of a sample.

## Schema and evidence boundary

The closure wave adds `load_step_endpoints.profiles` with separate IDs and
`low_a`/`high_a` endpoints, and `thermal_limit.limits` with separate component,
quantity and value fields. An explicit malformed list cannot fall back to an
old scalar. Legacy scalar requirements remain readable; simulation coverage
requires the explicit load profiles. See [scenario contract](../../engineering/scenarios/README.md)
for the simulation transport and measurement boundary. Merely generating two
reports is not an aggregate admission guarantee.

Thermal and component evidence must retain named quantities and per-part limits.
Do not fill scalar placeholders with invented aggregates to make the current
validator pass. The current component receipt already carries five capacitor
entries; reuse that representation when implementing the requirements linkage.
Active requirements now carry the adopted targets; capacitor and inductor
evidence requirements remain unresolved. Registry approval and physical
measurements remain separate. The detailed repeated-pulse, slew, recovery,
startup-corner and thermal procedures above are not all automated by the new
profile-coverage check.

The proposed heating-policy clarification is full heating through 40°C,
derating from 40–70°C, and 70–75°C reserved for cooldown. It intentionally
changes conflicting rows in `docs/specs/REQUIREMENTS.md`; it is not a discovered
existing requirement. The curve and firmware remain unchanged. Buck capacity
for control electronics is independent of the heating-power derating curve.
