<!-- provenance: baseline artifact scratch_out/temper_routed_nlayer.kicad_pcb produced on branch
fix/router-nlayer-routing (commit 1d6aa4020, docs measurement committed as f870bc966), worktree
/home/bennet/Desktop/temper-worktrees/router-nlayer-routing -- read-only input to this document, never
regenerated or modified here. This document's own fix is on branch agent/router-pad-attachment-diagnosis,
built from origin/fix/router-nlayer-routing (f870bc966), commit b460db6e7
(fix(router): land N-layer routes on their pad's real copper layer), plus two unrelated commits already
on that branch when this work started (ee3e5f2aa, dd7131e13 -- another agent's trace-width ampacity work,
untouched by this document). PR #1178 (the 6-layer stackup decision this branch descends from) has NOT
merged to main as of this writing -- board_layer_roles.py and ENGINE_SUPPORTED_SIGNAL_LAYERS do not exist
on main; the 2-grid cap in _pipeline_route.py and enable_nlayer_astar_spike=False are what's live there.
_astar_nlayer.py itself (the module this fix lives in) DOES already exist on main as a pre-existing,
flag-gated spike module. "Clean" measurement (the After column) was produced in a THIRD, freshly
`make venv-isolate`d worktree (/tmp/.../scratchpad/clean-wt, branch
agent/router-pad-attachment-diagnosis-clean, detached at b460db6e7) specifically to rule out contamination
from a different agent's concurrent uncommitted edits to trace_width_assignment.py in the original
diagnosis worktree -- confirmed identical to a same-commit run taken in the (possibly contaminated)
original worktree, so the contamination did not in fact affect these results, but the isolated run is
what these numbers are cited from. pcb/temper.kicad_pcb sha256=
1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d -- unchanged throughout. No DRU/
clearance/creepage threshold changed. No ceiling in power_pcb_dataset/drc_ceiling.json touched. -->

# Router N-layer routing: pad-layer landing was the bottleneck, not routing capacity -- diagnosis, fix, and a measured before/after

**Verdict up front.**

1. **Root cause, confirmed by direct coordinate audit, not assumption:** `channel_mapping._assign_layer` applies a net's netclass-SSOT working layer (e.g. `GateDriveHV`/`GateDriveSELV`'s `layer: "B.Cu"` in `netclass_rules.yaml`) unconditionally once the net's class is explicit (non-`Default`) -- with **no check that this layer matches the layer the net's own footprints are actually placed on** (every SMD part on this board sits on `F.Cu`). A prior version of this function had exactly that check (a "divergence guard: ssot == heuristic"); it was deliberately removed, on the stated assumption that "via-aware transitions (U1-U6) provide legal layer changes." That assumption is false for `_astar_nlayer.py`'s 3-tier cascade: Tier 1 (same-layer 2D search on the net's single assigned working layer) has no notion of "does this (x, y) have real copper on THIS layer" -- an SMD pad leaves no grid obstacle on a layer it has no copper on, so Tier 1 walks straight to the pad's exact (x, y) on the SSOT-forced layer and reports success. Because Tier 1 succeeded, Tiers 2 and 3 -- the ONLY tiers that ever place a via -- never run. §1.
2. **Measured directly, real coordinates, no inference:** on the real board, net `GATE_HS`'s emitted copper (67 segments, all on `B.Cu`) starts at exactly `(47.6025, 115.35)` -- pad `R18.1`'s center, on `F.Cu` -- and ends at exactly `(82.735, 137.555)` -- pad `U6.15`'s center, on `F.Cu` -- with zero vias anywhere in the net. This is not a coordinate-transform bug, not a grid-quantization short, not an off-by-one-cell error: the copper lands EXACTLY on the pad center, on a layer that pad has zero copper on. Same shape, same precision, for 8 more nets. Generalized across all 71 fake-completion nets in the baseline: 64/71 show the identical "copper reaches the pad's (x, y), wrong layer, no via" shape on at least one pad. §2.
3. **Fix: `_land_route_on_pad_layers`** (`_astar_nlayer.py`), inserted into `run_astar_pathfinding_nlayer` right after a route succeeds and before pad-unblock restoration. Lands a route on its pad's real layer via an explicit via wherever the two disagree, using the same same-XY-different-layer encoding Tier 2's alternate-detour already uses. Fails closed (declines the net) rather than land a via through another net's already-claimed copper. §3.
4. **Measured before/after, same tool, same board:** fully pad-connected 52/139 -> **59/139** (+7); fake-completion 71 -> **58** (-13); honest-gap 16 -> **22** (+6). The accounting closes exactly: of the 13 nets that left fake-completion, 7 became genuinely connected and 6 became honest failures (the fail-closed path declining rather than fabricating). This is the correct direction -- fakes converting to real completions and to honest declines, not honest gaps converting into fakes. §4.
5. **Two real caveats that cut against over-claiming, both reported plainly, not smoothed over:** (a) 3 of the original 9 confirmed nets (`cs_n`, `sdo`, `RTD_DRDY`) remain fake-completion via a SECOND, distinct mechanism this fix does not address -- root-caused, not fixed. (b) `gnd` and `vcc` regress from partial (fake) copper to zero copper under this fix -- confirmed NOT a zone-pour audit blind spot (checked directly: zero zone blocks for either net in both the before and after board), a real trade-off of net-level fail-closed decline on large multi-pad nets. §5.
6. **The pad-connectivity audit tool itself (`pad_connectivity_audit.py`) has two independent bugs found during this diagnosis, both false positives that inflate the fake-completion count, both left untouched per this task's explicit instruction not to edit the detector.** §6.
7. **The `[LedgerReport IMBALANCED] routing_complete: net_count: 112 -> 0, component_count: 168 -> 0` message is a real accounting defect, not a routing regression** -- confirmed by code reading alone, present identically in the pinned pre-migration oracle, not a Rust-migration bug. Not fixed (would require updating a content-hash-pinned oracle file). §7.

