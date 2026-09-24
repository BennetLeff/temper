# Coil/pan bench intake (no measurements yet)

The seven rows in [coil-run-register.tsv](coil-run-register.tsv) map exactly to the `coil` rows in the [inverter U3 registry](../evidence/measurement-scenarios.tsv). Every row is unmeasured (`NOT_RUN` or an explicit hold). The header-only [run-manifest.tsv](run-manifest.tsv) and [coil-points.tsv](coil-points.tsv) are capture schemas, not evidence. No coil article, pan, fixture, frequency limit, drive current or loaded-impedance bound has been accepted. The old 88 µH, 59.8 µH, 300 nF and 47 kHz numbers in [coil-evidence.md](../coil-evidence.md) remain historical hypotheses.

## Article, fixture and preflight

Before any run, freeze a drawing/revision and serial for the physical winding, ferrite, terminals, bracket and gap reference. Name pan material, base diameter, thickness, ID and preconditioning. Retain photographs and dimensional records. Use one fixture geometry and coil build across the reference, weak, offset and lift comparisons; if a build changes, start a new campaign rather than combining extrema. Identify lead length and the open/short fixture compensation used by the impedance instrument. Record model/serial, calibration certificate and validity, frequency/current capability, correction settings, temperature sensors and their calibration, operator, reviewer and UTC time in `run-manifest.tsv`.

Preflight begins with all cooker power sources disconnected, VD and VB independently verified discharged by an approved rated instrument, and the coil leads isolated from any gate/inverter circuit. Inspect the fixture for exposed conductors and secure the pan mechanically. Do not infer zero energy from an off command or open F2. Set excitation within an instrument- and article-reviewed low-energy envelope recorded in header-only [run-approval.tsv](run-approval.tsv); record the actual voltage/current at every point. Stop and preserve the run if current, temperature, fixture motion or instrument range exceeds the approved preflight bounds, or if any sensor is invalid. A missing bound is a hold, not permission to choose one at the bench.

## Sequence

1. Record no-pan cold points and, separately, a documented hot-coil state. At minimum span the prior [coil-evidence](../coil-evidence.md) 20, 30, 40, 47 and 50 kHz investigation points, plus any frequencies needed for the proposed design window. Use more than one excitation-current level; small-signal data does not establish high-current behavior.
2. Capture the same frequency/current matrix for an identified reference pan cold and hot, a *different* weak-coupling pan, and the mechanically approved maximum offset and lift. Do not guess the maximum geometry. If a pan or geometry limit is not selected, leave that registry row `HOLD_INPUT`.
3. At each point save `Z_re`, signed `Z_im`, phase, RMS voltage/current, winding/ferrite/pan temperatures, gap/offset/lift, raw instrument file, corrections and uncertainty components. `coil-points.tsv` has explicit units. Keep individual samples; never replace them with only a rounded extrema summary.
4. Repeat points needed to expose instrument drift, temperature hysteresis and winding sample spread. Resolve questionable points against raw files and recalibration before summarizing. Review extrema for loaded real and imaginary impedance independently; one pan need not set both extremes. Calculate series-equivalent L only where inductive `Z_im` and the chosen equivalent circuit are valid. Report frequency/current/temperature applicability and uncertainty separately from extrapolation.
5. `coil_live_removal` stays `HOLD_ENERGIZED`: it requires an accepted protected native inverter, bounded source energy/current, separate pan-motion fixture, synchronized current/command/gate capture, measured current-zero, and an independently approved procedure. Static before/after impedance cannot fill its removal/trip/current-zero times.

Do not connect an LCR instrument to the Rev38 roughly 390 V bus or an energized coil. No full-bank short or live fault injection is part of this packet.

The eventual home-kitchen behavior test must measure set/hold and recovery across identified pan and placement states, through-glass and probe temperature disagreement, heat-intensity changes and preset transitions. Those tests need a built protected cooker and defined Temper targets; they cannot be inferred from complex impedance or from another cooker's published behavior.

## Transfer to the existing U3 gate

An independent reviewer first reconciles points and uncertainty against raw captures and checks run IDs, article/fixture identity and pan states. Then, for a single U3 scenario, compute `f_min_hz`, `f_max_hz`, `i_min_a`, `i_max_a`, temperature, `z_re`/`z_im` extrema, `u_z_ohm`, geometry and sample count from the reviewed points; place the original immutable raw file under `zapote/inverter/evidence/raw/`, record its full SHA-256 and reviewer in the U3 manifest. The gate also requires article, coil, pan and `HOT0` return fields. Its `CAPTURE_RECORDED` is a typed byte-bound record, not engineering acceptance. Complete coil records still cannot select a switch/frequency without the independent bus, stop, fault and part rows.

Capture tables use decimal values in the units named by each column. A field that is required for a run must never be blank, `UNKNOWN`, or silently zero. If a field does not apply to a particular point, use `NA` and explain why in the run's raw record; such a row cannot be promoted if the existing U3 gate requires that field. Store the uncertainty calculation or instrument specification used, rather than only an unexplained `u_` value.

The selected VB-local capacitor and any inverter-side detached capacitance must be handed to discharge with tolerance, bias, temperature, aging, physical location, fault-loop and discharge path. Coil/pan loss is not automatically heat inside the fan duct: split winding/ferrite, pan, switch, tank-capacitor and bus-component destinations when measured. Until then, both discharge energy and cooling loss maps remain incomplete.

### Negative controls already exercised by the U3 checker

Its Rust tests reject an unloaded-L-only record, a single frequency/current point, a `PWR_RTN` return, mixed coil/fixture campaigns, missing raw digest, synthetic observations presented as hardware, and gate-off without a separate measured current-zero. Re-run those tests when transferring records; header-only templates and `NOT_RUN` rows are expected to yield no measured claim.
