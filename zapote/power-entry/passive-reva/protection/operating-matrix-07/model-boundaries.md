# Applicability of the operating-matrix model

Host audit, 2026-09-20. This register is based on the executable
`normal-tracked/cold.cir`, its includes, and the earlier source-bound
contracts. It describes the limits of conclusions even if a numerical run
passes. It does not replace the pending operating/fault results.

| Element | What the current run actually models | Boundary on interpretation / next evidence |
|---|---|---|
| Mains and load | 60 Hz sine, fixed source resistance, scripted NTC bypass and resistive load connection | The declared line/load matrix covers these stimuli; it does not cover arbitrary mains distortion, surge, brownout trajectories or an induction inverter's dynamic load. |
| Inductor | Constant 180 uH with 20 milliohm winding resistance | The selected part's 43 A saturation figure is typical at a stated inductance reduction, not a current cap. Hot L(I,T), core loss and thermal behavior are absent. Use explicitly conditional L bounds for sensitivity; do not claim a guaranteed magnetic envelope. |
| Local and bulk capacitance | Constant 19.8 uF / 2240 uF, with no installed ESR/ESL distribution | The local capacitance is a chosen effective-floor assumption. Temperature/frequency/voltage tolerance and physical parasitics require vendor evidence or measurement. VB energy must not be credited upstream after F2 opens. |
| Power MOSFET | Level-1 channel, separately represented body path, fixed Cds/Cgd/Cgs | Model current and voltage waveforms are nominal surrogates. Nonlinear capacitance, loaded turn-off, reverse recovery, SOA, loss and junction temperature are not qualified. |
| Boost diodes and bridge | Authored diode equations and declared constant/model capacitances | These establish modeled conduction paths, not exact installed hot-device behavior or reverse-voltage margin under unmodeled ringing. |
| F2 and interconnect | Ideal controlled switch with finite on/off resistance | An opening case is a circuit-topology intervention. It does not prove fuse clearing time, arc interruption, restrike, or disposal of local-reservoir energy. A shorted switch receives no current-interruption credit from a gate command. |
| UCC28180 | Authored functional surrogate with reviewed loop/pole/latch behavior | The 0.72 V ICOMP/ramp offset is an explicit inference; nominal limiting, blanking, reset and edge timings are not guaranteed hot/tolerance limits. Six fixtures and numerical regressions constrain modeled behavior, not silicon correlation. |
| UCC27511A driver | Original authored threshold/RC/output-resistance surrogate; separate unchanged TI model with split outputs; finite 2.1–2.3 V transfer diagnostic | Both the original surrogate and vendor-model full startup have numerical failures. The finite transfer is an arbitrary regularization under test, not manufacturer behavior. Numerical completion alone cannot validate input hysteresis, source/sink current, propagation delay or disable timing. A source-bound fidelity comparison is required before relying on protection margins. |
| Clamp | Corrected location/polarity, but assumed Vishay BAV23C diode equation | Existing assumed-model pass cannot qualify selected-part loading. Manufacturer-model follow-up is separate, and another manufacturer's BAV23C model cannot silently qualify the Vishay part. |
| Rails, ARM and PERMIT | Ideal external voltage/sequence stimuli feeding physical modeled consumers | Prior supply-candidate traces do not make these ideal sources a complete cold rail co-simulation. Isolation, real sequencing producer, partial power, rail overshoot and load coupling remain integration requirements. |
| Protection and standby | Candidate divider/comparator/latch/driver and two-FET inhibit representations | Focused timing/default-off checks support declared models. Layout, parasitic coupling, component spread and installed disable/current-cessation timing remain unqualified. |

## Authority and acceptance

The inherited source requirement is 108–132 VAC and at most 15 A input RMS;
the current campaign explicitly uses 60 Hz. The 389.615 V nominal bus and
selected 25/50/90% conditional load points are the declared simulation
configuration, not a newly established continuous output-power rating.

The normal checker uses a chosen ±5% regulation envelope, final-three-cycle
drift below 0.5%, positive input/output power and energy-accounting checks.
Its 500 V VD ceiling is a chosen screen. The 450 V VB, 650 V VDS and ±25 V
VGS values are rating screens, not guaranteed installed transient margins.
Inductor peak current is reported without inventing a maximum-current rating.
A numerical pass must remain `qualification=NOT_CLAIMED`.

An actual normal-point pass enables source-bound conditional fault studies.
Sensitivity points should use justified inputs and retain unknown physical
bounds explicitly. They cannot establish a continuous worst-case envelope
from an arbitrary finite grid. A waveform outside a screen must be retained
and investigated; a changed model invalidates evidence tied to the old hash.

## Evidence already retained

- `../controller-integration-06/host/integration-contract.md`: connectivity,
  control ownership and the distinction between the retained source and the
  integration candidate.
- `../controller-integration-06/limits/README.md` and `result.json`: node
  authorities, conditional current/delay/L/C region and exact missing data.
- `host/controller-model-review.md`: source-backed reset/pole/latch work and
  the explicitly inferred offset.
- `controller-finite-edge-safe/README.md` and `numerical-repair/README.md`:
  finite-edge and unknown-state regressions, without hardware timing claims.
- `clamp/datasheet-audit/report.md`: applicability failure of the assumed
  diode model and primary-source requirements.
- `checker/hardware-validation-spec.md`: observations needed to compare a
  future prototype to accepted simulated conditions.

Normal/fault margins and resulting schematic decisions are still pending.

## Hysteretic driver candidate

The newer `normal-hysteretic-driver-candidate/` run uses native hysteretic
states for PWM and INM (2.2/1.2 V), and AUX qualification (4.2/3.9 V), plus
the TI model's nominal input loading. It retains a collapsed output with a
1-ohm/18.75-nF internal pole, 1-ohm output resistance and external10-ohm gate
resistor. It does not reproduce the vendor's separate source/sink transistor
paths. Host-reviewed fixtures compare slow/fast PWM, RUN/AUX, partial-rail
thresholds and a late-time edge. The tested fast gate4 V falling crossing is
37.5 ns later than the vendor model, and AUX-loss gate4 V is119.6 ns later.
These observed differences bound only those declared fixtures; they are not
worst-case device delays or proof of fidelity under arbitrary Miller current.
The full startup remains unaccepted until its complete trace passes the normal
checker. See the source-bound bench report under
`numerical-repair/driver-hysteresis-candidate/`.
