---
title: "feat: All-Pad Routing Connectivity"
type: feat
status: proposed
date: 2026-07-19
origin: docs/brainstorms/2026-07-19-all-pad-routing-connectivity-requirements.md
plan_id: APC1
---

# All-Pad Routing Connectivity

## Outcome

A Router V6 net is successful only when every required conductive pad is in
one copper component **after the router has written the KiCad board**.  A
path between selected waypoints is merely an intermediate routing attempt.
The resulting implementation reports a deterministic `routed`, `incomplete`,
`plane_connected`, `exempt`, or `failed` disposition, never lets an
unverified path inflate completion, and plans ordinary multi-pad nets as
legal incremental trees rather than endpoint paths plus writer-side stubs.

The external acceptance oracle remains `kicad-cli pcb drc --format json` on
the written output.  The in-process graph is a fast, explainable preflight;
it is deliberately not presented as a replacement for KiCad DRC.

## Execution record (2026-07-19)

U1 and the first U2 slices are implemented, test-first, but the experimental
planner is intentionally **default-off**.  The layer-aware verifier now
reports deterministic all-pad components and unresolved islands; it is backed
by focused Hypothesis properties.  The router can retain all physical
terminals for fallback and SAT-mapped paths, and a multi-pad edge that would
need legacy forced/direct geometry is reported as an incomplete tree failure
instead of being emitted.

The production activation experiment is a measured failure, not a partial
pass: enabling all-terminal expansion raised KiCad
`unconnected_items` from the U3 baseline of 149 to **218**.  The feature gate
was therefore made explicit (`RouterV6Pipeline(enable_all_pad_tree=False)`),
with tests preserving historical two-endpoint behavior by default.  A fresh
production `route_pcb` → `kicad-cli pcb drc` regression run with the default
gate passed in 145.84 s, confirming the non-regression baseline is restored.
This blocks promotion until the next U2 slice diagnoses tree attachment/order
and lowers the measured count without worsening other DRC classes.

Follow-up experiments confirmed that this is not resolved by terminal order
or a larger search window.  Nearest-terminal ordering made the experimental
sequence deterministic, but its KiCad result remained **218** unconnected
items.  The first unbounded run also exposed a termination defect: each extra
terminal could enter the 200,000-iteration 3D fallback and repeat through
rip-up.  Experimental tree routing now caps that fallback at 10,000
iterations per edge and stops at the first failed edge with its terminal in
the diagnostic.  The bounded opt-in run completed and still measured 218,
which rules out both ordering and runaway search as the primary cause.  The
next U2 design must preserve and verify already-realized partial copper while
separately reporting unsatisfied terminals, then use a true component-aware
attachment strategy; it must not reinstate forced/direct edges.

The first half of that follow-up is now complete: experimental failures retain
only their actual A*-routed prefix in `PathfindingResult.partial_paths`, while
the net remains failed/incomplete and the prefix is excluded from
`RoutingResults` and writer input.  Property tests verify that the missing
terminal is absent from this geometry and that it cannot inflate success
metrics.  Serializing a partial route is deferred until the writer can consume
only realized tree geometry without its legacy missing-pad direct-stitch path.

That serialization boundary was then implemented experimentally and measured.
It writes only actual prefix segments/vias and skips both writer stitch and
plane-MST fallbacks.  KiCad `unconnected_items` improved from 218 to **203**,
but is still worse than the 149 baseline, so promotion remains blocked.  It
also revealed two distinct quality failures: 199 `track_width` violations
(partial prefixes fell back to an invalid width) and large clearance/short
deltas (54 clearance, 118 shorts).  The next bounded fix is the width source;
clearance/short remediation is not folded into a connectivity metric change.

The partial-width source was corrected by feeding partial paths through the
existing board/netclass trace-width assignment stage.  A fresh opt-in KiCad
run verified `track_width: 199 → 0` and total violations `1146 → 932`.
`unconnected_items` remained **203**, while clearance and shorts remained
high (50 and 119 respectively).  This is a valid quality improvement but not
a connectivity promotion: default-off stays in force until a component-aware
tree algorithm improves connectivity without those DRC regressions.