---

## 1. Root cause

`packages/temper-placer/configs/netclass_rules.yaml` declares:

```yaml
GateDriveHV:      # GATE_HS, GATE_LS
  layer: "B.Cu"
GateDriveSELV:    # PWM_HS, PWM_LS
  layer: "B.Cu"
```

Both are explicit (non-`Default`) netclasses. `channel_mapping._assign_layer` (Rust: `assign_layer_impl` in `temper-orchestration/src/channel_mapping.rs`):

```rust
let heuristic = if net_class_is_power(...) || is_ground || is_hv { "B.Cu" } else { "F.Cu" };
if let Some(ssot) = ssot_layer_for_net_impl(...)? {
    return Ok(ssot);   // <-- applied unconditionally, no comparison against `heuristic`
}
Ok(heuristic)
```

The pinned differential oracle (`tests/router_v6/_channel_ops_py_oracle.py`) carries the same behavior with an explicit comment explaining why:

> W2 U2 / R2 / U7: SSOT-driven layer assignment from the netclass YAML. When the net has an explicit netclass with a routable SSOT layer, apply it. **The divergence guard (ssot == heuristic) is removed**; via-aware transitions (U1-U6) provide legal layer changes, and the fallback tier handles unreachable terminals gracefully.

The removed guard would have refused to force a net (e.g. `GATE_HS`, whose name-heuristic says signal -> `F.Cu`) onto a netclass-declared `B.Cu` when the two disagreed. Its replacement's assumption -- "via-aware transitions... provide legal layer changes" -- does not hold for `_astar_nlayer.py`'s per-segment tier cascade (`packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py`, `_astar_route_nlayer`):

