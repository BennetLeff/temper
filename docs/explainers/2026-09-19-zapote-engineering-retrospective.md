---
title: Why Zapote's PCB work slowed down, and the smallest useful corrections
date: 2026-09-19
input_shape: recap
subject: Temper and Zapote unit construction, power-entry loss and protection, and harness workflow
---

# What happened and what to change

We built useful board-editing and validation capability, found real electrical
defects, and then spent too much effort correcting claims and strengthening
process without closing the physical design. The recurring bottleneck was not
that agents needed a new placer or router. It was choosing experiments that
could change a decision, keeping the current circuit and evidence conditions
straight, and carrying those conditions into the coordinator's conclusions.

The current protected, thermally defensible passive power-entry milestone is
**not complete**. The [bounded follow-up](../../zapote/power-entry/passive-reva/REVIEW-2026-09-19.md)
separates the remaining design work from missing physical evidence. F2 and a
larger local reservoir are not in its CAD/BOM. This retrospective does not
reclassify that checkpoint as milestone completion.

## Evidence and scope

This review combines the supplied conversation, selected older task turns,
path-scoped Git history for September 9–19, the retained campaign reports,
current source files, and this coordinator's recent execution receipts. It is
not an exhaustive audit of every chat, PR, agent action or uncommitted attempt.
No labor hours or model-quality ranking are inferred from commit counts.

Older tasks examined: **Shift to harness engineering**, **Assess board loss
re-engineering**, and **Improve Temper harness traces**. Selected turns and
their identifiers are retained in [conversation evidence](evidence/2026-09-19-selected-task-history.json).
Their engineering assertions are historical statements, not current authority.
In particular, earlier loss and bound language was subsequently corrected.

## The useful progress

| Stage | Concrete result | What it did not establish |
|---|---|---|
| Initial harness trials | Agents repaired supplied route defects and combined placement/routing on U3/C9; three combined trials passed independent checks | General board capability or electrical qualification |
| Buck and standalone sensing/control units | Authored source, native boards, semantic/model checks and repeatable unit workflows | Whole-cooker integration or physical performance |
| Routed PFC section | Actual routing, source/native identity and current/domain checks; commit `6226537c9` retained clean native receipts | Installed cooling, surge/fault protection or safe release |
| Bridge and shunt studies | Real copper repair, independent thermal references, source-bound geometry and heat-path findings (`4e5ca1165`, `5bd51b46f`) | An installed assembly with known airflow and all losses |
| Loss campaign | Identified model degeneracy, cross-model disagreement, double counting and promising conditional alternatives | A qualified winning replacement architecture |
| Fault analysis | Refuted phantom voltage stress and exposed an internal stored-energy path bypassing F1/U12 | Fuse clearing or actual fault survival |
| Passive checkpoint | Preserved the GBJ baseline with source binding and honest unresolved protection/cooling | New protection copper or completed milestone |

The first trials are especially instructive. The older task recorded three
combined placement/routing trials at 133, 74 and 155 seconds, with three or four
edits. Success meant a small, fixed set of observations. Later work often
reported hundreds of tests, source captures or a finished report while the
engineering acceptance row remained unresolved. Those are different kinds of
progress. See [combined results](../../harness-lab/COMBINED-RESULTS.md),
[campaign arc](../../zapote/power-entry/loss-budget/campaign/ARC-SUMMARY.md), and
[passive verification](../../zapote/power-entry/passive-reva/validation/README.md).

## Where we lost time

### 1. The target changed without an explicit decision boundary

The original goal was an agent placing/routing individual cooker units while
Rust and KiCad evaluated them. Power-entry work then had to address circuit
efficiency, thermal assembly, surge behavior, destructive faults, and physical
qualification. Much of that work was necessary for the cooker, but it was no
longer the same experiment as demonstrating the layout harness.