The topology prerequisite for that next algorithm is now separately tested:
a deterministic Prim-style planner chooses a canonical root and connects each
new terminal to the lowest-cost member of the existing component (with stable
identity tie-breaks).  It is intentionally not wired to A* yet; integration
must route each chosen edge to real component copper, validate the resulting
graph, and commit it only on success.

A synthetic-only execution spike now establishes that contract against the
existing A* primitive: each Prim edge is routed as separate branch geometry,
all reachable pads validate as one component, and the first unreachable edge
returns an incomplete result with no forced/direct segment.  The spike does
not mutate occupancy or production dispatch; its next integration step needs
stable parsed terminal identities and same-net component-copper reservation.

U0's evidence validator is implemented and fail-closed, but no baseline JSON
is committed: a fresh routed corpus measurement produced 6 unconnected items,
not the required zero.  Recording a clean corpus artifact would be false;
classifying those six items is the first evidence follow-up.

## Current facts and decisions

* `channel_mapping.fallback_channel_path()` collapses a fallback net to
  `pads[0]` and `pads[-1]`; `_astar_route_multilayer()` then routes only
  adjacent waypoints.  This is the source of the endpoint-path contract.
* `astar_pathfinding._should_route()` skips power, ground, and HV nets, while
  `pipeline._run_stage5()` turns those names into zero-length "plane" routes.
  `_write_routes_to_content()` emits their direct Euclidean MST.  Neither
  name-based behavior proves an emitted and filled zone exists, so it cannot
  count as `plane_connected` in this feature.
* The current writer's `CONNECTION_THRESHOLD_MM = 0.5` direct F.Cu stitch is
  an unsafe compatibility workaround.  It cannot route through obstacles and
  leaves the known `0 < distance <= 0.5 mm` hole documented by the strict
  `#229` xfail in `test_via_layer_properties_pbt.py`.
* Reuse the deterministic pipeline's *semantics*, not its stage dependency:
  extract a router-local, dependency-light connectivity module from the
  Union-Find approach in `deterministic/stages/connectivity_validation.py`.
  The legacy `Pad.layer`/`Via` model is insufficient because its vias have no
  layer span and it assumes plane connectivity.  Extend the common geometry
  dataclasses with explicit layer sets/spans before sharing the verifier.
* Via-aware work (`2026-07-18-003`) remains a prerequisite for any tree edge
  that changes layer: `RoutePath3D.via_positions`, `place_vias()`, and the
  writer's real `(via ...)` output must all be retained.  This work must not
  revive the historical hard-coded F.Cu stitch or bypass via legality.
* The initial tree policy is deterministic Prim-style expansion: canonical
  root is the lexicographically smallest `(ref, pad, x, y, layer-context)`;
  select the next unconnected terminal/component by
  `(estimated Manhattan distance, canonical pad key)`; and, within equal-cost
  attachment points, use the existing A* deterministic order.  It preserves
  two-pad behavior and can later be replaced by an obstacle-aware
  MST/Steiner heuristic without changing the result contract.
* A PTH pad is a legal bridge on every copper layer in its declared plated
  span.  An SMD pad is only conductive on declared copper layers.  XY overlap
  across different layers does not connect unless a matching-span via or PTH
  bridge joins it.  Contact uses pad shape/extent plus one shared documented
  geometric tolerance (the existing `1e-4` only after it is named and tested),
  not a global distance threshold.

## Requirements

* R1. Define one canonical router-facing all-pad connectivity result with
  deterministic pad identities, components, counts, dispositions, unresolved
  islands, and reason data.
* R2. Build the result from real pad copper, tracks, vias and their layer
  spans; preserve SMD/PTH semantics and prohibit XY-only cross-layer joins.
* R3. Route ordinary multi-pad nets as legal incremental trees through the
  current A*/via-aware machinery; an unreachable terminal becomes
  `incomplete`, never a forced/direct writer segment or a success.
* R4. Make `PathfindingResult`, `RoutingResults`, pipeline messages, metrics,
  JSON, and diagnostics derive completion from R1 rather than path count.
* R5. Serialize only the router-produced legal tree for ordinary nets, remove
  the arbitrary writer stitch and name-based dummy plane MST, then re-check
  written copper with R1.
* R6. Provide independent KiCad evidence: versioned corpus/production
  before/after counts, per-net data, all DRC-class deltas, and fail-closed
  `UNMEASURED` handling. Corpus remains zero; production never exceeds 149
  and the first enabled tree slice lowers it or records why activation is
  blocked.
