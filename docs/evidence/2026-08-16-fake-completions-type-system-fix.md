<!-- provenance: commit=71b3325d88338cc106112bc9584d42631b65c027 dirty=false -->
<!-- provenance: this document's fix is on branch fix/fake-completions-type-system,
built from origin/main @ 5cebf30f0 (docs(evidence): definitive final route on
main -- 92/139 pad-connected, 0 unconnected DRC items (#1247)). The measured
board is /tmp/opencode/definitive-route.kicad_pcb (the #1247 route output;
sha256 9126a1afbd19fa72...); pcb/temper.kicad_pcb is NOT modified by this
change (verified: git status shows no board diff). No DRU/clearance/creepage/
copper-weight threshold changed. No ceiling in
power_pcb_dataset/drc_ceiling.json touched. -->

# Fake completions are now unrepresentable: `NetRouteResult`, whose `Connected` variant is constructible only by `verify_continuity()`

**Verdict up front.** The router reported 14 of 139 nets as "routed
successfully" on the definitive route (#1247) while the emitted copper did
not form a continuous path between all of the net's pads — the fake
completion. The root cause is that "A* found a path through the grid" and
"verified continuous copper connects all pads" are different claims, and
the router's completion reporting used the former. This change makes the
latter the ONLY way to obtain a `Connected` verdict, at the type level:
`NetRouteResult::Connected(VerifiedRoute)` is unrepresentable outside
`verify_continuity()` (private `VerifiedRoute` fields; pinned by a
`compile_fail` doctest). Re-running verification over the definitive
route's emitted copper now classifies all 14 fake completions honestly —
13 `partial` (with the specific unconnected pads named) and 1
`zone_dependent` (DC_BUS_RTN: 33 zone outlines, zero fill) — and all 92
genuinely connected nets still verify `connected` (zero downgrades).

## 1. The mechanism: four layers of "done", only one of which checks copper

The router's completion claim travels through four layers, and the fake
completions come from the gap between layer 1 and layer 4:

1. **A* path found.** `_astar_reconstruct.py` prints `✓ <net> routed
   successfully` (lines 300, 418) when the occupancy-grid search returns a
   path, and records the net in `PathfindingResult.routed_paths`. This is a
   *grid-path* claim. Realizing it as copper is a separate step with
   documented failure modes: segments landing on the wrong layer or short
   of a pad boundary, a via emitted at the wrong coordinates or not at all,
   zone outlines with no fill.
2. **`RoutingResults.success_count`** (`routing_results.py`) falls back to
   `len(compiled_routes) + len(tree_routes) + plane_net_count` whenever
   `connectivity` is None — and `_run_stage5` hardcodes
   `connectivity=None` (`_pipeline_route.py:791`). The U3 "truthful
   completion from NetDisposition" path exists but is never fed data.
3. **`route_pcb`'s `completion_rate`** is derived from the same A* path
   counts (`PathfindingResult.success_count + failure_count`), walked by
   `temper_orchestration::pipeline_route::run_build_routing_result`.
4. **The post-write verifier** (`kicad_connectivity.connectivity_preflight`,
   U4) parses the emitted content and runs `verify_net_connectivity` — but
   it is gated behind `enable_connectivity_verifier=False`, which is the
   default in `route_pcb` **and** hardcoded in `_adapter_core.py:206` (the
   `rrr_route_all_nets` path); `route_board.py` never enables it.

The PRIMARY metric line (`pad_connectivity_audit.audit_pcb_file`, run
post-hoc by `route_board.py`) caught the discrepancy — "92/139
fully-pad-connected, fake-completion=14, honest-gap=33" — but it runs
*after* the route and changes no router claim. PR #1177 fixed ONE fake
completion mechanism (pin-identity collapse for K2/K3's duplicated relay
contact pads: A* "routed" a zero-length path). The 14 remaining nets are
the general shape.

## 2. The 14 fake completions, and why each one was reported "routed"

The definitive route (#1247, 2026-08-15) printed
`fake-completion=14 honest-gap=33`. The audit's `is_fake_completion` is
`has_any_copper and not fully_connected` — copper exists for the net, so a
segment/via counter called it done, but the copper does not join all pads.
Per-net (this work's classification, §4):

| net | why the audit called it fake | NetRouteResult verdict |
|---|---|---|
| +15V | copper joins pads 3,4,5,7,8; pads 0,1,2,6,9 unreached | partial |
| +15V_LS | pad 1 unreached | partial |
| DC_BUS_RTN | 33 zone outlines, no fill; 8 pads in outlines | zone_dependent |
| GATE_LS | pad 0 unreached | partial |
| OCP2_VREF_2V5 | pad 1 unreached | partial |
| RTD_HW_FAULT | pad 2 unreached | partial |
| WDT_RESET_N | pad 1 unreached | partial |
| bias | via ring at U8.4's centre overlaps U8.5's pad but the audit's point-node model cannot see extents | partial |
| gnd | 88 pads; largest joined group 15, 69 unreached | partial |
| hb.gate_hs.driver-p1-1 | two 2-pad groups, no bridge | partial |
| safety.coil_thermal-line | pad 1 unreached | partial |
| safety.thermal.comp-inp | pad 2 unreached | partial |
| safety.uvlo_logic.mon-ina_p | pad 1 unreached | partial |
| vbias | pad 1 unreached | partial |

Every one of these was counted as "routed successfully" by the A* layer
because a grid path existed; none had its emitted copper checked before the
claim was made.

## 3. The type-system fix

`packages/temper-geometry/src/net_route_result.rs`:

```rust
pub struct VerifiedRoute {
    pad_ids: Vec<usize>,      // private
    segment_ids: Vec<usize>,  // private
    via_ids: Vec<usize>,      // private
}

pub enum NetRouteResult {
    Connected(VerifiedRoute),                                  // ONLY from verify_continuity
    ZoneDependent { outline_count, pads_in_outlines },
    Partial { segment_count, via_count, connected_pad_groups, unconnected_pads },
    Failed { reason: FailureReason },
}

impl NetRouteResult {
    pub fn verify_continuity(pads, tracks, vias, zone_layers, zone_outline_count) -> NetRouteResult;
}
```

* `VerifiedRoute` has no public constructor — its fields are private, so
  `Connected` cannot be written by hand anywhere outside the module. The
  `compile_fail` doctest on `NetRouteResult` pins this: a fabricated
  `NetRouteResult::Connected(VerifiedRoute { .. })` does not compile. This
  is the same structural-guarantee pattern as `layer_identity::Layer`.
* `verify_continuity` runs the existing union-find kernel
  (`connectivity_kernels::connectivity_partition`, extracted from
  `connectivity_components` with bit-identical output, pinned by the Wave-4
  differential) over the ACTUAL pads/segments/vias, then classifies:
  * all pads in one component → `Connected` (with the participating
    segment/via ids — isolated copper is excluded);
  * 0 pads → `Failed(NoPads)`; 1 pad → `Connected` (trivially, matching the
    audit's ground truth for <=1-pad nets);
  * otherwise, if every unreached pad has a zone outline on one of its
    layers → `ZoneDependent`;
  * otherwise, if any copper exists → `Partial` (with the specific
    unconnected pads);
  * otherwise → `Failed(NoCopperEmitted)`.
* **Zones are outlines, never copper.** A `(polygon ...)` block is the
  pour's drawn outline; nothing in this codebase runs KiCad's fill pass
  (measured: zero `filled_polygon` blocks in `definitive-route.kicad_pcb`'s
  391 zones). Zone presence only feeds the `ZoneDependent` classification —
  a net whose only claimed connection is an outline is NEVER `Connected`.
  This matches the audit's `zone_dependent_unmeasured` ("cannot measure",
  not a pass).
* The A* engine cannot claim "connected": it produces segments, and the
  verdict comes from `verify_continuity` on the emitted geometry.

pyo3 surface: `verify_net_route_result_py` + a frozen `NetRouteResult`
pyclass with no Python-side constructor — a `disposition == "connected"`
object from Python is proof the Rust union-find ran over real geometry.

## 4. Wiring and measurement

### Router-side (always on)

* `connectivity.verify_net_route_result` — Python shim over the Rust
  verdict (same flattening as `verify_net_connectivity`).
* `kicad_connectivity.net_route_result_preflight` — parses the EMITTED
  content with **real pad geometry** (world position via the canonical
  `pin_world_position` kernel; shape/size/rotation/layers from the parsed
  pins; THT barrels spanning the board's declared copper layers from the
  `(layers ...)` role block). This is stricter than the legacy U4
  preflight's best-effort 1.0×1.0 both-layer rects: a segment on the wrong
  layer from a pad's own layers is a genuine miss, not a silent union.
  Through-via semantics match the audit: a via with no type token pierces
  every copper layer; a typed (blind/buried/micro) via connects exactly its
  declared pair.
* `_build_routing_result` runs the preflight ALWAYS (not flag-gated like
  U4); failure is loud (`net_route_results=None`), never a fabricated
  verdict. `RoutingResult.net_route_results` carries the per-net verdicts.
* `route_board.py` prints a `(verified copper, NetRouteResult)` line with
  the per-net dispositions and names the partial / zone-dependent nets,
  alongside the post-hoc PRIMARY-metric audit (kept as the independent
  cross-check).

### Measured against the definitive route (139 pad-bearing nets)

```
NetRouteResult verdicts:  connected=92  zone_dependent=6  partial=13  failed=28
audit (PRIMARY metric):   fully_connected=92  fake_completion=14  honest_gap=33

cross-tab (audit category -> NetRouteResult disposition):
  audit-connected:  {'connected': 92}          <- all 92 genuinely connected verify
  audit-fake:       {'partial': 13, 'zone_dependent': 1}   <- NONE connected
  audit-honest:     {'zone_dependent': 5, 'failed': 28}
```

* **All 92 audit-connected nets pass `verify_continuity()`** — zero
  downgrades. (An earlier via-layer modeling bug downgraded 21 of them;
  fixed in commit `a5327de31` — a via with no type token is THROUGH.)
* **All 14 fake completions are now `partial` (13) or `zone_dependent`
  (1)** with the specific unconnected pads named (§2 table). None can be
  `Connected`: that variant does not exist outside `verify_continuity`.
* The 33 honest gaps decompose into 28 `failed` (no copper emitted at all)
  and 5 `zone_dependent` (outlines declared on the unreached pads' layers —
  the copper that would connect them has not been produced).

### Cost

Union-find per net is `~pads + segments + vias` unions — trivial compared
to the A* search. The preflight's board parse is the same cost the post-hoc
audit already paid in `route_board.py`; it now runs inside `route_pcb` so
the router's own result is honest.

## 5. Tests

* Rust (`temper-geometry`): 13 new tests in `net_route_result.rs` —
  fake-completion shape → partial with the specific unconnected pads;
  wrong-layer segment → partial; wrong-coordinate via → partial;
  zone-outline-only → zone_dependent (never connected); zone on the wrong
  layer does not rescue; partial copper + zone rescue → zone_dependent;
  multiple groups report which pads join which; isolated segments excluded
  from the verified route; single-pad trivially connected; zero-pads →
  failed. Full crate: 8432 pass. `compile_fail` doctest pins the
  unconstructible-`Connected` guarantee.
* Python: `tests/router_v6/test_net_route_result.py` (14 tests, shim +
  preflight over real written content) and a coverage-gate mirror in
  `tests/core/test_coverage_paydown_v17.py` (the gate runs only
  tests/core). Related suites pass: `test_kicad_connectivity_preflight`,
  `test_pad_connectivity_audit`, `test_all_pad_connectivity`,
  `test_routing_results`, `test_adapter_convert_rust_differential`,
  `test_adapter` (98 passed). The `edges_with_data` failures in
  `test_bundle_analyzer_rust_differential` / `test_bundled_full_pipeline`
  are the pre-existing SkeletonGraph-fixture issue (confirmed failing on
  `main` before this change; see handoff 2026-08-15 §5).

## 6. Known residuals

* `bias` is classified `partial` (pad U8.5 unreached). The audit agrees
  (fake). The pad-rotation model uses the parser's canonical convention
  (`initial_rotation_quadrant * 90 + pad_rotation_deg`); under a different
  reading of KiCad's pad-angle stacking the U8.4 through-via's annular ring
  would overlap U8.5's pad and the net would verify connected. Both models
  agree with the audit here; the parser's convention is what the rest of
  the codebase consumes. Worth a one-line human sanity check when U8's
  footprint is next touched.
* The A* "routed successfully" log line remains a *path-found* claim (it is
  now visibly contradicted by the verified line in normal output, not
  silently trusted). Retiring the print in favour of verified-verdict-only
  reporting is a follow-up, not this change.
* The legacy `V6RouterAdapter.rrr_route_all_nets` path (`_adapter_core.py`)
  builds `_AdapterRoutePath` success flags directly from
  `stage4.routed_paths` and does not run the preflight — it is the
  MazeRouter-compatibility surface, not the `route_pcb` production entry
  point (`route_board.py`'s docstring: route_pcb "is now the only routing
  entry point"). Wiring the verified verdicts into that legacy surface is a
  follow-up.
* `verify_net_connectivity` (U3/U4, flag-gated) is left untouched: it is
  differential-pinned and its 1-pad → INCOMPLETE semantics differ from the
  audit's/`NetRouteResult`'s 1-pad → connected. The new type is the
  authoritative verdict; the old preflight stays for compat/tests.
