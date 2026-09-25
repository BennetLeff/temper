# Operating-matrix-07 simulation campaign report

**Status: INTERIM.** The modeled normal grid and three fault cases have
source-bound receipts, but the campaign is not complete. SW-SHORT is
indeterminate after an endpoint abort; DIODE-SHORT is running; BOTH-SHORT and
BYPASS-NEG remain unexecuted. Nothing here is a hardware, fuse, thermal, SOA,
safety, or production qualification.

## What is established

The accepted [normal baseline](../accepted-baseline-11/acceptance.json) and
[nine-point grid](operating-envelope-checkpoint-53.md) use the declared
event-aware policy: finite, nondecreasing complete rows; endpoint within its fixed tolerance;
all-row electrical extrema; cycle drift; and equal-time predicate/integral
audits. The source is a 60 Hz model with resistive output loads; it is not an
induction-inverter or full-cooker model and does not establish a continuous
108–132 VAC or full-rated-power envelope. Tested modeled load powers are
approximately 359–1392 W. The legacy strictly-increasing checker remains visibly rejected on
repeated timestamps and is not used to discard rows.

| Point | VAC RMS | Rload (Ω) | Load power (W) | Bus min–max (V) | Input RMS (A) | Drift (%) |
|---|---:|---:|---:|---|---:|---:|
| LL01 | 108 | 416.460489 | 359.07 | 385.676–387.716 | 3.869 | 0.1499 |
| LL02 | 108 | 208.230244 | 705.40 | 381.308–385.189 | 7.510 | 0.2726 |
| LL03 | 108 | 115.683469 | 1242.52 | 375.858–382.392 | 13.412 | 0.4156 |
| LL04 | 120 | 374.814440 | 398.20 | 385.202–387.442 | 3.844 | 0.1653 |
| LL05 | 120 | 187.407220 | 783.85 | 381.212–385.347 | 7.420 | 0.2749 |
| LL06 | 120 | 104.115122 | 1383.94 | 376.244–382.998 | 13.199 | 0.3873 |
| LL07 | 132 | 374.814440 | 398.38 | 385.328–387.507 | 3.505 | 0.1563 |
| LL08 | 132 | 187.407220 | 785.86 | 381.772–385.749 | 6.699 | 0.2508 |
| LL09 | 132 | 104.115122 | 1392.35 | 377.461–384.029 | 11.890 | 0.3551 |

The table rounds the recorded metrics for display; the linked receipts retain exact source values. These are discrete modeled points, not interpolation or selected-part limits.
Each normal run is a 650 ms cold-start simulation; its drift screen uses the
last three 60 Hz cycles, not an indefinite stable limit-cycle claim. The
controller is driven by prescribed nominal 15 V and 5 V rails, without a
physical auxiliary-supply droop model.

Normal electrical screens are fixed at input RMS current ≤15 A; settled bus
minimum, mean and maximum within370.13425–409.09575 V; three-cycle drift
<0.5%; VD≤500 V, VB≤450 V, |VDS|≤650 V and |VGS|≤25 V over the full trace;
and armed/enabled fractions≥0.99. Input RMS voltage must be107.999–132.001 V.
The energy residual `Pin − Pload − ΔE/Δt` must be at least
`−max(1 W, 0.005 × abs(Pin))`; it is not a thermal-loss qualification.
Normal inductor peak is report-only. These are the unchanged
[model screens](../numerical-repair/event-aware-normal-metrics/metrics.rs),
not validated part ratings. Fault checks additionally impose |IL|≤100 A,
with0.2 V gate-off and0.1 A channel-off thresholds, the declared event/turnoff/
observation windows, and separate all-row/retained-off checks; see
[the frozen fault checker](../faults/fault_checks.rs).

The [startup F2 receipt](../faults/startup-compact-analysis-23/acceptance.json)
passes its declared modeled screens for a startup-only case. Bank and diode
side peaks are about 127 V and 167 V, so it is not a settled 390 V test.
Channel current was already below 0.1 A before detection; the result does not
show causal interruption.

The [F2-CREST receipt](../faults/settled-reanalysis-40/F2-CREST38/acceptance.json)
and its [normal-prefix](../faults/settled-prefix-analysis-42/normal-prefix/acceptance.json)
and [phase43 acceptance](../faults/phase-audit-43/full-F2-CREST38/parent-phase-acceptance.json)
cover a complete 0.662 s trace. Its source-bound modeled screens pass, but
channel current was already below 0.1 A 2.819 µs before detection; passive
current reached 8.879 A after detection. Retained-off follows detection by106.6 ns, with7.772 ms of observation to the endpoint; that delay is not proof of causal interruption. Detection itself occurs61.228 µs after injection.

