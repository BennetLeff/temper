## Current milestone: baseline and four of nine grid points accepted

Accepted modeled650ms baseline120VAC/190ohm: `accepted-baseline-11/acceptance.json`.
LL01..LL04 have parent `acceptance.json` and `parent-evidence.json` in
`line-load-native-runner-12/full-LL0N-initialized/LL0N/`, under
`event-aware-normal-v1`. Original electrical screens unchanged, legacy strict
repeat-time rejections retained, all raw rows kept and individually audited.

| Case | Mains | Load output | Bus range | Input RMS | Full case wall |
| --- | --- | --- | --- | --- | --- |
| LL01 |108V|359.07W|385.68..387.72V|3.869A|2195.77s|
| LL02 |108V|705.40W|381.31..385.19V|7.510A|2147.68s|
| LL03 |108V|1242.52W|375.86..382.39V|13.412A|2114.95s|
| LL04 |120V|398.20W|385.20..387.44V|3.844A|2225.35s|

LL04:30,400,545rows,32equalgroups/44repeats, no backwards/logic/boundary
ambiguity, drift.001652792<.005. Parent raw/tool/source hashes verified;
`LL04-independent-review-19.md` supports acceptance. Peaks/current andresidual
are model outputs, not device/thermal qualification. LL04session58055complete0.

Live full solvers, maximum two:
- LL05 `line-load-native-runner-12/full-LL05-initialized/`, session49865,
 120VAC/R187.407220031ohm,650ms,3600wallcap. StartedafterLL04solverreleased.
- Compact F2-START `faults/startup-compact-candidate-20/`, session40304,
 75ms injection/89msendpoint/10mshealthyprefix,600wallcap, native supervisor19.
 Only the isolated960002-pointVschedule is replaced with3pointrepeatingPWL;
 electricalmodels, KLU, tolerances, saves, load andfaultwaveforms unchanged.
 `parent-preparation.json` verifies exactoneblockdiff tocase17.

Do not restart a live session solely for observation timeout. About16GiB free
beforecandidate20launch; keep10GiB reserve and allcanonical raw. No alternate
drive available; user mayfree space. Remainingcampaign storage needs reassessment
using actual compactfulltrace size. No wholetraceconversion/deletion authorized.

Fault history, not accepted protection:
- Originalstartup13:SPARSE aborted4.416873ms before75msfault; raw retained.
- KLU10ms/native42 probe `klu-native-16/parent-review.json`:142,428finite/strict
 rows,500nsmaxgap, identicalelectricalsource; permitsboundedinvestigationonly.
- KLUstartup17:600wallcap at76.358555915ms;3,749,174raw42rows retained/decoded0.
 Actualinjection74.999999504ms captured; only1.3586mspostmutation (<2ms required),
 so nofaultverdict. `parent-disposition.json` recordscompletepartialarchive.

Exactngspice45.2 source in `faults/pacer-cost-review-18/` shows largePWL source
andbreakpoint evaluation scanfromstart. PULSE PW0 substitutesTSTOP: notatriangle.
CompactPWL isolated89ms bench `compact-pacer-bench-18/parent-review.json` passed:
4,365,703finite/nondecreasingrows,960002uniqueexpectedcornersallpresent,
maxrequired65..89msgap12.859ns, triangleerror2.09e-10V. Parent independently
compiled/reran correctedchecker. This isisolatedinstrumentationproof only.

Native supervisor19 `faults/native-runner-19/parent-review.json` parentaccepted:
9tests; positivetrace gzipdrains beforesemanticwall-limitrejection, oldordering
regressionproved with2sdelayedfooter, receipt/hasherrorspropagate; evenonepositive
point drains. Currentbinary /private/tmp/matrix07-fault-native-supervisor19-parent.
SourceSHA571d449ed74eeddd6476f7ba2e0f32b9470334801d6917212f800c5eb0e6c7fb.
All other reviewednative42/adapter13/validator13/prefault14 tools retained.
Supervisor exit0 remainsreviewpending, neverfaultacceptance.

Luna fault_readiness owns new `faults/event-aware-validation-22/`: prepareonly
8million retained-row capacity (old13limit4million likelytoo small fordense
full89ms trace). Noengineering/time/eventcriteriachange. Await actualoldcap
failurebeforeadoption; ifneeded reanalyze SAMEraw innewreceipt, noresimulation.

`faults/compression-probe-21/` isbounded32MiBearly-prefix evidence: xz~20.5%
smaller thanpigz but~25xslowercompression; zstd~2.2%smaller. Allreportedroundtrips
match; parentreviewpending. No codec adoption fromunrepresentativeprefix alone.

