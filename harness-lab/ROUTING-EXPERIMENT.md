# Experiment 00R: two capacitor connections

Build the next increment in the existing harness lab. Keep U3 and C9 fixed
at the first successful placement: U3 (10, 10, 0 degrees), C9 (6, 10, 90).
Run three fresh repetitions of this same geometry, not three unseen circuits.
Use the approved Muse Spark 1.3 Contributor Free model through OpenCode Zen.

## Frozen task and pass/fail criteria

Connect C9.1 to U3.3 (+15V) and C9.2 to U3.1 (gnd) using 0.25 mm straight
track segments on F.Cu. The width is an experiment constraint, not a validated
power-current rating. No vias, zones, arcs, footprint moves, net changes, or
connections to other pads. U3.5 remains outside this task even though it is
also on +15V. The board outline and all existing rules remain protected.

Every accepted result must have both required pad pairs connected through
actual copper according to KiCad's rebuilt connectivity, no unintended pad
connections, no applicable native DRC findings, all track copper inside the
outline, and the original placement requirements still satisfied. Empty
copper, correct net labels alone, missing reports, and unmeasured claims
cannot pass. Native DRC's remaining U3.5 open connection is reported explicitly.

Each scored repetition has at most five minutes and ten routing edits,
including removals. Each route contains 2–12 explicit vertices; no more than
22 segments total. All three repetitions must pass, ending in a successful
check and a separate host verification. No human routing hints, trial retries,
or policy changes during the scored batch. Preserve failures as evidence.

## Tool surface and implementation

- `inspect`: native pad geometry, current tracks, connectivity, and findings.
- `route(net, points_mm)`: replace that net's current copper with the exact
  supplied polyline. The agent selects every vertex; the adapter performs no
  routing search, snapping, shove, or repair.
- `remove_route(net)`: remove that net's tracks for recovery.
- `check`: reload, measure connectivity, run native DRC, and evaluate in Rust.

Extend the qualified host with explicit adapter/session hooks, and reuse its
recording, budgets, atomic edits, DRC environment, and MCP transport. A thin
pcbnew adapter creates/removes tracks and obtains native connectivity.
Rust owns acceptance. Freeze footprints and sidecars by content hash; exclude
only inventoried tracks from the routing protected-board hash. Preserve E00
placement behavior and its historical evidence.

The OpenCode runner selects the routing task explicitly. Its request guard
admits only the approved model and these four exact tool schemas. Match
provider requests, returned observations, action logs, and board snapshots.
No local model or separate repository is needed.

## Qualification before scored runs

Use real KiCad cases for disconnected pads with identical net names, a valid
two-route witness, one missing route, a broken path, a wrong-net track, shorts,
insufficient clearance, unsupported layer/width/copper type, copper outside
the outline, unwanted U3.5 connectivity, footprint/net/rule tampering, and
remove/replace recovery. Prove multi-segment connectivity and deletion are
measured after reloading. Missing or invalid connectivity evidence must fail
closed. Retain the E00 suite and test the four-tool request guard and routing
edit audit. A successful inspection-only preflight precedes the scored batch.

## Why this is harness engineering

The YC thin-runtime idea is tested by exposing reliable copper edits rather
than admitting the shelved router. Focused native connectivity and DRC deltas
give the next decision useful context, as in Chase's talk. Preserved traces
can feed the later Continual Harness outer loop; this experiment does not
implement a refiner or claim comparative improvement, electrical validation,
or manufacturing readiness.