The [F2-ZERO receipt](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json)
likewise passes its own normal prefix and zero-phase all-choice bound. It
records channel current low 0.788 µs before detection and a 3.715 A passive
post-detector peak. Detection occurs1.267940 ms after injection, retained-off follows106.768 ns later, and observation continues22.399 ms to the endpoint. Its ideal F2 opening disconnects the bank branch without interrupting every source or energy path.

## Fault dispositions

| Case | Current disposition | What it establishes / excludes |
|---|---|---|
| F2-START | Accepted modeled screens | Startup sequence only; no settled-fault or fuse claim |
| F2-CREST | Accepted modeled screens | Exact scripted ideal-F2 case; no causal interruption or hardware claim |
| F2-ZERO | Accepted modeled screens | Exact zero-phase case; bank-only ideal-F2 behavior |
| SW-SHORT | **INDETERMINATE** | Solver stopped at 0.6544026486 s before 0.662 s; adapter/validator rejected endpoint. The [campaign verdict](../faults/settled-sw-short-59/full-SW-SHORT/campaign-verdict-86.json) assigns no protection-gap category. Its 256-row tail is diagnostic only. |
| DIODE-SHORT | **RUNNING** | Prepared terminal-graph experiment; no result yet and no package/die-current claim |
| BOTH-SHORT | **UNEXECUTED** | Prepared failed-short graph; no gate-interruption credit |
| BYPASS-NEG | **UNEXECUTED** | Prepared negative control with F2 open and detector bypass; frozen bypass rejection alone would not validate waveform behavior |

The SW-SHORT tail shows high q/en and ordinary PWM-low gate samples, not an
external latch witness. A fixed 180 µH model sample near 182 A is neither a
physical 182 A claim nor a component-survival result. The [tail review](../faults/sw-short-tail-parent-review-85.json)
and [strategy review](switch-short-strategy-review-83.md) preserve those
limits. No blind SW retry is promised.

## Model and prototype boundary

The [model-gap closeout](model-gap-closeout-12.md), [controller evidence](accepted-controller-test-binding-54.md),
and [clamp sensitivity review](../clamp/limiting-envelope-13/parent-review.json) identify
authored controller behavior, generic MOS/diode models, nominal passives,
unbounded selected-part clamp VF, and ideal F2 behavior. The authoritative
[inductor audit](inductor-manufacturer-audit-72/vendor-model-parent-review-73.md)
records a linear vendor subcircuit with fixed loss/parasitics but no
current-dependent inductance, saturation, temperature, or thermal law. The
selected-part datasheet
[review](inductor-manufacturer-audit-72/parent-disposition.md) separately records
43 A typical saturation and a24.5 A rating at40 K temperature rise;
neither is a guaranteed instantaneous limit. Whole-trace peaks must not be
called settled RMS or hardware current margins.

The selected-clamp temperature fixtures are sensitivity checks on the authored
leakage law: the [retained temperature report](../clamp/README.md) passes its1 µA/2 mV screens at −20/25 °C and
fails them at 85/125 °C. They are not a Vishay temperature envelope or a
production tolerance result. Those chosen loading screens are not TI requirements and do not qualify current limiting over temperature. The separate [saved ISENSE diagnostic](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.md) did not exercise PCL or a large clamp event. Controller-only PCL coverage is bound to the exact accepted include by the controller evidence above; its integrated fixture uses a different protection include and cannot qualify the full accepted power closure.

A future strategy needs an independent means of interrupting the source-fed
failed-switch path; F2 bank isolation alone cannot do that. Its actuation,
clearing and restart behavior must be specified for the actual voltage/current/
energy and AC or DC placement, with residual VD/VB energy handled separately.
This is a functional requirement, not a mandatory electronic detector/latch
architecture: an appropriately qualified passive device may serve it. The
[parent-reviewed strategy](switch-short-strategy-review-83.md) and
[hardware correlation specification](../checker/hardware-validation-spec.md)
identify observations of source/failed-branch current, VD/VB/bank paths and
q/en/gate. No real interrupting device, component qualification or schematic
ECO is completed here.

## Reproducibility and completion

Use the [reproducibility index](reproducibility-index-87.md), the source-bound receipts linked above, the [campaign evidence register](campaign-evidence-register-28.md),
the [SW verdict](../faults/settled-sw-short-59/full-SW-SHORT/campaign-verdict-86.json),
the [completion requirements review](completion-requirements-parent-review-86.json),
and the [SW tail review](../faults/sw-short-tail-parent-review-85.json). Preserve
raw/source/tool hashes and the event-aware policy for every remaining case.
The report becomes final only after DIODE-SHORT, BOTH-SHORT, and BYPASS-NEG are
independently dispositioned and the remaining model and prototype questions
are explicitly retained or closed.
