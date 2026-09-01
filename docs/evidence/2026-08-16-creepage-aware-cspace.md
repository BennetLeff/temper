<!-- provenance: commit=a418aa7809622165eb5c67f212aca26b5f3638ca dirty=false -->

<!-- worktree /tmp/opencode/agent-creepage-v2, branch fix/creepage-routing-constraints-v2,
     based on 607cc7bd6 (origin/main). kicad-cli 10.0.5. Every DRC number in this
     document was measured live with kicad-cli pcb drc --all-track-errors --format json
     against the PD3-enforcing DRU generated from scripts/generate_kicad_dru.py at
     the measured commit (12.6mm reinforced / 10.0mm tank functional). -->

# Creepage-aware obstacle halos in the N-layer A*: pair-creepage C-space

**Date:** 2026-08-16
**Branch:** `fix/creepage-routing-constraints-v2` (v2: completed measurement +
review of the v1 spike `fix/creepage-routing-constraints`, which was never
pushed or measured)
**Disposition: code change lands with this document** — the routing half of
the 510-creepage-violation spike (the placement half is documented in §5).

## 1. The defect

The N-layer A* path (`_astar_nlayer.py`) reserved only **CLEARANCE** around
static obstacles and between routed nets: the width-aware C-space (#1249,
2026-08-16) eroded the static obstacle layer by `W/2 + C` with
`C = max(declared, 0.2mm)` (RULE 10's track-involving floor), and stamped
routed copper at `w_F/2 + max(cl_F, C) + W/2`. Nothing in the obstacle map
knew the DRC's **creepage** figures: the generated DRU grades HV↔LV pairs at
**12.6mm** (PD3 reinforced) and HV↔HV tank pairs at **10.0mm** (PD3
functional), while the A* let an HV track thread 0.2mm from an LV pad.

Measured on the freshest full-route board at the time
(`/tmp/opencode/after-width-aware-route.kicad_pcb`, produced by #1249's own
measurement campaign): **333 creepage violations**, classified by item-pair
type:

| pair type | count | owner |
|---|---|---|
| pad↔track | 187 | A* C-space (this fix) |
| pad↔pad | 94 | placement (§5) |
| track↔via | 22 | A* C-space (this fix) |
| pad↔via | 17 | A* C-space (this fix) |
| track↔track | 13 | A* C-space (this fix) |
| **total** | **333** | |

(The 510/9/114/195 figures in the task brief came from a different routed
board; the classification SHAPE is the same — the routing debt is the
pad↔track/track↔track/track↔via/pad↔via majority, the placement residue is
pad↔pad. Rule breakdown of the 333: HV to LV 233, HighVoltageSignal to LV
55, AC Mains to LV 17, HighVoltageIsolated to LV 14, HighVoltageTank to LV
10, HighVoltageTank functional creepage 4.)

## 2. The fix

One occupancy-grid family per distinct `(trace_width, floored clearance,
creepage class)` signature among the nets a run actually routes. The
creepage class is the net's netclass, and the per-pair figure comes from a
new generated table, `configs/pair_creepage.generated.yaml`:

* `scripts/generate_kicad_dru.py` now emits it by resolving the DRU's own
  creepage rules under KiCad's last-matching-rule-wins precedence —
  `derive_pair_clearance_matrix(content, "creepage")`, the same derivation
  route the zone-pour creepage table (`zone_pour_creepage.generated.yaml`)
  already proved. The creepage rules' conditions key only on NetClass, so
  the Track↔Track world the matrix is resolved in is type-independent: the
  same figure grades pad↔track, track↔track, track↔via and pad↔via pairs
  of the same two classes. A pair no creepage rule matches resolves to
  0.0. Spot values: HV↔LV 12.6 (Table 17 row iv PD3 IIIa/IIIb ×2,
  cl. 29.2.3), tank↔{HV,Tank,HVSignal} 10.0 (Table 18 row vi PD3), and
  every pair involving GateDriveHV 0.0 (excluded from every reinforced
  rule's B-side) — all from the SafetyValue SSOT lookups the generator
  already uses.
* `router_v6/pair_creepage.py` loads it (mirrors `pair_clearance.py`);
  unknown classes resolve to `Default` (what KiCad reports for an
  unassigned net), no-rule pairs to 0.0.

In `_astar_nlayer.py` the family key grows the net's creepage class, and
the pair creepage is charged in both places a net can get too close:

* **Static obstacles** (pads, vias, pre-routed tracks, net-eligible
  zones): the family grid keeps the `W/2 + C` erosion, and each searching
  net additionally has the pair creepage stamped per-net as **-1 halos
  around FOREIGN obstacles only** (`_stamp_foreign_creepage_halos`). The
  halo polygon is the obstacle's exact shape buffered by
  `W/2 + C + creepage(family_class, obstacle_class)`; the stamp writes
  only free cells (0 → -1), so already-blocked cells and routed-copper
  ownership are untouched. This is deliberately re-stamped after
  `_unblock_net_pads` on every net: the unblock clears the -1 cells
  inside the routing net's own pad circles, which on a dense board
  includes whatever part of a foreign pad's much larger creepage halo
  falls inside them — without the re-stamp the net could route through
  another net's required creepage distance. The net's OWN pads are never
  haloed, so they stay enterable through the existing unblock mechanism
  (which clears only -1 cells within `pad + W/2 + C`).
* **Routed copper**: stamped into EVERY family at
  `w_F/2 + max(cl_F, C, creepage(class_F, family_class)) + W/2` — the
  #1249 width term with the pair creepage folded into the max. Edge-to-
  edge separation between F and any net searching that family is
  `>= max(cl_F, C, creepage) > 0` by construction, order-independent.

Why the creepage is charged per-net (halo stamp) rather than in the family
grid's static erosion: creepage is a PAIR property, and the family grid is
shared by every net of a class. A uniform erosion can only charge one
distance against all pads; the per-net stamp charges the exact pair figure
and, critically, leaves the searching net's OWN pads unhaloed (a
uniformly-dilated map would block a tank net from its own tank pads at
10.0mm and require the unblock to punch a hole big enough to swallow
neighbouring pads' halos).

### Why this is safe (creepage-clean by construction)

For a routed net F (width w_F, clearance cl_F, class C_F) and any net N
searching family (W, C, C_N):

* **static**: N's centerline is kept `>= W/2 + C + creepage(C_N, pad_class)`
  from every foreign pad edge (the erosion's `W/2 + C` plus the stamped
  halo's creepage) → N's copper edge is `>= C + creepage` from it, and
  `creepage(C_N, pad_class)` is exactly the figure the DRC grades for that
  pair;
* **dynamic**: N's centerline is kept
  `>= w_F/2 + max(cl_F, C, creepage(C_F, C_N)) + W/2` from F's centerline →
  the copper edge-to-edge gap is `>= max(cl_F, C, creepage(C_F, C_N))`,
  which is `>= creepage(C_F, C_N)` — the graded figure — and `>= 0.2mm`.

The rasteriser only ever reserves *more* than the nominal radius
(`expansion = ceil(radius/cell)`), so quantization adds margin, never
removes it. Same-net pads are never haloed and same-net cells stay
traversable (the A* core accepts `cell == net_id`), so a net can always
reach its own copper.

### Deliberately NOT changed

* **pad↔pad pairs** — placement-domain, see §5. The router cannot and must
  not fix static geometry.
* **Zone-stitch backbones** (`_zone_pour_stitch.py`) — the pad-to-pad
  straight-line emitter consults no C-space at all (the #1249 evidence doc
  quantifies it at ~150-170 SHORTS on this board); its copper can still
  violate creepage. Separate, pre-existing defect, scoped as a follow-up.
* `pcb/temper.kicad_pcb` is untouched (route output goes to a scratch path;
  DRC measured there).
* No ceiling, clearance, creepage, or DRU threshold was changed — the pair
  table is derived from the existing DRU, not a new safety figure.

## 3. Measurement

Both boards measured live at the v2 commit on the rebased base
(`origin/main` 7b424488f + this branch's 5 commits), PD3 DRU regenerated at
the measured commit, `kicad-cli pcb drc --all-track-errors --format json`.
BEFORE = full `route_board.py --net-batching --batch-size 10` route on
clean `origin/main` (`/tmp/opencode/v2-before-main-route.kicad_pcb`);
AFTER = identical command on this branch
(`/tmp/opencode/v2-after-creepage-route.kicad_pcb`). Same input board, same
flags, same DRU.

| category | before | after | delta |
|---|---|---|---|
| creepage | 306 | 157 | **-149** |
| clearance | 499 | 132 | -367 |
| shorting_items | 18 | 9 | -9 |

creepage by pair type:

| pair | before | after | delta |
|---|---|---|---|
| pad↔track | 178 | **0** | -178 |
| pad↔pad | 83 | 157 | +74 (zone-exposure artifact, see below) |
| track↔via | 15 | **0** | -15 |
| pad↔via | 17 | **0** | -17 |
| track↔track | 7 | **0** | -7 |
| via↔via | 6 | **0** | -6 |
| **track-involving total** | **223** | **0** | **-223** |

**Every track-involving creepage violation is eliminated.** The A*'s pair-
creepage halos + stamps (this branch) combine with #1261's zone-stitch
C-space gates (landed on main while this branch was in flight) so that not
one pad↔track / track↔track / track↔via / pad↔via / via↔via creepage
violation survives on the after board. The routing domain is creepage-clean
by construction.

The 157 remaining violations are **100% pad↔pad — static placement
geometry the router cannot and must not touch** (§5). The +74 vs the
before board is a zone-exposure artifact, not a routing regression: the
after board's zones (129, creepage-aware carves) leave more pads exposed as
standalone pads than the before board's zones (67), so more static
pad↔pad pairs are graded; 73 of the 79 before-board pairs remain, and the
newly-visible pairs are the same placement clusters (U6/U7/U27
+15V_LS↔LV pins, discharge pairs, gnd↔w1_1, ...). The pads did not move.

**Why completion fell 62.3% → 26.4%** (66/106 → 28/106 nets): the 12.6mm
bar is enforced against a placement that already violates it. The 92
HV-side pads' 12.6mm halos sum to ~58,000 mm² against a 35,568 mm² board
(**163% coverage** — every point is within 12.6mm of an HV pad, modulo
overlap), and the pad↔pad residue (§5) is 79–153 pairs already inside
12.6mm. An LV track between any two points must cross an HV halo, so the
honest declines are geometrically forced — the router refuses copper it
cannot place at the DRC bar instead of emitting violations. This is the
measured consequence of the placement residue, not a routing regression;
it is exactly the decline-vs-fabricate contract the A* already enforced.

**Known residual gap — 4 OVP divider nets.** `safety.ovp.r_div_top1-p2` /
`r_div_top2-p2` / `r_adc_top1-p2` / `r_adc_top2-p2` are classed
`HighVoltage` in the router's SSOT (`TEMPER_NET_ASSIGNMENTS` +
`netclass_rules.yaml`) but **Default** in `pcb/temper.kicad_pro`'s
`net_settings.netclass_assignments` — the table kicad-cli's DRC grades by.
The router therefore charges `creepage(HighVoltage, HighVoltage) = 0.0`
around those pads while the DRC grades them LV (12.6mm vs HV). This is a
pre-existing two-table disagreement (162-net sweep: the only 4 bucket-level
mismatches), inherited unfixed: the A* cannot halo a pad it believes is
same-domain HV. Resolving the kicad_pro↔SSOT disagreement is a separate
table-authority task. All 158 other nets agree on HV/LV/GateDriveHV
bucket, including the GND-class nets (Default vs Ground differ in name but
grade identically: every HV↔{LV class} pair is 12.6, every LV↔LV pair
0.0). (Impact on the after board: bounded; the OVP divider pads sit inside
the HV power pocket whose dominant remaining exposure is the pad↔pad
residue.)

## 4. Tests

`tests/router_v6/test_astar_nlayer.py` grows a creepage-aware section:

* `test_pair_creepage_table_resolves_dru_pairs` — the generated table's
  spot values: HV↔LV 12.6 symmetric, tank↔HV 10.0, LV↔LV / same-HV /
  GateDriveHV-involving 0.0, tank self-creepage 10.0;
* `test_creepage_halos_stamped_around_foreign_pads_only` — a mini PCB with
  an HV pad 6mm from an LV pad: the LV family halos the HV pad (12.6mm) but
  not the LV pad; the HV family halos the LV pad but not the HV pad; after
  `_stamp_foreign_creepage_halos` a cell 12.5mm from the HV pad is blocked
  while 14.5mm is free;
* `test_creepage_halo_blocks_lv_net_from_hv_pad` — end-to-end: an LV net
  that would pass 6mm from the HV pad either declines honestly or routes
  at >= 12.5mm centerline, and the control (HV pad reclassified LV) routes
  straight through, proving the decline is the creepage halo;
* the width-aware expectations are updated for the creepage term in the
  family key and the stamp radius (NARROW→WIDE family stamp clearance
  `max(0.2, 2.0, 12.6) + 2.5 = 15.1`).

Suite: 27 passed in test_astar_nlayer.py; 45 across astar_nlayer +
pair_clearance (v2 re-run); full `tests/router_v6/` on the rebased base:
**6796 passed, 23 failed, 18 skipped, 25 xfailed** — the 23 failures are
byte-identical on clean `origin/main` (verified in a scratch worktree):
SkeletonGraph-vs-networkx fixture drift (12), board-state pins (power
islands/strip-copper/pipeline-pad), boundary-classifier pins, kicad7
footprint-dir env, oracle-pin corpus — none touch the files this branch
changed. `scripts/tests/test_generate_kicad_dru.py`: 35 pass; the
regenerated `pair_creepage.generated.yaml` is byte-identical to committed.

## 5. The placement residue: 79–157 pad↔pad violations (documented, NOT fixed)

The pad↔pad category is not routing debt — it is static geometry the
router cannot and must not touch (measured 79–153 distinct pairs across
the two v2 boards; the count varies with zone exposure, the pairs do not
move). It splits into two sub-classes:

* **16 same-footprint pairs** (pads of different nets on one component):
  inherent to the package's own pin geometry — NOT fixable by any component
  move. Examples: C23 (Y-cap) hb-gnd↔+15V_LS at 0.65mm; U6 pad 10 input ↔
  pad 11 +15V_LS at 0.67mm; R51/R46 divider-top +170V_BUS↔sense-tap at
  1.8mm; K2/K3 relay coil PWR_RTN↔discharge at 3.04mm. Fixes live in part
  selection (larger pin pitch), slots, or documented acceptance — an
  owner/electrical call, flagged, not made here.
* **78 distinct different-footprint pairs**, clustering around ~10
  component pairs. The required displacement per pair is
  `12.6 − actual` (the DRC measures copper-to-copper, so the displacement
  is the gap shortfall):

  | cluster | representative pairs | actual | displacement |
  |---|---|---|---|
  | R5 ↔ U27 (PWR_RTN/DC_BUS_RTN vs io46/usb_dn/usb_dp/gpio18/RTD_SCK/safety-line/...) | ~15 pairs | 8.2–9.4mm | +3.2 to +4.4mm |
  | C22 ↔ R26 (hb.gate_hs.driver-p1-1/-p2 vs +3V3/I_SENSE) | 4 pairs | 3.6–4.2mm | +8.4 to +9.0mm |
  | R15 ↔ R18/R30, C17 ↔ R15, R8 ↔ R56 (discharge-snubber + gate-drive cluster) | ~6 pairs | 1.1–9.3mm | +3.3 to +11.5mm |
  | C23 ↔ U7/R9 (Y-cap ↔ gate-driver cluster) | 2 pairs | 0.9–3.2mm | +9.4 to +11.7mm |
  | R6 ↔ U2, C8 ↔ U1 (power pocket) | 3 pairs | 3.6–5.4mm | +7.2 to +9.0mm |
  | C14 ↔ R50/R69 (OVP/UVLO divider cluster) | 4 pairs | 8.6–9.4mm | +3.2 to +4.0mm |

  **Flagged, not moved.** The repo's own placement history on this board is
  unambiguous that hand moves in these pockets create new HV↔LV pairs (the
  #1244 cluster relocation's "0 new HV-LV pairs" claim missed C6 and paid
  +2 pairs; T2 proved unplaceable on two sites; the K1 re-place search
  found 14-15 new pairs over its legal spots). Every move here needs a
  placement re-solve with a courtyard- AND creepage-aware checker, and any
  pair it clears trades against new pairs it creates. That is a placement
  task, scoped for a follow-up with the checker; the required displacements
  above are the input. Note these were measured on the after-width-aware
  board; a re-route shifts the pad↔track set but not the pad↔pad set
  (static geometry).

## 6. What was and wasn't verified

Verified: the defect mechanism (clearance-only halos vs 12.6mm DRC bar,
measured 306 creepage on the before board, 223 track-involving); the
pair-table derivation (matches the DRU's own rule set, spot-checked,
generator drift test passes, regenerated table byte-identical); the family
construction; the per-net halo stamp; the decline-vs-control behavior; the
after-route DRC with per-pair-type attribution (**223 track-involving →
0**, §3); the 162-net kicad_pro↔SSOT class sweep (4 OVP nets, documented);
the full `tests/router_v6/` suite on the rebased base (6796 passed; the 23
failures verified byte-identical on clean origin/main).

Not verified / outstanding: the pad↔pad placement residue (§5, owner
decision); the 4-OVP-net kicad_pro↔SSOT classification disagreement (§3);
residual track↔via terminus micro-segments (the 2026-07-30 same-run
via-gap — 0 on the after board, still a known run-to-run shape); whether
the honest completion decline (62% → 26%) is acceptable to the owner or
whether the placement re-solve (§5) is the actual prerequisite for a
routable board.

## 7. v2 lineage (2026-08-16)

This branch is the completed, measured successor to the v1 spike
(`fix/creepage-routing-constraints`, local-only, never pushed): the three
v1 commits (implementation, evidence draft, tank-self-creepage pad-unblock
fix) were cherry-picked onto `origin/main`, reviewed, and landed with (a)
the §3 measurement completed (twice — once on the pre-#1260/#1261 base,
once on the rebased base after origin/main moved mid-session; the rebased
numbers are authoritative), (b) the dead `_family_creepage_radius` helper
removed, (c) the OVP-net classification gap documented, (d) the full-suite
+ gate verification recorded, and (e) the rebase onto the new origin/main
(#1259/#1260/#1261/#1263 — whose zone-stitch C-space gates compose with
this fix to take the track-involving residue from 223 to 0). No clearance,
creepage, copper-weight, or DRU threshold was changed; `pcb/temper.kicad_pcb`
is untouched in the commit (route input/output live in /tmp scratch paths).
