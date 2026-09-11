# RTD milestone: coordinator acceptance audit

This audit tracks the full five-part user objective. Dispatching an agent or
passing a small fixture is not completion. This is an initial current-state
review, not a new validation run or final acceptance.

## Ownership

GPT-6 Astra/high owns `rtd_milestone_execution`, placement, routing and combined
integration. Luna `rtd_circuit` owns circuit/contract/BOM/model preparation in its
isolated worktree. Luna `rtd_rust` owns Rust workspace/check/test preparation in
its isolated worktree. The coordinator owns this audit; implementation owners
must preserve unrelated WIP and use explicit integration of their changes.

## Requirement-to-evidence matrix

| Requirement | Evidence needed to accept | Initial verdict |
|---|---|---|
| 1. Circuit and interfaces | Current source-derived contract covering temperature range, measurement-error allocation, timing, each fault mode, exact selected parts, MCU pins, four-wire connector and OVP/OCP2 shared reference. Resolve conflicting source/docs using datasheets and actual compiled identities. | NOT YET PROVEN: contract preparation delegated. |
| 2. Full Atopile chain | Reproducible compiler inputs/outputs with hashes; canonical instance/pin/pad/net correspondence; actual insertion into the accepted growing full-board context; no duplicate or omitted owned instances. | NOT YET PROVEN: existing control candidate has no full-board overlay. |
| 3. Rust validation | Real registered entry points with production-shaped input/configuration and results; per-rule positive/boundary/deliberately broken cases; required topology/domain/return/noise/firmware/fault coverage; copied code/test provenance. Missing inputs and dormant placeholders fail closed. | NOT YET PROVEN: no canonical Zapote Cargo workspace at initial inspection. |
| 4. Placement/routing and regressions | Recorded Astra decisions executed through existing KiCad adapter, actionable Rust findings followed by correction/recheck, exact saved integrated candidate, native ERC/DRC/parity, buck/MCU and whole-candidate regression comparison. Required prerequisite issues resolved without silent relaxation. | NOT YET PROVEN: prior candidate is explicitly apparatus-only-assisted and has failures. |
| 5. Safety handoff | Exact BOM and source/board/suite/model evidence index, documented fault/reference destinations and load/polarity contracts, reviewed lessons/counterexamples made available to the next owner, unperformed physical tests remain NOT RUN. | NOT YET PROVEN: needs final accepted candidate. |

Specific fault coverage must distinguish element open/short from opens of each
of the four conductors. A simulation, behavioral model or firmware diagnostic
must not be presented as independent analog detection of a fault it cannot
observe. Local fault-high logic assumes a powered upstream pull-up; complete
upstream loss needs an explicit downstream disable obligation.

## Initial prerequisite evidence

`docs/hardware/control-assembly/README.md` reports an apparatus-only-assisted
result and identifies open schematic parity, MCU-local connectivity, power-width
and full-board integration obligations. The receipt binding below confirms which
bytes the old reports address; matching hashes do not make failed checks pass.

| Bound artifact | Current hash comparison | Current SHA-256 |
|---|---|---|
| `pcb/temper.kicad_pcb` | MATCH | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| `pcb/blocks/control-assembly/assembly-candidate/control-assembly.kicad_pcb` | MATCH | `bde0b0055397e06c72cb8c6f5dbe4e6f30474af132616ea60eb4502c24d1649d` |
| `pcb/blocks/control-assembly/verification/apparatus-only/control-assembly-routed.kicad_pcb` | MATCH | `09c6e46d6c35ad954df1989897945e018b4a80aa15d71ce8470a57c813e4e7c4` |
| `pcb/blocks/control-assembly/verification/apparatus-only/summary.json` | MATCH | `e636d96c26f17e8296f00960f910398eb38a635c9fbcfdee23f7b3edab11549b` |

`pcb/blocks/control-assembly/verification/apparatus-only/cross-view-report.json`
currently has `overlay_view: null` and `status: pending-overlay`.
`docs/hardware/control-assembly/harness-report.md` and `zapote/Cargo.toml` were
absent at initial inspection. The existing power-width failure list includes
`fb`/`boot` as well as the output supply: verify rule applicability and current
engineering constraints before deciding on geometry changes.

These are repairable dependencies under the execution owner, not evidence that
an external actor must be awaited. No active milestone-1 owner appeared in the
current collaboration tree or current app task inventory at inspection.

## Final acceptance procedure

Inspect final manifests and recompute their file identities. Read the actual
coverage/registration and defect corpus before trusting aggregate counts. Check
native reports and their invocation/environment, source correspondence, rendered
layout and full-board integration boundary. Confirm that passing section results
do not hide new failures elsewhere and that physical-only obligations remain
separate. Retain any failures/assistance honestly. Mark the thread goal complete
only when all five requirements are proved by the current deliverables.

## Initial execution evidence review

The recorded full-Top compiler run under
`zapote/rtd/evidence/initial/top-source/` reports successful generation. This is
source-build evidence only; the RTD contract and final corrected source still
need their own binding. The extension receipt under
`zapote/rtd/evidence/initial/extensions.txt` is a lenient pass: four modules are
fresh and six are missing, including `temper-drc-rs`. It must not be credited as
execution of the planned Rust validation suite. The source bridge's required
design-bundle and geometry modules are among the four fresh modules.

The isolated Luna worktrees are based on a prior committed revision while the
canonical worktree includes later and uncommitted inputs. The execution owner
has explicitly directed both workers to consume current canonical source and
compiled inputs. Final copy provenance and contract hashes must demonstrate
that alignment; isolated HEAD alone is not the milestone source identity.

## Independent protocol review findings

1. **Conversion/DRDY contract:** current
   `firmware/components/sensors/max31865.c` writes VBIAS plus automatic fault
   detection (0x84), without one-shot or automatic conversion, and the service
   reads fault status without reading RTD data. `rtd_service.c` waits for falling
   DRDY. Manufacturer documentation binds DRDY assertion to a completed RTD
   conversion and release to reading RTD data. A valid fix must exercise that
   actual sequence, including rearming later samples, rather than mock a DRDY
   event for a diagnostic cycle. Reported to the execution owner for resolution.
2. **Fault table semantics:** Table 12 lists disconnected FORCE+ and FORCE-
   under fault-status bit D5. Its “Indeterminate” entries describe resulting
   conversion data; they do not mean there is no digital fault indication.
   Correct the draft contract's classification and test the status handling.

Source: [MAX31865 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf),
DRDY section and Table 12. These are review findings, not results of a hardware
measurement. Final acceptance must inspect the resolved source, contract and
regression evidence.

## Draft Rust review before integration

