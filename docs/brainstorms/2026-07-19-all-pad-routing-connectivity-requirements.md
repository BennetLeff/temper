# All-Pad Routing Connectivity — Requirements

**Date:** 2026-07-19  
**Status:** Requirements — ready for planning  
**Scope tier:** Deep — router topology, KiCad emission, and truth-measurement

## Problem

`router_v6` currently reports a net as successfully routed when it has
produced a route for its selected channel waypoints.  That is not the same
contract as PCB electrical connectivity: every conductive pad belonging to a
net must be in one connected copper component after the output has been
written and KiCad has interpreted it.

The discrepancy is measurable on the ship board.  The current U7
via-aware-routing run has internal completion `1.0`, but `kicad-cli pcb drc`
reports **149 `unconnected_items`**, unchanged from the pre-U1/U3 production
baseline.  For example, `DC_BUS_RTN` is reported routed while several of its
PTH/SMD pads remain in different KiCad connectivity islands.  This is not a
via-transition regression: the via work fixed actual F.Cu/B.Cu endpoint
transitions and did not make the production count worse.  It exposes a
separate, older false-success condition.

The issue is architectural rather than cosmetic.  A two-endpoint route is a
path; a net with three or more pads needs a connected tree.  Reporting the
former as the latter makes all completion metrics unsafe and prevents the
router from prioritising the pads that actually remain open.

## Verified current state

### Route construction loses the all-pad contract

- `channel_mapping.fallback_channel_path()` constructs a degenerate path from
  `pads[0]` to `pads[-1]`.  A fallback path therefore represents only two
  pads, regardless of the number of pins on the net.
- `_astar_route_multilayer()` routes consecutive channel *waypoints*, then
  returns a `RoutePath3D`; `RoutingResults.success_count` is currently the
  count of those path objects, not the count of electrically connected nets.
- The existing bottleneck/min-cut model already recognizes the intended
  topology: `_resolve_pad_cells()` treats the first pad as source and all
  other pads as sinks, explicitly describing this as the main router's
  “MST-routing pattern.”  That semantic has not been made an enforced output
  contract.

### Writer-side stitching is a best-effort workaround, not a proof

`adapter._write_routes_to_content()` knows the parsed pad positions and, for
non-plane paths, adds a straight F.Cu stub to a pad farther than 0.5 mm from
the emitted route.  This is valuable defensive behavior, but it is not a
reliable connectivity algorithm:

- a pad at `0 < distance <= 0.5 mm` is deliberately not stitched; the
  existing property test documents this as strict expected failure `#229`;
- it reasons from coordinate proximity and parsed positions, not from a
  connectivity graph with pad copper geometry, layer span, and vias;
- a straight stub can be illegal or can create a short/crossing; and
- completion is recorded before emitted copper is checked.

Plane/dummy paths are handled differently: the writer emits a greedy
Euclidean minimum-spanning tree for their pads.  This is another useful
implementation precedent, but it ignores obstacles and is not shared with
ordinary multi-pad nets.  The two output paths therefore have different and
incompatible meanings of “complete.”

### Existing tests are necessary but mask the production defect

`tests/router_v6/test_via_layer_properties_pbt.py` has a Hypothesis property
that checks emitted segments connect all synthetic pads.  Its generator
filters out pads in the known `0 < d <= 0.5 mm` stitch hole, and it only
models F.Cu segment endpoints.  It proves the current workaround on its
chosen domain; it does not establish all-pad connectivity for real output.

The deterministic pipeline separately has
`stages/connectivity_validation.py`, which builds a Union-Find graph across
pads, tracks, and vias and reports multiple pad-containing islands.  The
router should reuse or extract this semantic rather than invent another
incompatible definition.

### Ground truth and baseline

For this work, the ground truth is `kicad-cli pcb drc --format json` on the
written output.  Internal path status and the deterministic oracle are
diagnostic signals only.  The current production baseline is 149
`unconnected_items`; the corpus board's corresponding baseline is 0.  The
initial acceptance bar is never worse on either board, then a measured
reduction of the production count.  A literal zero is a subsequent outcome,
not a value that may be fabricated by changing which pads are counted.

## Required outcome