* R7. Protect R1--R6 with focused TDD, Hypothesis properties, KiCad
  round-trips, and traceability annotations.

## Dependency order and implementation units

### U0 — Freeze an honest baseline and establish the test seam

**Depends on:** none. **Requirements:** R6, R7.

**Files to add/modify:**

* Add `packages/temper-placer/tests/router_v6/test_all_pad_connectivity.py`.
* Add `packages/temper-placer/tests/router_v6/test_all_pad_connectivity_pbt.py`.
* Add `docs/evidence/2026-07-19-all-pad-routing-baseline.json`.
* Modify `packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py`
  and/or `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`
  only to consume the checked baseline helper introduced in U6; do not change
  the board or expected DRC limits in this unit.

**Red:** write fixture tests for (a) a three-pad net whose two-pad route is
not `routed`, (b) a same-XY F.Cu/B.Cu SMD pair that is disconnected, (c) the
same pair joined by a via with the correct span, and (d) a PTH bridge.
Record raw command, `kicad-cli --version`, source-board SHA, routed-output
SHA, invocation arguments, `unconnected_items`, per-net parsed DRC evidence
where available, and all error-class counts for corpus and production.

**Green:** no production change yet; make test fixtures explicit about the
future result API and check that an absent/invalid KiCad result is
`UNMEASURED`, not clean.  The committed baseline records `0` corpus and
`149` production unconnected items only after the command is rerun on the
current checked-out inputs; it must not be copied from prose.

**Gate:** execute real KiCad DRC before and after the unit; no PCB files are
rewritten.  Keep a narrowly mocked unit test for JSON parse failures, but
never permit mocks to produce a committed evidence record.

### U1 — Canonical geometry graph and all-pad result

**Depends on:** U0. **Requirements:** R1, R2, R7.

**Files:**

* Add `packages/temper-placer/src/temper_placer/router_v6/connectivity.py`.
  Define immutable `PadIdentity`, `CopperPad`, `CopperTrack`, `CopperVia`,
  `ConnectivityComponent`, `NetConnectivity`, `NetDisposition`, and
  `verify_net_connectivity()` / `verify_connectivity_by_net()`.
* Modify `packages/temper-placer/src/temper_placer/router_v6/constraints_spatial_index.py`:
  make `Via` carry `layers: tuple[int, int] | frozenset[int]` (or an
  equivalent ordered span), and expose each `Pad`'s conductive layers rather
  than relying only on one `layer` plus `is_pth`.
* Refactor `packages/temper-placer/src/temper_placer/deterministic/stages/connectivity_validation.py`
  to adapt its geometry into the new module and preserve orphan/dangling
  reporting; remove its plane-name/assignment assumption rather than copying
  it into the router.
* Extend `packages/temper-placer/tests/deterministic/stages/test_connectivity_validation.py`.

**Red:** test all graph edges: track–track intersection/endpoint contact only
on a common layer; track–pad contact against rotated pad copper; track–via,
via–pad and via–via contact only on a shared via span; and deterministic
components when input order changes.  Include two SMD pads at identical XY on
opposite layers, an out-of-span blind/buried via if represented, PTH contact,
and an orphan copper island.  Assert component records contain stable
`(component_ref, pad, net, coordinate, layers)` identities, not object IDs.

**Green:** implement a per-net Union-Find graph.  Deterministically sort
inputs and components by pad identity; select the primary component by
largest required-pad count then its smallest key.  `routed` means precisely
one component contains every required pad; `incomplete` retains all
unresolved pad islands.  `plane_connected` is unavailable in U1 except from
an explicit emitted/verified-zone adapter added in U5; `exempt` requires a
typed reason supplied by parsing, never a net-name heuristic.

**PBT:** generate 2–6 pads, tracks and vias on two layers.  Permuting every
input list must preserve disposition, connected-pad count and canonical
components.  A cross-layer edge without an allowed bridge must not merge
components.  Adding an isolated required pad must turn `routed` into
`incomplete` and name that pad.  Compare the graph to a small brute-force
adjacency oracle for all generated geometries.

### U2 — Carry all terminals and route a tree, without widening ordinary-net permissions