The user repeatedly had to ask whether we were building a harness, finishing
one section, or qualifying the whole cooker. A routed candidate, a numerical
PASS and a physically defensible design were too often adjacent in the same
completion language. The [current milestone](../../zapote/power-entry/passive-reva/MILESTONE.md)
finally distinguishes them; keep that boundary instead of rewriting success
each time a new unknown appears.

**Change:** maintain one short milestone card with separate software/geometry,
circuit-design and physical-qualification rows. Every dispatch names which row
it can close. A new requirement may be necessary, but the coordinator must say
whether it is a current blocker, later qualification work or a separate study.

### 2. We launched comparisons before checking whether the model could decide them

The frequency campaign held `L·f` fixed and lacked the magnetic-loss input
needed for a meaningful optimum. Constant-drop passive comparisons could not
express the current-sharing benefit being investigated. Gross bridge loss was
initially treated as the available saving, before replacement losses and
integration obligations were accounted for. These problems were found after
work had been dispatched.

The corrected [architecture decision](../../zapote/power-entry/loss-budget/DECISION.md)
and [campaign closeout](../../zapote/power-entry/loss-budget/campaign/CLOSEOUT.md)
provide the better pattern: compare net benefit under matched conditions and
state which missing input can reverse the choice. The STW sensitivity and the
C7 independent result cannot be combined as if they describe one device; the
[accounting audit](../../zapote/power-entry/loss-budget/campaign/LOSS-ACCOUNTING-AUDIT.md)
already makes that explicit.

**Change:** before a campaign, run one cheap discriminating probe. Name the
decision, controlled conditions, uncertain term and outcome that changes the
next build. If the model is invariant or its missing term dominates the
decision, acquire that input or defer the comparison. Do not expand the sweep.

### 3. Summaries strengthened evidence that the underlying artifact had already limited

Repeated examples include a MOV maximum at one current becoming a lower bound
elsewhere, a normal-device resistance becoming a destructive-fault model,
source-bound sensitivities becoming bounds, and a conditional loss opportunity
becoming an architecture recommendation. Some worker results were defective;
some were correctly limited and the coordinator overstated them. Blaming the
workers alone would miss the failure mechanism.

This continued after the lessons were written. In this follow-up, the
[F2-open model](../../zapote/power-entry/active-rectifier/experiments/f2-open/MODEL.md)
still had a table claiming a startup-cycle upper bound that section 4 withdrew.
The table is now corrected. The [review skill](../../zapote/skills/electrical-model-review/SKILL.md)
also contains conflicting language: procedure step 7 says a pass means sound
derivations, while its limits correctly say only specific violations are
detected. Its fault-loop table similarly overstates a necessary terminal-net
check as a conduction check. These should be corrected in place, not answered
with another generic semantic validator.

**Change:** keep the evidence class, exact part, conditions and unresolved
inputs beside any number used to make a decision. Review the coordinator's
final receipt against the raw result, not just the worker's code. For a
withdrawal, search current decision tables and summaries for the old claim;
preserve historical evidence with an explicit supersession link. A narrow
report generator is justified only for repeatedly copied decision tables, and
must inherit conditions/status rather than manufacture stronger language.

### 4. We sometimes modeled the wrong artifact or transferred facts between variants

AR-BOUNDS was dispatched against `pcb/temper.kicad_pcb`, which lacked the
relevant PFC nets. The worker caught the mismatch and used the actual
shunt-repair board. Earlier route replay disagreed with saved copper widths.
The latest passive copy has a new source entry, but the common runner still
uses the maintained shunt-repair contract; the copy is separately bound and
byte-identical. The native export also retains a historical current-sense
schema label. All are explainable, but they impose repeated discovery work.

See [AR-BOUNDS corrections](../../zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/coordinator-receipt.md),
[passive reproduction boundary](../../zapote/power-entry/passive-reva/README.md),
and [source-entry dispatch](../../zapote/packages/zapote-erc/src/power_entry.rs).

