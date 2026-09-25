# Simulation-to-prototype decisions

## Checkpoint86 interpretation — switch-short coverage remains excluded

The switch-short attempt has a [source-bound INDETERMINATE disposition](../faults/settled-sw-short-59/full-SW-SHORT/campaign-verdict-86.json).
The successful full decode of its partial archive and final256-row extraction
are diagnostic evidence, not a complete fault observation or an accepted own
normal prefix. The final-row gate is about0.77uV, not0.182V (that is the switch
node). q/en remain high. A late driver-request transition coincides with the
collapse; causality and unrecovered simulator state remain unresolved.

[Parent-reviewed strategy implications](switch-short-strategy-review-83.md)
establish that the source-fed failed-switch path bypasses both gate control
and the VD-to-VB F2 bank branch. A future strategy needs independent source-path
interruption and a residual-energy/restart policy; implementation is not
selected. No physical182A prediction, device qualification, or electronic-only
protection architecture is inferred. The retained bounded-attempt contract
allows this inconclusive result without an unsupported rerun. No validated
post-abort coverage is claimed. DIODE64 remains live; BOTH65 and BYPASS66 remain
pending. The [parent requirements audit](completion-requirements-parent-review-86.json)
keeps the remaining complete-case and negative-control evidence requirements.

## Current checkpoint81 — switch-short incomplete; diode-short running

The switch-short run is [rejected as incomplete](../faults/settled-sw-short-59/full-SW-SHORT/parent-disposition-80.json).
Ngspice stopped at 654.402649 ms with a timestep-too-small error near
`vdboost2sense#branch`, about235.982 us after the commanded fault. The662ms
endpoint was not reached. All30,686,230 generated rows were saved in a
5,088,782,620-byte compressed archive; successful export is not successful
simulation. Both adapter and validator reject the endpoint. Root cause remains
unknown; the named branch alone does not establish causality. A separate bounded
original-row tail extraction supports diagnosis only. Full69 analysis gates are
unchanged and have not been run on this known-shortened trace.

DIODE-SHORT64 is now live under session52815, runner54751/monitor54752; its exact
source and parameter binding are parent verified. F2 remains closed. BOTH65 and
BYPASS66 remain prepared. Packets74/75/76 are prepared and parent reviewed for
complete captures. There is one full solver. The nine-point normal grid and the
startup/F2-CREST/F2-ZERO modeled acceptances remain unchanged; no new protection
acceptance is granted. About40GiB remains locally. Small checkpoint77 metadata
is byte-verified on private Google Drive; waveform backup/restore is unverified.

The selected-inductor manufacturer audit72/73 explicitly leaves saturation and
thermal behavior unbounded by the linear model. Other component-model and
hardware limitations below remain. Goal ACTIVE; the fault campaign is incomplete.

## Historical checkpoint68 — F2-ZERO accepted, switch-short running

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

Status: decision aid for operating-matrix-07. This document separates accepted
**modeled normal** evidence from remaining fault, model, and hardware questions. It
does not qualify a component, fuse, thermal design, protection function, or
product.

## Current disposition

The exact 120 VAC RMS, 190 ohm, cold-start source is an accepted modeled normal
baseline under `event-aware-normal-v1` ([`accepted-baseline-11/acceptance.json`](../accepted-baseline-11/acceptance.json)). Its 650 ms trace has complete finite rows and an event-aware audit; the legacy strictly-increasing checker still rejects the unchanged repeated-time branch. That rejection is retained in the receipt and is not hidden by deduplicating or shifting timestamps. The versioned policy retains every row and audits equal-time groups before applying the normal screens.

All nine declared normal-grid points, LL01–LL09, are now parent accepted.
The [nine-point table and bound receipts](operating-envelope-checkpoint-53.md)
record each condition, bus range, load power, input current and cycle drift;
the [JSON companion](operating-envelope-checkpoint-53.json) retains every
acceptance and source identity. LL09's [acceptance receipt](../line-load-direct-retry-47/full-LL09/LL09/acceptance.json)
has SHA-256 `30ce810b146331f8db0cf0e2c0a1bc22032062d529773039dd62aeeaa5075737`.
These are exact modeled points, with no interpolation or hardware qualification.
The earlier failed LL05 and LL08 archives remain rejected and preserved.

The separate [startup-fault acceptance](../faults/startup-compact-analysis-23/acceptance.json)
covers 89 ms and 6,025,180 rows. Its bank peaked near 127 V, and channel current
was already below 0.1 A before detection. It therefore does not establish
loaded 390 V shutdown or fuse clearing. The earlier numerical startup abort
at 4.42 ms remains preserved.

