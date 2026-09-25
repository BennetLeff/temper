# Campaign evidence register (interim)

## Current checkpoint68 — F2-ZERO accepted, switch-short running

[F2-ZERO51 acceptance](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json)
(SHA-256 `42c3bac2b9cad3051268fa6c2be59581d2bd2dfb03c0b9bc6574ef1e4276b760`)
binds the complete36,625,031-row archive, its own accepted normal prefix,
1% all-choice zero-phase bound and recovered electrical validation. Detection
occurs1.267940ms after injection; retained gate-off follows106.768ns later.
Channel current is already below0.1A0.788us before detection, while passive
current reaches3.714564A after detection. This demonstrates modeled screens,
not causal current interruption or physical fuse performance. The original
stage2 header failure remains unexplained and preserved; independent complete
reanalysis passed with the same frozen decoder, adapter and validator.

All nine normal points, startup F2, F2-CREST and F2-ZERO have exact modeled
receipts. Four settled cases await disposition: SW-SHORT is running under
session76829; DIODE-SHORT64, BOTH-SHORT65 and BYPASS-NEG66 are prepared and
parent reviewed. BYPASS opens F2 with its detector disabled; the diode/both-short
decks instead keep F2 closed. The selected-component and hardware limitations
below remain. The goal is not complete.

User-freed storage cleared the capacity block. About45GiB is free at this
checkpoint, with16GiB launch and10GiB runtime gates unchanged. Google Drive has
a byte-verified small baseline acceptance backup; large waveform transfer and
restore remain unverified. All local and failed evidence is preserved.

Status: **interim; not goal-complete**. This register records what the current
receipts establish for the simulation-only campaign. It does not promote an
unrun case, a failed transport, or an authored/typical model into a pass.
There is no hardware available; nothing here is thermal, SOA, fuse, safety, or
production qualification.

Authoritative starting points are the [active goal](../GOAL.md),
[normal baseline receipt](../accepted-baseline-11/acceptance.json), the parent-reviewed grid receipts,
[accepted LL09 receipt](../line-load-direct-retry-47/full-LL09/LL09/acceptance.json),
[startup fault receipt](../faults/startup-compact-analysis-23/acceptance.json),
[settled-case preparation review](../faults/settled-compact-prep-24/parent-review.json),
[saved-pin observation review](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.json),
[model gaps](model-gap-closeout-12.md), [clamp review](../clamp/limiting-envelope-13/parent-review.json),
and [prototype implications](simulation-to-prototype-decisions.md).

## Completion requirements

| Requirement | Authoritative evidence | Establishes | Does not establish / remaining |
|---|---|---|---|
| 1. Complete cold-start normal baseline under unchanged screens and versioned event-time policy | accepted-baseline-11/acceptance.json; accepted-baseline-11/README.md | Exact 120 VAC / 190 ohm / 650 ms source-hashed model passes finite, endpoint, electrical, current/power/bus/drift, and equal-time observable audit. 30,108,912 rows; 66 equal intervals in 45 groups; no backwards/nonfinite rows. | Legacy strict-increasing checker remains REJECTED_NONINCREASING_TIME. This is one modeled case only; no hardware or total-energy qualification. |
| 2. Execute and disposition all nine line/load points | LL01–LL08 acceptance/parent-evidence receipts; [LL09 acceptance](../line-load-direct-retry-47/full-LL09/LL09/acceptance.json) (SHA-256 `30ce810b146331f8db0cf0e2c0a1bc22032062d529773039dd62aeeaa5075737`); `line-load-direct-retry-47/` launch packet; host/direct-native-export-parent-37/parent-review.json | LL01–LL09 now have source-bound modeled normal receipts under event-aware-normal-v1. LL09 is a complete 132 VAC RMS / 104.115122239 ohm case with 30,141,001 rows, all screens zero, and event-aware audit/metrics. Direct export removed the selected-vector copy and passed 21 unit tests plus 99,366 stopped-plot bitwise comparisons. | These are exact source-bound modeled cases only; no extrapolation to hardware, fuse, thermal, SOA, protection, or total-energy qualification. |
| 3. Exercise prepared faults from accepted conditions and assess interruption/stress | faults/startup-compact-analysis-23/acceptance.json; faults/settled-compact-prep-24/parent-review.json; faults/fault-matrix.md; `faults/settled-reanalysis-40/F2-CREST38/acceptance.json` | F2-START has an exact startup modeled-screen receipt. Six settled decks are source-checked and mechanically prepared. F2-CREST38 now has a complete source-bound exact modeled-screen acceptance; its 32,237,324-row trace, accepted healthy prefix, corrected global/local gap contract, and phase43 all-choice 1% crest bound are parent-receipted. | The F2-CREST result is a scripted ideal-F2 modeled case, not a physical interruption or fuse qualification. Injection-to-detector is 61.228 us; retained-off is 106.628 ns after detection, but channel current was already below 0.1 A 2.819 us before detection and passive current remains 8.879 A. The original phase35 and wrong-global-gap stage38 rejections remain preserved as historical evidence; F2-ZERO is also accepted; four settled cases await disposition (see checkpoint68). F2-START is startup, not settled 390 V: VB peak 127.054 V, VD 167.183 V; channel current was already <0.1 A about 596 ns before detector. |
| 4. Resolve or bound material component-model gaps | host/model-gap-closeout-12.md; clamp/limiting-envelope-13/{README.md,parent-review.json} | Missing evidence is named; clamp fixture quantifies sensitivity of ISENSE loading/energy to declared VF laws and diagnoses loose-tolerance peak inflation. | It does not qualify selected parts or convert typical curves/assumed SPICE into limits. Selected diode low-current temperature VF, controller silicon behavior, device SOA/losses, and F2 DC clearing remain open. |
| 5. Consolidate reproducible inputs, traces, screens, margins, prototype implications | This register; host/simulation-to-prototype-decisions.md; host/simulation-to-prototype-parent-review-14.json; source-bound receipts above | Current evidence, boundaries, and next gates are traceable; parent review confirms the interim decision aid. | The campaign report cannot be final until the four remaining settled faults and remaining model/hardware questions are dispositioned explicitly. |

