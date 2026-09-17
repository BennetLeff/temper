# PFC experiment campaign: broad search with independently checked evidence
Created: 2026-09-17

Status: instructions ready for coordinator review and preparation; no campaign
experiments have been run. This plan authorizes no purchase, fabrication or
powered bench operation. Those require a separate qualified physical test plan.

## Start here

Give the coordinating agent this file. Give each worker the complete
[worker instructions](2026-09-17-pfc-experiment-campaign/WORKER.md), exactly one
record from [the task registry](2026-09-17-pfc-experiment-campaign/tasks.json),
and a coordinator-issued dispatch packet. Do not send a worker just its title.
The task registry is a catalog, not an instruction to launch all 26 immediately.
Use [the result template](2026-09-17-pfc-experiment-campaign/result-template.json)
and [the checker specification](2026-09-17-pfc-experiment-campaign/CHECKER.md).
These JSON documents are draft interfaces to implement in G0; they are not an
already installed executable harness.

One worker owns one experiment. A coordinator owns scheduling, frozen inputs,
review and integration. Start with G0 (campaign runner/checker preparation),
R0 (baseline verification), M065/M090 (magnetic candidates), and B-TI/B-INF
(reference applicability). Source-only tasks may run while G0 is prepared.
Do not dispatch numerical variants until G0 and R0 are accepted.

All tasks have explicit output artifacts and stopping rules. A valid answer may
be INDETERMINATE or a demonstrated infeasibility. Missing evidence must never be
turned into a numerical win merely to complete a task.

## Objective and boundaries

Find materially different, credible ways to improve the cooker PFC assembly's
loss, volume, cost and complexity. Avoid optimizing only the existing switch,
frequency or footprint. Preserve safety, electrical interfaces and the 15 A
true-RMS input ceiling. Determine a shortlist for further modeling and eventual
hardware qualification, not a production-ready winner or a guaranteed global
optimum.

The previous research is at commit
`1e0d8132d66e16027bbe4f6b21844b2d208b87d2` and
`zapote/power-entry/loss-budget/options/architecture-comparison/RESULTS.md`.
The conditional baseline is buffered IPW65R045C7/UCC27624, 12 V nominal drive,
4.7 ohm external gate resistor, 400 V bus, 180 µH effective L and
129107.39198576905 Hz. Its nominal no-assist partial switch/gate loss is
45.502337474982966 W. This is not a measurement or a whole-assembly loss.

The retained report is
`zapote/power-entry/loss-budget/options/experiment-02/evidence/report.json`,
SHA-256 `3805a41c953ae04dec3f65084de51a153e048d9ac4abfd204a8c52abde26749c`.
The current PCB still uses STW65N65DM2AG; the buffered C7 is an experimental
candidate. Neither the baseline nor a winning experiment silently edits CAD.

### Fixed comparison contract C1

- Input lines: 108, 120, 132 Vrms. Use the maintained project's 60 Hz reference;
  G0 must verify the source frequency before freezing C1, or record a discrepancy.
- Bus target: 400 V. Do not substitute the older 389.615 V control calculation.
- Requested nominal real input power: 1796.31003212911 W.
- Input current ceiling: 15 A **true RMS including ripple**.
- Per line, solve the waveform model for the requested real power. If reaching
  it requires more than 15 A, evaluate at 15 A and record the achieved power and
  derating. Do not assign P/V as the true-RMS current. At 108 V, full nominal
  power is infeasible even at ideal PF; preserve that derating.
- Every case records achieved Pin, Idc/Pdc if available, all relevant waveform
  moments, and loss boundaries. Do not equate wall input, bus output and pan power.
- Default load fractions: 0.2, 0.5 and 1.0 of nominal requested input power.
  These are exploration points, not newly approved product operating requirements.
  An unsupported CCM point is a model-domain gap, not a zero-loss result.
- Source-conditioned electrical screens at 25, 100 and 125 °C where source data
  applies. These are prescribed device evaluation temperatures, not predicted
  junction or ambient temperatures. Do not replace unavailable hot curves by
  Rds×2 and label the result 125 °C.
- Thermal candidates retain separate ambient, case, junction, contact, airflow,
  enclosure and cooling-power assumptions. A common ambient/cooling contract
  must be frozen before any temperature ranking. Until then, report electrical
  losses and required cooling only, with temperature/size totals unknown.
- Compare raw whole-assembly objectives without an invented weighted score.
  Absolute size/cost/efficiency targets are not established here. The coordinator
  records explicit user-approved budgets if available; missing budgets prevent
  final acceptance, but do not prevent exploring tradeoffs.

