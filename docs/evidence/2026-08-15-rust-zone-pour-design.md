---
module: pcb
tags: [routing, zones, pour, rust-migration, geometry, creepage, gnd]
problem_type: design-and-prototype
date: 2026-08-15
---

# Rust Zone-Pour Design — root causes, algorithm, and working prototype (2026-08-15)

**Purpose**: root-cause the zone-emission defects the 2026-08-15 DRC
classification measured (fill resolves only 3 of 57 zone-net unconnected
items but adds **+222 creepage** and **167 isolated_copper islands**; gnd
has **no zone anywhere**; +3V3 zones are **dropped** by the router), design
the Rust replacement for the Python zone emission, and prototype the core
algorithm with measurements against the real board.

**Status**: design complete, prototype working (8/8 pure-Rust tests,
kicad-cli-verified output format, 8462 crate tests green, clippy clean,
wasm32 build green). The prototype is a NEW algorithm, not a port, so it
carries no oracle pin; it deliberately diverges from the Python emission
where the Python is measured wrong.

**Branch**: `feat/rust-zone-pour-design` (worktree `/tmp/opencode/agent-zone-rust`),
base `origin/main` @ `6285d6889`.

---

## 1. Root cause: why `gnd` has no zone

`pcb/temper.kicad_pcb`'s largest net (`gnd`, 88 pads) appears in **no zone
declaration** (classification §3: "net 48 appears in no zone declaration").
The chain of causes, each verified by reading the code:

1. `core/design_rules.py:709` assigns `"gnd": "Power"` in
   `TEMPER_NET_ASSIGNMENTS`.
2. The `Power` netclass (`design_rules.py:208-260`) declares **no
   `routing_strategy`** at all.
3. `_zone_pour_stitch.py::_zone_layers_for_net` grants zone eligibility
   only to classes whose `routing_strategy` is `plane_required` or
   `plane_preferred`. `Power` is neither → `_zone_layers_for_net("gnd") ==
   []` → `_emit_zone_pours` emits nothing for gnd.
4. `_net_policy.py::_should_route` excludes Power/GND/HV-named nets from A*
   **only when** `_zone_layers_for_net` returns a non-empty list. For gnd it
   is empty, so gnd *should* fall through to A* — but A* does not route it
   (it is one of the 87 unconnected gnd items). Net result: gnd gets copper
   from **neither** mechanism.

