# Operating-matrix-07 simulation campaign report

**Status: INTERIM.** The modeled normal grid and three fault cases have
source-bound receipts, but the campaign is not complete. SW-SHORT is
indeterminate after an endpoint abort; DIODE-SHORT is running; BOTH-SHORT and
BYPASS-NEG remain unexecuted. Nothing here is a hardware, fuse, thermal, SOA,
safety, or production qualification.

## What is established

The accepted [normal baseline](../accepted-baseline-11/acceptance.json) and
[nine-point grid](operating-envelope-checkpoint-53.md) use the unchanged
event-aware policy: finite, nondecreasing complete rows; exact endpoint;
all-row electrical extrema; cycle drift; and equal-time predicate/integral
audits. The source is a 60 Hz model with resistive output loads; it is not an
induction-inverter or full-cooker model and does not establish a continuous
108–132 VAC or full-rated-power envelope. Tested modeled load powers are
approximately 359–1392 W. The legacy strictly-increasing checker remains visibly rejected on
repeated timestamps and is not used to discard rows.

| Point | Condition / Rload | Modeled result |
|---|---|---|
| LL01 | 108 VAC, 416.460 Ω (25%) | Accepted; 359.07 W, bus 385.68–387.72 V, 3.869 A RMS |
| LL02 | 108 VAC, 208.230 Ω (50%) | Accepted; 705.40 W, bus 381.31–385.19 V, 7.510 A RMS |
| LL03 | 108 VAC, 115.683 Ω (90%) | Accepted; 1242.52 W, bus 375.86–382.39 V, 13.412 A RMS |
| LL04 | 120 VAC, 374.814 Ω (25%) | Accepted; 398.20 W, bus 385.20–387.44 V, 3.844 A RMS |
| LL05 | 120 VAC, 187.407 Ω (50%) | Accepted retry; 880.54 W input, 783.85 W load, 7.420 A RMS, 0.2749% drift |
| LL06 | 120 VAC, 104.115 Ω (90%) | Accepted; 1383.936 W load, bus 376.244–382.998 V, 13.199 A RMS, 0.3873% drift |
| LL07 | 132 VAC, 374.814 Ω (25%) | Accepted; 398.384 W load, bus 385.328–387.507 V, 3.505 A RMS |
| LL08 | 132 VAC, 187.407 Ω (50%) | Accepted retry; 872.226 W input, 785.859 W load, 6.699 A RMS, 0.2508% drift |
| LL09 | 132 VAC, 104.115 Ω (90%) | Accepted; 1559.826 W input, 1392.350 W load, bus 377.461–384.029 V, 11.890 A RMS, 0.3551% drift |

These are exact modeled points, not interpolation or selected-part limits.
Each normal run is a 650 ms cold-start simulation; its drift screen uses the
last three 60 Hz cycles, not an indefinite stable limit-cycle claim. The
controller is driven by prescribed nominal 15 V and 5 V rails, without a
physical auxiliary-supply droop model.

The [startup F2 receipt](../faults/startup-compact-analysis-23/acceptance.json)
passes its declared modeled screens for a startup-only case. Bank and diode
side peaks are about 127 V and 167 V, so it is not a settled 390 V test.
Channel current was already below 0.1 A before detection; the result does not
show causal interruption.

The [F2-CREST receipt](../faults/settled-reanalysis-40/F2-CREST38/acceptance.json)
and its [normal-prefix](../settled-prefix-analysis-42/normal-prefix/acceptance.json)
and [phase43 acceptance](../phase-audit-43/full-F2-CREST38/parent-phase-acceptance.json)
cover a complete 0.662 s trace. Its source-bound modeled screens pass, but
channel current was already below 0.1 A 2.819 µs before detection; passive
current reached 8.879 A after detection. The 106.6 ns retained-off interval
is therefore not proof of causal interruption.

The [F2-ZERO receipt](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json)
likewise passes its own normal prefix and zero-phase all-choice bound. It
records channel current low 0.788 µs before detection and a 3.715 A passive
post-detector peak. Its ideal F2 opening isolates modeled bank energy only.

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
and [clamp reviews](../clamp/limiting-envelope-13/parent-review.json) identify
authored controller behavior, generic MOS/diode models, nominal passives,
unbounded selected-part clamp VF, and ideal F2 behavior. The authoritative
[inductor audit](inductor-manufacturer-audit-72/vendor-model-parent-review-73.md)
records a linear vendor subcircuit with fixed loss/parasitics but no
current-dependent inductance, saturation, temperature, or thermal law. Its
43 A saturation value is typical and its 24.5 A figure is a 40 K-rise rating;
neither is a guaranteed instantaneous limit. Whole-trace peaks must not be
called settled RMS or hardware current margins.

The selected-clamp temperature fixtures are sensitivity checks on the authored
leakage law: the retained report passes its 1 µA/2 mV screens at −20/25 °C and
fails them at 85/125 °C. They are not a Vishay temperature envelope or a
production tolerance result. PCL, thermal, and state-of-charge behavior remain
model-only questions.

A future interruption strategy must detect a failed channel independently of
PWM-low samples, interrupt a gate-independent mains-fed failed path, and
isolate/discharge the VD/VB stored-energy path with DC-clearing and no-restrike
evidence. Prototype work must instrument both F2 terminals/current, VD, VB,
source and failed-branch current, and q/en/gate transitions. A qualified
passive interrupter could satisfy the function; no real protection part is
selected here.

## Reproducibility and completion

Use the source-bound receipts linked above, the [campaign evidence register](campaign-evidence-register-28.md),
the [SW verdict](../faults/settled-sw-short-59/full-SW-SHORT/campaign-verdict-86.json),
the [completion requirements review](completion-requirements-parent-review-86.json),
and the [SW tail review](../faults/sw-short-tail-parent-review-85.json). Preserve
raw/source/tool hashes and the event-aware policy for every remaining case.
The report becomes final only after DIODE-SHORT, BOTH-SHORT, and BYPASS-NEG are
independently dispositioned and the remaining model and prototype questions
are explicitly retained or closed.