- **Tier 1**: 2D A* on `primary_grid` (the net's single assigned working layer, chosen once for the whole net from `channel_path.preferred_layer`). No layer-correctness check against the segment's start/end pads.
- **Tier 2**: whole-segment detour on every OTHER layer, anchored with explicit vias at both ends -- but only runs when Tier 1 FAILS.
- **Tier 3**: full via-aware 3D search across every grid -- also only runs when Tiers 1-2 fail.

An SMD pad physically exists on exactly one copper layer. A layer it has no copper on carries no grid obstacle at that pad's location -- there is nothing there to route around, so Tier 1's same-layer search can walk straight through the pad's own (x, y) coordinate on the wrong layer and report a clean, obstacle-free "arrival." Because Tier 1 already returned success, Tiers 2 and 3 -- the only tiers that ever call the via-insertion path -- never execute. `_unblock_net_pads` (`astar_grid.py`) was checked and confirmed to correctly restrict its temporary unblocking to a pad's OWN declared layer (`elif layer in grids: target_grids = [grids[layer]]`) -- the wrong-layer cell isn't spuriously unblocked by that mechanism; it's simply never blocked in the first place, because nothing else on the board occupies it either.

This is real on `main` today, independent of the unmerged 6-layer stackup work: `GateDriveHV`/`GateDriveSELV`'s `layer: "B.Cu"` and `_assign_layer`'s unconditional SSOT-apply are both present on `main`. It only manifests at the scale measured here once the 2-grid routing cap is lifted (the `fix/router-nlayer-routing` branch's contribution) and channel capacity lets Stage 3's SAT solver commit far more nets to a topology at all.

---

## 2. The measured shape, real coordinates

Net `GATE_HS` (2 pads), from `scratch_out/temper_routed_nlayer.kicad_pcb`:

```
PAD  R18.1  (47.6025, 115.35)     layer=F.Cu
PAD  U6.15  (82.735, 137.555)     layer=F.Cu

SEG  (47.6025, 115.35) -> (47.75, 115.45)   layer=B.Cu   <- starts EXACTLY at R18.1
  ... 65 more segments, all on B.Cu ...
SEG  (82.65, 137.45) -> (82.735, 137.555)   layer=B.Cu   <- ends EXACTLY at U6.15

vias: 0
```

Same shape (exact-XY match, single wrong layer, zero vias) for `PWM_HS`, `PWM_LS`, `sclk`, `RTD_SDI`, `RTD_CS_N`, `cs_n`, `sdo`, `RTD_DRDY` -- 9 nets total, all `pad_count == 2`. Not a coordinate-transform error (checked `kicad_transform.rs`'s R(+θ) history per this task's lead -- not implicated; the XY math is exact to the pad center every time), not a grid-quantization short.

Generalized across all 71 fake-completion nets in the baseline (checking, per net, whether EVERY pad has copper or a via touching its exact (x, y) on ITS OWN layer): **64 of 71 fail this check on at least one pad.** The remaining 7 are a distinct, unrelated bug in the audit tool itself, not the router (§6) -- confirmed by hand for each: the copper genuinely does connect, the audit's own graph construction is what's wrong. Some fraction of the 64 are large power/ground/plane nets (`gnd` at 88 pads, `+15V`, `vcc`, `DC_BUS_RTN`, etc.) the audit tool cannot evaluate correctly at all in the presence of zone pours (it parses only `segment`/`via` blocks, never `zone`) -- that fraction is not separated out here and the 64 figure should be read as an upper bound on nets this fix's mechanism could plausibly help, not a proven count.

---

## 3. The fix

`_land_route_on_pad_layers` (`_astar_nlayer.py`), called from `run_astar_pathfinding_nlayer.attempt_route` immediately after a route succeeds (`forced_segment_count == 0`) and **before** `_restore_net_pads` runs -- ordering matters: `_restore_net_pads` re-blocks any pad-radius grid cell the route didn't itself claim, which would make every landing check see "blocked" even for a legitimate landing, since the wrong-layer cell was never the one temporarily unblocked in the first place.

For a route's first and last emitted point: if that point sits on a net pad's (x, y) but the pad's own layer differs from the point's layer, insert a via there using the exact same same-XY-different-layer segment-list encoding Tier 2's alternate-detour already uses -- proven correct end-to-end already in the SAME measured baseline artifact: `WDT_KICK`'s via round-trips this exact encoding into a real emitted `(via ...)` block with correct `from`/`to` layers, unmodified existing code, not something introduced here.

Fails closed (declines the net, new failure reason `pad_layer_landing_blocked`) when the pad's own layer is not actually free at that point -- another net's copper already claims it -- rather than fabricate a via through it. A no-op whenever a route already lands correctly. Every existing test in `test_astar_nlayer.py` never passes `pcb=`, so `pad_centers_per_net` is always empty there and this code path is provably never reached by any of them (confirmed: all 10 pre-existing tests pass unchanged). Added 5 new tests -- a no-op case, a landing-via-insertion case (exact segment/via layout assertion), a fail-closed-when-occupied case, a THT-pad-skip case, and one full `run_astar_pathfinding_nlayer` end-to-end reproduction (SSOT forces `B.Cu`, pads are `F.Cu`, asserts the final routed copper lands on `F.Cu` at both ends with vias at both pad positions) -- all 15 pass. Ran the broader `router_v6` suite (~1500+ tests, `packages/temper-placer/tests/router_v6/`): 2 pre-existing failures, neither caused by this change -- `test_bundle_analyzer.py::test_identical_signal_nets_bundle` (a `networkx` `Graph.edges_with_data` API mismatch predating this session, confirmed by `git blame`) and `test_phase1_anti_false_zero.py::test_kicad7_footprint_dir_resolves` (this sandbox has no KiCad footprint library installed -- confirmed a pure environment gap by running it in isolation).

This fix does **not** restore the removed divergence guard. Restoring it would push every SSOT-classified net (`GATE_HS`, `PWM_HS`, all of `GateDriveHV`/`GateDriveSELV`) back onto whatever its bare name-keyword heuristic says, discarding the actual netclass-driven copper-weight/routing-convention intent those classes exist to express. The fix instead makes the router's own via-insertion machinery do what the guard's replacement already assumed it was doing.

---

## 4. Before/after, same tool, same board

`pad_connectivity_audit.audit_pcb_file` -- same tool, same audit path this branch's earlier measurement used.

| | before (baseline, `fix/router-nlayer-routing`) | after (this fix) |
|---|---:|---:|
| fully pad-connected | 52/139 | **59/139** (+7) |
| fake-completion | 71 | **58** (-13) |
| honest-gap | 16 | **22** (+6) |
| unrouted (Stage-4 topology) | 9 | 15 (+6) |
| segments | 6114 | 5612 |
| vias | 74 | **103** (+29) |
| F.Cu↔B.Cu vias specifically | 10 | **43** (+33) -- the landing vias appearing, directly |
| zones | 160 | 160 (unchanged) |
| topology-routed | 97/106 | 91/106 |
| wall time | 483.2s | 679.3s (isolated worktree) / 518.5s (same commit, contaminated worktree -- identical connectivity numbers both times, see provenance note) |

The 13-net movement out of fake-completion accounts exactly: 7 became genuinely fully connected, 6 became honest declines. This is the fail-closed path doing precisely what it is for -- declining a net rather than emitting copper that does not land -- not gaps converting into fakes, which would have been the wrong direction and was explicitly checked for.

Of the 9 confirmed-by-coordinate-audit nets from §2, **6 are fixed**: `GATE_HS`, `PWM_HS`, `PWM_LS`, `sclk`, `RTD_SDI`, `RTD_CS_N` all show `fully_connected=True` in the after board. **3 remain fake-completion** -- see §5a.

**Both before and after numbers were measured with the same audit tool, which is itself known to have two false-positive bugs (§6) and a zone-pour blind spot.** All three push the fake-completion count in the same direction on both sides of this comparison, so the *delta* reported above is meaningful (the instrument is identical on both sides) -- but the absolute values (52, 59, 71, 58, 16, 22) should not be read as ground truth until the audit-tool fixes land separately. This is stated explicitly, not left implicit.

---

## 5. Two caveats, reported plainly

### 5a. Three nets still fake-completion via a second, distinct mechanism

`cs_n`, `sdo`, `RTD_DRDY` remain fake-completion after this fix. Root-caused, not the same shape as the other 6:

For these 3 nets, the net's `primary_grid` (working layer choice) is ALSO wrong (not `F.Cu`) -- the same §1 root cause -- but Tier 2's whole-segment alternate-layer detour fires (rather than Tier 1 trivially "succeeding"), and Tier 2 **already** anchors its own via at the pad's (x, y) using the (wrong) primary layer. This fix's landing check then ALSO fires at that same coordinate and inserts a second via, producing three distinct layers meeting at one physical point (the pad's real layer, Tier 2's wrong primary, Tier 2's chosen alternate).

`via_layer_pair` (`packages/temper-geometry/src/via_clearance.rs:100`) infers a via's `from`/`to` layer pair by finding the FIRST index in the route's flat point list where the via's (x, y) occurs (`via_segment_index`), then returns `(points[i].layer, points[i+1].layer)` -- it does not know how to resolve more than one via crossing stacked at the same coordinate. Traced by hand for `cs_n`: both duplicate via records at each pad position resolve to the identical (and, at one end, wrong) layer pair, because both calls independently re-scan from the start of the list and land on the same first occurrence. The transition that would actually land the copper on the pad's real layer is silently never captured as a via.

This is a pre-existing latent gap in `via_layer_pair` (it assumes at most 2 layers ever meet at one point) that this fix newly exposes, by being the first thing to stack a second via crossing atop a point Tier 2 already used. Not fixed here. Two candidate directions for a follow-up, not attempted: (a) have `_land_route_on_pad_layers` detect and extend/replace an existing co-located via rather than append a duplicate, or (b) fix `primary_grid` selection itself so Tier 2 never anchors on the wrong layer to begin with, which would prevent the 3-layer collision from arising at all. (b) looks like the more correct long-term direction, since (a) is a patch on top of a still-wrong root layer choice.

### 5b. `gnd` and `vcc` regress from partial copper to zero copper

Checked directly per this task's specific caution about zone-pour blindness: `gnd` and `vcc` have **zero** `(zone ...)` blocks with their `net_name` in BOTH the before and after board (confirmed by direct paren-balanced block extraction, not the audit tool). The 14 nets that DO have zone pours (`+15V_LS`, `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n`, plus several small `discharge.*`/misc nets) are identical, same per-net zone counts, between the before and after boards. So this is confirmed **not** a zone-pour audit artifact.

It is real: before, `gnd` had 106 segments (0 vias) and `vcc` had 150 segments (0 vias) -- both fake-completion, copper existed but never actually joined every pad. After this fix, both have exactly 0 segments and 0 vias. Mechanism: this fix's fail-closed decline is net-level, all-or-nothing -- if even one endpoint's landing via cannot be legally placed, the ENTIRE net (even an otherwise mostly-valid multi-hop route) is discarded, not just the bad landing. For a large multi-pad net whose chain touches many congested regions (`gnd` has 88 pads), this is a real trade-off: honest zero copper instead of copper that never actually worked. This matches the project's stated fail-closed philosophy (never emit copper that does not genuinely connect its pads) but is reported here explicitly as a cost of this specific fix, not smoothed over. A more surgical per-endpoint decline (keep valid mid-chain segments, refuse only the bad landing) was not attempted.

---

## 6. Audit-tool bugs found during this diagnosis (not fixed, per task instruction)

Both in `pad_connectivity_audit.py`, both false positives (inflate the fake-completion count on nets that are actually correctly connected), both left untouched.

**Bug A -- union-find stale-root reassignment on THT/`"*"` pads.** `check_net_pad_connectivity`'s pad loop unions a THT pad's per-layer node set together via `_UnionFind.union`, which is not rank-based (`self._parent[ra] = rb` unconditionally, no size/rank comparison). Processing a SECOND THT pad's own multi-layer expansion can drag the root of an ALREADY-merged component (which an earlier pad's `pad_roots.append(uf.find(...))` snapshot already pointed at) onto an untouched, pad-position-specific node -- the earlier snapshot goes stale. Minimal repro: `thermal.j_fan-p1` (2 THT pads) -- verified the 167 segments between its two pads form exactly one connected component via a standalone segment-only union-find, yet `check_net_pad_connectivity` reports them disconnected. `discharge.r_dis1a-p2`, `discharge.r_dis2a-p2` are two more repros of the identical shape.

**Bug B -- `_cluster_key` round-half-to-even tie boundary.** `_cluster_key` does `round(coord / tolerance_mm)` with `tolerance_mm=0.02`. Pad positions can carry ~1e-14mm float noise from footprint-transform composition (e.g. `139.53000000000003`); router-emitted via/segment coordinates are clean literals (`139.53`). When the true value divided by 0.02 lands exactly on a `.5` boundary, Python's round-half-to-even sends the clean value to the nearest even bucket while the noisy value (fractionally above .5) rounds to the next bucket up -- splitting one physical point in two. Confirmed repro: `WDT_KICK` -- its via and adjoining segment DO correctly meet (checked by hand, both ends), but the audit reports it fake-completion purely from this bucket split. `i2c_sda_ui`, `safety.ocp-line`, `safety-line-3` are three more repros.

---

## 7. `[LedgerReport IMBALANCED] routing_complete` -- accounting defect, not a routing regression

Confirmed by code reading alone, no run required. `self.ledger.checkout("routing_complete", result)` is called with `result` = the final `RouterV6Result` wrapper dataclass (`.pcb`, `.stage2`, `.stage3`, `.stage4`, etc. -- no top-level `.nets`/`.components`, no `._parsed_pcb`). `snapshot_cardinality` (`packages/temper-orchestration/src/stage_ledger.rs`) only recognizes a `BoardState`-shaped object (`._parsed_pcb.nets`/`.components`) or a `ParsedPCB`-shaped object (top-level `.nets`/`.components` directly) -- `RouterV6Result` matches neither, so every field of the post-snapshot defaults to 0, producing exactly the observed `112 -> 0`, `168 -> 0`. The actual routed board still has all 112 nets and 168 components; this is purely a diagnostic-message defect.

Not a Rust-migration regression: the pinned Python oracle (`tests/router_v6/_pipeline_core_py_oracle.py:325`) has the byte-identical call with the same object, so `temper-orchestration/src/router_pipeline.rs:816-819`'s Rust port is faithfully reproducing a pre-existing defect in the original pipeline. The obvious fix (pass `result.pcb` instead of `result` at both call sites) is simple in isolation, but the oracle file is content-hash-pinned in `scripts/oracle_hashes.json` -- correctly updating it is a distinct, separately-reviewable unit of work. Judged provable but not cheap; not attempted here.

---

## 8. What was deliberately not changed, and why

- The removed divergence guard in `_assign_layer` was not restored -- see §3's closing paragraph for why that would be the wrong fix.
- `pad_connectivity_audit.py`'s two bugs (§6) were diagnosed and reported with concrete repros but not fixed -- per this task's explicit instruction not to edit the fake-completion detector.
- The ledger accounting defect (§7) was diagnosed but not fixed -- provable, not cheap (crosses a pinned-oracle change-control boundary).
- The `via_layer_pair` co-located-via limitation (§5a) was diagnosed but not fixed -- cross-crate (`temper-geometry`), has its own oracle/differential tests, and two candidate fix directions with different tradeoffs that deserve their own review rather than a rushed patch here.
- The net-level all-or-nothing fail-closed decision (§5b) was not made more surgical (per-endpoint partial decline) -- a real, separately-scoped improvement, not attempted here.
- No DRU/clearance/creepage threshold changed. No ceiling in `power_pcb_dataset/drc_ceiling.json` touched. `pcb/temper.kicad_pcb`'s sha256 unchanged throughout.