The `"gnd": "Power"` assignment was a deliberate 2026-08-12 fix
(`docs/evidence/2026-08-12-nonexistent-gnd-class-mapping.md`): the `"GND"`
class was never declared in `pcb/temper.kicad_pro`, so assigning gnd to it
was inert on the fab path. The comment **flags** the zone-eligibility side
effect explicitly ("Reassigning `gnd` here measurably drops it out of
F.Cu/B.Cu zone-pour eligibility") but does not fix it. `router_v6/_ground_plane.py`
targets the literal net name `gnd` (In1.Cu plane + via stitching) but is a
spike — **no production entry point calls it** (`scripts/route_board.py`
uses `router_v6.adapter.route_pcb` exclusively).

## 2. Root cause: why `+3V3` zones are dropped

`"+3V3": "Power"` (`design_rules.py:662`), and `Power` is deliberately
trace-only. This is a **documented policy decision, not an accident**
(2026-07-28, R1/R7 of `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`):
`test_power_class_is_not_zone_eligible` and ~a dozen other fixtures pin it.
The mechanism that makes it *visible* as "zones dropped": the router's write
path `strip_existing_zones` removes **every** committed zone, and
`_emit_zone_pours` re-emits only zone-eligible classes — so the committed
board's 34 `+3V3` zones vanish on every route (classification §3: "+3V3 49
[unconnected] — the router dropped the committed board's 34 +3V3 zones").

The policy's own evidence (2026-07-28 audit) found +3V3 pours historically
fragmented into 17/12/4 pad-sized remnants — i.e. **the old +3V3 pours were
already a failure mode of the same hull-buffer emission**, which is why the
policy exists. The measured 49 unconnected +3V3 items are the policy's
unpaid cost: A* has not routed them either.

## 3. Root cause: the 47+ island fragmentation

`power_in.ntc-no` is the fragmentation case (handoff §8.6, measured 47+
islands under real DRC-aware fill). Three interacting causes:

1. **Single board-spanning hull.** `_CONTINUITY_EXEMPT_NETS` exempts
   `power_in.ntc-no` from clustering (2026-08-14), so its 4 pads
   (30–140 mm apart) get ONE convex hull covering ~2223 mm² of the densest
   region of F.Cu (519 foreign pads, 1120 foreign tracks, 44 vias).
2. **Holes dropped from the outline.** `_carve_outline`
   (`_zone_pour_stitch.py:414-450`) subtracts the keepout but **discards
   interior holes** ("the emitted s-expression carries a single
   `(polygon (pts ...))` and cannot express one"). Every foreign pad inside
   the hull therefore stays inside the outline; the FILL then carves around
   it at local clearance, leaving thin rings that fracture into islands.
   All 96 committed zones on the board have exactly one polygon — none
   carries a hole.
3. **Fill adds its own clearance carving** on top of the outline carve, so
   the emitted 12-piece outline (measured, see §7) becomes 47+ filled
   islands (KiCad island removal then flags 167 `isolated_copper` warnings
   board-wide).

**The fill is not the problem — the outline is.** The router emits
outlines; KiCad fills them. A correct outline (holes preserved, pair-aware
carve, honest island policy) produces a fill that cannot fragment into
unconnected pieces.

## 4. Root cause: the +222 creepage violations from fill

The carve is **clearance-aware, not creepage-aware**:

- `pair_clearance_keepout` (`zone_pour_clearance.py:196`) buffers foreign
  copper by `configs/zone_pour_clearance.generated.yaml` — the DRU
  **clearance** table. For HV-vs-LV pairs that figure is **2.0 mm**
  (`HighVoltage|Power: {Track: 2.0, Pad: 2.0, ...}`).
- The DRC judges HV-vs-LV **creepage** at **12.6 mm** (PD3 reinforced —
  live in the routed board's DRU; the classification measured the exact
  symptom: "+170V_BUS pour 2.0 mm from +3V3 pad of U16").
- The fill pours right up to the 2.0 mm carve edge; the creepage rule then
  measures 2.0 mm of surface separation where 12.6 mm is required. Measured
  here: a gnd pour carved at 2.0 mm has min gap **2.00 mm** to HV pads; the
  same pour carved at 12.6 mm has min gap **12.58 mm** (see §7).

So the single `(clearance ...)` scalar and the clearance-table carve cannot
fix this — the outline must subtract **pair creepage** halos (12.6 mm
HV↔LV, 10.0 mm HV↔HV PD3), not pair clearance.

## 5. The Rust design

### 5.1 Where it lives

New pure-Rust module `packages/temper-geometry/src/zone_generator.rs`
(always compiled, wasm32-safe), pyo3 surface under the `python` feature,
registered in `lib.rs` alongside `zone_pour.rs`. Uses the already-pinned
`geo = "0.28"` dependency (same crate `convex_hull.rs` uses) for the
polygon boolean operations (`geo::BooleanOps::union`/`difference` on
`MultiPolygon`) — **no new external crate**.

### 5.2 API

```rust
pub enum ZoneObstacle {
    Pad { position: Point, half_w: f64, half_h: f64, rotation_rad: f64, clearance_mm: f64 },
    Track { start: Point, end: Point, width_mm: f64, clearance_mm: f64 },
    Via { position: Point, diameter_mm: f64, clearance_mm: f64 },
}
// clearance_mm is the caller-resolved PAIR figure (clearance or creepage,
// whichever governs that net pair).

pub struct ZoneOutline { pub exterior: Vec<Point>, pub holes: Vec<Vec<Point>> }

pub enum IslandPolicy { KeepAll, PadsOnly }   // plane nets vs clustered pours

pub struct PourResult {
    pub outlines: Vec<ZoneOutline>,
    pub dropped_islands: usize,
    pub keepout_area_mm2: f64,
    pub pour_area_mm2: f64,
}

pub fn pour_outline(
    region: &[Point],          // board outline / per-cluster hull (caller-clipped)
    own_pads: &[Point],        // the net's own pads on this layer
    obstacles: &[ZoneObstacle],// foreign copper, per-pair separation resolved
    min_island_area_mm2: f64,  // sliver floor (0.25*0.25 == KiCad min_thickness^2)
    policy: IslandPolicy,
) -> PourResult

pub fn emit_zone_s_expr(net_number, net_name, layer, outline, clearance, priority, min_thickness) -> String
```

### 5.3 Algorithm

1. **Keepout union**: one halo per obstacle — disc for pads/vias
   (`max(half_w, half_h) + clearance`, matching the Python
   `Point.buffer(...)` convention; `rotation_rad` accepted but unused by the
   disc — documented), capsule for tracks (`LineString.buffer` convention).
   Unioned via `MultiPolygon::union`.
2. **Carve**: `region.difference(keepout)` — the polygon-boolean core that
   Python's shapely does today, now in Rust.
3. **Decompose + orient**: each resulting polygon becomes a `ZoneOutline`
   (exterior + holes), normalised exterior-CCW / holes-CW (KiCad's
   convention). **Holes are preserved** — the key representational fix.
4. **Filter**: drop pieces below the area floor; under `PadsOnly`, drop
   pieces containing no own pad. Deterministic output ordering (bbox area
   desc, then first-vertex lexicographic) so zone emission order never
   depends on geo's internal iteration.
5. **Emit**: one `(zone ...)` per outline, one `(polygon (pts ...))` element
   per ring.

### 5.4 The format discovery (worth its own record)

The first emitter draft wrote multiple `(pts ...)` blocks inside ONE
`(polygon ...)` — an easy guess, and **wrong**. kicad-cli 10.0.5 rejected
it at load ("Expecting ')'", caught by the splice test before anything
consumed it). The actual format, verified against the KiCad source:

- **Writer** (`pcb_io_kicad_sexpr.cpp::format(const ZONE*)`): iterates the
  outline poly-set's chains and emits **one `(polygon (pts ...))` element
  per chain**.
- **Parser** (`pcb_io_kicad_sexpr_parser.cpp::parseZONE`): each
  `(polygon ...)` element is read into a chain and passed to
  `ZONE::AddPolygon`, whose contract is "If the zone outline is empty, this
  is the main outline. Otherwise it is a hole inside the main outline."

So: exterior = first `(polygon ...)`, holes = subsequent `(polygon ...)`
elements. The splice test now splices a real 3-hole zone into a copy of the
board and `kicad-cli pcb drc --refill-zones` **exits 0 and refills** — the
format is accepted end-to-end.

## 6. Python stopgap assessment (what a quick fix can and cannot do)

The two "why no zone" root causes are policy/SSOT decisions, not geometry:

- **gnd**: reassigning `"gnd"` to a `plane_preferred` class (or granting
  `Power` a routing strategy) re-enables emission, but the F.Cu/B.Cu
  emission would pour gnd over the whole board at 6 mm clearance and
  reproduce the exact oversized-pour regression the 2026-07-28 audit
  measured (Task 2). The correct gnd fix is an **inner-layer plane**
  (In1.Cu), which is `_ground_plane.py`'s spike — the production wiring of
  that spike is a real task, not a one-liner.
- **+3V3**: flipping Power to zone-eligible would silently revert the
  R1/R7 decision for every net in the class (`+15V`, `vcc`,
  `V_BUS_SENSE`), which the audit explicitly rejected. A +3V3-specific
  pour needs per-net treatment, and the honest measurement (§7) shows only
  19/50 +3V3 pads can be pour-covered at PD3 anyway (the rest sit within
  12.6 mm of HV copper and must be trace-routed).
- The **creepage carve** (12.6/10.0 mm halos) can be done in Python today
  (shapely, exactly the harness's `halos_for`), but it makes the current
  emissions *fail*: ntc-no's F.Cu hull gets 0/4 pads covered (see §7). A
  Python carve fix without the Rust outline machinery (holes, honest
  island policy, per-layer routing) would emit empty or near-empty zones.

**Conclusion: the Python stopgap is not cheap and not obviously safe. The
Rust module is the right home; wiring it into `_emit_zone_pours` is the
next session's job.**

## 7. Prototype measurements (real board, `pcb/temper.kicad_pcb` @ origin/main)

Harness: `docs/evidence/scripts/2026-08-15-zone-pour-design.py` (shapely mirrors
the Rust algorithm; run with the shared venv, read-only). Board: 35568 mm²,
6-layer, 19 HV-domain nets (elec/domain_manifest.yaml).

**A. gnd full-board pour on In1.Cu (carve: HV pads @ 12.6 mm PD3):**

| metric | value |
|---|---|
| pour pieces | **6** (single connected-ish plane, not 47+) |
| keepout area | 21713 mm² (61 % of board — HV halos dominate) |
| gnd pads inside pour | **67/88** |
| uncovered by cause | 18 inside HV halo (must via-stitch), 3 outside 1 mm edge margin |
| min gap pour→HV pad | **12.58 mm ≥ 12.6 ✓** |
| contrast: old 2.0 mm carve | **2.00 mm — creepage VIOLATION** (the +222 family) |

**B. power_in.ntc-no single hull on F.Cu:**

| carve | pieces | pads covered |
|---|---|---|
| old (2.0 mm clearance) | 12 | 1/4 |
| new (creepage 12.6/10.0) | 2 | **0/4** |
| new on In3.Cu (sparse inner layer) | 1 | **0/4** |

**The single-hull pour for ntc-no is infeasible at PD3 on every layer.**
The new algorithm says so explicitly (0 pads covered) instead of emitting a
pour that fragments into 47+ misleading islands. The 2026-08-14 evidence
doc's own conclusion stands: this net needs component re-placement
(K1/RT1/U1/U2), real traces for ampacity, or manual routing — no outline
generator can pour a 150 mm corridor at 12.6 mm creepage through this board.

**C. +3V3 per-cluster pours on F.Cu (pair carve):** 21 clusters → 18
pieces, **19/50 pads covered**. 31 pads sit within 12.6 mm of HV copper
and cannot be pour-covered; they are the A* trace burden.

## 8. What is implementable now vs what needs a bigger effort

**Done in this session (implemented, tested, committed):**
- `pour_outline` core (keepout union → boolean carve → holes → island
  policy → deterministic ordering), 8 unit tests, 8462 crate tests green,
  clippy clean, wasm32 build green.
- `emit_zone_s_expr` in KiCad's real hole format, verified against
  kicad-cli 10.0.5 via the splice test.
- pyo3 surface (`pour_outline_py`, `emit_zone_s_expr_py`) — compiles under
  `--features python`; NOT built into any venv (no shared-venv rebuilds).

**Next session (wire-up):**
1. `_emit_zone_pours` (or a new `_emit_zone_pours_rust`) calls
   `pour_outline_py` per net/layer: region = board outline (gnd plane) or
   per-cluster hull (HV pours), obstacles = `pair_clearance_keepout`'s
   geometry re-expressed as `ZoneObstacle`s **with creepage figures** where
   creepage > clearance (needs a creepage pair table — the DRU generator
   `scripts/generate_kicad_dru.py` writes the creepage rules; a
   `zone_pour_creepage.generated.yaml` twin of the clearance table is the
   natural source).
2. gnd: production-wire the In1.Cu plane (adopt `_ground_plane.py`'s
   via/MST stitching for the 18 halo-excluded + 3 edge-margin pads).
3. Island bridging (copper necks) for pours where split islands each carry
   pads — needs a neck-width-validated corridor search; documented, not
   attempted (a wrong-width neck is its own DRC violation).

**Not in scope of the design:** thermal relief, board-edge keepout beyond
the region clip, netclass policy changes (gnd/+3V3 eligibility is an owner
decision, see §6).

## 9. Verification summary

- `cargo test --no-default-features` (temper-geometry): **8462 passed, 0 failed**
- `cargo clippy --no-default-features`: 0 warnings for `zone_generator`
- `cargo check --features python`: clean (pyo3 surface compiles)
- `cargo check --target wasm32-unknown-unknown`: clean
- `kicad-cli 10.0.5 pcb drc --refill-zones` on spliced hole-carrying zone:
  exit 0, refilled, DRC report produced
- Board file `pcb/temper.kicad_pcb` untouched (sha256 of the worktree copy
  unchanged from origin/main; the main checkout's copy was already dirty
  before this session and was not used for any measurement)
