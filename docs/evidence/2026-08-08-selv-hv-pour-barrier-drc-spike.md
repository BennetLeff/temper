<!-- provenance: commit=10083607 dirty=false -->

# SELV/HV isolation-barrier pour-crossing DRC spike

**Date:** 2026-08-08
**Branch:** `spike/selv-hv-pour-barrier-drc` (worktree, based on `agent/router-combined` @ `6121c49f`)
**Scope:** spike a DRC detector that catches copper zone/pour polygons crossing the SELV/HV
isolation barrier, per the measured gap in `docs/evidence/2026-08-08-power-plane-spec-readiness.md`
(commit `2f6c02cc`, §3b).

All figures below come from commands run in this session against this worktree, listed inline.

---

## 1. What existed before this change

Searching for prior work (`git branch -a`, `git log --all --grep`) turned up no existing
pour-crossing-the-barrier detector on any branch. The closest prior artifacts:

- `origin/safety/mains-selv-isolation-barrier` (commit `645154b7`): places a
  `MAINS_SELV_ISOLATION_BARRIER` KiCad keepout zone directly on `pcb/temper.kicad_pcb` (a vertical
  strip, x=90.203–99.203mm i.e. centerline x=94.703mm, 9.0mm wide, spanning `F.Cu In1.Cu In2.Cu
  B.Cu`, y beyond both board edges). Its own commit message reports that **no single straight
  barrier line can separate this board's HV and SELV pads**: an exhaustive search over axis-aligned
  positions and all 180° of orientation still misclassifies 28–32% of pads, because HV/SELV pad
  centroids are only 5.9mm apart on a 152×234mm board. This branch is unmerged and this spike does
  not merge or build on it directly (per the hard constraint against modifying
  `pcb/temper.kicad_pcb`), but its derived geometry is reused below as a documented, honestly-cited
  *candidate* barrier line for the real-board demonstration in §4.
- `origin/plans/isolation-barrier`, `origin/plans/barrier-feasibility-experiment`,
  `origin/exp/barrier-corridor-feasibility-recut`: placement-feasibility studies (corridor width,
  drift cost) for where a barrier *could* go. No DRC-check code.

**A relevant existing mechanism was found that the gap-finding evidence doc's own search (scoped to
`packages/temper-drc-rs/src/rules/safety/`) did not surface**, because it lives in a sibling
directory: `packages/temper-drc-rs/src/rules/routing/isolation_barrier.rs` already defined a
`routing::IsolationBarrierCheck`, registered in the default rule registry
(`rules/mod.rs:252`), that reads real zone-polygon geometry (`BoardState::zones: Vec<CopperZone>`,
which already carries a full `geo::Polygon<f64>` — this is *not* the same struct as
`constraints::ZoneDefinition`, which the gap-finding doc correctly diagnosed as missing `bounds`)
and a `constraints::IsolationBarrier` (`name`, `x_mm`, `y_span`, `layers`) config type, and checks
zone/trace intersection with the barrier line. However, it was:

1. **Untested** — zero unit tests existed for it before this change.
2. **Crossing-only** — no clearance/near-miss semantics; a pour 0.001mm short of the line passed.
3. **`layers` field present but unused** — declared in the config type, never read by `check()`.
4. **Dead against the real project config**, for the same root reason the gap-finding doc
   identified for `IsolationCheck`: `packages/temper-placer/configs/temper_constraints.yaml` has
   zero `isolation_barrier` entries (`grep -c isolation_barrier temper_constraints.yaml` → 0), so
   `ConstraintSet::isolation_barriers` is empty on every real run and the check is a structural
   no-op — not because of a geometry bug, but because nothing supplies it a barrier to check
   against.

So the gap-finding doc's core conclusion ("nothing in the DRC/validator surface checks plane/zone
geometry against the isolation barrier") is correct in effect — the one rule capable of it never
fires on the real project — but not quite correct in mechanism: the geometric capability already
existed and needed hardening + activation, not invention from zero.

---

## 2. Where does the barrier live? Nowhere machine-readable, confirmed independently

`grep -rn "isolation_barrier" packages/temper-placer/configs/temper_constraints.yaml` → 0 hits.
The only machine-readable barrier representation in the whole project is the unmerged KiCad
keepout on `origin/safety/mains-selv-isolation-barrier` (§1), which is not part of any config a
DRC run reads, and is not merged. This is the key finding the task asked to make explicit if true,
and it is true: **there is no adopted, certified isolation-barrier geometry anywhere in this
project's committed, machine-readable state.**