All C1 controls have a contract hash. Alternative topology tasks retain C1's
external power/current/bus interfaces, but must use their own correct internal
waveform/driver/control model. They cannot reuse single-boost moments by relabeling.
A lower-bus or 230 V architecture would require a new contract and downstream
inverter/coil comparison; it is not a C1 competitor.

## Why this search can escape the present narrow optimum

The registry allocates six conventional frequencies, three drive variations,
three package/technology candidates, three topology studies, three assembly-loss
studies, two magnetic sourcing tasks and two external-reference tasks. It also
reserves an interaction experiment and an independent finalist rerun.

This changes multiple structural choices without confusing their effects:

1. First compare one principal change at a time against frozen controls.
2. In parallel, examine interleaved, bridgeless and totem-pole architectures,
   even if conventional boost has not yet failed. This supersedes the previous
   narrow study's defer-topology rule for **research only**. No topology gets
   a dedicated solver or board merely because its initial story sounds better.
3. Combine promising compatible changes only in a declared factorial interaction
   experiment. Do not add isolated savings together.
4. Retain dominated-looking candidates when uncertainty could reverse the ranking.
   Revisit an earlier pruning decision when new evidence changes its assumptions.

A batch of 2,916 variations of the same uncertain gate model is one family of
sensitivities, not 2,916 independent physical experiments. More agents sharing the
same model do not create independent validation.

## Preparation gate G0: required before numeric fan-out

The current `zapote-pfc-drive-experiment` binary accepts only a source manifest
or `--replay SOURCE REPORT`. It has no generic frequency/inductance experiment
flags. Its adapter hardcodes L, bus, profiles and the scenario grid in
`zapote/packages/zapote-harness/src/pfc_drive_experiment.rs`.
Do not tell workers to run invented CLI arguments or change these constants in
many independent forks.

Assign one implementation owner to add a minimal Rust campaign adapter and
checker. Reuse `zapote-erc::pfc_currents`, `pfc_losses`, `pfc_switching` and the
existing assurance separation. Do not rebuild placement/routing or create a
second Python engineering model. The future command names and input schema are
chosen and documented by G0; this plan does not pretend they exist today.

G0 delivers:

- Validated per-case input manifests with units, source-conditioned quantities,
  independent on/off gate paths, explicit frequency and effective inductance,
  finite/domain validation and a fixed list of expected case IDs.
- A bounded matched-power true-RMS solve on [0,15 A], with residual and iteration
  limits. At a model-domain boundary return UNSUPPORTED, never extrapolated PASS.
- Content-based identity of raw sources, input, model source, executable, tool
  version, waveform logs and results. Requested inputs and actual solver inputs
  must both be serialized and compared; editing a title must not change identity.
- Replay, baseline parity and semantic/mutation checks in CHECKER.md. Historical
  experiment01/02 evidence and numerical/serialized behavior remain unchanged.
- Separate finding dimensions: numerical correctness, input/source applicability,
  assembly completeness and physical qualification. No model-only task can
  promote itself to measured or hardware-qualified.
- A documented executable invocation using an explicit binary path. The coordinator
  builds once, records its SHA-256, and issues that binary/read-only baseline to
  numerical workers. A runner that cannot express a task returns UNSUPPORTED.
- Focused Rust tests, independent analytical anchors, mutation receipts, retained
  replay and the repository's common `check-units` run on maintained candidates.
  Use actual commands documented by the implementation; resolve missing commands,
  do not invent flags. Run repository gates applicable to changed files.

G0 passes only after coordinator review of actual files and behavior. Until then,
this campaign has instructions, not an enforcing harness. Reserve production
Rust changes for this owner; ordinary experiment workers own data/reports only.

## Scheduling and isolation

The registry contains 26 tasks, of which G0 is infrastructure and R0/V0 are
verification. Every registry record has a task kind; research completion is never
confused with numerical or physical acceptance.

| Wave | Work | Gate |
| --- | --- | --- |
| Preparation | G0, M065, M090, B-TI, B-INF; R0 after G0 | Freeze C1, baseline and checker; accept actual baseline replay |
| Breadth A | F030/F045/F065/F090/F129/F180; L-BRIDGE/L-DIODE/L-AUX; A-INTERLEAVED/A-BRIDGELESS/A-TOTEM | Numerical tasks require G0/R0; source/architecture tasks can begin earlier |
| Breadth B | D12/D15/D-SPLIT and K-SILICON/K-SIC15/K-SIC18 | Coordinator freezes a reference design from Breadth A and publishes its exact hashes |
| Interaction | X1 | Select at most two compatible changes and freeze all four factorial cases |
| Verification | V0 | Independent reconstruction/rerun of baseline and up to three shortlist candidates |

