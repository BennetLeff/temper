# Experiment 00R-O: local obstacle qualification passed

The next fixture is ready. **All 10 obstacle controls and all 23 prior routing
controls pass. No Muse obstacle trial has run.** Automatic approval review
rejected the external preflight because it considered the synthetic keepout
experiment outside the prior routing-fixture authorization. The command never
started and no obstacle data was sent.

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

The prepared experiment remains one inspection preflight followed by three
fresh repetitions, five minutes and ten edits each. Both required physical
connections and zero applicable DRC findings are necessary to pass, with a
separate host check. U3.5 remains the sole deliberately open connection.
No unseen geometry, routing recovery by an agent, or manufacturing readiness
is claimed. A successful local witness proves feasibility and validates the
measurement path; it does not predict the model's result.

## Run after obstacle-payload approval

```sh
python3 harness-lab/run_zen_trials.py harness-lab/runs/obstacle-zen-preflight-01 \
  --routing --routing-fixture e00r-obstacle --preflight \
  --qualification harness-lab/evidence/obstacle-qualification.json
python3 harness-lab/run_zen_trials.py harness-lab/runs/obstacle-zen-scored-01 \
  --routing --routing-fixture e00r-obstacle \
  --qualification harness-lab/evidence/obstacle-qualification.json \
  --preflight-receipt harness-lab/runs/obstacle-zen-preflight-01/results.json
```

Use fresh directories for any later batch; never retry a scored outcome to
success. Requalify after changes to source, contract, fixture or evaluator.
The fixture can be rebuilt once into a new directory by `build_obstacle.py`
with KiCad's bundled Python; rebuilding creates new native object identities
and therefore requires a new frozen contract and qualification.
