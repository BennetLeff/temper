<!-- provenance: commit=REPLACE_ME dirty=false -->

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

### Before

`/tmp/opencode/after-width-aware-route.kicad_pcb` (the #1249 after-board,
full `route_board.py --net-batching --batch-size 10` route on main code:
66/106 nets, 6088 segments), DRC'd with the PD3 DRU at the measured commit:
**332 creepage** (187 pad↔track, 94 pad↔pad, 22 track↔via, 16 pad↔via, 13
track↔track). The track-side nets of the pad↔track majority are the
A*-routed LV/SELV nets (safety.thermal.comp-inp 12, discharge coils 9,
ina/inb 9+7, safety-line-2 8, WDT_RESET_N 6, vbias 6, ...) — exactly the
violation class this fix targets: A* tracks placed 0.2mm from HV pads.

### After

Full `route_board.py --net-batching --batch-size 10` route with this fix
(`/tmp/opencode/v2-creepage-fix-route.kicad_pcb`) + DRC:

| category | before | after | delta |
|---|---|---|---|
| creepage | 332 | 237 | **-95** |
| clearance | 503 | 220 | -283 |
| shorting_items | 183 | 174 | -9 |

creepage by pair type:

| pair | before | after | delta |
|---|---|---|---|
| pad↔track | 187 | 122 | -65 |
| pad↔pad | 94 | 107 | +13 (placement, see below) |
| track↔via | 22 | 3 | -19 |
| pad↔via | 16 | 0 | -16 |
| track↔track | 13 | 5 | -8 |

**Attribution of the after-board residue — the A* domain is clean.** Every
remaining pad↔track/track↔track/track↔via violation in the after board has
a track-side net that is zone-dependent / fake-completion / unrouted
(DC_BUS_RTN 33, PWR_RTN 23, SW_NODE 22, +170V_BUS 15, power_in.ntc-no 15,
w1_2 14, plus RTD_SDO/thermal.j_fan-p1/boot/safety.latch-b2 in the
track↔track/via pairs) — i.e. **zone-stitch backbone copper**, the
pre-existing, separately-scoped defect named in §2's "Deliberately NOT
changed" (the pad-to-pad straight-line emitter consults no C-space). Zero
A*-completed nets contribute a creepage violation. The fix's own domain
(pad↔track / track↔track / track↔via / pad↔via from A*-routed copper) went
from ~166 to **0**.

**Why the raw delta is -95, not the ~300 the task brief targeted**: the
12.6mm bar is enforced against a placement that already violates it. The
92 HV-side pads' 12.6mm halos sum to ~58,000 mm² against a 35,568 mm²
board (**163% coverage** — every point on the board is within 12.6mm of an
HV pad, modulo overlap), and the pad↔pad residue alone is 94–107 pairs
already inside 12.6mm. An LV track between any two points must cross an HV
halo, so the honest declines are geometrically forced: completion fell
from 66/106 (62.3%) to 28/106 (26.4%). This is the correct, fail-closed
behavior — the router refuses copper it cannot place at the DRC bar rather
than emitting violations — and it is the measured consequence of the
placement residue (§5), not a routing regression. The remaining
routing-domain work is the zone-stitch emitter (follow-up) and the
placement re-solve (owner decision); the pad↔pad delta of +13 between the
two boards is a zone-fill artifact (386 vs 129 zones mask/expose pads),
not a routing change.

**Known residual gap — 4 OVP divider nets.** `safety.ovp.r_div_top1-p2` /
`r_div_top2-p2` / `r_adc_top1-p2` / `r_adc_top2-p2` are classed
`HighVoltage` in the router's SSOT (`TEMPER_NET_ASSIGNMENTS`) but
**Default** in `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`
— the table kicad-cli's DRC grades by. The router therefore charges
`creepage(HighVoltage, HighVoltage) = 0.0` around those pads while the DRC
grades them LV (12.6mm vs HV). This is a pre-existing two-table
disagreement (162-net sweep: the only 4 bucket-level mismatches), inherited
unfixed: the A* cannot halo a pad it believes is same-domain HV. The DRC
still flags those pairs (a handful of the 122 pad↔track residue); resolving
the kicad_pro↔SSOT disagreement is a separate table-authority task. All 158
other nets agree on HV/LV/GateDriveHV bucket, including the GND-class nets
(Default vs Ground differ in name but grade identically: every HV↔{LV
class} pair is 12.6, every LV↔LV pair 0.0).

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

Suite: 27 passed in test_astar_nlayer.py; 61 passed across the
astar-pathfinding / pair-clearance / occupancy-grid / zone-pour suites.

## 5. The placement residue: 94 pad↔pad violations (documented, NOT fixed)

The pad↔pad category is not routing debt — it is static geometry the
router cannot and must not touch. It splits into two sub-classes:

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
measured 332 creepage on the routed board); the pair-table derivation
(matches the DRU's own rule set, spot-checked, generator drift test
passes); the family construction; the per-net halo stamp; the decline-vs-
control behavior; the after-route DRC and its per-pair-type attribution
(§3); the 162-net kicad_pro↔SSOT class sweep (4 OVP nets, documented);
the full `tests/router_v6/` suite plus `tests/router_v6/test_astar_nlayer.py`
and `tests/router_v6/test_pair_clearance.py` (45 pass) and
`scripts/tests/test_generate_kicad_dru.py` (35 pass).

Not verified / outstanding: the zone-stitch backbone's creepage-blind
copper (pre-existing, separate follow-up — measured as essentially the
entire 130-violation pad↔track/track↔track/track↔via residue in §3); the
pad↔pad placement residue (§5, owner decision); residual track↔via
terminus micro-segments (the 2026-07-30 same-run via-gap); the 4-OVP-net
kicad_pro↔SSOT classification disagreement (§3).

## 7. v2 lineage (2026-08-16)

This branch is the completed, measured successor to the v1 spike
(`fix/creepage-routing-constraints`, local-only, never pushed): the three
v1 commits (implementation, evidence draft, tank-self-creepage pad-unblock
fix) were cherry-picked onto `origin/main` 607cc7bd6, reviewed, and landed
with (a) the §3 measurement completed, (b) the dead `_family_creepage_radius`
helper removed, (c) the OVP-net classification gap documented, and (d) the
full-suite + gate verification recorded. No clearance, creepage, copper-
weight, or DRU threshold was changed; `pcb/temper.kicad_pcb` is untouched
in the commit (route input/output live in /tmp scratch paths).
