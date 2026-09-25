# Required dynamic acceptance — no full-system result yet

Use the corrected revision19 native graph and exact revision18 part
identities. The nominal source is15V; the provisional normal range used in
prior work is14.625–15.75V. A12V startup would sit below the nominal12.88V
UV threshold and must not be used as a normal-startup pass case.

Start with C3=1.30/1.70uF crossed with a declared output-capacitance model.
The198–495uF bulk test-factor screen and≤18uF downstream allocation are
separate objects: total output may be tested at520uF as the deliberately
conservative upper allocation, but198uF total must not be described as the
minimum populated assembly. Local input ceramics and ESR/impedance/frequency
behavior must be represented separately where converter interaction matters.
None of these allocations establishes a full-life capacitance bound.

| Case | Initial state and stimulus | Required observation / acceptance |
|---|---|---|
| Cold startup | Declared initial charge;15V and normal-range endpoints; real buck/load startup with PWM and relay disabled | Rails establish without unintended switching, repeated UV cycling or foldback stall; record current, actual driver-pin voltage, TMR, VGS and converter startup |
| SHDN during operation | Charged C3/C4 at normal rail;120ms low and longer investigative pulses | Measure Q1 current cessation and VGS separately from timer reset. A pulse passing timer reset is not evidence of full discharge. Check output hold-up and precharged restart |
| UV/brownout | Slow and fast source collapse, recovery and repeated threshold crossings | Observe controller supply, source and gate together; no unintended RUN on return. Below controller operating voltage, do not extrapolate its valid-supply guarantees |
| Reset after latched fault | Begin after natural cooldown, and at multiple points during cooldown | Verify SHDN low voltage/duration and release slew; Q1 thermal recovery must be sufficient. New source authorization and valid session remain necessary; service reset cannot grant RUN |
| Source overvoltage | Nominal15V to provisional35V envelope, with explicitly bounded source impedance, slew and duration | Actual voltage at driver supply stays below18V for the declared case; assess VDS/ID/time and energy against applicable hot SOA. Return of normal voltage must not erase a latched fault |
| Overload/short | Explicit load and fault path; do not equate nominal or typical current with a maximum | Observe foldback, timer expiry, current cessation and latch behavior; verify the modeled pass device remains functional and within the applicable SOA |

Record Q1 gate and source independently and compute VGS from those traces.
A chosen gate-to-ground threshold, a4V threshold-voltage datum, or disappearance
of gate drive alone cannot prove a safe off state. Measure Q1 current and load
behavior at the relevant source/drain voltages. Downstream stored energy can
sustain the load after Q1 stops conducting.

No numeric complete-shutdown deadline, required zero-charge restart state,
ride-through duration, guaranteed source surge waveform or allowed repeat
rate is established here. Those are requirements/data gaps, not passing cases.
Do not choose a requirement from a convenient nominal simulation result.

Vendor-model preparation must verify -1 latch-off rather than -2 retry,
actual pin mapping, shutdown sink behavior, UV behavior, current-limit
foldback, timer operation and FET nonlinear gate charge. Sweep numerical
step size on a small initial case before expanding. Keep each attempt bounded
at30seconds and record failure/incompletion distinctly. A nominal vendor
model can expose failures but cannot certify unmodeled datasheet corners.
