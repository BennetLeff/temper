# Simulation-to-prototype decisions

Status: decision aid for operating-matrix-07. This document separates accepted
**modeled normal** evidence from open grid, fault, and hardware questions. It
does not qualify a component, fuse, thermal design, protection function, or
product.

## Current disposition

The exact 120 VAC RMS, 190 ohm, cold-start source is an accepted modeled normal
baseline under `event-aware-normal-v1` ([`accepted-baseline-11/acceptance.json`](../accepted-baseline-11/acceptance.json)). Its 650 ms trace has complete finite rows and an event-aware audit; the legacy strictly-increasing checker still rejects the unchanged repeated-time branch. That rejection is retained in the receipt and is not hidden by deduplicating or shifting timestamps. The versioned policy retains every row and audits equal-time groups before applying the normal screens.

LL01 (108 VAC RMS, 416.460488957 ohm) is also an accepted modeled normal grid point under the same policy ([`LL01/acceptance.json`](../line-load-native-runner-12/full-LL01-initialized/LL01/acceptance.json)). LL02 (108VAC,208.230244479ohm) also passed its source-bound modeled screens ([`LL02/acceptance.json`](../line-load-native-runner-12/full-LL02-initialized/LL02/acceptance.json)). LL03 (108VAC,115.683469155ohm) now also passes ([`LL03/acceptance.json`](../line-load-native-runner-12/full-LL03-initialized/LL03/acceptance.json)); all three108VAC loads are accepted modeled points. LL04 (120VAC,374.814440062ohm) is also accepted ([`LL04/acceptance.json`](../line-load-native-runner-12/full-LL04-initialized/LL04/acceptance.json)). LL05's initial export reached the callback endpoint but its gzip was incomplete and lacked the native header; that archive remains rejected and retained. The runner-27 retry is now accepted under its own [source-bound receipt](../line-load-native-runner-27/full-LL05-retry/LL05/acceptance.json) (120 VAC, 187.407220031 ohm; 30,103,973 rows; all screens 0). LL06 is now also accepted under its [source-bound receipt](../line-load-native-runner-27/full-LL06/LL06/acceptance.json) (120 VAC, 104.115122239 ohm; 29,845,886 rows; 1,383.936 W load; all screens 0). LL07 is now also accepted under its [source-bound receipt](../line-load-native-runner-27/full-LL07/LL07/acceptance.json) (132 VAC, 374.814440062 ohm; 30,812,694 rows; 398.384 W load; all screens 0). LL08 session50666 was resource-guard aborted with only a 10-byte gzip header and no electrical result; its raw failure artifact is preserved. Retry41 is now accepted under its [source-bound receipt](../line-load-direct-retry-41/full-LL08/LL08/acceptance.json), SHA-256 `8c6f8fb701395ecb95cbdfd980fc9a2f94ca1417a456542a18d39e460c3e8fdd` (132 VAC, 187.407220031 ohm; 30,447,163 rows; 785.859 W load; all screens 0). LL09 is live in `line-load-direct-retry-47/full-LL09/LL09` (session33042, runner66517, host66769, monitor66518) with no acceptance yet. The first startup-fault attempt aborted numerically at4.42ms before75ms injection. Compact-source startup20 subsequently reached89ms; same-raw analysis23 passed the unchanged modeled startup screens with6,025,180rows ([`startup acceptance`](../faults/startup-compact-analysis-23/acceptance.json)). The bank peaked127V and channelcurrentwasalreadybelow0.1A beforedetection, so this does not establish loaded390V shutdown or fuseclearing. The accepted scopes are exact source-hashed model cases only; they do not establish hardware, fuse, thermal, device-SOA, or total-energy qualification.

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

| Decision question | Evidence | Practical disposition |
| --- | --- | --- |
| Can the model support the declared normal operating screens? | Baseline and LL01–LL07 acceptance receipts above, with complete raw traces, all-row extrema, cycle metrics, and equal-time audits. | Yes, for those exact source-hashed modeled cases and their stated screens. Do not extrapolate to unrun grid points. |
| What does the legacy checker result mean? | It rejects the first repeated timestamp although the event-aware receipts retain all rows and independently validate finite/order/event data. | Keep the strict result visible; use the versioned event-aware policy for these receipts. Do not deduplicate or nudge rows. |
| Are the other normal points complete? | LL05–LL08 are accepted; LL09 is live in the reviewed direct-export retry with no acceptance yet. | Await LL09's complete trace, source hashes, event audit, normal screens, and parent review. |
| Have full faults been demonstrated? | F2-CREST38 has a complete raw capture and an accepted exact modeled-screen receipt; phase43 defines the accepted sampled crest phase, while the original phase35 and stage38 rejection artifacts remain preserved. The parent branch-model review records the other settled cases as unexecuted topology experiments ([`branch-model-review-13-parent.json`](../faults/branch-model-review-13-parent.json)). | The exact F2-START modeled screens and F2-CREST modeled screens are accepted for their source-bound case. They do not establish causal current interruption, a physical fuse, or hardware behavior; the other five settled faults remain prepared/unrun. |

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
LL09 is live in `line-load-direct-retry-47/full-LL09/LL09` (session33042,
runner66517, host66769, monitor66518) with no acceptance yet. The other five
settled fault cases remain prepared/unrun. The LL08 resource receipt recorded
12.53356 GiB minimum free space, 3.79431 GiB maximum owned RSS sum, no system
swap increase, 29.933 s export, and 2,288.238 s full-case wall time; samples do
not bound instantaneous peaks. The latest storage forecast still projects
roughly 30 GiB additional free space for all remaining archives, with the 10
GiB guard authoritative; this is not a measured bound. No external drive is
available, and canonical evidence is not to be deleted.

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