`clamp/limiting-envelope-13/parent-review.json` bounds authored sensitivity;
original instantaneouspeaksUNVALIDATED afternumericalinflation; selectedVishay
ratings remainunqualified. RevAactualATO stillcommonhv_plus/noF2VDVBsplit;
gate-off cannotinterrupt failedshort; F2isolatesbank only, local/sourceenergyremain.

# Active simulation goal

Established at the user's request, 2026-09-20. Establish a defensible
simulation-supported operating envelope and protection strategy for the
approximately 390 V AC power-entry/PFC supply. The induction inverter is
outside this campaign. Hardware is unavailable.

## Completion evidence

1. A complete cold-start trace accepted by the unchanged endpoint, sampling,
   energy, regulation and stress screens plus the explicit versioned
   event-aware time policy in `accepted-baseline-11/acceptance.json`.
   The legacy strict-increasing-time rejection is retained, never relabelled
   as a pass; repeated rows require a case-specific observable audit.
2. All nine declared line/load points executed and dispositioned. Passing
   points and actual limits must be explicit; a failing point is investigated,
   not made green by widening its acceptance criteria.
3. The prepared fault cases exercised from accepted operating conditions,
   with remaining stress and actual current interruption assessed. Gate-off
   alone cannot pass a failed-short switch scenario.
4. Material component-model gaps resolved or bounded with identified primary
   evidence and clear limits. Missing guaranteed data remain named hardware
   questions, never an assumed passing rating.
5. Reproducible inputs, traces, checker results, minimum observed margins,
   schematic/prototype implications and remaining physical validation work
   consolidated into a host-reviewed report.

This is conditional simulation evidence, not hardware correlation, thermal
qualification, or safety certification. A numerical blockage is not electrical
acceptance and is not a reason to silently shrink the goal.

## Delegation and ownership

Luna handles bounded implementation, research and evidence preparation.
The host coordinates dependent work, independently verifies key outputs,
corrects defects, and alone accepts canonical changes and engineering results.

| Unit | Owner | Output / dependency |
|---|---|---|
| Baseline result and acceptance | Host | `normal-tracked/` rejected; full partial capture retained, no accepted normal point |
| First invalid-time capture | Luna implementation, host verified | `first-invalid-capture/run/`; complete capture reproduced first bad time, all sixteen internal signals present |
| Driver-boundary diagnosis | Luna `revb_plant` | `numerical-repair/driver-threshold-full-probe/`; bounded one-change experiment, no adoption |
| TI driver interface | Luna `revb_circuit` | `vendor-driver-integration/`; active PWM/disable/AUX tests before model adoption |
| Manufacturer-model clamp follow-up | Luna implementation, host independently verified | `clamp/vendor-model-followup/` and `clamp/vendor-model-host-check/`; temperature-dependent current-limit shift measured for alternate manufacturer's model, no part adoption |
| Nine-point materialization and bounded scheduler | Luna `matrix_runner` | `line-load-runner/`; execution gated on hash-bound accepted baseline |
| Fault-case readiness and missing instrumentation | Luna `fault_readiness` | `faults/readiness-08/`; execution gated on accepted initial conditions |

Use two concurrent full cases initially; only increase after measuring actual
memory, disk and completed-case throughput. Preserve experiment06 and all
earlier frozen evidence. No changes to unrelated working-tree files, production
PCB or firmware are authorized by this simulation goal alone.

The tracked run (tool session7460, compressor session23672) has finished.
Its first nonincreasing time is 0.256990362212805523 s; it ultimately froze
at 0.348534537976268155 s. Both the strict checker and inspector rejected it.
Read `normal-tracked/progress.tsv`, `stop.txt`, and execution logs for the
retained result. The diagnostic replay in `first-invalid-capture/run/` has
now finished: it reproduced that exact first bad time, captured the driver
input at its 2.2 V threshold, and stopped with 9,737,177 finite rows and one
nonincreasing interval. Its successful capture does not establish electrical
acceptance. The subsequent one-minute finite-driver-transfer probe reached
66.327 ms without meaningful speed improvement; it did not reach the original
failure and was not adopted. The TI driver interface passed independent
35-us PWM, RUN and AUX tests. Its full-plant candidate then aborted at
97.345625 ms after 292.260 wall seconds with a timestep-too-small error in
the vendor driver. All 4,353,208 exported rows are finite and strictly
increasing, but the unchanged normal checker rejects the truncated endpoint.
Luna's reduced driver tests did not reproduce that failure, including a late
edge near 97 ms under both integration methods. The host independently checked
both late traces. The full-cold Gear2 sensitivity run in
`normal-vendor-driver-candidate/gear2-sensitivity/` (producer97282,
compressor52463) has finished and also failed: 57.498293 ms after36.626 wall
seconds, with a timestep-too-small error naming `vac#branch`. All658,685
exported rows are finite/strict; the110 ms endpoint is incomplete. This
numerical-method change is not adopted. Its last PWM input is approximately
2.200001 V; the named source branch alone does not establish the root cause.
That run is complete; the newer active run is recorded below. Luna's explicit PWL fault-window
sampling fixture now passes the host-reviewed checker and five tests; its
sparse negative control fails the25 ns gap requirement. This is instrumentation
readiness, not executed fault evidence. No normal operating point has been
accepted. Do not infer progress from CPU
use. A future completed baseline export must
pass `gzip -cd trace.tsv.gz | /private/tmp/matrix07-normalize 190 |
/private/tmp/matrix07-checker --end-s 0.5` with pipeline failure propagation.
Update execution receipts and root evidence hashes after any final result.