Consequently `constraints::IsolationBarrier` is documented (in its own doc comment, this change)
as the explicit-input mechanism: a barrier is supplied by whoever calls the check (a future config
key, or a caller passing one directly), and the detector activates the moment one exists, without
further schema changes.

---

## 3. What was built

`packages/temper-drc-rs/src/rules/routing/isolation_barrier.rs` (commit `dde6625f`):

- `constraints::IsolationBarrier` gains `clearance_mm: f64` (default `0.0`, preserving prior
  crossing-only behavior for any caller that doesn't set it) and the previously-unused `layers`
  field is now actually read.
- `check()` now flags, per barrier, per covered layer:
  - **Crossing** (`ROUTING_ISO_001` trace / `ROUTING_ISO_002` zone) — direct
    `geo::Intersects` with the barrier line, CRITICAL, unchanged from before.
  - **Clearance** (`ROUTING_ISO_003` trace / `ROUTING_ISO_004` zone) — new: edge-to-edge
    `geo::EuclideanDistance` (the crate's existing K5 convention — see `board.rs`'s
    `Component::edge_distance_to`) below `barrier.clearance_mm`, CRITICAL. A pour that comes close
    without literally touching the line is still caught.
- Layer scope: `barrier.layers` (comma-separated KiCad layer names, or `"all"`) now filters which
  zones/traces a barrier applies to. **Design decision, justified in code**: `"all"` is the default
  because an inner-layer (`In1.Cu`/`In2.Cu`) pour crossing the barrier is exactly as dangerous as an
  outer-layer one — nothing about copper on an inner layer makes it less of a shock hazard. A test
  (`barrier_spanning_all_layers_catches_inner_layer_crossing`) constructs an `In1.Cu` crossing and
  confirms it is caught under the default; a companion test
  (`barrier_scoped_to_outer_layers_ignores_inner_layer_crossing`) confirms the narrowing mechanism
  itself works, for the (non-default) case a caller has a specific reason to scope it.
- 10 new unit tests (`cargo test --lib`: 157 passed, was 147; 0 failed), listed in §4's summary.
- Also registered in the WASM32 test registry (`scripts/gen_wasm_test_registry.py`'s `ELIGIBLE`
  list + regenerated `wasm_test_registry.rs`), so these tests run on the Worker tier too.

**`constraints::ZoneDefinition`'s missing `bounds` field (deliberately not touched):** the
gap-finding doc's evidence pointed at this struct (used by `safety::IsolationCheck`,
`isolation_slot`, `zone_containment` — all *named-config-zone* checks keyed by net-class name, not
real copper). This detector does not use that struct at all — it reads real geometry directly from
`board::CopperZone.polygon`, which already carries a full `geo::Polygon<f64>` and needed no schema
restoration. Restoring `bounds` to `constraints::ZoneDefinition` would be dead weight without also
rewiring `IsolationCheck`'s containment logic (currently pure net-class-name matching) to use it —
a separate, larger fix this spike does not attempt, and one that would need care around whatever
existing behavior depends on the current name-matching semantics. Assessed and consciously not
done; not an oversight.

---

## 4. Anti-vacuity demonstration

### 4a. Synthetic FAIL case — a pour that genuinely crosses the barrier

`zone_pour_crossing_barrier_is_rejected`: a GND-net rectangular pour on `F.Cu` from
`(60,50)` to `(110,90)` against a barrier at `x=94.703mm` — the pour's right edge is at
`x=110`, past the barrier. **Result: 1 violation, `ROUTING_ISO_002`, `Severity::Critical`.**

```
running 1 test
test rules::routing::isolation_barrier::tests::zone_pour_crossing_barrier_is_rejected ... ok
```

### 4b. Synthetic PASS case — a pour that respects the barrier

`zone_pour_respecting_barrier_with_margin_is_accepted`: the same net, `F.Cu`, entirely inside
`(10,50)`–`(60,90)` — 34.7mm clear of the barrier, well past the 8.0mm REINFORCED clearance figure
used in the fixture. **Result: 0 violations.**

### 4c. Clearance (near-miss) semantics — not just crossing

`zone_pour_within_clearance_but_not_crossing_is_rejected`: a pour whose nearest edge sits at
`x=92.0`, i.e. 2.703mm from the barrier — inside the 8.0mm clearance requirement but never crossing
`x=94.703`. **Result: 1 violation, `ROUTING_ISO_004`, reported distance 2.703mm** (asserted exactly,
not just "some violation"). The companion test `zero_clearance_barrier_only_flags_actual_crossings`
confirms the same geometry produces **0 violations** when `clearance_mm=0.0`, i.e. the new clearance
path is additive and doesn't change crossing-only behavior when unused.