## Nine-point normal grid

The declared points are in line-load-prep/manifest.json; their target loads
are planning values, not results. The nominal 120 VAC / 190 ohm baseline is a
reference case, not one of LL01–LL09.

| Point | Declared condition | Current status | Evidence / next action |
|---|---|---|---|
| LL01 | 108 VAC, 25%, 416.460 ohm | **ACCEPTED modeled** | 359.07 W; bus 385.68–387.72 V; input RMS 3.869 A. Receipt + parent evidence retained. |
| LL02 | 108 VAC, 50%, 208.230 ohm | **ACCEPTED modeled** | 705.40 W; bus 381.31–385.19 V; input RMS 7.510 A. Receipt + parent evidence retained. |
| LL03 | 108 VAC, 90%, 115.683 ohm | **ACCEPTED modeled** | 1242.52 W; bus 375.86–382.39 V; input RMS 13.412 A. Receipt + parent evidence retained. |
| LL04 | 120 VAC, 25%, 374.814 ohm | **ACCEPTED modeled** | 398.20 W; bus 385.20–387.44 V; input RMS 3.844 A; 30,400,545 rows; event audit/drift pass. |
| LL05 | 120 VAC, 50%, 187.407 ohm | **ACCEPTED modeled** | Retry receipt: 880.54 W input, 783.85 W load, bus 381.21–385.35 V, input RMS 7.420 A, drift 0.2749%, 30,103,973 rows; all screens 0 and event audit pass. Initial bad archive remains rejected and retained. |
| LL06 | 120 VAC, 90%, 104.115 ohm | **ACCEPTED modeled** | 1383.936 W load; bus 376.244–382.998 V; input RMS 13.198676 A; drift 0.3873%; 29,845,886 rows; all screens 0 and event audit pass. |
| LL07 | 132 VAC, 25%, 374.814 ohm | **ACCEPTED modeled** | 398.384 W load; bus 385.328–387.507 V; input RMS 3.505044 A; drift 0.1563%; 30,812,694 rows; all screens 0 and event audit pass. |
| LL08 | 132 VAC, 50%, 187.407 ohm | **ACCEPTED modeled** | Direct retry receipt `line-load-direct-retry-41/full-LL08/LL08/acceptance.json` (SHA-256 `8c6f8fb701395ecb95cbdfd980fc9a2f94ca1417a456542a18d39e460c3e8fdd`): 872.226 W input, 785.859 W load, bus 381.772–385.749 V, input RMS 6.698508 A, drift 0.2508%, 30,447,163 rows; all screens 0 and event audit pass. Prior session50666 failure artifact remains preserved. |
| LL09 | 132 VAC, 90%, 104.115 ohm | **ACCEPTED modeled** | [Acceptance receipt](../line-load-direct-retry-47/full-LL09/LL09/acceptance.json), SHA-256 `30ce810b146331f8db0cf0e2c0a1bc22032062d529773039dd62aeeaa5075737`: 1,559.826 W input, 1,392.350 W load, bus 377.461–384.029 V, input RMS 11.889830 A, drift 0.3551%, 30,141,001 rows; all screens 0 and event audit pass. |

