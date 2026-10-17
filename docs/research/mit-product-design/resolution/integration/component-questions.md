# Component questions needed before design freeze

Draft technical requests only; no supplier has been contacted.

## CDE resonant bank: 942C12P22K-F and 942C12P1K-F

Temper's provisional full bridge uses two 0.22 µF parts and one 0.1 µF part in parallel as a 0.54 µF series resonant bank. The assumed switching range is 20–60 kHz with a 60 Hz rectified-line amplitude envelope, on a 108–140 V RMS input design range. The physical coil/pan impedance and fault waveforms are not yet measured. The catalog's 1200 Vdc / 430 Vac at 60 Hz ratings do not settle this application.

Request, for **each exact part**:

- Continuous allowable bipolar peak voltage and RMS voltage versus frequency and case/ambient temperature, including the basis for a carrier whose amplitude varies over the line cycle.
- Allowable RMS current, pulse current, dV/dt, voltage reversal and pulse repetition limits; ESR/loss and thermal-resistance data needed to predict self-heating.
- Mounting/lead-length/airflow assumptions, case-temperature measurement location, maximum hot-spot temperature and life derating.
- Approved practice for this unequal-capacitance parallel bank: current sharing, layout symmetry, thermal coupling and failure behavior; recommended alternatives if this family cannot meet the eventual measured envelope.
- Required startup, detuning, pan-removal and fault waveform captures for an application review.

Attach the actual waveforms when available. The corrected model reports roughly 400 V p95 line-crest capacitor voltage **only among modeled full-power cases**; it does not bound reduced-power or fault stress. Do not present that statistic or the former arbitrary 650 V screen as a required or proven maximum. The model's ideal current-sharing sensitivity is in [electrical-model.md](../electrical-model.md).

## Knob switch and stop: C&K PTS645SH43SMTR92LFS candidate

The inherited dimensional budget has delivered plunger motion at the hard stop of 0.20–0.50 mm, while the assumed switch trip interval is 0.15–0.40 mm. It therefore permits a missed click at one corner. An early-tripping unit could receive a further 0.35 mm motion; this is **not** a demonstrated safe overtravel allowance.

Request the exact order-code drawing and conditions for maximum total plunger displacement, permissible post-trip travel, force at the mechanical limit, static overload, repeated overload life, temperature dependence and off-axis loading. Ask whether the quoted operating travel is measured at electrical make, tactile snap or bottoming. Obtain any required external stop guidance and mounting-plane tolerances.

Then set the stop, rest gap and compliance using two independently checked inequalities: minimum delivered travel exceeds maximum trip by the chosen actuation margin; maximum delivered stroke and force remain within supplier limits. Do not move the present stop merely to hide the missed-click corner. Confirm the complete hot/cold/reassembled stack on a physical control mockup before accepting the mechanism.