The first ERC draft in the isolated Rust worker was reviewed before acceptance.
These findings were sent to both that worker and Astra; they require resolution
and meaningful regressions in the final code, not only a documentation response:

- Bind contract expectations to actual board MPNs, numbered pads and connections.
  Comparing the contract to itself must not let a mutated board pass unchanged.
- Require expected endpoints to share an actual native copper cluster; presence
  of any cluster record for a net does not prove that net is connected.
- Preserve the direct DRDY connection. The existing four SPI series resistors
  do not imply a fifth resistor on DRDY.
- Derive fault outcomes from a qualified circuit/model, with explicit unsupported
  cases. A classifier that labels every non-SENSE+ string a covered cable open
  cannot prove each conductor's fault response.
- For the strict low-threshold ADC comparison, check an exactly integral code
  boundary: floor(exact)+1 differs from ceil(exact). Validate encoding widths
  before shifting and bind them to the MAX31865 contract.
- Supply real pad/copper geometry for physical claims. Component-center locality
  screens must remain labeled as such; do not credit them as copper return-path
  or clearance proof.

## Follow-up review of proposed corrections

The circuit worker's `source_patch_proposal.patch` now proposes an explicit
one-shot conversion and RTD-data read, addressing the original missing-conversion
finding. It is still a proposal, not accepted firmware. Two issues were returned
to the owner: adding two settling ticks before resetting the ten-tick timeout
extends the total bound to 120 ms despite retaining a 100 ms claim; and starting
the automatic fault cycle simultaneously with BIAS enable does not establish
that the diagnostic itself ran after BIAS settled. Waiting afterwards cannot
repair that ordering. Acceptance needs the corrected complete sequence and
protocol-faithful repeated-sample and timeout regressions.

The first Rust integration defect corpus still mutates expected-contract fields
for connector, ADC and RREF topology cases. Those cases do not replace tests
that mutate actual board pads, nets, MPNs and copper clusters while holding the
correct contract fixed. Its SENSE- coverage expectation also conflicts with the
circuit draft's unresolved classification. Both owners were asked to reconcile
the physical/protocol evidence before accepting the classifier. Digest syntax
checks must not be described as detection of well-formed stale artifact hashes.

The native baseline DRC report is now present under
`zapote/rtd/evidence/initial/overlay/baseline-drc.json`; this establishes a
baseline to compare, not a section or integrated-board pass. The initial
full-board overlay remains an explicitly failing construction attempt.

## Physical-rule review and partial fixes

The Rust worker has now added board MPN, connection and cluster mutations while
leaving the expected contract fixed. SENSE- is explicitly indeterminate, and
claimed/observed digest equality is checked. These are code-review observations;
passing execution and adapter computation of observed hashes remain to verify.

Review found a concrete missed intrusion in `trace_near_region`: a segment from
`(0, 5)` to `(20, 5)` crosses the rectangle `[8, 4, 12, 6]`, but its vertex-only
predicate returns false. Trace width is also ignored. The owner was asked to
reuse applicable proven Temper geometry and add crossing/width boundary cases.
Decoupling still needs actual capacitor pad connections and board positions,
coverage of all required local ICs, and connected supply/return endpoints;
declared capacitor metadata and the existence of a supply cluster are weaker
than those obligations. These remain acceptance gaps, even when labeled as
heuristics in coverage documentation.

The native baseline report identifies KiCad 10.0.4 and includes 808 violations
and 348 unconnected items. Four checks are disabled in its environment:
`track_not_centered_on_via`, `tuning_profile_track_geometries`,
`footprint_filters_mismatch`, and `footprint_type_mismatch`. Final receipts must
retain the actual version/disabled-check inventory and explicit parity command;
an empty `schematic_parity` array alone does not prove that parity was requested.

## Independent initial-overlay copper reconciliation

A read-only parse of complete top-level native board objects compared the saved
initial baseline with its overlay, including segments, vias and zones. The
removal set exactly matches the explicit instruction: 2,378 segments, 36 vias
and three zones (2,417 objects total). No unexpected copper objects were added,
and every retained object's serialized form is unchanged. This proves the
recorded copper edit boundary for this initial attempt, not routing correctness
or final-board acceptance. Later attempts need their own reconciliation.

| Artifact | SHA-256 inspected |
|---|---|
| `zapote/rtd/evidence/initial/native-baseline.kicad_pcb` | `5db72b0839e5e156262d95b634c36c2c097950d31212bea5d14c2afeb5f7121d` |
| `zapote/rtd/evidence/initial/overlay/cooker.kicad_pcb` | `e8f8dc52872210fab25090a9f94c3f11b7d8cde1dcc56b1d42e5d0018a082161` |
| `zapote/rtd/evidence/initial/overlay-instruction.json` | `e963ddef22fc890f496b77c3e5622173cd28c98ec777f4563a0322924bfd1bc5` |

## Independent diagnostic-RC run

The coordinator ran the circuit worker's revised `rtd_sense_open_rc.cir` with
ngspice 45.2. The isolated 10 MΩ / 2.2 nF RC deck exits successfully and reports
1.978785 V at 100 ms, then 2.000000 V at 1 s and 5 s, matching the worker's
summary. This verifies that narrow model calculation only. The deck explicitly
excludes cable capacitance, leakage, internal switches and conversion loading.
It does not establish detection by the service deadline: conversion sampling,
arbitrary fault timing and component/cable corners must be included in that
argument. The reduction from the manufacturer's typical 100 nF filter also
needs an explicit filtering/error tradeoff. Both obligations were sent to the
circuit owner before acceptance.

## Route-edit boundary review

The new `zapote/rtd/apply_routes.py` replays explicit net/path instructions
through `block_native.replace_copper`. Native pad references resolve coordinates
and validate net membership; bend coordinates, layers, widths and vias come
from the authored instruction. The reviewed adapter contains no path search or
placement optimizer. It records before/after board and instruction hashes.
This supports the agreed agent-editing boundary; actual successful routing,
live Rust feedback, complete dependency binding and saved-board regression
results still require verification.

## Runtime fault-response requirement reconciliation

The source requirement is stronger than a missing-DRDY watchdog:
`docs/requirements/FIRMWARE_REQUIREMENTS.md`, REQ-FW-SAFETY-06 (lines 237–249),
requires RTD probe open/short detection and transition to FAULT in less than
100 ms. Its 500 Ω open threshold is stale relative to the current 300 Ω
contract, but no reviewed evidence supersedes its timing requirement.
`docs/hardware/RTD_SAFETY_DUAL_PATH.md:188` independently states a 100 ms
system fault-response budget. A 400–450 ms runtime conductor-open bound cannot
be accepted merely by renaming the 100 ms budget as a DRDY-only watchdog.