**Change:** use an existing variant manifest as the dispatch anchor: authored
entry, native board, exact MPNs, stackup, required loop nets, source hashes and
validation command. Show these resolved identities before analysis. Check a
few circuit-specific anchors before a costly solve. Avoid another manifest
schema unless the existing one demonstrably cannot represent the variant.

### 5. Capturing memory did not ensure it changed the next action

The older **Assess board loss re-engineering** task explicitly reported a debug
run taking over 25 minutes and a release run taking about five, plus pcbnew and
display failures. The recent passive checkpoint repeated the debug mistake,
then stopped an optimized run after a test file changed during execution.
The coordinator owns those avoidable reruns.

The cause is more specific than “agents forgot”: [check-units](../../zapote/Makefile)
still invokes `cargo run` without `--release`, and always uses
`validation/units.json`. Meanwhile the current passive instructions require a
different manifest. The correct command exists in a report, but the normal
entry point does not encode it. [Memory delivery](../../zapote/skills/README.md)
already distinguishes stored, selected, submitted and actually used notes;
adding another note alone would repeat the same failure.

**Change:** make the routine runner accept an explicit maintained manifest and
use the appropriate optimized profile by default. Check native Python,
display access and libraries before the expensive replay using existing native
commands; do not build a new preflight framework. Freeze worker edits
before the final suite. Preserve the same validators and failure semantics;
speed comes from the right build and avoiding invalid runs, not skipping checks.

### 6. Review findings repeatedly became new harness projects

The Rust claims and fault-loop checks now catch useful concrete failure
classes. Independent PFC/geometry/thermal oracles also found real defects that
self-comparison missed. Those were valuable additions.

But the cycle became: find an overclaim → strengthen the ledger → discover a
new encoding escape → migrate evidence → review the checker. That displaced
the circuit work. The [harness freeze](../../zapote/power-entry/loss-budget/campaign/ARC-SUMMARY.md)
explicitly recognizes this. A valid ledger is still not proof of physical
truth, and no practical schema makes arbitrary engineering prose correct.

**Change:** retain the freeze. A new check needs a reachable incorrect
acceptance in the actual workflow, a current milestone consequence, and an
explanation of why existing review cannot handle it. Fix the narrow owner and
add a real negative case plus a nearby valid case with the intended diagnostic.
Do not expand a generic claims language to automate every review comment.

### 7. Delegation optimized for finished reports rather than integrated decisions

Bounded workers often did complete their assigned report while the parent still
needed a working circuit. “Done” was ambiguous. The current two Luna reviews
were useful precisely because they answered narrow questions, inspected actual
artifacts and stopped short of inventing missing evidence. They did not close
the protected-board milestone and are not counted as doing so.

**Change:** dispatch a deliverable plus an integration test and a decision it
must enable. Require the worker to distinguish implemented, evaluated,
unsupported and externally blocked items. Keep shared-CAD mutations sequential;
parallelize independent source review, circuit review and mechanical work.
Stop completed agents, integrate once, then run the final shared suite. If a
worker cannot close its row, the parent chooses a smaller useful artifact or
records the external dependency; it does not repeatedly redispatch “finish it.”

## Recommended changes, in priority order

These are proposals, not implemented harness changes. Reuse existing homes.

