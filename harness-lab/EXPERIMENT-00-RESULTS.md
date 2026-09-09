# Experiment 00: Muse Spark places C9

On September 9, 2026, Muse Spark 1.3 Contributor Free through OpenCode Zen
completed all three frozen U3/C9 placement starts. Each final board passed the
native KiCad/Rust evaluator and a separate host verification. No scored trial
was retried, and no coordinates or corrective hints were supplied by a human.

| Trial | Initial C9 (x mm, y mm, degrees) | Seconds | Placement edits | Final C9 | Mapped distances (mm) | Result |
|---|---|---:|---:|---|---|---|
| 1 | 22, 15, 0 | 22.10 | 1 | 6, 10, 90 | 2.910 / 2.910 | Pass |
| 2 | 22, 5, 180 | 49.43 | 2 | 13.8, 10, 90 | 4.965 / 4.965 | Pass |
| 3 | 16, 16, 270 | 80.75 | 2 | 5, 10, 90 | 3.898 / 3.898 | Pass |

Budgets were five minutes and ten placement edits per fresh session. All
reported model costs were $0 under the free Contributor offer; this is
OpenCode's accounting output, not an independently obtained billing receipt.
Zen's response metadata reported `muse-spark-1.3-contributor-free` throughout.
The installed OpenCode version was 1.18.29; its executable hash is recorded.

## What the agent actually did

Trial 1 chose a valid placement directly. In trial 2, the first placement
at (13.5, 10, 90) caused courtyard overlap. The agent moved C9 to (13.8, 10, 90)
and cleared it. In trial 3, the first placement at (5, 10, 0) left one mapped
pad too distant. The agent rotated C9 to 90 degrees and cleared the finding.
Every trial ended with an explicit `check` call and a final answer.

The agent saw only `pcb_inspect`, `pcb_place`, and `pcb_check`. The local
recorder checked the actual outgoing tool names, schemas, descriptions, and
model ID before forwarding each request. Post-run verification matched the
provider's requested calls to OpenCode's executed calls, the actual tool
outputs sent back to the provider, and the native action/snapshot log.
KiCad, board mutation, evaluation, and evidence storage ran locally.

## Defects discovered, without rewriting the evidence

The first inspection preflight failed at the second model request: OpenCode
sent server-side item references that Zen could not resolve. Setting the
model option `store: false` made OpenCode send the complete conversation.
This is a protocol setting, not an opt-out from Meta's Contributor data terms.

The second preflight solved the placement despite an inspection-only user
instruction. It is retained as an unsuccessful preflight and unscored
integration attempt. The final preflight used explicit inspection-only system
instructions and a host that rejected placement. It passed in 9.54 seconds
with exactly one inspection and zero edits. The scored runner was frozen
after that successful preflight.

After scoring, trace review found a **validator feedback defect**: native KiCad
reports 270 degrees as -90 degrees. The original evaluator incorrectly added
`unsupported_orientation` to trial 3's initial findings. Thus this batch
contains imperfect initial feedback and should not be described as a clean
comparison of harness strategies. All three final poses were 90 degrees,
and their acceptance was unaffected.

A new real-KiCad case reproduced the false rejection on an otherwise valid
(5, 10, 270) placement. Rust now normalizes angle equivalence modulo 360;
the native geometry adapter is unchanged. The corrected apparatus passes
19 qualification cases. All three saved final boards were checked again
locally with the corrected evaluator and passed. No model trial was rerun.

## What this supports

The tiny agent/tool loop works for this task: the agent can choose placements,
read native feedback, repair a failed attempt, and verify the saved result.
The [YC harness discussion](https://www.youtube.com/watch?v=n9xKblqyQ28)
motivated the clean environment and three-tool surface. The overlap repair
is a concrete example of feedback reaching the agent at its next decision,
as emphasized in the [Chase talk](https://sequoiacap.com/podcast/owning-your-intelligence-starts-with-the-harness).
The preserved trajectories are development data for a later outer refinement
loop, as proposed in [Continual Harness](https://arxiv.org/html/2605.09998v1).

This is three starts of one two-footprint geometry, not unseen circuit
generalization or evidence that a refiner improves performance. No baseline
comparison or learned refinement was run. Passing means meeting the frozen
placement thresholds, not finding the best placement: trial 2 is close to
the 5 mm limit. Three intentionally open connections remain outside scope.
Routing, electrical performance, fabrication readiness, and the full Temper
board are untested by this experiment.

The next proposed increment is to route the two capacitor connections in
this fixture, with explicit copper-edit operations and connectivity checks.
That increment has not been implemented or run.

## Evidence and reproduction

- [Original scored results](evidence/zen-e00.json)
- [Corrected-evaluator final-board checks](evidence/zen-e00-corrected-checks.json)
- [Corrected apparatus qualification](evidence/qualification-rotation-fixed.json)
- [Native qualification archive](evidence/qualification-rotation-fixed.tar.gz)
- [All three preflights, scored trials, and regression evidence](evidence/zen-e00-traces.tar.gz)
- [Runner](run_zen_trials.py) and [boundary tests](test_zen_runner.py)

The original apparatus is recoverable from local commit `57cd7c71f`; its
qualification receipt and archive remain unchanged. Run manifests bind the
original source/evaluator hashes and the scored runner hash. The corrected
qualification is a separate receipt. The trace archive retains failed
preflights and the failing rotation regression, along with all trial boards,
native reports, actions, model events, and provider request/response bodies.
It does not contain authorization headers.

The production PCB was not edited. No repository push or publication was
performed. The user's authorization covers sending the U3/C9 experiment to
Zen/Meta under the Contributor terms; the earlier Codex/OpenAI proposal
remains deferred.
