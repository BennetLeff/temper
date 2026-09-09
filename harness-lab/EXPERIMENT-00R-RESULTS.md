# Experiment 00R: three agent routing trials passed

**All three Muse Spark 1.3 Contributor Free routing trials passed**, including
independent native KiCad checks of each final board. The user explicitly
authorized the expanded routing payload with “send it”; the earlier approval
block was resolved before execution. No code, rules, prompts or budgets changed
during the scored batch, and no trial was retried or given human routing hints.

| Trial | Elapsed | Routing edits | Final copper | Host check |
|---|---:|---:|---|---|
| 1 | 22.30 s | 2 | 2 straight segments | Pass |
| 2 | 48.64 s | 2 | 2 straight segments | Pass |
| 3 | 30.34 s | 2 | 2 straight segments | Pass |

An inspection-only preflight passed in 7.93 seconds with zero edits. Each
trial inspected, added one +15V trace and one ground trace, and finished with
a passing check. All three independently chose the same direct pad-center
connections. There were no routing repairs or removals. Every final board
has both required physical connections, zero applicable DRC findings, and
one explicitly out-of-scope open connection to U3.5.

OpenCode reported $0 for each trial. This is its reported free-model cost,
not an independently obtained billing receipt. The wire audit verified the
served model, exact four-tool catalog, executed arguments, shown observations,
and native action/snapshot chain. The three final content hashes differ
because independently created track UUIDs differ; the route geometry matches.

[Agent result rendered by KiCad](evidence/routing-agent-trial-1.svg).
[Scored results](evidence/routing-zen-results.json).
[Inspection preflight](evidence/routing-zen-preflight.json).
[Complete model and native traces](evidence/routing-zen-traces.tar.gz).

## Implemented task

U3 stays at (10, 10, 0 degrees); C9 stays at the first successful placement,
(6, 10, 90 degrees). The agent connects C9.1 to U3.3 (+15V) and C9.2 to
U3.1 (gnd). U3.5, also on +15V, deliberately remains disconnected.

The four tools are `inspect`, `route`, `remove_route`, and `check`. The agent
chooses all polyline vertices. Copper edits use 0.25 mm straight segments on
F.Cu; no hidden router, snapping, shove, net correction, vias, arcs, zones,
or footprint moves. Each trial has five minutes and ten edits,
including removals. Three fresh repetitions use the same geometry.

Rust evaluates physical connectivity measured by KiCad, complete applicable
native DRC, copper bounds, supported copper, unchanged placement, and protected
state. Saved track net assignments are measured before connectivity rebuilding.
The initial board is separately pinned so a pre-routed fixture cannot replace it.

## Local evidence

- **23 routing controls passed their expected outcomes:** repeated connected
  witnesses; blank, missing and broken routes; wrong nets (including a wrong
  admitted net that KiCad would otherwise repair); shorts; clearance; layer,
  width and via rejection; copper outside the outline; unwanted U3.5
  connectivity; fixed-placement, pad-net and rule tampering; missing/partial/
  inconsistent connectivity; remove/replace recovery with transcript audit;
  input, edit/time-budget and preflight boundaries.
- **19 placement regression controls passed**, retaining the previous task.
- **2 Rust unit tests and 9 Python boundary tests passed**, together with
  Clippy, Ruff, formatting and Python compilation.
- A locally scripted two-route witness has both physical connections, zero
  applicable DRC findings, and exactly one reported open connection to U3.5.
  This witness qualifies the tools; **it is not an agent result**.

[Native KiCad witness render](evidence/routing-witness.svg).
[Routing qualification receipt](evidence/routing-qualification.json).
[Placement regression receipt](evidence/routing-placement-regression.json).
[Retained local traces](evidence/routing-local-traces.tar.gz).
[External execution status](evidence/routing-model-status.json).

## Instrument defects found before model execution

KiCad's Python `Remove` transfers a track to Python ownership. In this adapter
that caused cleanup crashes and SWIG messages after JSON output. The adapter
now uses native `Delete`, a separate canonical board, and an explicitly owned
connectivity graph. Repeated measurement and remove/replace controls pass.
The host never accepted a crashing or malformed measurement as evidence.

KiCad's convenience load/save helpers and connectivity builder propagate
track net assignments. Our first wrong-net control therefore failed to create
the intended saved defect. The adapter now uses raw KiCad file I/O and captures
the copper census before connectivity rebuilding. Both wrong-net controls
fail acceptance, even when KiCad's subsequent DRC process normalizes the net.
The initial failed qualification and development probe are retained.

## What this establishes

Reliable edits, focused native feedback and protected evaluation implement
the thin-harness and contextual-feedback ideas from the YC and Chase talks.
The old optimizer remains shelved. Recorded attempts can support a later
Continual Harness refinement loop; none is implemented or measured here.

This demonstrates repeatable agent routing on one deliberately simple, fixed
fixture. It does not demonstrate routing around obstacles, recovery, unseen
geometry, a full converter, or a full board. No electrical/current-rating
assessment or fabrication approval is claimed. The 0.25 mm width is an
experiment constraint.

The next useful experiment would introduce one fixed obstacle that forces a
detour while keeping the same two connections and small tool surface. Freeze
that new fixture and its acceptance criteria before running it. That would
test route planning beyond the direct connections demonstrated here.