| Priority / home | Bounded change | Evidence that it helped |
|---|---|---|
| P0 — milestone card and `zapote/AGENTS.md` | Require a named acceptance row, exact variant and explicit design-versus-qualification status in each dispatch; apply the existing freeze | Next unit's handback maps to the original rows without a newly invented definition of done |
| P0 — `zapote/Makefile`, passive validation instructions | Optimized `check-units`, explicit manifest parameter; verify native setup with existing commands; final run only after edits stop | Same rule IDs, source hashes and findings as direct release invocation; no rerun caused by debug selection or coordinator edits |
| P0 — `electrical-model-review/SKILL.md` | Correct the two overstatements; explicitly review the coordinator's final receipt against raw results and current decision tables; link freeze from reporting instructions | Skill no longer claims general soundness/conduction; one reviewed report keeps every operative assumption attached |
| P1 — existing memory selection and dispatch records | Deliver a short applicable lesson set, including the current decision and superseded claims, rather than a growing incident anthology | Retained outbound prompt contains the relevant notes; observed tool choice or resulting artifact demonstrates use; no claimed benefit from delivery alone |
| P1 — existing source/native manifest and `power_entry.rs` integration | Resolve variant identity before expensive work; explicitly bind any new maintained source entry instead of silently borrowing a donor | Wrong-board fixture and source/native mismatch fail; actual passive graph passes; no unrelated donor-schema rewrite |
| P1 — repeated decision tables only | Generate numeric rows with part, condition, evidence class and status from the reviewed record; keep narrative reasoning reviewed | Changing a datum or withdrawing a bound updates the current table; historical raw receipts remain intact |
| Conditional — existing ERC/DRC owners | Add only demonstrated missing checks on current edited geometry/model paths, with independent oracle or analytic case and valid counterexample | A representative old defect fails for the intended reason while a correct neighboring case passes; coverage includes actual production inputs |

The first batch should be the first three rows. It is a small workflow repair,
not a new harness architecture. The remaining proposals wait until their actual
consumer is touched. Do not mix all seven into the next circuit revision.

ERC/DRC still matter: source-to-native pin identity, stackup, clearances,
physical connectivity and applicable current/thermal models are reusable.
However, more DRC checks will not reveal a missing AUX supply specification,
provide a fuse clearing curve, or measure installed airflow. Keep numerical
verification, applicability and physical qualification separately visible.

## What to stop doing

- No fresh optimization campaign until its deciding input and a useful
  comparison are identified. In particular, no transfer of a C7 switching
  result into an STW cooling budget.
- No full-suite rerun for a prose-only correction on unchanged source and CAD.
  Check links and contradictions instead; rerun affected behavior when it changes.
- No completion claims based on test counts, files copied or reports written.
  The passive checkpoint added 460 files, largely retained source/native/
  validation artifacts; that is evidence packaging, not 460 design improvements.
- No “single gating input” language when other independent acceptance rows
  remain unresolved. No assumption that an email, one specimen or a new curve
  qualifies a population or complete assembly.
- No claim that every reversal was waste. Rejecting a degenerate experiment,
  tracing the real fault loop and exposing the source of a false bound were
  necessary corrections. The avoidable part was overstating them again.

## How to tell whether we are improving

Use the next few comparable unit/ECO attempts, not another synthetic campaign.
Record time to first useful native finding; time in compilation/replay versus
agent reasoning; edits and reruns; acceptance rows actually closed; repeated
known incidents; and late changes to an approved circuit interface. Keep
physical wait time separate. Existing traces and run receipts already supply
much of this; add missing fields only when they answer a concrete question.

Before claiming a harness improvement, compare the same frozen fixture and
acceptance contract, identify model/runtime differences, and retain unsuccessful
attempts. Three tiny fixture successes do not prove generalization; neither do
hundreds of arithmetic tests prove a power supply. The useful outcome is fewer
avoidable retries and a verified engineering decision reached sooner.

## Immediate engineering sequence

Keep the passive GBJ baseline. Specify the actual auxiliary/gate-drive interface
and one coordinated F2-open protection circuit; review those interfaces before
routing another revision. Resolve switch loss with applicable evidence and then
bind the cooling assembly to that heat budget. Physical protection and installed
thermal acceptance remain physical-evidence work. The full requirements and
limits are in the [milestone](../../zapote/power-entry/passive-reva/MILESTONE.md).

This review intentionally does not choose new semiconductor or fuse parts,
authorize a powered test, or resume the active-bridge construction campaign.
