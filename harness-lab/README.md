# Temper harness lab: placement and routing

Two small experiments use the real buck input capacitor C9 and regulator U3.
Experiment 00 places C9; Experiment 00R freezes that placement and routes its
two mapped connections. Existing optimizer code is shelved; this directory
imports none of it.

**All three scored placement trials passed using Muse Spark 1.3 Contributor
Free through OpenCode Zen.** They took 22, 49, and 81 seconds and used 1, 2,
and 2 placement edits. Read the [results and limitations](EXPERIMENT-00-RESULTS.md),
including an initial-feedback defect found after scoring and fixed locally.
The corrected tool chain passes **19 native qualification cases**, and all
three final boards also pass the corrected evaluator.

The user approved the Zen/Meta Contributor data terms on September 9. PCB
operations and validation run locally; model inference is hosted. The earlier
Codex/OpenAI proposal remains deferred. See [payload authorization](TRIAL-INPUTS.md).

## What is admitted

- U3 and C9 footprint geometry and pad/net assignments from Temper's PCB.
  The fixture records the source content hash and includes its own footprint
  library, project settings, rules, and outline.
- KiCad **10.0.4**: bundled `pcbnew` for native editing and coordinates;
  `kicad-cli` for a separate DRC process. The small adapter pins this version.
- One standalone Rust evaluator. It uses native coordinates, checks placement
  requirements and protected state, and interprets complete DRC evidence.
- Three tools: `inspect`, `place`, `check`. Python handles process/file/MCP
  plumbing; it contains no pad-transform, clearance, or distance implementation.

## Acceptance

C9 alone may change x/y and orientation (0, 90, 180, 270 degrees). U3 is fixed
at (10, 10) mm, 0 degrees, inside a 28 x 18 mm outline. All footprint geometry
must remain within that outline, without courtyard overlap. Copper clearance
is at least 0.2 mm. Both mapped pad-center distances are at most 5 mm:

| C9 | U3 | Net |
|---|---|---|
| 1 | 3 (VIN) | +15V |
| 2 | 1 (GND) | gnd |

The 5 mm threshold is an experiment constraint, not a manufacturer limit or
proof of electrical performance. The fixture has three intentionally open
connections; these are reported separately. A placement pass is not a
full-circuit DRC pass, routing success, or fabrication approval.

All three frozen bad starts must succeed in fresh trials, each within five
minutes and ten placement edits. No retry-to-success or human placement hints.
Missing, invalid, stale, disabled, or failed measurement cannot pass.

## Run locally

Prerequisites: KiCad 10.0.4, Rust/Cargo, Python 3, and Ruff. KiCad's bundled
Python is detected at the standard macOS installation path. Override
`TEMPER_KICAD_PYTHON` for another installation. `make` uses the repository's
shared Cargo target directory; `TEMPER_E00_JUDGE` can select a built evaluator.
Dependencies are locked; no old Temper packages or shared virtualenv are used.

```sh
make -C harness-lab build check
make -C harness-lab qualify OUTPUT=runs/qualification-new
```

On this Mac, the outer Codex shell sandbox caused `kicad-cli` to crash before
writing a report (`SwiftNativeNSArray: Array index out of range`). The native
qualification ran successfully through the approved local execution path.
The host records nonzero exits and never substitutes an empty report.

For a future Zen batch, first qualify the current source, then run an
inspection-only preflight. These commands create fresh evidence; the completed
batch is preserved in the results above and should not be replaced with retries.

```sh
python3 harness-lab/run_zen_trials.py harness-lab/runs/preflight-new \
  --qualification harness-lab/runs/qualification-new/qualification.json --preflight

python3 harness-lab/run_zen_trials.py harness-lab/runs/scored-new \
  --qualification harness-lab/runs/qualification-new/qualification.json \
  --preflight-receipt harness-lab/runs/preflight-new/results.json
```

The Zen runner requires a successful preflight with matching runner,
OpenCode executable, and qualification hashes. It isolates OpenCode's XDG
state, disables unrelated skills/plugins/tools, and records actual provider
traffic through a local relay admitting only the selected free model and the
three PCB tools. Preflight prohibits placement in the host. The original
`run_trials.py` Codex integration remains unverified and deferred.

Output directories must be new. Each run retains the initial/final board,
every action snapshot, request/response log, native DRC reports, shown model
transcript, model usage when supplied, and final host verification. Zen costs
are OpenCode-reported values, not independently obtained billing receipts.
Qualification binds the fixture, tools, and evaluator binary by full SHA-256;
changes require requalification.

## Why this is a harness experiment

The [YC notes](https://www.youtube.com/watch?v=n9xKblqyQ28) motivate the clean
environment and thin tool surface. The agent chooses placements; native tools
execute and measure them. No search optimizer is hidden in `place`.
[Chase's talk](https://sequoiacap.com/podcast/owning-your-intelligence-starts-with-the-harness)
motivates exact context at each decision: current pads, constraints, and
introduced/resolved findings. We reuse OpenCode as the general agent
runtime and build the PCB boundary and experiment recorder.
[Continual Harness](https://arxiv.org/html/2605.09998v1) motivates preserving
traces for a later outer refinement loop. This milestone deliberately stops
before implementing that loop or claiming learned improvement.

The routing increment is specified in [Experiment 00R](ROUTING-EXPERIMENT.md).
The broader plan is
[here](../docs/plans/2026-09-09-001-feat-buck-harness-experiment-plan.md).


## Routing increment 00R

The routing profile offers `inspect`, `route`, `remove_route`, and `check`.
The agent supplies every vertex; `route` replaces one net's copper with the
explicit polyline. It performs no snapping, path search, or repair. Width is
fixed at 0.25 mm on F.Cu. Both footprints stay fixed, and U3.5 must remain
unconnected. Three fresh repetitions use the same geometry and limits of
five minutes / ten routing edits each.

The Rust evaluator requires KiCad physical connectivity for both mapped
pairs, rejects unintended connections and unsupported copper, checks all
applicable native DRC, and verifies protected state. Raw saved track nets are
inventoried before KiCad's connectivity builder can propagate them. Empty
copper and a nominally correct net list cannot pass.

```sh
python3 harness-lab/qualify_routing.py harness-lab/runs/routing-qualification-new
python3 harness-lab/run_zen_trials.py harness-lab/runs/routing-preflight-new \
  --routing --preflight \
  --qualification harness-lab/runs/routing-qualification-new/qualification.json
python3 harness-lab/run_zen_trials.py harness-lab/runs/routing-scored-new \
  --routing \
  --qualification harness-lab/runs/routing-qualification-new/qualification.json \
  --preflight-receipt harness-lab/runs/routing-preflight-new/results.json
```

Use fresh output directories. The routing results and retained evidence are
reported in [Experiment 00R results](EXPERIMENT-00R-RESULTS.md).