**Depends on:** U1 and the landed/verified portions of via-aware U2–U6.
**Requirements:** R2, R3, R7.

**Files:**

* Modify `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py`:
  change `fallback_channel_path()` to receive canonical terminal records and
  retain every terminal rather than `[0], [-1]`; document the canonical order.
* Modify `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`:
  add a small `_route_net_tree()` invoked by `attempt_route()` / before
  `_astar_route_with_ripup()` for nets with more than two required terminals;
  reuse `_astar_route_multilayer()`/`_route_segment_3d()` per selected edge.
  Return attempted edge failures and per-edge paths/attached components.
* Modify `packages/temper-placer/src/temper_placer/router_v6/astar_grid.py`
  and `occupancy_grid.py` only as needed to reserve a routed net's own copper
  as attachable while preserving other-net obstacles, width and clearance.
* Add `packages/temper-placer/tests/router_v6/test_all_pad_tree_routing.py`
  and extend `test_astar_route_multilayer_via_fallback.py`.

**Red:** create a three-terminal unobstructed net where endpoint-only routing
is insufficient; an obstacle case where a direct segment would cross blocked
copper; a terminal reachable only through a legal F.Cu/B.Cu transition; and
an unreachable third terminal.  Assert routing attempts two legal edges for
three pads, emits no forced completion edge, and reports the blocked terminal
and last A* failure.  Lock two-pad coordinate/path behavior with a regression
fixture.

**Green:** derive terminals from parsed pad geometry, not bare pin centres.
For an existing SAT channel tree, first verify whether all terminals are
represented; if it is not, append all-pad expansion from the current copper
component.  Do not change the SAT skeleton format in this slice.  Each next
edge starts at a legal attachment candidate of the connected component and
ends at an unconnected pad copper region; route it with existing net class,
clearance, occupancy, and via logic.  Commit/mark an edge only after it joins
the canonical graph; stop on the first no-path terminal and return partial
tree + deterministic failure detail.  Delete `_astar_route_multilayer()`'s
"Fallback: add direct segment" success path for tree routing; a forced edge
must be treated as incomplete until a later separately approved policy
decides otherwise.

**PBT:** for obstacle-free 2–6 pad grids, `routed` produces exactly one
all-pad component and at most `n-1` accepted tree edges (excluding internally
segmented geometry).  Pad permutations preserve disposition and connected-pad
set; tie cases produce identical serialized edge order.  A generated
unreachable terminal is reported and cannot leave the net `routed`.  A
cross-layer attachment is accepted only if the generated output has a legal
via/PTH bridge.

### U3 — Make statuses, reports, and completion truthful before writer migration

**Depends on:** U1, U2. **Requirements:** R1, R3, R4, R7.

**Files:**

* Modify `router_v6/astar_pathfinding.py`: extend `PathfindingResult` with
  per-net connectivity/tree attempts; calculate `success_count`,
  `failure_count`, and `completion_rate` from dispositions.
* Modify `router_v6/routing_results.py`: add `connectivity: dict[str,
  NetConnectivity]`; make `CompiledRoute` carry only realized tree geometry;
  replace `plane_net_count` as a success override with explicit verified
  `plane_connected` dispositions.
* Modify `router_v6/diagnostics.py`: add disconnected `PadIdentity` islands
  and last candidate failure fields to `NetRoutingReport`; use
  `RoutingStatus.PARTIAL` for `incomplete`.
* Modify `router_v6/pipeline.py` (`RouterV6Result.success_count`, console
  lines near `_run_stage5()` and completion calculation) and
  `router_v6/result_aggregate_stage.py` so they do not advertise path count.
* Extend `tests/router_v6/test_routing_results.py`,
  `test_router_v6_output_validity_pbt.py`, and
  `test_router_v6_drc_invariants_pbt.py`.

**Red:** a path object for only two of three pads must yield `incomplete`, be
present in `failed_nets`/partial diagnostics, and not increase completion.
Assert exact diagnostic ordering and that zero required pads and one-pad nets
get explicit `exempt` dispositions with a reason, rather than a hidden
success.  Retain a test proving a real, validated zone adapter is the only
way to get `plane_connected`.

**Green:** compile results only after fast connectivity verification over
realized router geometry; propagate an incomplete net independently of
whether A* found some path.  Failure reporting includes primary component and
each unresolved island's stable identities, layer context, and last edge
failure.  Do not make the legacy deterministic DRC oracle determine
completion.