The execution owner rejected that slower proposal and is evaluating a revised
filter/continuous-conversion diagnostic. It also identified that repeated
automatic fault cycles can disturb the current node watched by the independent
hardware comparators. Acceptance must establish normal-operation coexistence
of both paths, startup/reset obligations, runtime fault latency and the revised
filter's error/noise assumptions. The earlier one-shot proposal and its focused
mock tests do not settle these requirements.

## Independent first real-input Rust run

The coordinator ran the worker-built `zapote-rtd` binary against
`rtd-current-native.json` with telemetry disabled. Exit status is 1 and report
status is FAIL. Binary and fixture hashes were unchanged across the run:

- Binary: `5c76703faa2e6e66a364918b91ee62e000486a31d5693bb373e9a1099a09d891`.
- Fixture: `1f3edb50a167eb3ee0118e6767084907861fe9345d71ae781837cc2964b61560`.

The report contains four disconnected probe-net findings, four bypass locality
failures (ADC, low/high window comparators and window AND), and three split or
omitted supply/ground endpoint findings. It also reports missing native pad
geometry. These are useful initial feedback on the supplied placement-02 input;
they do not describe later routing attempts.

Twenty reported rule IDs do not establish twenty exercised requirement
families. The initial binder supplies empty sensitive-net/aggressor/prohibited
connection populations, no per-conductor-open scenarios, and hardcoded firmware
values; it infers domains from names and discards native pad records. The native
snapshot is not yet bound to its board bytes at extraction. These limitations
were sent to the owners; final acceptance requires actual populated inputs and
missing required populations must remain indeterminate.

## Route-01 native snapshot binding

The later `placement-03/native-routed01.json` corrects the initial extraction
binding gap. Its board hash equals both the route receipt's output hash and the
current saved candidate hash:
`fadfb90f37530a4d2e6ebbf6726aaf6f51a03abc1d1a0ca9669c8bb77aaa5e98`.
The extractor hash also matches its current source. The snapshot contains 525
pad records with position, size, drill, orientation, shape and layers. The
route receipt records 18 operations, 81 segments and 19 vias. This verifies
identity of this routing attempt; it is not an engineering pass. The binder
must still reject native snapshots whose board identity does not match the
board supplied to the validator run.

The route-01 and route-02 native connectivity records now put each intended
probe pair in one cluster: header pins 1/2/3/4 connect respectively to ADC
pads 8/10/11/12. The BIAS cluster includes RREF pad 1 and ADC pads 4/5; REFIN-
includes RREF pad 2, the comparator inputs and ADC pads 6/7. These observations
resolve the four disconnected-probe findings for those snapshots only. They
do not prove absence of cross-net shorts, clearance compliance or connectivity
of diagnostic parts not yet incorporated from the revised source.

## Canonical Rust snapshot and return connectivity

The coordinator ran `cargo test --manifest-path zapote/Cargo.toml --workspace
--locked --offline` on the imported Rust workspace using the existing temporary
Zapote target directory. All 20 tests pass: five DRC, three ERC, one harness
unit test and eleven defect-corpus cases. This verifies those test cases, not
full required coverage or a passing real board. The source inventory digest is
`e2d7222dd25c0fcd2e4865d7e33607e5ad089655e68b4f6e54c75e554eae5b99`.

The saved return-01 board and `native-return01.json` have matching SHA-256
`948381f9c3f425267b16aaa719830153baf6caf073aafe007d8a952ecf1ffdaa`.
All 22 RTD ground endpoints appear in one native 27-node ground cluster. This
is connected-return evidence for that saved attempt; finite geometry, shorts,
clearance and routing quality remain separate acceptance obligations.

## Series-resistor correction and route-03 identity

The coordinator verified the recorded chain from return-01 through three
explicit footprint rotations (R29, R31, R32) to the route-03 replay. The
series-correction output hash equals the route receipt's input hash,
`be781380e7b5de76b1444d1b6be52e810a4d13c290136ac87cb981d5d7132ee0`.
The receipt contains 18 route operations, and its output hash equals the
saved candidate bytes inspected by the coordinator:
`2b8b0f80eeef383c651e867f3cf364723a2e20fa3ef773206ef350399f8eff61`.
The correction records native DRC's discovery of copper bypassing series
resistors as its reason. This is a bound edit/correction attempt, not proof
that the bypass shorts are resolved: a new native connectivity/DRC result
and Rust feedback on this exact saved revision are still required.

## Circuit handoff review and focused firmware execution

The circuit owner's completed proposal has SHA-256
`6dcafc25bed7e1aecfb848ab4627e8fea61169f783c810bfd8d2ce1b005dbbae`.
The coordinator independently executed the retained isolated
`/tmp/rtd-build7/firmware/test/build/test_max31865_only` binary: all 12 tests
pass. These exercise register sequencing, fresh data reads, repeated DRDY,
read/bootstrap failures and missing-DRDY handling; they do not inject analogue
conductor breaks or establish physical fault latency. The proposal now uses
the consistent 60 Hz sequence `0x80 -> 0x84 -> 0xC0`.

Acceptance still needs a consistent arbitrary-runtime-break bound including
settling, conversion/filter phase, polling and fault handoff. The handoff
alternates a 65 ms runtime claim with a longer RC-inclusive allocation while
allowing a contaminated sample; the retained transient decks cover opens
present at startup. A 95 ms startup observation plus 5 ms handoff also does
not by itself prove the strict less-than-100-ms requirement.

The proposal's approximately 2.73 C accuracy ledger is evaluated near the
250 C range end. `docs/FUNCTIONAL_TEST_CRITERIA.md` specifies the 2 C accuracy
criterion at 100 C, and 1 C stability at 60 C. Recalculate and allocate error
at those required conditions, including remaining control/contact allowance;
do not invent a 2 C full-range requirement or claim the existing ledger proves
the actual criterion. These findings were delivered to the execution owner.

## Startup readiness integration gap

The proposed service keeps its public readiness accessor false until a fresh
sample, but the current production state-machine callers do not consume that
accessor. `main.c` ticks the service before updating the state machine;
`state_init_update` proceeds through POST to IDLE, and a start event can enter
PAN_DET, whose entry requests 5 percent power. The only located implementation
of `test_rtd_sensor` is a host test stub. The isolated test target also supplies
a strong stub for `read_rtd_resistance`, overriding the proposal's weak reader.
Consequently the 12 focused service tests do not prove production startup
inhibition until a valid sample. The execution owner was asked to resolve the
focused RTD readiness integration or explicitly assign its downstream obligation;
an unused accessor cannot be credited as a functioning startup power gate.

## Expanded Rust test verification and mutation-test limitation