## Current driver-model dependency

The full finite-transfer capture is prepared but deliberately unlaunched in
`numerical-repair/driver-threshold-full-probe/full-capture/`. The host verified
its electrical inputs, original first-invalid harness and unique executable.
The parallel fidelity check found a material omission: TI's model has nominal
2.2 V rising / 1.2 V falling input thresholds; the finite transfer has no
hysteresis. In the tested5 V/us input ramp, the loaded gate4 V falling
crossing differs by162.155 ns. This does not isolate hysteresis from the
different output/delay representations, and neither model is hardware-qualified.

Luna's source-derived hysteretic surrogate is now bench-checked in
`numerical-repair/driver-hysteresis-candidate/`. The host independently compiled
and ran the strict checker on slow/fast PWM, RUN/AUX, a late257 ms edge and
partial-rail threshold sweeps. The collapsed output remains an approximation:
tested fast gate4 falling time is37.5 ns later than the TI model, and AUX-drop
gate4 falling time is119.6 ns later. These are observed model differences,
not worst-case hardware bounds.

The full cold run in `normal-hysteretic-driver-candidate/` is COMPLETE.
Producer67830 and compressor53231 exited0. The independent inspector confirms
22,686,813 finite, strictly increasing rows ending at0.5s. The unchanged normal
checker rejects only bus cycle drift:0.005763 versus the0.005 limit. Its final
three cycle means are375.392,376.527,377.555V. All other reported screens pass.
This resolves numerical completion for this candidate, not settled-operation
acceptance. The raw gzip hash is dd20b2bb827a0fc876fa95f83fcb023e66e3207fcab854c13982e5ab3469d032.

A source-identical extension except TSTOP=650m is LIVE in
`normal-hysteretic-settling-extension/`: producer56946, compressor15482,
2700wall-second solverlimit. The measured late-cycle trend supports650ms
as a bounded margin; it does not supply a passing waveform. A full cold replay is required because no validated state
checkpoint exists. Do not relax the unchanged0.5% cycle-drift criterion.

Fault readiness now has a host-tested seven-case materializer and a minimally
extended streaming adapter (14tests) supporting armed F2-START and SW-SHORT.
Timing windows remain predeclared relative to injection. The proposed F2/VD/VB
split is absent from the current passive-revaATO; ideal-switch simulation does
not qualify fuse clearing. See `host/fault-preflight-09-review.md`.

## Late 501 ms extension failure

The 650 ms extension halted at its first repeated accepted timestamp,
0.501554914485680681 s, after about1492 wall seconds. Producer56946 and
compressor15482 both finished with exit0. The full inspector found22,759,008
finite rows and three nonincreasing intervals; the endpoint is501.576349ms.
Inspector and normal checker both rejected it. No accepted baseline;
the grid remains unlaunched. Diagnose in numerical-repair/late501ms-diagnosis/ and
numerical-repair/late501ms-timebase/. Do not deduplicate timestamps or relax
acceptance. The source-bound500 ms run remains numerically complete but
unsettled. The future reduced grid export is parent-reviewed in
line-load-normal-export/host-review.json. Staging support has passed parent
review and independent tests so actual first-two storage can be reviewed
before the remaining seven. See line-load-runner/host-staged-review.json.

## Latest live followups

Two source-bound650ms runs launched after parent review and complete1ms
smokes. Strict hybrid candidate: normal-vendor-comphys-native-candidate/,
producer22231/compressor87211, originalstrict host. Exact vendorCOMPHYS
input topology with two native-expression translations, originalauthored
output; logic aliases preserve protection Ben. Unchanged-circuit diagnostic:
numerical-repair/nonstopping-first-invalid/run/, producer30817/compressor83044.
It records duplicate timestamps but continues; backwards/nonfinite times and
original120s stall/wall guards still stop. It cannot supply an accepted baseline
under the unchangedchecker. Bothwalllimits2700s, target.65s, fulltrace/pigz-p4.
No more full runs while these are active. Waitbothproducer+compressorbefore
inspection/hashing; compareactual outcomes before model/policy decisions.
Seehost/parallel501-followups.json. Previous output-pole and verbatim-PS
fullcandidatefolders remain UNLAUNCHED. FaultFIFO runbook remains draft
until bounded child supervision is implemented/tested.

