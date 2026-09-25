# Timestamp-validity audit: repeated ngspice callback times

This is a read-only review of the existing full-cold traces. It does not alter the checker, delete rows, relax solver tolerances, or claim a passing circuit. The narrow question is whether a strict `dt > 0` requirement for every serialized data callback is a circuit-validity law or a conservative acceptance policy.

## Primary ngspice contract evidence

The official ngspice 45 manual (the 45.2 source release is documented as a bug-fix release) says that `SendData` is called each time a new data point is added to the current plot and that `vecvaluesall.vecindex` is “the number of accepted data points” (manual pp. 495–496 and 506–507):
`https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf`.

The release-45.2 source tarball is the project’s tagged source (`ngspice-45.2.tar.gz`):
`https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/45.2/ngspice-45.2.tar.gz/download`.
The exact source was fetched and SHA-256 verified locally: `ba8345f4c3774714c10f33d7da850d361cec7d14b3a295d0dc9fd96f7423812d`. Short line-numbered excerpts and per-file hashes are in `source-45.2-excerpt.txt` and `source-45.2-sha256.txt`; the exact archive is `/private/tmp/ngspice-45.2.tar.gz` and was extracted under `/private/tmp/ngspice-45.2-src/`. The public source mirror exposes the corresponding functions: [`dctran.c`](https://github.com/ngspice/ngspice/blob/master/src/spicelib/analysis/dctran.c) and [`sharedspice.c`](https://github.com/ngspice/ngspice/blob/master/src/sharedspice.c). The exact tarball is the version authority.

The source sequence is decisive about what the callback means, but not about strict monotonicity:

* Exact 45.2 `dctran.c` lines 402–420 call `CKTaccept(ckt)`; the normal analog output path calls `CKTdump(ckt, ckt->CKTtime, ...)` at lines 484–486. `cktdump.c` then passes that accepted time and state to `SPfrontEnd->OUTpData` (lines 32–44), and `outitf.c` invokes `sh_ExecutePerLoop()` only under `#elif defined SHARED_MODULE` (lines 65–71 and 779–789). Thus the source-bound dump-to-callback chain is `CKTaccept -> CKTdump -> OUTpData -> sh_ExecutePerLoop`; the excerpt does not show any monotonic-time filter between those calls. Lines 578–607 are the non-XSPICE breakpoint path; they clamp ordinary deltas and set a breakpoint delta by subtraction, with no explicit `next_time > current_time` guard. The XSPICE path used by this installed shared library is at lines 612–700: it also sets breakpoints by `current - CKTtime` and only requires event breakpoints to exceed `CKTtime + CKTminBreak`. Lines 752 and 815 advance `ckt->CKTtime += ckt->CKTdelta` and divide `CKTdelta` by 8 on non-convergence; lines 982–987 stop only when the adaptive delta reaches `CKTdelmin` twice. A sufficiently small positive delta can round the sum back to the same binary64 time (generally below half an ULP in round-to-nearest arithmetic). This is a mechanism consistent with the trace, not proof of the internal delta on its failing step.
* Exact 45.2 `sharedspice.c::sh_ExecutePerLoop()` lines 2255–2288 read the last output-vector entry and call `datfcn(...)`; exact `sharedspice.h` lines 195–196 define `vecindex` as the accepted-point index. Neither the header nor the manual promises that successive callback `time` values are strictly increasing, and neither inserts a monotonicity filter.
* The manual’s shared-library transient sequence explicitly places SendData after “send simulation data to output” and before the next-step loop, then describes adding `cktdelta`, retrying on non-convergence, and dividing the step. That supports interpreting a finite same-time pair as two accepted output records after a rounded-to-zero step. The distinction between an isolated pair and a long no-progress run is an engineering diagnostic inference from these traces, not a promise in the ngspice API.

The exact source initializes the first transient delta as `min(finalTime/100, CKTstep)/10` (lines 133–135). The full 45.2 source also shows where the minimum step comes from: `CKTdoJob` first copies `task->TSKdelmin` into `ckt->CKTdelmin` (cktdojob.c lines 50–76), then `TRANinit` overwrites it with `1e-11 * CKTmaxStep` (traninit.c lines 17–39). Therefore `CKTdelmin` is not derived from `finalTime` in `dctran.c`; its transient value is tied to the computed `CKTmaxStep` (which may itself default from the stop/start interval). For the current 500 ns maximum-step deck, this source rule gives `CKTdelmin = 5e-18 s`; that is below the approximately `1.11e-16 s` binary64 ULP at 0.5 s. This is a representability bound, not evidence that the failing event requested exactly `5e-18 s`. With XSPICE, `CKTminBreak` defaults to `10*CKTdelmin` (dctran.c lines 167–174), while the non-XSPICE fallback is `CKTmaxStep*5e-5`. The shared synchronization helper receives `delmin` and can subtract `1.1*delmin` when clamping against final time (sharedspice.c lines 2428–2481); its `!wantsync` branch simply returns on a converged step, while a redo subtracts the old delta and returns a retry request (lines 2446–2454). The installed shared run logs report “Reducing trtol to 1 for xspice 'A' devices”, and the Homebrew `libngspice` 45.2 package contains XSPICE code-model strings, so the XSPICE breakpoint path—not the `#ifndef XSPICE` branch—is the relevant compiled configuration evidence here.

These references are primary project documentation/source, not a claim inferred from this project’s checker. The GitHub links are the public current mirror; the release-45.2 tarball is the exact-version anchor.

## What the traces establish

The callback harness (`normal-hysteretic-driver-candidate/progress.rs`) receives one `Values` packet, extracts the scalar `time`, and applies `current <= previous` as its first-invalid diagnostic. That comparison is a harness rule; it is not an assertion obtained from an ngspice API contract. The callback also copies analog vectors at the repeated time, so the rows are not merely duplicate text.

The 650 ms hysteretic-driver extension first repeated time at0.501554914485680681s (zero-based callback indices22,757,955/22,757,956). Its first repeated pair is in `normal-hysteretic-settling-extension/first-invalid.tsv` and the surrounding rows are in `normal-hysteretic-settling-extension/tail.tsv`. At the repeated time, `xdriver.drv_delay` changed from `6.3142786e-10` to `4.0188183e-8` V (about 39.6 nV), while `pwm_input` was 2.1999891 V and `xdriver.driver_req` was 15 V. The next callback advanced by one binary64 ULP. The producer then advanced to 0.501576349290274059 s, about 21.4 us beyond the first repeat, before the watchdog/export halt. Parent inspection counted only three non-increasing intervals among22,759,008rows.

The original hard-driver run is materially different: it produced 1,126,438 non-increasing intervals and stopped advancing at 0.34853453797626816 s after the first repeat at 0.256990362212805523 s. The large persistent run of repeats is a numerical stall, not an isolated event callback. Both traces are retained and rejected by the strict acceptance path; no validity conclusion is inferred from ngspice returning process exit 0.

## Adverse review of the strict guard

A strict positive timestamp check is a sound conservative *acceptance gate* for this project: it makes the exported trace unambiguous for derivative/integral metrics and catches the original hard-driver stall. It is not sufficient evidence that every same-time callback is physically invalid. The documented source path calls `SendData` for each accepted output point; if `CKTtime += CKTdelta` rounds back to the same binary64 value, more than one accepted record can therefore carry the same serialized time. That is a representable numerical outcome, not proof that the corresponding zero-duration circuit update is physically meaningful. A zero-duration state update has no elapsed-time contribution to an integral, but it can change a switch state and must remain available for stress maxima and event ordering.

The current extension is the adverse case for an unconditional rule. The repeated rows have tiny analog changes below the deck's `vntol=1e-7` (the driver-delay change is approximately `4e-8` V), then time resumes by one ULP and later by ordinary positive steps. Treating that one event as an automatic circuit failure is conservative, but it conflates a representable-time collision with the 1.1-million-row stall seen in the original run. Conversely, simply dropping or deduplicating the row would hide a real state update and would invalidate event-sensitive stress metrics.

The correct distinction is therefore between **non-decreasing callback time with finite vectors** and **forward-progress health**:

* Preserve every serialized row and reject non-finite values.
* Permit a bounded same-time event group only in a diagnostic classifier; integrate energy over positive `dt` segments, give `dt=0` segments zero measure, and still include all rows in peak/stress scans.
* Require eventual positive progress after each group, with an explicit bound on duplicate count, wall time, and simulated-time advance. A short group followed by 21 us of progress is a different verdict from 1,126,438 repeats with no meaningful advance.
* Keep the existing `dt > 0` checker for qualification until a source-bound callback contract and event-state proof are established. A relaxed diagnostic must never be substituted for the acceptance result.

This split preserves the safety property that motivated the strict guard while avoiding an unsupported claim that the ngspice callback interface promises strictly increasing times for all ideal-source/switch events.

## What would justify redesigning the guard

A redesign needs primary evidence from the exact ngspice shared-library callback path, not a tolerance tweak: (1) a minimal, bounded event deck that produces a finite same-time callback and then advances; (2) a second deck with the same callback pattern but a true no-progress stall; and (3) an independent check that ngspice's callback packet represents accepted output points versus event/interpolation notifications. The full cold trace should then be classified by the same bounded-progress rule without changing electrical parameters. Until those three pieces exist, strict positive `dt` remains the appropriate release gate, while the bounded non-decreasing classifier is the appropriate diagnostic view.

The binary64 spacing explains why the repeats are exposed at these absolute times but does not make them valid or invalid by itself: the original event is at 0.25699 s (ULP `5.55e-17` s) and the extension event is at 0.50155 s (ULP `1.11e-16` s). Solver retries that request a sub-ULP step can serialize the same representable time. That is a numerical symptom; circuit validity depends on whether the solver subsequently makes bounded forward progress and whether the event-state update is physically represented.

## Source-bound evidence

* `normal-hysteretic-driver-candidate/progress.rs`: callback extraction and `current <= previous` diagnostic rule.
* `normal-hysteretic-settling-extension/execution.json`, `first-invalid.tsv`, `tail.tsv`: 501.55 ms event, 22.76 M rows, three repeats, and subsequent progress.
* `normal-tracked/execution.json`, `numerical-repair/first-time-spacing/excerpt.tsv`: original 256.99 ms event and persistent stall.
* `normal-tracked/cold.cir`: `method=trap`, `reltol=2e-4`, `abstol=1e-10`, `vntol=1e-7`, which bounds the interpretation of sub-tolerance analog changes.

This review recommends no checker change in the current acceptance run and no deletion of same-time rows. It recommends reporting both the strict result and a separate bounded-progress diagnostic until the callback semantics are directly verified.