No worker chooses the shared Breadth B reference. Default preference is the
90 kHz branch only if it survives evidence review; otherwise the coordinator
issues an explicit alternative. This dependency prevents each worker optimizing
against a different unreported baseline.

- Create one ordinary, fully populated isolated git worktree and `codex/` branch
  per task from a coordinator-approved revision. Do not copy a live dirty tree.
  No `git stash`, no shared working-directory edits. Keep the existing shared
  Cargo cache convention; do not create many compilation caches.
- Prebuild binaries and serialize shared builds. Do not let 20 agents concurrently
  rebuild the same extension environment. Gmsh/Elmer jobs have a separate bounded
  compute queue; model/provider parallelism does not imply unlimited solver slots.
- Default concurrency: four source/research agents, two numerical workers, one
  shared build or heavy FEM job. These are conservative scheduling defaults,
  not hardware-performance findings. Increase only after measuring contention.
- Default research attempt: 60 minutes, at most three candidate parts and eight
  primary sources. Numeric attempt: 90 minutes, at most 48 solver invocations
  including failures, controls, refinements and diagnostic reruns. No automatic
  budget extension. G0 gets a separate 4-hour implementation/review budget and
  checkpoints; expiry preserves work and returns a handoff, not a false completion.
- Coordinator writes an actual UTC deadline and unique attempt ID into each packet.
  Agents without those fields must not start. At 75% budget consumed, preserve
  current files and emit a checkpoint; at expiry, return whatever evidence exists.
- One rerun may diagnose a tool failure, within budget and with a new invocation
  ID. Restarted agents get new attempt directories; preserve failed attempts.
  Interrupt/close terminal children. A chat summary alone is not a handback.

## What every experiment must retain

Use a unique directory
`zapote/power-entry/loss-budget/campaign/runs/<campaign-id>/<task-id>/<attempt-id>/`.
No worker edits another run, the registry, the baseline or acceptance thresholds.

Required artifacts:

- `dispatch.json` plus complete delivered prompt, contract, registry-record and
  memory-note hashes, requested provider/model/reasoning and actual receipt where
  available. Unknown served identity stays null; preparation is not delivery.
- `inputs.json`: complete applied conditions, exact candidate parts and source
  references. Retain primary PDFs/curves or a source-capture failure record.
- `cases.json`: predeclared complete case list including controls and stress points.
- `raw/`: solver inputs, stdout, stderr, exit codes, versions, timestamps and
  actual outputs. No regenerated summaries replacing missing raw evidence.
- `result.json`: structured result from the template with explicit unknowns.
- `REPORT.md`: question, one change, method, results, failure/uncertainty and
  next evidence; no more than 150 lines plus source tables.
- `manifest.json`: full hashes of delivered evidence and dependencies. Hash after
  file closure; exclude itself from its contents. Do not claim a clean revision
  when changed model source was used; hash those bytes and record dirty=true.

Download failure is not evidence absence: record the difference. A PDF signature
or hash is not proof of correct part/revision/test conditions. Review the contents.

## Common assembly ledger

Every candidate includes the same term list, even when most values are null:
MOSFET conduction; switching/commutation; gate-network and driver static;
boost diode; input bridge/rectification; inductor DC/AC/core; shunt; bulk and
other capacitor ESR; EMI components; PCB/vias/fuse/connectors/relay/NTC;
controller and auxiliary conversion; cooling electrical power.

Each term has accounting boundary, source conditions, evidence class, nominal
value or null, justified uncertainty or null, and possible overlap with other
terms. Gate-network heat is not all MOSFET-die heat. Measured Eon/Eoff may already
include Eoss and diode recovery; do not add those again. Loaded driver supply
current may already include Qg*f. Rectifier removal is not a free subtraction:
include added switches, drivers, control, commutation and EMI effects.

`total_loss_w` remains null if any required term is unknown or overlapping.
A supported subtotal may be reported with its exact coverage list. Unknown terms
must not be encoded as zero. Whole-assembly mass/volume/cost stay null without
an accounted assembly (including cooling, auxiliary supplies and magnetics).

## Comparison, pruning and promotion

