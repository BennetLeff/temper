# Experiment 00R-O: valid routes, one indeterminate run

**All three final boards pass independent native KiCad checks. Two trials
pass the full run audit; trial 2 remains indeterminate after two model-stream
read timeouts.** The strict three-clean-runs experiment criterion was not met.
The user explicitly approved the obstacle payload with “do it,” resolving
the earlier approval block before any request was sent.

| Trial | Elapsed | Edits | Run verdict | Independent board check |
|---|---:|---:|---|---|
| 1 | 76.72 s | 2 | Pass | Pass |
| 2 | 184.20 s | 2 | Indeterminate | Pass (supplemental, after run) |
| 3 | 91.02 s | 2 | Pass | Pass |

The inspection-only preflight passed in 6.65 seconds with zero edits. Each
trial ultimately chose the same bottom detour for +15V: descend from C9.1
to y=12.5 mm, cross below the keepout, then rise to U3.3. Each used one
`route` operation for that three-segment path and one for the direct ground
connection. All three finished with a passing PCB `check`. No agent changed
an already attempted route or used `remove_route`.

[Trial 1 diagram](evidence/obstacle-agent-trial-1.svg),
[trial 2 diagram](evidence/obstacle-agent-trial-2.svg),
[trial 3 diagram](evidence/obstacle-agent-trial-3.svg).
Diagrams use native copper coordinates and widths; pads are native bounding
boxes. Red marks the protected track keepout.

[Original scored results](evidence/obstacle-zen-results.json).
[Preflight](evidence/obstacle-zen-preflight.json).
[Complete model/native traces](evidence/obstacle-zen-traces.tar.gz).
[Trial 2 supplemental board check](evidence/obstacle-trial-2-offline-check.json).
[Trial 2 supplemental action audit](evidence/obstacle-trial-2-action-audit.json).

## Why trial 2 is indeterminate

The local recording relay's 60-second read timeout fired on responses 2 and
3. Both had HTTP 200 but ended before a `response.completed` event. Requests
2, 3 and 4 contain identical input histories: the runtime reissued the
request after the interrupted streams despite the configured provider
`maxRetries: 0` option. The exact upstream cause is not established.

The model later completed the two routes and its final PCB check, exiting
normally within the five-minute trial limit. The frozen scorer nevertheless
rejected the run because the provider trace contains wire errors. We retained
that verdict. A separate post-run check confirms its final board is valid,
and a supplemental action/observation/snapshot audit passes; neither proves
the incomplete provider streams were complete nor converts the run to a pass.
No scored trial was rerun, and the apparatus, budgets and hints were unchanged
during the batch. The two internal request reissues remain in the archive.

Trials 1 and 3 pass the exact model/tool/wire/action audits and independent
host checks. OpenCode reports $0 for their completed free-model runs; the
incomplete requests in trial 2 do not supply complete usage receipts.

## What changed

One native KiCad track keepout occupies (7.55, 10.5)–(7.95, 12.0) mm on F.Cu.
It blocks the direct +15V connection between C9.1 and U3.3. U3/C9 placement,
pad nets, ground connection, width, tool schemas, budgets and Rust acceptance
remain the same. Inspection now includes native keepout polygons. The tool
adapter performs no obstacle avoidance or waypoint search.

The keepout is protected with the rest of the board. Native KiCad DRC reports
`items_not_allowed` when copper enters it. Deleting or disabling the keepout
removes that DRC finding but still fails protected-state acceptance. Track
width matters: the control whose centerline clears the region by 0.05 mm
fails because its 0.25 mm copper width still overlaps.

[Local detour witness diagram](evidence/obstacle-witness.svg).
This diagram uses native track coordinates and widths; pad rectangles are
native bounding boxes. The witness is manually scripted qualification data,
not an agent result, and is excluded from model inputs.

## Evidence and limits

Ten controls cover the blank board, native keepout context, the rejected
direct route, three valid-detour checks, width intrusion, keepout deletion
and disabling, and real tool feedback during repair/removal/replacement.
All 23 previous routing controls also pass. The Rust unit tests (2), Python
boundary tests (10), lint, formatting and compilation checks passed.

[Obstacle qualification](evidence/obstacle-qualification.json).
[Prior routing regression](evidence/obstacle-routing-regression.json).
[Retained local traces](evidence/obstacle-local-traces.tar.gz).
[Prepared model inputs](evidence/obstacle-trial-inputs.json).
[External execution status](evidence/obstacle-model-status.json).

The experiment used one inspection preflight followed by three fresh
repetitions, five minutes and ten edits each. Both required physical
connections and zero applicable DRC findings are necessary to pass, with a
separate host check. U3.5 remains the sole deliberately open connection.
This demonstrates route planning around one known synthetic obstacle on a
fixed two-footprint fixture. It does not demonstrate generalization, repair
of a rejected copper attempt by the agent, or manufacturing readiness. The
valid local witness was used only to qualify the apparatus and was not sent
to the model.

## Reproduce in a separately declared future batch

```sh
python3 harness-lab/run_zen_trials.py harness-lab/runs/obstacle-zen-preflight-new \
  --routing --routing-fixture e00r-obstacle --preflight \
  --qualification harness-lab/evidence/obstacle-qualification.json
python3 harness-lab/run_zen_trials.py harness-lab/runs/obstacle-zen-scored-new \
  --routing --routing-fixture e00r-obstacle \
  --qualification harness-lab/evidence/obstacle-qualification.json \
  --preflight-receipt harness-lab/runs/obstacle-zen-preflight-new/results.json
```

Use fresh directories for any later batch; never retry a scored outcome to
success. Requalify after changes to source, contract, fixture or evaluator.
The fixture can be rebuilt once into a new directory by `build_obstacle.py`
with KiCad's bundled Python; rebuilding creates new native object identities
and therefore requires a new frozen contract and qualification.


## Next issue to address

Investigate interrupted model streams and make the retry policy explicit
before increasing PCB complexity. Test that behavior with local fault
injection, keeping wire completeness and board validity distinct. Any policy
change needs requalification and a new declared batch; do not rescore this
batch under a relaxed rule. The routing tools themselves produced the
required detours without a hidden router or an agent refinement policy.