**PBT:** no generated result can satisfy `success_count > 0` for a net whose
canonical result is incomplete; adding a required pad cannot preserve
`routed` if absent; serializing then deserializing reports preserves all
counts, identities, and dispositions.

### U4 — Replace writer stitching with geometry-backed output and post-write preflight

**Depends on:** U1–U3 and via-aware U5/U6. **Requirements:** R2, R3, R5, R7.

**Files:**

* Modify `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
  (`_write_routes_to_content`, `_build_routing_result`).
* Add `packages/temper-placer/src/temper_placer/router_v6/kicad_connectivity.py`
  (or an adapter section in `connectivity.py`) to parse emitted pad/segment/
  via geometry into the canonical verifier without importing the deterministic
  pipeline.
* Extend `packages/temper-placer/tests/router_v6/test_via_output_writer.py`
  and replace the threshold-specific portion of
  `test_via_layer_properties_pbt.py` with complete-domain tests.

**Red:** preserve the existing strict `#229` counterexample as an ordinary
failing test: pads `(0,0)`, `(0,0.5)`, `(0,1)` with a two-terminal path must
not be declared/serialized as connected.  Test that an attempted F.Cu stub
to B.Cu output without an emitted via fails verification.  Test writer output
for a legal tree routes every pad, contains no synthetic direct edge that was
not in `CompiledRoute`, and verifies identically after KiCad s-expression
serialization.

**Green:** delete `CONNECTION_THRESHOLD_MM` and the ordinary-net direct
stitch branch.  Delete the name-based dummy plane Euclidean MST branch.
Writer input is realized tree tracks and actual `CompiledRoute.vias` only;
it retains the via-aware per-segment layers.  Parse the written content and
run the canonical verifier immediately.  If serialization loses a net ID,
layer, via, or pad connection, rewrite the net disposition to `incomplete`
and return the evidence—not a success.  Remove the `#229` xfail only when
the complete-domain property is green.

**PBT:** generate pads at arbitrary lattice and sub-threshold distances; no
filter may exclude `0 < d <= 0.5`.  For each successful synthetic result,
writer → parser → canonical graph preserves exactly one all-pad component.
Layer mismatch without a via/PTH bridge never round-trips as connected.

### U5 — Explicit exemption and zone policy

**Depends on:** U4. **Requirements:** R1, R5, R6.

**Files:**

* Modify `router_v6/net_classification.py`, `astar_pathfinding.py`, and
  `pipeline.py` to replace `_should_route()`'s broad power/ground/HV skip
  with a typed per-net disposition input.
* Modify `router_v6/stage0_data.py` / the parsed PCB adapter only if required
  to carry authoritative no-connect/testpoint metadata and emitted-zone
  evidence.
* Add `tests/router_v6/test_all_pad_dispositions.py`.

**Red:** power/HV/ground names with two pads are not automatically exempt or
plane-connected.  No-connect and declared testpoint cases need an explicit
reason and remain visible in reports.  A claimed plane net without a filled,
written-zone connectivity proof is `incomplete`, not `plane_connected`.

**Green:** initially route every non-exempt multi-pad net, including current
power/HV/ground names.  Permit `plane_connected` only through a future
adapter that proves a specific emitted/fill-verified zone joins every
required pad; do not implement zones in this plan.  Keep zone support behind
an explicit feature capability and leave it disabled until its own KiCad
round-trip tests exist.

### U6 — KiCad ratchet, committed evidence, and production activation

**Depends on:** U0–U5. **Requirements:** R4, R6, R7.

**Files:**

* Add `packages/temper-placer/src/temper_placer/router_v6/all_pad_evidence.py`.
* Add `packages/temper-placer/tests/router_v6/test_all_pad_evidence.py` and
  extend `test_temper_production_board_routing.py` plus
  `tests/placer/cp_sat/test_regression_drc.py`.
* Add `docs/evidence/2026-07-19-all-pad-routing-after-<slice>.json` per
  measured feature slice; do not overwrite U0 baseline evidence.
* Modify `docs/traceability-registry.yaml` and
  `packages/temper-placer/tests/router_v6/TRACEABILITY` when implementation
  begins (not in this planning-only change).