The coordinator tested the clean Zapote subtree at worker commit `5e2c39ba8`:
the offline, locked Cargo workspace run passes 23 tests (5 DRC, 3 ERC,
1 harness, 14 defect-corpus cases). A Cargo-built CLI run against its retained
native fixture exits 1. This is feedback on that retained fixture, not a pass
for the later source-02 board.

Some mutation assertions are weaker than their names imply. The native
conductor-expectation case changes only the expected classification and checks
for any `ERC.RTD.FAULT_CORNERS` finding, although two findings in that family
already exist on the baseline. The pad-net mutation similarly checks for any
`DRC.RTD.NATIVE_GEOMETRY` finding while the baseline already fails that family
on three supply/ground clusters. These cases must assert the newly introduced
finding for the targeted object, or use a baseline clean for that obligation.
The execution owner has the correction; 23 passing tests are not credited as
proof that all named mutations are independently detected.

## Source-02 native schematic-parity receipt

The coordinator recomputed the receipt's board, sibling schematic and DRC
report hashes: all three match the saved files. The recorded KiCad 10.0.4
command explicitly includes `--schematic-parity --all-track-errors
--severity-all`. The native report contains no electrical connectivity parity
mismatch and four testpoint BOM-exclusion attribute warnings (TP1–TP4).
The owner records the latter as inherited copper-testpoint metadata pending
BOM reconciliation; this is not a zero-warning parity pass. The same report
still has 305 unconnected items and 1,197 reported violations, with the two
199-entry silk categories capped. Electrical parity is now supported by a
bound native report; routed-section and whole-board acceptance remain open.

## Circuit followup: upstream compatibility and composed firmware tests

The revised 698 kOhm monitor proposal calculates a maximum rising release
threshold of 3.25555 V and maximum falling trip of 3.22349 V, but compares
release only to nominal 3.3 V. The adopted upstream buck requirement in
`harness-lab/engineering/requirements.json` permits 3.135–3.465 V. Therefore
the proposed monitor is not yet compatible with the full accepted upstream
envelope, before even allowing ferrite/wiring drop. TPS3700's official Rev G
threshold limits agree with the proposal's arithmetic inputs; the unresolved
issue is the cross-section contract. The execution owner must qualify a tighter
upstream guarantee or an appropriate monitor solution, without substituting a
nominal supply for a guaranteed bound.

The startup-gating change in `28cafe0d8` checks readiness before PAN_DET both
at the button handler and common transition entry. Its tests, however, use the
older service startup sequence (bootstrap, immediate DRDY, one tick). They
must be composed with the circuit owner's BIAS/diagnostic/continuous sequence
and prove START is inhibited after bootstrap but before the first valid
sample. The initial false-readiness test also relies on runner ordering and
uninitialized service state. Review of `0d81b5591` confirms stronger assertions
for several mutation cases; its native pad-net mutation still checks an entire
already-failing geometry family and needs a targeted new finding assertion.

## Requested review: local RTD native rule applicability

The source of eight 0.235 mm MAX31865 pad-gap failures is confirmed: the
existing same-footprint exceptions require equal netclasses, while adjacent
Power and Default pads fall back to Power's 0.5 mm clearance. A scoped 0.20 mm
pad-to-pad clearance for source-identified, verified single-SELV RTD packages
is appropriate for the existing land pattern and default routing floor. This
does not justify changing all Power nets or lowering cross-footprint rules.
The separate 0.1986 mm U8 pad-13/sdi-track clearance is below the existing
0.20 mm routing rule and remains a real layout failure.

Recommended width allowance: 0.25 mm only for qualified local load/escape
branches with at most 3 mm complete branch length to the intended pad/via/pour,
known maximum current, and verified copper geometry. The native candidate has
six copper layers, with 70 um outer and 35 um inner copper specified. Initially
scope this allowance to outer layers. A nominal 3 mm x 0.25 mm x 0.07 mm copper
segment has approximately 2.955 mOhm resistance at 20 C; the existing
`packages/temper-drc-rs/src/ipc.rs` scalar formula estimates 1.963 A at a 20 C
rise for external copper. These are supporting estimates, not a qualified
current rating. Use minimum finished copper, hot resistance, actual load and
voltage-drop limits; short bypass return inductance is a separate obligation.

Reject eligibility for shared trunks or return spines, buck input/output/SW
and inductor paths, MCU supply trunks, or any unbounded downstream current.
Preserve their applicable 0.6/1 mm floors and all domain-isolation constraints.
An explicitly named native group can convey a Rust-validated eligible segment
set, provided Rust independently checks exact membership, branch endpoints,
length and current. The group itself must not serve as evidence of eligibility.

KiCad's documented courtyard/area intersection predicates match when any part
of an object intersects: a long track can inherit the exception outside the
region. They are insufficient as the sole local-branch predicate. Rules are
evaluated in reverse file order, so isolation constraints must retain priority
and also be protected by disjoint eligibility. Required checks include valid
local branches, below-minimum width/gap, excessive branch length, added shared
load, a narrowed buck trunk and an HV/SELV crossing in either object order.
Generate native constraints from the same reviewed contract used by Rust.
These are recommendations to the execution owner; no CAD/rule files were
mutated by the coordinator, and implementation/oracle evidence is pending.

Source: [KiCad 10 PCB Editor custom-rule documentation](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html).

## Followup review: targeted native mutation and phased readiness tests

Read the Rust owner's committed `3064187e6` and `cb28ef7ab`. The native ADC
pad-8 net mutation now requires both an increase over the baseline geometry
finding count and an exact `rtd_pan.adc.8` FAIL. This resolves the previously
identified assertion weakness in that case. The binder also now rejects native
extraction whose declared board hash differs from the supplied board bytes.
These are source-review conclusions; they do not establish a passing current
integrated-board run.

The firmware tests in `3064187e6` now bootstrap the real service before checking
that START is inhibited, advance the BIAS/fault/continuous phases before sample
handoff, and install a real RTD register value before claiming readiness. The
Rust owner's isolate still contains the older service implementation, so test
acceptance requires the composed build with the circuit owner's service and
production state-machine caller. Requested that exact source identity and test
receipt from the owner; no merged execution result is credited here yet.

## Executed counterexample: local exception false admission

Frozen Rust owner commit `25909d5df` into
`/private/tmp/rtd-root-escape-review` and ran its actual `zapote-rtd` CLI on a
mutated typed fixture. Two 1 x 1 mm ADC pads have centers only 0.5 mm apart,
so their copper overlaps; a selected 1 mm trace fragment is at (100, 100),
unconnected to those pads near (40, 40). Nevertheless
`DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY` returns PASS for `root-counterexample` and
states that the group is admitted. Input and report are retained in that
scratch directory as `counterexample.json` and `report.json`.