LL05's 4 GB FIFO probe (faults/host/fifo-export-probe-26/parent-review.json)
proves only that one synthetic stream can round-trip through the transport. It
did not reproduce the initial failure and its probe harness was not adopted.
Runner-27's transport was parent-adopted for the retry; its 20 us native
comparison was byte-identical and decoded 316 normal15 rows, and the full LL05
retry now has a parent-verified acceptance receipt. Fault runner-29 now has a
parent-reviewed bounded transport receipt (faults/native-runner-29/parent-review.json):
all 12 tests passed, but no settled fault capture is accepted. Successor
runner45 is also parent-reviewed (faults/native-runner-45/parent-review.json):
12 default tests and one separately approved inherited-file-descriptor test
passed, but it has no full-case runtime and is not an acceptance receipt.

The failed F2-CREST32 and prior LL08 raw artifacts remain preserved. The LL08
direct-export resource receipt records minimum free space 12.53356 GiB,
maximum owned RSS sum 3.79431 GiB, no increase in system swap, 29.933 s export,
and 2,288.238 s full-case wall time. Five-second samples do not bound
instantaneous peaks, and the receipt does not establish a before/after memory
reduction. LL09's corrected parent resource summary records 422 samples, a
minimum free space of 10.451938629 GiB, maximum owned RSS sum 4.07556 GiB,
and host-wide swap observations; these are observations, not capacity
guarantees. The corrected parent summary supersedes the stale 419-sample/Luna
snapshot. Those resource values describe earlier runs. The user has since
freed space: about45GiB is available at checkpoint68, and SW-SHORT59 has launched
with the unchanged16GiB gate and10GiB runtime floor. Large Drive archive backups
remain unverified; do not delete canonical evidence.

## Seven fault cases

faults/fault-matrix.json defines the seven cases and required result states
(PASS, FAIL, PROTECTION_GAP, INDETERMINATE, UNEXECUTED). Every settled case must
first prove its own contiguous accepted 650 ms normal prefix, actual source
phase, finite complete trace, unchanged node/gap limits, detector/latch
behavior, and separate channel versus passive current.

| Case | Status | What is established / what remains |
|---|---|---|
| F2-CREST | **ACCEPTED exact modeled screens; physical review remains limited** | F2-CREST38 acceptance is `faults/settled-reanalysis-40/F2-CREST38/acceptance.json` (SHA-256 `bc00f63b08b5218d74f7fa673e60ab6f976194d32a871c776432547130ccfa7e`) over the unchanged 32,237,324-row raw trace. It binds the accepted healthy prefix, corrected global 1 us / frozen local 25 ns contract, phase43's three successful pipeline stages and unchanged 1% all-choice crest bound. This is one exact source-bound scripted ideal-F2 modeled case, not physical interruption or fuse qualification. Injection-to-detector is 61.228 us; retained-off is 106.628 ns after detection, but channel current was already below 0.1 A 2.819 us before detection and passive current remains 8.879 A. Original phase35 and wrong-global-gap stage38 rejections are retained historically. F2-ZERO is accepted; four settled cases await disposition. |
| F2-ZERO | **ACCEPTED exact modeled screens** | [Acceptance](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json), complete36,625,031-row archive, own normal prefix and zero-phase bound. Detection1.268ms; retained-off106.768ns; channel alreadylow0.788us beforedetector; passivepeak3.715A remains. Initial pipeline failure and legacy rejection retained. |
| F2-START | **ACCEPTED exact startup modeled screens** | 89 ms capture, 6,025,180 rows, frozen checker pass, 10 ms healthy prefault, 13.085 ms retained-off observation. Startup VB peak 127.054 V and VD 167.183 V; current was already low before detection. No settled-390 V shutdown or fuse claim. |
| SW-SHORT | **RUNNING; no verdict** | Reviewed59 launch passed source/tool/disk/single-solver gates; session76829. Failed-short channel remains a protection-gap experiment; gate-low alone cannot prove interruption. |
| DIODE-SHORT | **PREPARED, UNEXECUTED; terminal topology reviewed** | [Branch-model review](../faults/branch-model-review-13-parent.json) permits the terminal-short experiment, with no package/die claim. Healthy switch may interrupt only its own path; full waveform checks remain pending. |
| BOTH-SHORT | **PREPARED, UNEXECUTED** | Distinct failed-short + diode-short graph; no gate interruption credit. Requires settled-prefix run and current split. |
| BYPASS-NEG | **PREPARED, UNEXECUTED** | Negative control. Validator must reject bypassed protection; a clean simulator exit is not a pass. |