## Latest outcome: native COMPHYS candidate rejected

The strict native candidate is complete: producer22231 and compressor87211
exited0. Independent full inspection found11,176,288 finite rows and two
repeated-time intervals; first repeat259.732290783ms, last259.748700950ms.
It advanced16.41us after the first repeat before the strict host stopped.
This does not demonstrate a persistent stall. Both unchanged acceptance
checks rejected the trace. Retainedgzip1,962,876,932bytes, SHA256
49578ec2419cbf517bebc94a3b8c7527c7eb56099a4ed8b90ac55bb76e9bf41f.
The unchanged-circuit diagnostic30817/83044 remains running. No accepted
baseline and no full grid/fault campaign launched. Exact45.2 source audit,
bounded event diagnostics, and supervised fault-runner preparation continue.
The user has no other storage location and may free local space. Retain
canonical evidence, measure space before further launches, and keep10GiB free.

## Diagnostic passes the previous failure time

The unchanged-circuit diagnostic remains live (producer30817/compressor83044).
At1517.70wall seconds it had reached505.859483ms,77.82% of650ms, with three
equal-time callbacks and zero backwards callbacks. This reproduces the prior
three repeats and demonstrates continued progress beyond the old halt;
it does not grant endpoint, settling, or engineering acceptance. First-invalid
snapshot is written during final export, so its absence midrun is expected.

Parent independently verified exact45.2 archive bytes and489 numbered source
lines across7files after correcting a conflicting reconstructed excerpt.
TRANinit setsdelmin=1e-11*maxstep, i.e.5e-18s at500ns maxstep, below late-time
binary64 spacing. This is a possible mechanism, not measured failing-stepdelta.
New diagnostic event auditor passed6parenttests and full retained traces:
extension2equalgroups(2,3rows);nativecandidate1group(3rows). All groups were
followed bypositive time; all raw extrema remainincluded. Acceptanceunchanged.

Luna revb_circuit is preparing diagnostic-only final-three-cycle VB metrics
in numerical-repair/diagnostic-normal-metrics/. Luna matrix_runner is correcting
faults/runner-09 after parent found source-change verification and failure-path
gaps. Neither is adopted yet. Existing late-time minimal driver fixtures
finished under0.1s and didnotreproduce the full-plant repeats. Sourceaudit,
eventaudit, and minimalfixture completedchildren were interrupted after review.

## Current state: full 650 ms diagnostic complete

Both full followups have finished; the live snapshots above are historical.
The unchanged-circuit run reached 650 ms with 30,108,912 finite rows,
66 exact-equal intervals in 45 small groups, no backwards time, and positive
time following every group. The original strict checker rejects the trace.
Diagnostic final-cycle bus means are 382.8471, 383.3930, and 383.8926 V; their
range/first mean is 0.273086%, below the unchanged 0.5% settling threshold.
This is not a complete normal-operation acceptance result. No grid or full
fault cases have launched.

Next: quantify every equal-time group's saved-state change, assess numerical
metric ambiguity without discarding rows, and independently review a tiny
native-binary export experiment for storage savings. The exact-source audit
and existing complete/stalled traces can support this assessment; a separate
minimal duplicate reproducer is useful but not an invented prerequisite.
Fault supervisor parent tests and synthetic failure controls have passed;
this establishes transport handling only, not fault performance.

Retain all existing canonical evidence, keep a 10 GiB free-space floor, and
measure disk and memory capacity before any further full simulation. The
user has no alternate storage location and may free space locally.

## Latest bounded follow-up ownership

Exactngspice45.2 parent-reviewed source in `faults/pacer-cost-review-18/`
shows million-pointPWL evaluation andbreakpoint scheduling bothscanfromstart.
This explains a growing instrumentation cost; solecostnotproven. PULSE PW0
defaultsTSTOP andisnotatriangle. ThreepointPWL r=0/td isunderbenchmark.
Luna revb_plant owns `faults/compact-pacer-bench-18/`: isolated89ms source
run completed5.11s/4,365,703rows withzero25ns activegapviolations; parentcaught
checkerfirst-time/predelay/cornercomparisonbugs, correctedv2pending. Noadoptionyet.
Luna fault_readiness owns `faults/native-runner-19/`: ensurepositivepartialcapture
compressordrainsbeforesemanticmetadatarejection; independenttests/reviewpending.
Nevermodifylive/frozenrunner14inplace. LL04 remains onlyfullsolver.
