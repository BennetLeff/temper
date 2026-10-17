# Coordinator review notes

These notes record checks and requested corrections during execution. They
are not a substitute for the final reports or their reproduced outputs.

## A1 switching

- Package inductances in the vendor model must remain separate from external
  board terms. The requested sensitivity scales external deck inductances.
- Equal results at two endpoints do not prove a continuous range when the
  circuit can ring. Report the sampled cases and current monotonicity check.
- A 1 ns secant restricted to the 10–90% voltage interval is a specifically
  filtered edge metric, not the absolute full-transition peak dv/dt. Requested
  both metrics and explicit bandwidth/timestep treatment.
- Die VDS multiplied by an external drain-current probe can include storage
  energy and does not equal dissipated heat. Requested separate model loss
  terms, observation windows and validity limits for A6.
- The requested 120/170/198 V points do not cover the low-voltage part of a
  rectified mains cycle. B4 must show missing coverage or obtain additional
  validated thresholds; no silent extrapolation to zero bus.

## A2 inductance

- Two sandbox DNS errors were corrected by an escalated official-source
  download. They were not counted as failed builds.
- After two actual macOS compiler failures, the plan's fallback applies.
- Initial power pad-to-pad chords left real copper for much of their length.
  Those were rejected as complete loop models. Requested connected copper
  paths, plated vertical paths, gate returns and bulk-path accounting.
- Nearest return copper distance alone is not the separation of the actual
  current paths. Ordered heuristic scenarios must not be presented as
  guaranteed bounds or as a completed field solve.

## A3 protection

- Reviewed the shunt threshold equation and adverse resistor directions.
- Requested input-bias and reference-load allowances; exact BOM and pin/net
  checks; correct CT supply naming and supply range; separate IC Monte Carlo
  samples where joint behavior is reported. Initial narrow CT bands omitted
  the SELV rail range and are superseded by the worker's final artifact.
- A comparator's tested 20 mV step-response maximum does not automatically
  guarantee a response to an arbitrary time-varying input. The proposed
  20 mV-crossing-plus-55 ns calculation must retain its waveform conditions.
- Static corners and Monte Carlo percentiles answer different questions.
  Typical/random tails do not replace worst-case component corners.

## A4 copper

- Requested BUS_P convergence, not reuse of the prior coil-only check.
- Mixed DC and high-frequency injection heat depends on their signed moments
  and covariance. A coherent 15+19 A case is an assumed stress experiment;
  it is not established operating heat. Do not sum alternative path rows.
- Preserve historical `04-board-current-thermal/round3/README.md`; new A4
  evidence belongs in its own subdirectory.
- Independently reconstructed all 37 saved heat transfers from nodal NPZ
  arrays plus per-layer barrel heat. Every residual is below 1e-8 W.
  The separate sheet-plus-barrel audit tally is not added again.

## A5 tank

- Requested time-weighted RMS on adaptive simulation time points, explicit
  crest interval, loaded-inductance definition and energy-consistent trip
  initial conditions.
- Cases that exceed protection thresholds remain useful unconstrained tank
  stresses but cannot be treated as sustainable operating points for A6/B3.
- The event table must carry bus voltage and direction at every event.
- Corrected the handback's bleed-resistor voltage comparison: Yageo RC1206
  printed p. 5 defines continuous working voltage as DC or AC RMS. The
  205.574 V instantaneous peak is not a failure against the 200 V RMS
  criterion; maximum RMS is 103.133 V. Updated the integration analysis
  script, regenerated summary and report; repetitive peak qualification
  remains distinct. Original worker output remains in its worktree.

## Source intake for A6/A7

- The exact C1/C2 part is absent from KEMET's simulation search. A related
  1 µF/22.5 mm R46 variant was exported and identified by its different MPN.
- TDK lists the exact choke model but its download requires acceptance of a
  license. Confirmation was requested; no acceptance or download bypass has
  been performed. The published-curve fitting path remains available.
- Prepared official pad, bridge, regulator and auxiliary-supply datasheets.
  Area-normalized pad impedance, contact pressure and bridge per-element
  thermal resistance must retain their test conditions.