### 4d. Full local test run

```
$ cargo test --lib   # packages/temper-drc-rs, default features
test result: ok. 157 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

(147 pre-existing + 10 new for this check; 0 regressions.)

### 4e. Real board run — `pcb/temper.kicad_pcb`, unmodified

Board serialized read-only via the existing `tools/wasm/r2_serialize_board.py` bridge (already used
for the R2 cost-model benchmark; not written for this spike) — `pcb/temper.kicad_pcb` itself is
never touched. Board: 152.0mm × 234.0mm (independently re-verified against the file's own
`Edge.Cuts` `gr_poly`, lines 8245–8251: `(20,20)`–`(172,254)`), 96 real zones (all on `F.Cu`/`B.Cu`
— **confirms** the gap doc's finding that `In1.Cu`/`In2.Cu` have zero copper today), 54 real routed
traces.

Ran with the candidate barrier geometry derived on `origin/safety/mains-selv-isolation-barrier`
(§1: x=94.703mm, y∈[0,274], all 4 layers) and the REQ-SAFE-01 REINFORCED clearance figure
(8.0mm):

```
$ cargo run --example selv_hv_barrier_real_board -- real_board.json real_board_barrier_constraints.json
Board: 152.0mm x 234.0mm, 96 zones, 54 traces
Barriers supplied: 1
  'MAINS_SELV_ISOLATION_BARRIER' x=94.703mm y_span=[0.0,274.0] layers=all clearance_mm=8.00
Zones by layer: {"F.Cu": 48, "B.Cu": 48}
Distinct zone nets (14): {"+15V", "+15V_LS", "+3V3", "DC_BUS_RTN", "GATE_HS", "GATE_LS",
  "PWM_HS", "PWM_LS", "PWR_RTN", "SW_NODE", "V_BUS_SENSE", "ac_l", "ac_n", "vcc"}