1. Validate evidence before comparing values. Classify INVALID evidence separately
   from a valid model result showing a violated constraint. Both remain recorded.
2. Group only cases with the same external comparison contract. Derated cases are
   a separate group; never reward a candidate for processing less power.
3. Use Pareto comparison on loss, volume, cost and control/protection complexity.
   Unknown dimensions imply unresolved dominance, not a favorable value.
   An estimated interval is not a statistical confidence interval unless supported
   by a sampling model; sensitivity endpoints are not guaranteed physical bounds.
4. Prune a candidate only for a source-supported hard constraint or demonstrated
   dominance with comparable evidence and uncertainty. Do not use a missing curve,
   missing solver or first failed search as proof the architecture is bad.
5. Reserve all three architecture studies even if conventional variants appear
   promising. If their data is incomplete, preserve them as unresolved options
   with the cheapest discriminating next experiment, rather than declaring victory.
6. For shortlisted numeric candidates, require a reproducible control, valid
   energy accounting, justified source transfer and independently checked currents.
   Run X1 to find interactions. Run V0 to catch model/reviewer common-mode mistakes.
   Before optimizing, the coordinator seals two additional verification cases
   within the declared operating envelope and records their hashes. G0 checks
   their domain validity, but workers do not tune against their outcomes. V0
   reveals and evaluates them; domain gaps remain explicit. Holdouts check
   generalization of the implementation, not physical model truth.
7. Finish with up to three candidates, the uncertainties capable of reversing their
   order, and one proposed next experiment per unresolved dominant uncertainty.
   Final hardware selection requires approved product budgets and qualification.

Stop this campaign when scheduled tasks have terminal receipts and the shortlist
has passed coordinator review, or its explicit budget expires. Report coverage
(e.g. 18/23 exploration tasks complete), outstanding gaps and untested families.
Do not keep tweaking until a favored part wins, or describe a finite search as
proof of a global optimum. Do not fabricate an efficiency/cost cutoff to end it.

## Coordinator acceptance and learning

The checker in CHECKER.md is required for scalable execution. Human/strong-agent
review still checks physical applicability and source interpretation; machine
checks cannot establish that a cited curve means what a worker claims.

On a shared model/checker defect: pause affected numerical tasks, mark their
results quarantined, preserve bytes, repair the shared Rust owner with a failing
counterexample, issue a new model/checker revision, and rerun all affected cases
plus controls. Do not quietly patch each worker's totals.

A new useful lesson needs a cause, scope, counterexample and enforcement location.
Rules about acceptance become Rust regressions; explanatory advice becomes a
reviewed repository note. Publish memory revisions between waves, never mutate
old catalogs. Keep actual outbound prompt/delivery receipts and distinguish
reported memory use from observed helper use. See `zapote/skills/README.md`.

Coordinator closeout includes the complete task/attempt census, rejected results,
comparison groups, source coverage, uncertainty ledger, shortlist, next evidence
and exact git revision. Integrate only reviewed files, run relevant shared gates
when code changes, commit/push within existing authorization, and keep CAD/BOM
selection a separate explicit decision.

## Handoff and plan quality

Grounded in the retained architecture study, existing fixed-grid CLI and current
Rust APIs, not new solver runs. The task inventory and templates are instructions;
G0's enforcement remains unimplemented. No existing physical-validation gap is
closed by writing this plan.

The [planning review](2026-09-17-pfc-experiment-campaign/REVIEW.md) records
checked consistency and remaining execution inputs.

The standalone worker packet is the dispatch entry point. The checker specification
contains deliberately bad cases that must fail before bulk runs begin. A coordinator
must fill packet values and freeze the baseline; unresolved placeholders block
execution rather than being guessed by workers.

## Copyable coordinator instruction

> Read this campaign plan and its WORKER.md, tasks.json, result-template.json and
> CHECKER.md companions. Prepare the campaign with one isolated Luna worker per
> assigned task. Start G0 and the independent source-only tasks; gate numerical
> work on reviewed G0/R0 receipts. Fill every dispatch field, freeze exact inputs,
> issue absolute deadlines and preserve every attempt. Do not launch every task at
> once or let workers edit the measuring instrument. Review actual artifacts,
> enforce the checker, retain unknowns, reserve the architecture and interaction
> studies, and return a comparison with explicit untested regions. Close finished
> workers. Do not change production CAD/BOM or conduct powered bench tests under
> this instruction. Stop at the agreed campaign budget with an honest coverage
> census and a reviewed shortlist or an explicit unresolved comparison.
