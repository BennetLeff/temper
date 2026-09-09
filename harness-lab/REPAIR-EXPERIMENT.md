# Experiment 00R-R: repair seeded copper defects

Accepted September 9, 2026: the user said “ok continue” to the proposed three-case repair experiment. This uses the approved Muse Spark 1.3 Contributor Free model through OpenCode Zen and its accepted Contributor training terms. PCB operations remain local. No model or provider fallback is admitted.

## Frozen plan and acceptance

Use the same U3/C9 geometry, protected native keepout, pad nets, 0.25 mm F.Cu tracks, four tools, Rust judge and KiCad validators. Prepare three different starts, each containing both nets' copper:

1. `a`: +15V crosses the keepout; ground is valid.
2. `b`: +15V violates copper clearance; ground is valid.
3. `c`: +15V takes a valid detour; ground has a physical gap, retaining correct net labels.

Qualify each start locally: its intended native finding must be present, protected state must match, and an explicit scripted repair must resolve the finding and pass independent evaluation. The reference repairs are qualification inputs only, excluded from model inputs. Reject unknown starts or changed initial-board bytes before execution.

Run one inspection-only preflight on start a, then one fresh scored trial per start, sequentially. The same tools/host profile serve all three; qualification covers every start. Do not give defect names, diagnosis prose, reference paths or repair coordinates to the model. It receives the existing task prompt, native inspection and normal tool feedback. Freeze apparatus hashes before preflight; no changes during the scored batch and no retry-to-success.

**Pass:** all three trials meet the unchanged complete wire/action audit, independent final-board acceptance, five-minute and ten-edit limits. Additionally, each must begin with inspect showing the intended initial failure, perform at least one route edit, and record resolution of the initial defect IDs. Protected state, including footprints, nets, keepout and rules, stays fixed. Incomplete evidence is indeterminate and cannot satisfy batch acceptance.

Record initial findings, resolved findings, requested vertices, copper changes, all snapshots, final boards, elapsed time and reported cost. Evaluate any stream failure separately without changing its run verdict.

## Harness connection and limits

This exercises the thin interface and timely, native feedback from the YC and Chase notes: inspect an invalid state, act, observe the result, and reach a validated state. It adds no automatic repair or hidden route search. Traces are material for a later refinement loop; this experiment does not implement that loop.

These are three seeded failure cases, not a held-out generalization set or an ablation proving feedback causality. An agent may replace an entire net's route, or both routes; minimal copper changes are measured rather than required. Recovery from a supplied bad route is distinct from recovery after the agent's own failed attempt. Passing does not qualify this circuit for fabrication.

## Implementation

- Generate three native fixture directories and pin initial hashes in one repair contract.
- Add the repair fixture profile and select its frozen start in `routing_host.prepare`; keep tool schemas and prompts unchanged.
- Add a local repair qualification and a repair-specific action-evidence check to the runner.
- Run boundary/stream tests, 10 obstacle controls, 23 routing regression cases, and repair qualification before external execution.

## Results

All three scored repairs passed, in 85.11, 61.41 and 25.96 seconds, with one copper edit each. The original valid net remained intact in each trial. See [results, limitations and retained evidence](REPAIR-RESULTS.md).