For every non-exempt net with two or more conductive pads, a successful
router result means that all of its pads are in one electrically connected
copper component in the emitted KiCad board.  If this is not true, the net
is incomplete and must be reported with the disconnected pad/island set;
it may not contribute to `success_count` or a percentage-complete claim.

The contract applies after writing tracks, vias, and any explicitly supported
zone/pour connection.  A PTH pad connects across layers according to the
board model; an SMD pad connects only on its declared copper layer unless a
legal via/track connects it.  Coordinate overlap alone is never connectivity.

## Requirements

### R1 — Canonical all-pad connectivity contract

Define one router-facing connectivity model and apply it consistently in
route planning, output verification, `RoutingResults`, diagnostics, and
metrics.  It must model pad copper, track endpoints/intersections, and vias
with their layer spans.  It must expose, deterministically:

- `connected_pad_count`, `total_required_pad_count`, and the connected
  components for each net;
- a list of unresolved pads/islands with pad identity (component, pad,
  net), coordinate, and layer context; and
- an explicit disposition for every net: `routed`, `incomplete`,
  `plane_connected`, `exempt`, or `failed`.

The disposition must distinguish genuinely no-connect/testpoint exclusions
from electrically relevant nets.  It must not silently classify a multi-pad
net as a plane or exempt it merely to improve a metric.

### R2 — Plan connected route trees, not endpoint paths

For a net with *n* required pads, construct a legal connected routing tree
that adds an unconnected pad/component at a time to the copper already
committed for that net.  The first implementation may use a deterministic
greedy/MST-inspired order, but must be explicit about the root and tie-break
rules so output is reproducible.

Each candidate edge must be routed through the existing A*/via-aware path
machinery and obey occupancy, width, clearance, layer, and via legality.  It
must not be implemented as unconditional straight “stitch” geometry.  The
algorithm must stop with an honest incomplete report when no legal edge can
be found; it must not force a direct edge or declare success.

The plan must assess whether the existing channel skeleton can supply a
tree/terminal sequence.  If it cannot, the initial fallback must work from
all pads directly without changing the behavior of two-pad nets.

### R3 — Preserve physical connection semantics

Every addition to a route tree must attach to actual copper on a legal common
layer.  At a layer boundary it must emit and validate a matching via, except
where a PTH pad itself is the valid plated transition.  The implementation
must not create an F.Cu stub to B.Cu copper without a valid transition.

Pad contact must use actual pad extent/tolerance, not an arbitrary global
distance threshold.  The existing 0.5 mm writer threshold and `#229` xfail
are to be removed only when a geometry-backed connection rule makes the
property true across the complete domain.

### R4 — Make completion and diagnostics truthful

Replace path-count-based completion with the canonical all-pad result.  A
net with a path but disconnected pads is `incomplete`, not `routed`.
`RoutingResults.success_count`, completion percentages, printed “routed
successfully” messages, evidence JSON, and production regression tests must
all reflect that distinction.

When incomplete, emit deterministic diagnostics that identify the source
component and each disconnected pad/island, plus the last candidate route
failure reason where available.  This must make `DC_BUS_RTN`-type failures
actionable without manually parsing KiCad's human-oriented DRC text.

### R5 — Independent verification and anti-false-zero evidence

After writing the board, run the canonical in-process verifier and
`kicad-cli pcb drc --format json`.  Persist a versioned evidence record for
the corpus and production boards with command/version, input commit,
baseline and actual `unconnected_items`, per-net counts, and all DRC-class
deltas.  An unavailable/invalid measurement is `UNMEASURED`, not pass.

The in-process and KiCad results are not assumed identical at first.  Any
disagreement is a diagnosed failure: either a model bug, unsupported KiCad
semantics, or a writer/output defect.  The acceptance gate uses KiCad; the
in-process verifier is a fast preflight and diagnostic oracle.

### R6 — TDD and property-based verification

Implement test-first.  Add focused unit tests before each production change
and Hypothesis properties covering at least:

- for arbitrary small nets (two to six pads), a returned `routed` result has
  exactly one component containing every required pad;
- adding pads can never make an existing route claim stay `routed` while the
  new pad is absent from its component;
- pad-order permutation leaves the disposition and connected-pad set
  unchanged (and yields deterministic geometry where route-cost ties are
  resolved deterministically);
- a layer mismatch requires a legal via or PTH bridge, never mere XY
  coincidence;
