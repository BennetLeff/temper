# Late 501.55 ms timebase review (diagnostic only)

This folder records a source-bound review of the unchanged `normal-hysteretic-settling-extension` trace. It does not change the power-stage/controller model, relax a checker, deduplicate timestamps, or claim an accepted operating point. The extension changed only `TSTOP` from 500 ms to 650 ms; its electrical source receipt is `normal-hysteretic-settling-extension/execution.json`.

## Measured event

The strict export stopped at the first repeated accepted time after 500 ms:

| item | measured value |
|---|---:|
| previous/current time | 0.501554914485680681 s (identical f64) |
| previous/current callback indices (zero based) | 22,757,955 / 22,757,956 |
| prior positive `dt` | 1.1102230246251565e-16 s |
| local f64 ULP | 1.1102230246251565e-16 s |
| trace end after recovery | 0.501576349290274059 s |
| rows | 22,759,008 |

`first-invalid.tsv` and `crossing-excerpt.tsv` are copied from the completed export. The two same-time rows are not identical analog states: `xdriver.drv_delay` changes from `6.3142786e-10` V to `4.0188183e-8` V while the timestamp remains unchanged. Therefore the duplicate is a real repeated simulator callback/state update, not a decimal formatting collision.

At rows immediately before the duplicate, the source-bound state transition is visible:

* `pwm_input` rises through the 2.2 V input threshold (2.1999861 V, 2.1999876 V, 2.1999891 V, then 2.2000027 V).
* `xdriver.driver_req` changes from approximately 0 to 15 V between two adjacent one-ULP times.
* A second callback at the same representable time advances the 18.75 ns driver-delay state. The next callback advances by one ULP.

This pattern is consistent with a switch event being located at a time increment below the representable spacing. It is not evidence that the duplicate is harmless: it is the mechanism by which the solver loses strict time progress.

## Why this is a timebase symptom, not a standalone cause

IEEE-754 binary64 spacing doubles at each power-of-two boundary. The original hard-driver failure occurred at 0.256990362212805523 s with local ULP `5.5511151231257827e-17` s (`0x3fd07287b445d61f`); this extension failed at 0.501554914485680681 s with ULP `1.1102230246251565e-16` s (`0x3fe00cbce45ba681`). The absolute-time boundary is therefore a plausible amplifier: once adaptive retries request a sub-ULP step, the accepted time rounds back to the previous value.

It cannot by itself explain the electrical trigger. The unchanged candidate trace reached exactly 0.500 s with no repeated timestamp (`normal-hysteretic-driver-candidate/execution.json`: 22,686,813 rows, `first_invalid=false`), then produced the duplicate only after the PWM transition. The original hard `Bdriver_req` path duplicated much earlier at 0.256990 s. Time quantization is a necessary symptom of the failing edge search, not proof that the 0.5 s boundary is the root cause.

## Driver semantics implicated by the crossing

The candidate driver uses stateful native hysteresis (`SW_PWM_H`, `Vt=1.7`, `Vh=0.5`), so its nominal on threshold is 2.2 V and its off threshold is 1.2 V. The excerpt shows the state output jumping to 15 V while the instantaneous `pwm_input` is still 2.1999876 V. The accepted rows alone do not explain this slightly subthreshold transition: internal trial states and convergence tolerances are not recorded. It must not be declared expected hysteresis behavior without further evidence. The transition is followed by a same-time RC update, then advancing ULP steps. The original hard expression can reevaluate around 2.2 V during Newton/adaptive retries, but that remains a hypothesis about the earlier stall rather than a demonstrated cause.

The hysteretic candidate is a diagnostic improvement, not an accepted fix: it passes finite strict time through 500 ms but the unchanged bus-cycle checker rejects its measured 0.5763% late drift, and the 650 ms extension still repeats a timestamp at 501.55 ms. A physically defensible next model test is to retain the measured hysteresis and propagation state, then calibrate a finite source/sink slew/output pole against the checked UCC27511A behavior so the request transition is bounded in voltage and current. It must be rerun on the complete cold deck with strict timestamps and unchanged bus checks; no tolerance relaxation or timestamp deduplication is justified.

## Evidence and limits

Inputs are hashed in `input-sha256.txt`; `spacing.rs` prints binary64 bits and ULPs near the new failure time. `crossing-excerpt.tsv` contains the rows around the 501.55 ms state transition. The accidentally authored `switch-ramp.cir` is excluded from evidence: it requested 650 million 1 ns steps. Interrupting the delegated shell did not stop both ngspice children. The parent identified processes46225 and46316 by their exact fixture paths, sent TERM, and verified both absent with `ps`. No result or claim depends on that aborted fixture.

No standalone tiny fixture here proves that the native switch alone causes the failure. Different driver models failed at different times, and the retained waveforms implicate the threshold/state-transition path. These observations guide the next reproducer; they do not isolate a root cause or demonstrate a repair.