F2-CREST38 now has an accepted exact modeled-screen receipt under
[`faults/settled-reanalysis-40/F2-CREST38/acceptance.json`](../faults/settled-reanalysis-40/F2-CREST38/acceptance.json)
(SHA-256 `bc00f63b08b5218d74f7fa673e60ab6f976194d32a871c776432547130ccfa7e`).
It binds the unchanged 32,237,324-row trace, the accepted 120 VAC / 190 ohm
healthy prefix, corrected global 1 us / frozen local 25 ns processing, and the
phase43 three-stage all-choice 1% crest bound. The scripted injection-to-detector
latency is 61.228 us and retained-off is 106.628 ns after detection, but the
channel current was already below 0.1 A 2.819 us before detection and modeled
passive current remains 8.879 A. This is one exact source-bound modeled case;
it does not establish causal current interruption, a physical fuse, hardware,
thermal/SOA limits, or certification. The original phase35 and wrong-global-gap
stage38 rejections remain preserved as historical artifacts.

A separate saved-pin diagnostic on that exact F2-CREST38 trace is recorded in
[`parent-observability-review.md`](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.md) and its
[`JSON receipt`](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.json).
The saved ISENSE range is **-0.306538 to +0.000116321 V**; no sample exceeded
the cited TI absolute limits, while **1,241,371 rows** exceeded the strict
recommended 0 V comparison. PCL request and hold stayed zero throughout, so
this case does not exercise peak-current limiting or a large clamp excursion.
The result does not bound controller input current, selected Vishay VF over
temperature/lot, or hardware behavior.

| Decision question | Evidence | Practical disposition |
| --- | --- | --- |
| Can the model support the declared normal operating screens? | Baseline and LL01–LL09 acceptance receipts above, with complete raw traces, all-row extrema, cycle metrics, and equal-time audits. | Yes, for those exact source-hashed modeled cases and their stated screens. Do not extrapolate to hardware or unmodeled conditions. |
| What does the legacy checker result mean? | It rejects the first repeated timestamp although the event-aware receipts retain all rows and independently validate finite/order/event data. | Keep the strict result visible; use the versioned event-aware policy for these receipts. Do not deduplicate or nudge rows. |
| Are the other normal points complete? | LL05–LL09 are accepted under their own source-bound receipts; LL09's receipt is linked above. | The nine-point modeled normal grid is complete. These exact cases do not qualify hardware, fuse, thermal, SOA, protection, or total-energy behavior. |
| Have full faults been demonstrated? | Startup F2, settled F2-CREST38 and F2-ZERO51 each have source-bound modeled receipts. Both settled cases retain passive current and channel current was alreadylow beforedetector. | Three exact modeled cases are accepted within their screens; no causal current-interruption or hardware claim. SW-SHORT runs next; four settled cases await disposition. |

The accepted baseline's modeled residual and the clamp sensitivity results are
accounting/sensitivity evidence, not measured heat or a device margin. The
limiting-envelope review remains conditional and does not qualify the selected
diode ([`clamp/limiting-envelope-13/parent-review.json`](../clamp/limiting-envelope-13/parent-review.json)). The model-gap closeout records the same boundary for controller, MOSFET, diode, capacitor, and ideal-switch models ([`model-gap-closeout-12.md`](model-gap-closeout-12.md)).

Runner-27's parent receipt records an owned anonymous export descriptor,
separate compressor ownership, and a byte-identical 20 us native comparison
(316 normal15 rows). That transport was used for the accepted LL05 retry; its
initial failed archive remains unchanged. Fault runner-29 has 12/12 bounded
tests parent-reviewed. Successor runner45 is also parent-reviewed with 12
default tests plus one separately approved inherited-file-descriptor test; it
has no full-case runtime and is not an acceptance receipt. The direct-export
review adds 21 unit tests, 99,366
stopped-plot bitwise comparisons, and normal/fault anonymous-pipe proofs; it
removes an avoidable selected-vector copy but retains full simulation arrays, so
no comparable failed-run peak record exists for a quantified before/after resource comparison. F2-CREST32 remains preserved as an
incomplete failed artifact; F2-CREST38 is gzip-valid and complete at 32,237,324
rows. Its exact modeled-screen receipt now accepts the healthy prefix, corrected
global/local processing, and phase43 sampled crest bound; the phase35 and
stage38 rejection artifacts remain retained historically. LL08 retry41 is
accepted under its source-bound receipt (30,447,163 rows; 785.859 W load).
LL09 is accepted under its source-bound receipt linked above. The corrected
parent resource summary records 422 five-second samples, minimum free space
10.451938629 GiB, and maximum owned RSS sum 4.07556 GiB; these observations do
not bound instantaneous peaks. F2-ZERO is now accepted (checkpoint68), and
SW-SHORT is running. The user freed space; about45GiB is available with the16GiB
launch/10GiB runtime gates unchanged. Google Drive is authorized and connected,
but large archive backup/restore remains unverified. Canonical evidence remains
local and must not be deleted.