**Red:** evidence validation rejects missing command/version/SHA, malformed
KiCad JSON, `UNMEASURED`, a corpus unconnected count other than zero, a
production count above 149, an omitted DRC class, or an internal/KiCad
per-net disagreement left unclassified.  It also rejects a claimed
improvement accompanied by an increased safety/manufacturability class
(clearance, shorting_items, tracks_crossing, solder_mask_bridge,
hole_clearance) unless an explicitly triaged pre-existing delta is recorded.

**Green:** record schema version, inputs/output hashes, command, KiCad
version, timestamp, internal all-pad result per net, KiCad
`unconnected_items` and attributable per-net count where parseable, every
violation-class count/delta, status (`CLEAN`, `VIOLATIONS`, `UNMEASURED`), and
an explicit disagreement classification.  Gate corpus `== 0` and production
`<= 149`.  The first tree-routing slice additionally needs production `<149`;
if it cannot safely lower it, keep the feature disabled, commit the measured
failure evidence, and create a bounded follow-up rather than weakening the
gate or exclusions.

**KiCad round-trip:** invoke `kicad-cli pcb drc --format json --output …` on
the exact temporary emitted boards, not the source input.  Failure to launch,
non-JSON output, or stale/missing report is `UNMEASURED` and fails the
promotion test.  Run focused synthetic boards in normal CI where KiCad is
available; run corpus and production measurements in the existing explicit
integration/regression lane, never silently skip them.

### U7 — Traceability and final integration gates

**Depends on:** U1–U6. **Requirements:** R1–R7.

During implementation, change this plan to `status: active`, register
`APC1` in `docs/traceability-registry.yaml`, and scope exactly the modules
and tests above.  Extend the existing `tests/router_v6/TRACEABILITY` list to
allow `APC1`; add `# @req(APC1, R<n>): …` annotations in each opted-in test
and, if source traceability is adopted for the router, add a narrowly scoped
sentinel rather than a repository-wide one.  Keep R6's evidence parser and
its tests in scope so an evidence-only requirement has executable coverage.

Run, in this order:

1. Focused unit/PBT suites from U1–U5, including deterministic and complete
   `#229` replacement tests.
2. `uv run pytest packages/temper-placer/tests/router_v6/` plus relevant
   deterministic connectivity and CP-SAT DRC regressions.
3. `uv run ruff check packages/temper-placer` and project type checks.
4. `uv run python scripts/import_linter_gate.py`.
5. `uv run python scripts/check_traceability.py --all`.
6. KiCad corpus/production before/after ratchet and evidence validation.

No gate may be waived by reclassifying a net, loosening DRC, changing the
netlist/board, or making `UNMEASURED` pass.

## Rollout, rollback, and boundaries

Land U1–U3 first with the legacy writer still able to emit prior geometry,
but with status demotion available.  Land U4 in one reviewable change that
deletes the unsafe writer workaround only after U2 has legal tree geometry.
Then land U5 policy and U6 ratchet.  Feature-flag only the *tree planner*
while measurements are being compared; the canonical verifier and truthful
status must remain enabled, so a fallback cannot restore false completion.

If KiCad counts or any tracked safety/manufacturing class regresses, revert
the tree-planner/writer slice while retaining U0 evidence and the canonical
verifier tests.  Do not revert by restoring 0.5 mm stitching, marking power
nets plane-connected, or weakening the baseline.  An internal/KiCad mismatch
is a diagnosis stop: classify it as a graph-model defect, unsupported KiCad
semantics, or writer defect and open a narrowly scoped follow-up.

Deferred: globally optimal Steiner trees, simultaneous multi-net tree
optimization, zone/pour autorouting and broad real-DRC remediation.  These
may refine planning only after they satisfy the all-pad contract and KiCad
ratchet; none may be used to conceal current unconnected pads.

## Known blocker to resolve at U0/U1

The repository currently has a via-aware test referencing
`docs/evidence/2026-07-19-via-aware-routing-u8.json`, but that file was not
present in this checkout during planning.  This plan does not create or alter
that unrelated via evidence.  The implementer must first determine whether
it is an intentionally uncommitted artifact, a branch-sync issue, or a stale
test reference; all-pad evidence must use its own files and must not paper
over that missing provenance.