The [parent preparation receipt](../faults/settled-compact-prep-24/parent-review.json)
is PARENT_REVIEWED_PREPARED_CANDIDATES_UNEXECUTED; the individual manifests
remain prepared candidates. F2-CREST now has an exact source-bound modeled-screen
acceptance, but no physical interruption or hardware qualification. F2-START's
acceptance is limited to its exact scripted startup model.

## Model and prototype boundaries

- **Selected Vishay BAV23C-E3-08:** retained PDF clamp/datasheet-audit/bav23c.pdf (Vishay document 86374) guarantees high-current VF maxima and ratings at printed conditions, but does not provide a guaranteed low-current VF(min)/VF(max) envelope over -40 to +125 °C. Page-3 forward-current plot is typical. The 1 uA diode-current and 2 mV ISENSE-shift values are engineering screens, not TI/Vishay requirements. clamp/limiting-envelope-13 is an authored limiting-law sensitivity, not part qualification.
- **UCC28180D:** TI datasheet requirement and reference values are retained in clamp/datasheet-audit/report.md; the accepted controller is an authored functional surrogate. No usable open vendor transient model has been adopted here.
- **Saved ISENSE observation:** The parent-reviewed diagnostic on exact F2-CREST38 reports the saved pin over -0.306538 to +0.000116321 V. No absolute-voltage sample exceeded the cited TI limits, but 1,241,371 rows were above the strict recommended 0 V comparison. Both modeled PCL request and hold stayed zero, so this case does not exercise PCL or a large clamp excursion. The observation is not a silicon, selected-Vishay, input-current, or hardware qualification; see [`parent-observability-review.md`](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.md) and its [`JSON receipt`](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.json).
- **Power devices and F2:** generic/assumed MOSFET/diode models and an ideal scripted F2 switch do not establish losses, SOA, DC clearing, arc/restrike, I²t, or interruption. Rev A has no physical F2/VD/VB split; that is a proposed topology ECO, not a board fact.
- **Prototype work still required:** exact F2 DC-discharge/clearing data and bench instrumentation of F2 terminals/current, VD/VB, MOS/diode currents, gate, and F1/source path; then UVLO/restart and hot I/V/parasitic correlation. These are outside the simulation-only receipts.

This register is intentionally a checkpoint. It should be updated only when a
new source-bound receipt is parent-reviewed; it does not change the circuit,
checker rules, acceptance thresholds, or hardware status.

## Readiness and model-audit supplement54–55

The exact accepted controller source is bound to retained nominal small-fixture
receipts in [controller binding54](accepted-controller-test-binding-54.md).
The [threshold review54](controller-corner-coverage-54.md) limits the ideal15V
auxiliary-supply conclusion to source-defined voltage margins. The exact ST
MOSFET model is [listed but not retrieved here](stw65n65dm2ag-vendor-54/availability.md);
no model substitution or fidelity claim follows. Selected clamp VF remains open.

The [terminal-branch gate55](../faults/terminal-branch-gate-55.md) permits the
prepared diode/both-short cases only as terminal-graph experiments after their
own startup prefix and runtime gates. F2 stays closed in those exact decks.
The frozen failed-short message's "after latch" measurement actually starts
at the detector edge; a latch witness cannot be inferred from that wording.

The [bypass diagnostic55](../faults/bypass-observability-55/README.md) is parent
reviewed with7 unit tests and15 independent CLI cases. It reports sampled
q/en/gate/current behavior independently of the detector and never accepts a
circuit. No full archive was scanned and no additional fault was simulated.
The [second capacity-gate attempt](../faults/settled-direct-capture-51/gate-attempt-55.json)
again stopped before launching a solver. Nine normal points remain accepted;
five settled faults remained at historical checkpoint55. Checkpoint68 above supersedes that storage/status observation: F2-ZERO is accepted and storage is sufficient for the current launch.

## Selected-inductor evidence — checkpoint73

The exact-part [manufacturer/model audit](inductor-manufacturer-audit-72/parent-disposition.md)
clarifies an existing limitation. The selected inductor's43A saturation figure
is typical; its24.5A current rating has a40K thermal-rise condition. The normal
trace peaks alone cannot prove a thermal violation or a guaranteed saturation
margin. The [retrieved official model](inductor-manufacturer-audit-72/vendor-model-parent-review-73.md)
is linear and supplies no saturation/temperature law. Original ZIP/PDF bytes
and hashes are retained; no circuit model or acceptance receipt has changed.