The overall suite returns FAIL from other checks; this finding is specifically
about false admission by the proposed exception-authorizing rule. Its center
distance is not a copper-edge distance, selected length is not proof of a
connected complete branch, and authored trunk/spine booleans do not prove the
absence of other downstream loads. Sent the executed case to the Rust owner.
Do not use this rule to grant native exceptions until corrected and tested.
Same-package pad-clearance eligibility and local branch-width eligibility are
separate obligations and should not require a bypass branch to terminate on
an unrelated same-IC pad pair.

## Verified current-source integrated-board Rust feedback

Checked `placement-04/rust-window-receipt.json`: all eight referenced artifact
hashes match, including saved board, native export, source manifest, binder,
authored policy, actual binary, input and report. The native export's board
hash matches saved board `44a8fd42af05d096942982d441f3d6214e54273167b634e1b0860824472d2e1c`.
Independently reran the recorded binary and input, saving
`/private/tmp/rtd-root-window-report.json`: exit 1 and identical ERC/DRC findings.
This establishes real feedback from the source-02 integrated candidate, not
only a retained fixture.

The run reports four decoupling locality failures, split required endpoints on
+3V3 and gnd, and two indeterminate sense-conductor fault cases. The post-ferrite
rail no longer has the earlier split-net finding. The execution owner is using
these results: repairing real supply/return connections and correcting the
component-center locality proxy to actual supply-pad/return-route geometry.
A center-distance pass or fail alone is insufficient for bypass effectiveness.
The sense-open model is still the older adopted model; new circuit calculations
must be reconciled into the final executable contract before acceptance.

The execution owner superseded the first window receipt because its referenced
worker model bytes were mutable and not retained. Reviewed replacement
`placement-04/rust-window-receipt-02.json`: all nine artifact hashes match,
including the frozen model and preserved executable. Use this replacement
receipt for reproduction. It retains the same six DRC failures and two
indeterminate conductor cases; freezing model bytes does not supply missing
model semantics or change those engineering verdicts.

## Followup counterexample on revised local eligibility rule

Reviewed completed Rust snapshot `359e4ac55`. Pad-spacing checks now account for
pad extents, but complete branch connectivity is still unproven. Executed a
second case from a frozen copy in `/private/tmp/rtd-root-escape-review-359`:
non-overlapping ADC pads near (40, 40), with three selected 0.25 mm traces
forming a closed triangle near (100, 100), total length below 3 mm and no
connection to any selected pad. The rule again emits PASS/admitted for
`root-disconnected-cycle`. Input/report are retained as `counterexample.json`
and `report.json`. The overall CLI exits 1 due to other findings; this is a
rule-specific false admission. The scratch build used its own target directory,
leaving the execution owner's preserved/shared binaries untouched.

Requested one consolidated correction from the existing Rust owner: separate
pad-clearance and branch-width qualification; require same-net/layer physical
anchors and complete branch membership up to the intended trunk junction;
allow a valid low-current ground branch to reach MCU/buck ground without
classifying the entire net as a forbidden branch; and prove local decoupling
return-path length rather than accepting any connection in a global cluster.
Missing native inputs must remain indeterminate, not invoke fixture center
fallbacks. These are existing acceptance obligations, not new routing work.

## Independent composed firmware verification

Built a preserved scratch tree at `/private/tmp/rtd-root-firmware-composed`:
Rust owner's firmware, production caller gates and focused tests, with the four
current canonical MAX31865/service source/header files overlaid. CMake builds
`test_max31865_only` and `test_state_machine_only` from that composed tree.
Both execute successfully: 15 MAX31865/readiness tests and 60 state-machine
tests, zero failures. The focused tests include bootstrap-before-sample START
inhibition, first successful conversion enabling PAN_DET, and read failure
blocking startup, alongside the phased BIAS/fault/continuous service sequence.

Retained all 191 firmware source files, before/after source manifests, build and
test logs, both executables, and `receipt.json` with hashes in the scratch tree.
This closes the composed host-test evidence gap. It does not claim that caller
changes are already imported into canonical firmware, prove physical fault
response timing, or close the whole RTD milestone.

## User-directed scope replacement: standalone RTD first

The user explicitly changed the delivery order: each unit separately first,
with integration afterward under a separate goal. Updated the roadmap and RTD
plan accordingly. The execution owner stopped full-cooker CAD work and retained
`zapote/rtd/evidence/scope-change-standalone/receipt.json`. Independently checked
all four frozen artifact hashes (board, schematic, project and rules): all match.
The preserved board is `8bdc402851a450be088f056d67d36d1619a2aca9573474e9ed672cedcef5babd`.
Its receipt correctly says PAUSED_INTEGRATION_NOT_ACCEPTED and discloses that
latest edits were not rechecked. This is preservation, not acceptance.

Earlier integrated-board findings remain historical evidence and future
integration obligations. Current acceptance applies to the standalone RTD
source/board, circuit and interface contract, applicable Rust/native checks,
defect proofs, exact BOM and reviewed lessons. Do not reintroduce full-cooker
routing as a prerequisite based on the app's stale stored goal wording.

## Independently rerun shared native adapter regression

Verified the execution owner's four input hashes and refilled board/report
hashes under `zapote/rtd/evidence/adapter-regression`. Reviewed and independently
ran `zapote/rtd/tests/native_adapter_regression.py` with KiCad's Python 3.9 host,
saving scratch results under `/private/tmp/rtd-root-adapter-regression`.
Assertions pass for existing-zone deletion/replacement, saved priority/clearance,
and a late route-operation exception leaving destination bytes unchanged.

The first sandboxed CLI refill aborted with exit 134; the authorized unsandboxed
retry succeeded with zero native violations and zero unconnected items. Reloaded
the resulting board through pcbnew: filled area is 35.984522120362 mm2, priority
2 and clearance 0.22 mm remain intact. The scratch receipt retains the result
and output hashes. This closes the shared adapter zone-lifecycle/atomic-save
regression gap for the exercised sequence; it is not an RTD board acceptance.

## Standalone profile handoff review

Reviewed Rust owner's `b5c738cc8`. Its `UnitInput`/binder is typed transport;
the actual CLI and engineering suite do not yet execute it. `UnitProfile`
validation also requires connector qualification and the current budget to stay
pending, rejects a future qualified state, hardcodes the unconfirmed source name
`RTDSensing33`, and checks interface net order without unique/exact pin numbers.
The two ground contacts must represent one electrical ground net. A 1 nF input
filter must remain distinct from each IC's supply decoupling requirement.