- an unreachable terminal yields `incomplete` with that terminal reported,
  not a forced segment or false success; and
- emitted synthetic boards round-trip through `kicad-cli` where available.

Retire or broaden the current PBT generator’s deliberate exclusion of the
0–0.5 mm stitch interval.  A test must capture its minimal counterexample
before `#229` is removed.

### R7 — Non-regression and staged production acceptance

Keep the corpus board at zero unconnected items.  Keep the production board
at or below the pre-work baseline of 149 while each slice lands.  The first
feature slice must show an independently measured production reduction or
record why it cannot be safely enabled.  Do not broaden exemptions, loosen
DRC rules, exclude pads, or alter the board/netlist solely to buy the count.

Track clearance, shorts, mask bridges, crossings, and holes alongside
connectivity: a connection-count improvement that creates a new safety or
manufacturability regression does not pass.

## Scope boundaries

**In scope:** router_v6 multi-pad topology, the output writer's ordinary-net
stitching behavior, truthful status/diagnostics, router-facing connectivity
verification, evidence, TDD/PBT, and corpus/production DRC regression
measurement.

**Deferred:** globally optimal Steiner-tree routing, simultaneous multi-net
tree optimization, autorouting copper zones/pours, and resolving every
non-connectivity DRC category.  A deterministic legal tree that verifies all
pads is the prerequisite; route-quality optimization comes later.

**Outside scope:** board geometry/BOM resize decisions, changing the
electrical netlist to suppress failures, or treating all power nets as
implicitly connected by a future zone.  Zone connectivity becomes in scope
only after a zone is actually emitted and verified from the written board.

## Design decisions for planning

1. **Use a tree incrementally, not all-pairs paths.**  Connecting every pair
   would duplicate copper and make congestion worse.  A deterministic
   root-plus-nearest-connectable-terminal expansion is the smallest viable
   slice; it may later be replaced by an obstacle-aware MST/Steiner heuristic
   without changing the all-pad contract.
2. **Verification is a separate layer from planning.**  The same graph
   semantics should be shared where possible, but the writer must be checked
   after serialization because it can still drop layers, vias, or net IDs.
3. **Do not promote writer stitching into the route algorithm.**  It has no
   obstacle or clearance authority.  During migration it may remain only as
   a guarded compatibility behavior, and must itself be verified.
4. **KiCad stays the external oracle.**  The internal validator enables fast
   focused tests and meaningful diagnostics, but it does not replace the
   actual board-format/DRC result.

## Open questions for the implementation plan

1. Can the existing `ChannelPath.waypoints` be made to include all terminals
   without violating channel constraints, or should an all-pad expansion run
   after the channel path is routed?
2. Is it safer to extract/adapt deterministic
   `ConnectivityValidationStage`, or to introduce a small router-local
   geometry graph with a common protocol?  Planning must avoid importing the
   legacy deterministic pipeline wholesale.
3. How should existing copper be represented in the occupancy grid so a new
   terminal may legally attach to its own net without treating its own tracks
   as obstacles?
4. Which net categories are valid `plane_connected` cases today?  The answer
   must be derived from emitted/filled zones in the final board, not name
   heuristics.
5. Does the 149-item production baseline include only router omissions, or
   pre-existing board-content/netlist issues too?  The first evidence record
   must classify the count per net before setting a numerical reduction
   target.

## Evidence and related work

- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — U7
  production measurement: internal completion 1.0, KiCad 149 unconnected
  items; current non-regression baseline.
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — path
  writer, writer-side missing-pad stitch, and plane MST special case.
- `packages/temper-placer/tests/router_v6/test_via_layer_properties_pbt.py`
  — existing PBT, including documented `#229` threshold hole.
- `packages/temper-placer/src/temper_placer/deterministic/stages/connectivity_validation.py`
  — established Union-Find connectivity semantics to evaluate for extraction.
- `docs/plans/2026-07-18-003-feat-via-aware-layer-transitions-plan.md` —
  completed/active via work; this is its distinct follow-on, not a reopening
  of U1–U7.
- `docs/solutions/logic-errors/deterministic-pipeline-drc-oracle-only-checks-routing-not-real-drc.md`
  — why internal/oracle success never replaces KiCad DRC.