## What the passive Rev A schematic actually contains

The source is [`power_entry_passive_reva.ato`](../../../../../../elec/src/power_entry_passive_reva.ato). The mains path places F1 in the `ac_l` holder before the common-mode/NTC/bypass and bridge. The bridge feeds `l_boost`, `q_boost`, and the boost diode. `d_boost.K` is `hv_plus`; the four bulk capacitors, HF capacitor, output, and bleeder all connect from `hv_plus` to `control_gnd` (source lines 355–403). There is no F2 component and no separate VD/VB net in this retained Rev A source.

The proposed protection ECO is therefore a topology change, not a claim about the current board: reserve a physical diode-side `VD` node, a bulk-bank `VB` node, and a series `VD-out -> F2 -> VB-return` path. The intended internal failed-short path is `bank+ -> F2 -> U10 -> U9 -> bank-`; the passive disposition records the same boundary in [`DISPOSITION.md`](../../../protection/DISPOSITION.md). The disposition is conditional and unpowered, not a release authorization.

The F1 line path and the F2 stored-energy path remain separate:

| Fault | Physical source | Candidate interrupter | What is still unknown |
| --- | --- | --- | --- |
| AC line/boost fault with a healthy switch | Mains and line impedance | F1, if its complete clearing is coordinated | Installed source/holder/interconnect time-current behavior |
| U9 failed short, U10 healthy | Mains/boost path and local energy | Upstream line interruption/F1, subject to coordination | Gate-off cannot clear this path; the healthy boost diode blocks reverse bulk-bank feed |
| U10 failed short, U9 controllable | Charged DC bank | U9 gate shutdown plus F2 backup | Detector latency, failed-state current, F2 DC let-through |
| U10 and U9 failed short | Charged DC bank | F2 only | Capacitor-discharge clearing, arc/restrike, minimum breaking current |
| F2 open | Residual bank/local energy | A separately rated discharge path | Safe post-open voltage and discharge timing |

Opening F2 disconnects the modeled bank contribution only. The diode-side
local capacitor remains outside F2 and retains energy, and the AC source path
requires separate interruption. Neither source disappears because F2 opens.

Gate shutdown can limit energy only while U9 remains controllable. It cannot
open a gate-independent failed-short MOSFET. With a shorted diode and a healthy
U9, gate shutdown may interrupt the series path through U9; it does not remove
the diode short itself. F2 is not a qualified fuse in the current model: `SWF2` is an ideal
controlled switch with nominal resistance and scripted opening, with no melt,
arc, DC-clearing, restrike, or I²t state. The branch review explicitly limits
DIODE-SHORT to a terminal-level graph experiment and classifies SW-SHORT and
BOTH-SHORT as protection-gap topology stresses, not passes.

## What remaining simulation receipts add

1. **Normal grid:** each point needs its own complete cold trace, exact source
   substitutions/hashes, all-row extrema, cycle screens, and event-aware audit.
   A point does not inherit acceptance from the baseline or LL01.
2. **Fault cases:** begin only from an accepted healthy prefix and preserve
   source-bound injection timing, F2 terminal voltage/current, diode-side and
   bank-side voltages, MOS/diode currents, and latch/gate transitions. The
   unchanged fault checker must remain visible alongside event-aware evidence;
   equal-time rows cannot be discarded.
3. **Model-gap work:** the closeout document identifies generic diode/MOS,
   authored controller, nominal capacitance/ESR, and ideal F2 limitations.
   Additional sensitivity runs can characterize those assumptions but cannot
   turn them into production tolerances.

## Prototype evidence still required

- Obtain manufacturer DC capacitor-discharge clearing data for the exact F2
  assembly at maximum bus voltage, capacitor tolerance, residual short,
  loop R/L, minimum-breaking-current, and stated time-constant conditions.
  AC I²t data cannot substitute for DC clearing evidence.
- Instrument both F2 terminals and current, VD and VB, diode/MOS currents,
  gate voltage, and the real F1/source path during current-limited fault tests.
  Demonstrate arc extinction, no restrike, and safe post-open discharge.
- Verify supervisor/latch/driver UVLO and default-off timing over rail ramps,
  brownout, held PWM/ARM, and AUX return. A nominal model edge does not prove
  a tolerance or restart guarantee.
- Correlate MOSFET/diode hot I/V, nonlinear capacitance, gate charge,
  package/common-source inductance, and loop parasitics before assigning any
  device-survival margin.

Until those measurements and manufacturer data exist, keep VD/F2/VB explicit
in the schematic ECO, treat gate shutdown as a controllable-U9 damage-limiting
action, and report full-plant/fault traces as scoped modeled evidence rather
than interruption or hardware qualification.

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