Continued the existing Luna owner with runnable unit-suite integration, actual
source/board bindings and targeted observed-data defect proofs. This scaffold
is preparation, not standalone acceptance. Retain only genuinely outside-unit
applicability as deferred; local reference loading and fault/current models are
still required engineering inputs.

## Requested TLV3201 sense-monitor protection review

[TI TLV3201 Rev C](https://www.ti.com/lit/ds/symlink/tlv3201.pdf), sections 6.1,
7.3.2 and 8.1.1, specifies rail-clamped inputs, ±10 mA absolute-maximum input
current, and resistor limiting for momentary over-rail signals. Functional
common-mode is GND−0.2 to VCC+0.2 V; supply operation is specified at 2.7–5.5 V.
Full-temperature input bias is at most 5 nA per input. Differential voltage
above supply must be avoided.

A shared 100 kOhm sense-monitor resistor is plausible: two worst-direction bias
currents add about 1 mV threshold error, before resistor tolerance and board
leakage. Illustrative ±5% resistance gives at most 0.474 mA and 21.3 mW for
45 V across it. This arithmetic does not qualify a ±45 V unit interface.
Positive clamp current enters the local rail. Bound pulse amplitude/duration,
repetition, resistor ratings, rail capacitance and minimum sink load, including
local-off/upstream-on conditions. Check the LOW divider's path into REF2025
and clamped differential voltage. Sent the execution owner these bounded
checks; no protection hardware or transient immunity is accepted by this review.

## Independent reproduction of the candidate comparator DC table

Copied the active candidate solver and its result receipt into
`/private/tmp/rtd-root-window-review` before execution. Independently ran the
retained solver with `/opt/homebrew/bin/python3`: all 23 emitted lines match
the candidate receipt exactly (16,384 corners per case). Solver SHA-256:
`0c3510af03b7d49354003afca6118df07627a02e04145a54175c14a4a6cb9917`.
The scratch receipt binds the solver, original result file and reproduced table.

This establishes reproducibility of the passive DC table, not final circuit
qualification. The execution owner confirms this is an actively corrected
candidate: reference drift, complete threshold-node leakage, and transient /
partial-power bounds remain under correction. No frozen source or standalone
board acceptance follows from this result.

## Independent firmware threshold-generator check

Reviewed the current generator diff: low-threshold conversion changes from
`ceil(exact)` to `floor(exact) + 1`, retaining a strictly greater threshold
when the resistance boundary maps to an exact integer ADC code. The added
regression exercises that integer boundary and adjacent codes at the actual
10 Ohm / 430 Ohm contract. Independently ran
`.venv/bin/python -m pytest firmware/tools/test_board_derivation_lib.py -q`
in the canonical worktree: 41 passed. This checks threshold generation; it
does not establish device fault latency or physical fault response.

## External-engine check of the candidate passive solver

Independently expressed the retained candidate resistor/current-source network
as ngspice operating-point decks, without using its Gaussian-elimination code
to calculate oracle voltages. Ran 80 cases: healthy and each individual conductor
open, 100/194.1 Ohm RTD, 1/50 Ohm leads, and four selected endpoint combinations
(corner indices 0, 5461, 10922, 16383). Compared both sense voltages and both
offset-adjusted comparator margins with the retained Python solver. All agree
within 1e-7 V; maximum observed discrepancy is 4.079e-13 V.

The scratch comparison harness, each deck and native output, and the complete
receipt are retained under `/private/tmp/rtd-root-window-review`, with the
summary in `spice-comparison.json`. This checks the candidate passive solver
against a separate numerical engine. It does not establish that the component
limits, external topology, or transient assumptions cover the final circuit;
the execution owner's identified circuit corrections remain open.

## DSE library checkpoint review before unit generation

Compared the supervisor footprint checkpoint with TI's DSE0006A example
land-pattern drawing (retained page `/private/tmp/rtd-dse-25.png`). The drawing
aligns pad 1's outer left edge with pads 2/3, then extends its 0.80 mm land
0.10 mm farther inward than their 0.70 mm lands. Given ordinary row centers
at ±0.60 mm, pad 1 therefore centers at x = -0.55 mm, with extents
[-0.95, -0.15] mm. The draft kept x = -0.60 mm and produced extents
[-1.00, -0.20] mm. Sent this isolated +0.05 mm correction to the board owner.

The draft pin-1 silkscreen dot also overlaps its land; flagged relocation or
removal before native acceptance. This is a narrow checkpoint finding, not
an assertion that the complete footprint or board is accepted.

## Standalone reuse handoff: incorrect applicability and source authority

Reviewed the completed Rust handoff patch
`49bb3b1d7947090601d3508bbe9945adcbb987eb825df26f8101cab15842440b`.
It now calls the existing ERC/DRC functions, but its RTDUnit branch explicitly
skips four-wire probe pinout and ADC-to-probe native connectivity. The ten-pin
host interface is additional: the four-wire probe connector remains inside
this unit. These skipped rules are still listed among checked rules.

The adapter also supplies synthetic `unit.reference` / `unit.rail` entries,
collapses upstream and filtered rails into `+3V3`, and leaves required local
ICs empty; the ERC applicability return skips the corresponding local checks.
These are omissions of unit requirements, not legitimate deferrals of the
future MCU and reference consumers. Continued the Luna owner with a bounded
correction and targeted probe-swap, disconnected-conductor, ferrite/reference,
and local-rail defect proofs.

Source authority remains incomplete. The binder hashes the supplied source
manifest without inspecting its component/pin/net identities, while expected
ADC and RREF net maps are assembled from the same observed native pads being
checked. Requested a compiled-source contract separate from native observations
and a consistent board-net-swap defect against unchanged source. The profile
also still names `RTDSensing33` and alternate net names; authoritative wrapper
is `RTDUnit` importing `RTDSensing`, with `rtd_pan` and the published `RTD_*`,
`gnd`, and `RTD_AVDD` names. No standalone engineering acceptance is established
by the current passing package tests or registered-rule count.

## Standalone source preflight evidence

Inspected `zapote/rtd/unit/evidence/source-preflight-01`: successful Atopile
0.2.69 RTDUnit build with a 34-component resolved census. Independently verified
all 13 recorded source and generated-build hashes against retained bytes.
The census includes actual `rtd_pan.fb_power`, `rtd_pan.reference`, and the
additional `unit_io` host connector. This establishes a real standalone source
build; it is the pre-supervisor-change checkpoint, not the final circuit or
board. The execution owner is compiling the corrected source next.

## First standalone native placement capture

`unit/evidence/native-placement-01.json` now contains 35 real board components.
Using the candidate's source-manifest reference mapping, independently inspected
the observed J2 host connector's ten pad nets and J1 probe connector's four
force/sense pad nets; both match the published boundary pin orders.

This early capture has designator IDs, identity-only reference mappings, and
some passive-component `mpn` fields holding Value strings. The extractor reads
actual footprint MPN and falls back to Value. Sent the owner two separate
actions before Rust acceptance: apply the proper source-to-reference identity
mapping, and synchronize absent actual CAD MPN properties from source then
re-extract. Replacing observed MPNs with expected source data only in a binder
would hide a source/board mismatch. Placement DRC is an intermediate result;
no routed-board or complete source-symbol-pad-net acceptance is claimed here.

## Standalone schematic export/ERC closeout helper

At the execution owner's request, added isolated
`zapote/rtd/unit/close_schematic.py`, reusing the existing schematic donor's
parser and emitters. The helper supplies a real local symbol library/table,
qualifies embedded/instance library IDs, aligns symbols/labels to the connection
grid, sizes drawn boxes around unchanged pin positions, and places labels
outside the boxes. It preserves instance UUIDs and electrical assignments.
MAX31865 NC3 and the deliberately open supervisor CT pin receive explicit
no-connect markers while retaining their singleton global-label net identities.

Verified the source-02 / 35-component result in a separate scratch project
with actual candidate footprint libraries: native ERC reports zero violations
at all severities. Native before/after netlist maps match at all 117 pins and
30 nonempty nets; the source bridge also retains six empty abstract interface
net records (the earlier 36 count is the bridge-record count). Rendered and
inspected the native PDF: labels lie outside boxes and the drawing fits A2.

Frozen outputs, reports, render and hash receipt live in
`zapote/rtd/unit/evidence/schematic-closeout-35`. The candidate schematic was
not overwritten because the owner is generating the next source revision;
the helper is an explicit replay step, followed by final ERC/parity checks.
The donor's generic bidirectional pin electrical types are unchanged. This is
native schematic-format/connectivity proof, not manufacturer circuit qualification.

## Protected comparator handoff: omitted LOW-input clamp path

Reviewed the proposed shared 100 kOhm RTDIN+ branch alongside the retained
RTDIN−-referenced 61.9 kOhm / 10 kOhm LOW divider. The handoff's illustrative
45 V / (61.9 kOhm + 10 kOhm) current into REF2025 omits the TLV3201 input
clamp at the divider midpoint. With that midpoint clamped near the local rail,
the 10 kOhm bottom resistor can instead carry roughly 4 mA into the TLV/local
rail during a +45 V excursion and dissipate roughly 0.17 W instantaneously;
a negative excursion is roughly 4.5 mA / 0.20 W. These are explanatory nominal
figures, not qualified pulse limits.

Sent the circuit and execution owners this missing branch for their ongoing
transient/partial-power model. The REF2025 output-current rating alone does not
bound local-rail injection, TLV clamp behavior, or resistor pulse stress. The
MAX31865's device-level ±45 V capability does not automatically establish an
RTD-unit interface rating or impose that rating as a new requirement.

## Source-03 native checkpoint and actual tool version

Inspected saved `unit/evidence/drc-source03-01.json` and
`erc-source03-01.json`: zero DRC violations, zero unconnected items, zero
schematic-parity findings, and zero ERC violations. Both include error, warning
and exclusion severities. This is the routed 36-part checkpoint, before the
owner's subsequent change to the SPI-adjacent return plane; it is not the final
board receipt or circuit/Rust qualification.

Both reports identify KiCad 10.0.4. Independently queried the current CLI and
pcbnew runtime at the configured `/Applications/KiCad/KiCad.app` paths: both
return 10.0.4. Final receipts must bind this actual runtime, not inherited
10.0.6 wording from earlier work. No runtime change is required by this note.

## Independent reuse/defect execution and partial-binding counterexample

Retained the working Rust binary and the source-02 bound inputs under
`/private/tmp/rtd-root-unit-rust-review`. Independently reran the baseline,
probe-swap and ferrite-bypass cases. Probe mutation adds the intended
`ERC.RTD.FOUR_WIRE_PINOUT` and `ERC.RTD.BOARD_COMPONENT_BINDING` findings;
ferrite mutation adds `DRC.RTD.UPSTREAM_POST_FERRITE_RAILS`. These are targeted
findings beyond the baseline's unresolved locality/model items.

Removing all compiled source bindings correctly adds an indeterminate
`ERC.RTD.UNIT_SOURCE_BINDING` finding. However, retaining only the first of 117
bindings gives an entire report equal to the baseline report, with no new
finding. This demonstrates missing completeness enforcement, not acceptance
of the baseline (which already fails other checks). Sent Luna the exact
counterexample and requested complete source/native pad and component census
equality, including missing-mapping and extra-component rejection. The scratch
receipt binds the retained binary and records both experiments.

The subsequent `native-placement-02.json` closes that early identity/MPN
observation: compared the complete native component-ID set and every exact MPN
with the candidate manifest's compiled `source_attributes`; all 35 match.
The capture identifies board SHA-256
`9f0e5d62bb5dd4b3579ef47db1db140936c4f5d4668a3be9a4fd5a90c1f529ed`.
The owner reports this came from corrected CAD properties followed by a new
extraction. This census check is distinct from connectivity and routing checks,
which remain open.

## Complete source-to-native pad-net comparison for placement 02

Independently joined the compiled source bridge's nets through its explicit
`strict_pin_map`, then compared the resulting `(instance, pad) -> net` map with
every observed native footprint pad. Equality holds across all 35 components,
117 pads, and 36 nets. There are no missing, extra, or duplicate pad identities;
none of the source pin mappings is positional.

Frozen inputs and receipt are in `/private/tmp/rtd-root-unit-source-review`:
manifest SHA-256 `9d3e72fbcfbb0b297e9f8683a53aaf4f0359f8351f4c0c9cff9f94f8ee6d59e7`,
native export SHA-256 `463fb90e9d1f69e241143ca5f7cd9c95fecd51fb86a0e0f9d15828d70e5bc88d`.
This checks the whole snapshot's source-to-pad net assignments, not completed
copper connectivity. Later circuit/source changes require the corresponding
comparison again against their final board evidence.

## Causal native copper-cache regression

Independently reproduced the stale zone-fill hazard on a scratch copy of the
frozen source03-return-pass board. Removed the seven agent-authored ground
stitches, refilled the baseline, then replayed the same seven ground vias with
and without the two new `UnFill()` loops in the existing adapters. All seven
vias have the intended ground net before native refill in both variants. With
the loops removed, five change to +3V3 or RTD_AVDD after KiCad refill/save; with
the current adapters, all seven remain ground. This establishes causality for
the cache fix rather than observing only a repaired candidate.

KiCad version is 10.0.4. Frozen boards, reports, adapter sources, operation, and
hash receipt are under `zapote/rtd/unit/evidence/root-cache-regression-01/`.
This prepared baseline is distinct from the owner's original three-via
incident, so the five-via reproduction is not a revision of that observation.
No active candidate or production CAD was edited by this check.

## Independent transient capacitor-location mutation

The revised circuit model places its differential capacitor across the local
ADC sense pins. At the retained single corner, SENSE+ and SENSE− opens cross
the comparator threshold at 0.298 ms and 0.016 ms respectively. Deliberately
moving that capacitor to the remote probe nodes reproduces the erroneous
zero-time crossings for both faults. The scratch receipt and frozen model
variants are in `/private/tmp/rtd-root-transient-review/`. This is a model
topology defect proof, not a completed timing bound: final acceptance still
needs actual component corners, capacitance bounds, and comparator delay
conditions including overdrive and output loading.

## Source04 identity and partial-binding counterexample closeout

The complete source04 comparison passes across 36 exact component identities
and MPNs, 119 unique pads, and 31 nonempty net names. Every source mapping is
explicit rather than positional, and the native capture hash matches the
current candidate board at this checkpoint. See
`zapote/rtd/unit/evidence/root-source04-identity/receipt.json`.

Retested the prior partial-binding counterexample with the revised Rust binary.
Keeping only one of 119 bindings now produces explicit partial-binding and
source/native pad-census findings; the earlier silent acceptance of partial
source coverage is corrected. Baseline still fails unresolved model and layout
checks, so this is not full acceptance. The retained binary, both inputs,
reports, and hashes are in
`zapote/rtd/unit/evidence/root-source-binding-recheck-01/`.

## Added measurement-network error check at 100 C

Using the current passive circuit solver, independently calculated ADC ratio
from the actual RREF voltage drop, rather than applying the previous budget
without recomputing its network contribution. With nominal RREF (whose
tolerance and drift have separate ledger rows), 138.5055 ohm PT100, and 1 ohm
leads, nominal added-network error is about +0.144 C. Across 512 unique declared
model corners it is +0.1316 to +0.1572 C, within the allocated 0.22 C.

The calculation uses the same circuit solver, not an independent electrical
oracle. It also inherits that model's joint corner for both diagnostic 1 Mohm
parts; independent mismatch needs its own bound before final qualification.
Sent that condition to the circuit owner. Frozen model and result receipts are
in `zapote/rtd/unit/evidence/root-accuracy-network-01/`. Physical error remains
NOT RUN.

## Independent replay of the native defect/correction cycle

Verified all 72 retained file hashes in the owner's native-open-correction
receipt, then ran its frozen Rust binary against both native inputs. Both
reports reproduce exactly. The broken RTDIN− segment adds the required
`ERC.RTD.NATIVE_CONNECTIVITY` finding for `rtd_sense_n`; the agent-authored
restoration removes exactly that finding and adds none. Other baseline
findings remain unchanged. This is concrete native editing through Rust
feedback and correction, not a final whole-unit pass. Root replay reports
and receipt are under `zapote/rtd/unit/evidence/root-open-correction-replay/`.

## Return-plane correction corroboration

Independent Shapely inspection of native filled polygons found the In2 ground
absent at the B-layer clock crossings (30,18.6) and (31,18.6) in source04. The
owner's explicit CS move to F.Cu restores In2 ground at both coordinates in
return-correction-01; CS native trace layers change from F.Cu/In2.Cu to F.Cu
only. New board hash is
`6d4ba04aeeb958253d014a40967dc679a5cae1e47af646f201efec5d8a63a863`.
This confirms removal of the identified cut, not full route-corridor acceptance.
The prior independent 47-finding centerline triage is retained at
`/private/tmp/rtd-root-return-triage/receipt.json`; it distinguishes genuine
crossings from endpoint antipads and small native polygon margins. Final Rust
return coverage must bind the appropriate reference layer to each signal layer
and preserve legitimate local transition geometry without allowing remote slots.

## Stable circuit observation handoff replay

Verified the 37 canonical circuit import hashes, froze the producer and its nine
hashed inputs, and independently reproduced the ten-record observation JSON
byte for byte (SHA-256
`74e1187aabcd2f85e615866358f673a60e230f19d74d0bcfff5a0e6ee681fed8`).
The producer rejects missing FORCE+ endpoints, a nonfault open margin, a
nonfault short margin, and a missing healthy-to-short transition. Retained
inputs, executable check, replay and rejection receipt are under
`zapote/rtd/unit/evidence/root-circuit-final-review/`.
This establishes reproducibility and these specific negative controls. It does
not substitute for the final Rust acceptance run, independently prove every
model assumption, or change the physical status from NOT RUN.

## Local rail-loss timing: evidence and acceptance scope

The official TPS3890 Rev A timing table supplies a nominal 18 us falling
SENSE-to-RESET delay at 3.3 V, CT open and 5% input overdrive; its maximum
column is blank. Extracted text, rendered page 5, source digest and conditions
are retained in `zapote/rtd/unit/evidence/root-tps3890-timing/`. This is not a
worst-case timing guarantee and must not be entered as one in Rust inputs.

The standalone plan permits stated engineering model assumptions and defers
physical shutdown timing. Local-rail threshold/logic ownership can be evaluated
separately from timing characterization. However, the inherited RTD safety
specification's transient section explicitly includes fast and 10 ms brownout
ramps in its modeled under-100 ms chain. That requirement is not probe-only.
A conditional nominal model and an explicit allocated response budget may
support this layout handoff; they do not close guaranteed runtime behavior.
The absent guaranteed maximum must remain a named characterization/integration
obligation, with redesign required if the allocated bound cannot be met.

## Final standalone acceptance

The coordinator accepts the standalone RTD design/layout milestone. The final
requirement-by-requirement record is `zapote/rtd/unit/ACCEPTANCE.md`. All 90
canonical and 102 frozen owner-receipt hashes were independently checked; three
final DRC/parity reports and ERC are clean on unchanged inputs. The final Rust
report reproduces exactly; the same executable yields 14 return findings on the
earlier board and none on the corrected board. The exact local-brownout physical
timing indeterminate is retained, with no generic missing-input exemption.
Additional root mutation tests reject incorrect/late fault observations and
missing ground vias; omitted SENSE+ evidence remains a required-input gap.

Physical tests, fabrication, purchasing and integrated cooker acceptance were
not performed or claimed. Parts availability is recorded for all 20 BOM groups;
comparator sourcing and the RREF channel remain build obligations. Each later
unit and eventual integration remain separate goals under the user's direction.