=== IsolationBarrierCheck result: 398 violation(s) ===
```

Breakdown: 19 `ROUTING_ISO_001` (trace crossing), 20 `ROUTING_ISO_002` (zone crossing), 351
`ROUTING_ISO_003` (trace clearance), 8 `ROUTING_ISO_004` (zone clearance). Re-run with
`clearance_mm=0.0` (crossing-only, matching the pre-hardening check's exact prior behavior): **39
violations** (19 + 20 — the crossing counts are the same in both runs, as expected).

**Reading this result honestly, not vacuously:**

- This is *not* "the shipped board has 398 real safety defects." No barrier is certified or
  adopted anywhere in this project (§2) — `x=94.703mm` is a documented candidate line, not a
  design decision this spike is entitled to make. What this run demonstrates is that the check
  fires abundantly and specifically on real, non-trivial geometry — it does not just pass
  everything, which is the actual anti-vacuity bar.
- The result is also independent corroboration of `origin/safety/mains-selv-isolation-barrier`'s
  own finding (§1): that commit found no single straight line separates this board's HV and SELV
  *pads*. This run finds the same thing is true of the *copper* (zones on `ac_l`/`ac_n`/`DC_BUS_RTN`
  — HV-side nets — and `+3V3`/`vcc`/`PWR_RTN` — SELV-side nets — both cross whichever side of
  `x=94.703mm` the other domain occupies) via an entirely different code path (polygon geometry, not
  pad centroids). Two independent measurements agreeing is stronger evidence than either alone that
  this board's current component placement cannot be isolated by a single straight barrier, and
  that resolving it requires either a placement change or a non-straight (stepped) barrier — matching
  what the corridor-feasibility docs on `origin/exp/barrier-corridor-feasibility-recut` already
  concluded from a placement angle.
- Per the task's own framing: the empty `In1.Cu`/`In2.Cu` inner layers mean a clean *inner-layer*
  result would have proven nothing. This run is not clean, on the outer layers, which is
  actually stronger anti-vacuity evidence than a clean run would have been.

---

## 5. Would this have caught the defect commit `6976ef44` removed?

Commit `6976ef443e819db3466c3d8d2712cce43f6c15f9` ("fix(hardware): float SELV control domain,
remove star-point ground join") removed `power_return ~ gnd` from `elec/src/main.ato` — a
**net-topology** join that galvanically connected the SELV control-domain ground to the HV-side
doubler midpoint, shorting the AuxSupply IRM-10-15's certified 4.2kVAC isolation barrier (per
`docs/hardware/SELV_ISOLATION_REDESIGN.md` and `IEC60335_CRITICAL_COMPONENTS.md` §2.1).

**Precisely why the literal defect is out of this detector's scope**: it was a schematic net join,
never placed or routed PCB copper. The real board's `In1.Cu`/`In2.Cu` were and remain empty
(§4e), so there is no historical geometric artifact on `pcb/temper.kicad_pcb` to replay through a
copper-geometry check — this detector operates on physical zone/trace polygons, and the defect it
would need to "catch" never took that form. (The correct check for the literal, still-relevant
defect is `scripts/check_domain_partition.py`, which is net-topology-based and already wired into
CI per `elec/domain_manifest.yaml`.)

**What is in scope, and demonstrated**: the geometric construction that net join would produce if
someone had realized the same short as copper instead of a netlist join — a single pour on a
ground/return net physically bridging both sides of the barrier. Test
`catches_geometric_analog_of_star_point_ground_bridge_removed_by_6976ef44` constructs exactly this
(a `gnd`-net pour on `In2.Cu` from `x=20` to `x=140`, crossing the `x=94.703` barrier) and confirms
it is rejected (`ROUTING_ISO_002`, CRITICAL). This is an analog constructed to demonstrate the
mechanism, presented as such — not a claim that the historical defect is being literally replayed.

---

## 6. Productionizing — honest assessment

What this spike does *not* do, and what stands between it and CI enforcement:

1. **No certified barrier geometry exists to encode.** This is the load-bearing gap. Until the
   board owner adopts a specific barrier line/region (§2's finding), any config entry this spike
   could add would carry the same "unadopted candidate" caveat as §4e's demonstration run. Wiring
   this into CI today would either (a) run with zero barriers, staying the same structural no-op
   the gap-finding doc found, or (b) require choosing and defending a specific barrier geometry,
   which §4e shows is not currently satisfiable by a single straight line given the existing
   placement — a placement/architecture decision, not a DRC-detector decision.
2. **No config → `IsolationBarrier` wiring.** `temper_constraints.yaml`'s YAML schema would need an
   `isolation_barrier` (or `isolation_barriers`) key, and whatever builds `constraints_dict` for
   `build_constraint_set` (currently only `ConstraintSet::default()` in `r2_serialize_board.py`'s
   demo path, and no discovered production path at all) would need to populate it from that key —
   neither exists today.
3. **The real-board zone/trace pipeline is currently benchmark-only.** `tools/wasm/
   r2_serialize_board.py` (used for §4e) is the only discovered code path that populates
   `BoardState.zones`/`.traces` with real geometry from the real board via the Rust bridge; the
   placer's own `drc_runner.py` builds a differently-shaped `"zones"` dict (name/bounds placement
   zones, not net/layer/polygon copper) that would not deserialize correctly if fed to
   `build_board_state`'s zone parser (`extract_copper_zone` expects `net`/`layer`/`polygon` keys).
   This mismatch is a landmine for whoever wires real DRC runs to this check next — flagged here,
   not fixed, since fixing `drc_runner.py`'s schema is out of this spike's scope.
4. **Straight-line-only barrier model.** `IsolationBarrier` represents one vertical line segment. If
   the board owner's eventual barrier is stepped/non-straight (which §4e and
   `origin/exp/barrier-corridor-feasibility-recut`'s corridor-feasibility findings suggest may be
   required), the struct and the line-intersection/distance logic would need generalizing to an
   arbitrary polyline or polygon boundary — a moderate, well-scoped follow-up, not a rewrite (the
   `geo` crate supports `LineString`/`Polygon` distance and intersection the same way).
5. **Not yet in `create_default_registry()`'s enforced path for CI purposes** — it *is* registered
   (line 252, pre-existing), so it runs whenever `run_drc()` is called; what's missing is a caller
   that (a) supplies a real barrier and (b) supplies real zone geometry, in the same run, against
   CI's board of record. Today no such caller exists.

None of the above blocks using this detector today for exactly what it's for: given a barrier
(from any source — a future config key, a manual constraints object, or a caller like the example
in this change), it will correctly reject a crossing/near-miss pour and accept a compliant one, on
real or synthetic geometry, on any layer. What's missing is the barrier itself and the plumbing to
a CI-invoked real-board run — both organizational/config gaps, not detector-capability gaps.
