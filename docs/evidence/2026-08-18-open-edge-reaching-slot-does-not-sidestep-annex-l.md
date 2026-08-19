<!-- provenance: commit=e63028ccde1be397032479e0735f2a7c1f710d95 (origin/main), branch
     investigate/open-slot-creepage, own fresh git worktree
     (.claude/worktrees/openslot-2026-08-18), never the main checkout.
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified identical BEFORE and AFTER all work, in both this worktree and the main
     checkout (Sec 8). No board, footprint, DRU, netclass, threshold, or safety constant was
     opened for writing anywhere in this task. No slot was cut. All geometry was measured
     read-only with `kiutils` against the real board S-expression, and creepage with a
     `shapely`+`networkx` visibility-graph solver written this session under the session
     scratchpad, never into `pcb/`. `scripts/measure_cross_domain_creepage.py` was NOT used
     (its R(+theta)/R(-theta) bug is unmerged as of PR #1376). -->
---
module: pcb
tags: [creepage, pd3, slot, iec-60664-1, annex-l, isolation, analysis-only]
problem_type: standards-geometry
---

# 2026-08-18: An open, edge-reaching slot does **not** sidestep the contested closed-end credit — measured, not argued

**Authority: analysis only.** `pcb/temper.kicad_pcb` was not modified (Sec 8).

## 0. Verdict up front

The task this document answers was framed on two premises. **Both are false**, and the second is
false for a geometric reason that is measurable and was measured.

1. **"Nobody has tested it" is wrong.** The open/edge-reaching slot was tested on 2026-08-13 and
   the result is on `origin/main` today:
   `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md`. Its title states the
   conclusion: *"the standards question is narrowed to one end, not eliminated, for all three."*

2. **"A groove that reaches the board edge has no closed end" is wrong.** Reaching the edge removes
   **one** of a slot's two ends. The other end stays closed, and the governing (shortest) creepage
   path runs around **that** end. Opening one end changes *which pad pair governs* and does not
   change *what number governs* — reproduced this session to 4 decimal places, on the current board,
   for **both** T1 and U6:

| geometry | T1 governing creepage | U6 governing creepage |
|---|---:|---:|
| island (both ends closed) | **13.2655 mm** (pad1↔pad4) | **14.8525 mm** (pad9↔pad8) |
| OPEN, one end to board edge | **13.2655 mm** | **14.8525 mm** |
| worst-case (−0.2 mm/routed edge), island | **12.8296 mm** | **14.1106 mm** |
| worst-case, OPEN | **12.8296 mm** | **14.1106 mm** |
| both ends open (**severs the board**) | ∞ (no surface path) | ∞ (no surface path) |

The open slot's entire margin over 12.6 mm still rests on the credit for measuring the creepage path
**around a closed slot end** — exactly the credit that `IEC 60335-1` Annex L governs and that this
project has confirmed unobtainable. **The paywalled document is not sidestepped. It is load-bearing
in the open design too.**

The one thing that *is* uncontested — that no creepage path exists past a real board edge, because
there is no insulating surface there — contributes **nothing** to the governing figure, because
removing a candidate path can only ever remove a tie, never create a shorter minimum.

---

## 1. What the standard actually says, verbatim

Groove width `X`, minimum by pollution degree — IEC 60664-1 cl. 4.2 (2002-era text / IS 15382
(Part 1):2003), renumbered cl. 6.8 in editions 3.0:2020 and 3.1:2025, content unchanged. Transcribed
from primary source in `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` §1, **not
re-fetched or reconstructed here**:

> "The dimension X, specified in the following examples, has a minimum value depending on the
> pollution degree as follows:
>
> | Pollution degree | Dimension X minimum value |
> |---|---|
> | 1 | 0,25 mm |
> | 2 | 1,0 mm |
> | 3 | 1,5 mm |
>
> If the associated clearance is less than 3 mm, the minimum dimension X may be reduced to one
> third of this clearance."

The two governing worked examples, same clause:

> **Example 1** — "Condition: Path under consideration includes a parallel- or converging-sided
> groove of any depth with a width less than X mm. Rule: Creepage distance and clearance are
> measured directly across the groove as shown."
>
> **Example 2** — "Condition: Path under consideration includes a parallel-sided groove of any
> depth and equal to or more than X mm. Rule: Clearance is the 'line of sight' distance. Creepage
> path follows the contour of the groove."

And the general principle:

> "creepage distances and clearances measured between parts which can assume different positions in
> relation to each other, are measured when these parts are in their most unfavorable position."

**X at PD3 = 1,5 mm.** Both slots proposed below (4.0 mm for T1, 7.30 mm for U6) clear it by
2.7×–4.9×. **Groove-width legitimacy is not the blocker and never was.**

### 1.1 The precise gap — stated so it is not confused with a different one

Example 2 is a **2D cross-section**. It licenses "creepage path follows the contour of the groove"
across the groove's *width*. All 11 worked examples in every edition checked (PR #1155's 2002-era
read, PR #1160's 3.0:2020 / 3.1:2025 re-check) are cross-sections of a groove, rib, joint or screw
head that is implicitly edge-to-edge in the third dimension. **None pictures a groove that stops,
with an end a creepage path detours around.**

Going around a closed end is an extrapolation of "follows the contour" into the third dimension. It
is the credit every slot design here depends on, and it is **not** established by the text above.
The relevant measurement procedure lives in **IEC 60335-1 Annex L** (pp. 170–172), which
`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` establishes as **not
obtainable** after an exhaustive search (archive.org's complete `60335-1` catalog enumerated — 32
items, all read; targeted BS EN / AS NZS / SANS searches; two vendor previews reached far enough to
read the standard's own verbatim TOC and List of Figures, confirming Annex L's page range and that
its three figures are titled as measurement *procedure* flowcharts).

**Precision note, per this task's own warning:** Annex L is a normative annex of **IEC 60335-1**,
not of IEC 60664-1. The clause 4.2/6.8 groove text quoted above **is** IEC 60664-1. An earlier
analysis in this repo conflated the two; this document does not. Separately: **IEC 60335-1 Table 8
is *Maximum Winding Temperature*, not a creepage table** — Tables 17 and 18 are the creepage tables
and are recovered verbatim in-repo.

---

## 2. The topological reason this cannot be fixed by picking a better slot path

Let `B` be the board region and `V` the void a slot removes.

- If `B \ V` is **connected** (the board does not fall into pieces), then a continuous insulating
  surface path exists between any HV pad and any SELV pad, and its length is the creepage. That path
  must pass through the land bridge that keeps `B \ V` connected — i.e. it goes **around an end of
  `V`**. That end is closed by construction: if it were not, `V` would reach the boundary there too.
- If `V` touches the outline at **two** distinct points on the same connected void, `B \ V` is
  **disconnected** — an elementary consequence of the Jordan curve theorem for a simple arc with
  both endpoints on the boundary of a simply-connected planar region. The board outline is a single
  simple rectangle (`gr_poly`, 4 vertices, x 8→172, y 20→254; **verified directly this session:
  exactly one `Edge.Cuts` graphic item on the whole board, no existing internal slot or cutout**).

So: **every slot that does not sever the board has at least one closed end, and the governing
creepage path goes around it.** "Reaching the board edge" buys the removal of one candidate path.
The minimum is set by the *other* end. This is why the measured numbers in Sec 0 are identical.

The task's own brief already contains this fact — "By the Jordan curve theorem a mid-board part
always has a closed end" — and then draws the opposite conclusion for edge-reaching slots. The
inference "reaches the board edge ⟹ no closed end" is where it breaks.

The `∞` row in Sec 0 is the honest form of the alternative: it is what a genuinely open-at-both-ends
cut gives, and it is unavailable because it puts the board in two pieces.

---

## 3. Method and its validation

Creepage is computed as the shortest path along the board surface between two pad coppers, with the
slot as an impassable void and the board outline as the domain — a `shapely` + `networkx` visibility
graph over densified pad boundaries (0.05 mm) plus slot corners, Dijkstra-weighted by Euclidean
length. Written this session; **validated before use, in both directions**:

| check | computed | expected | source |
|---|---:|---:|---|
| T1, no slot | **9.1000** | 9.1000 | `pad_geometry.pad_pair_distance` (canonical kernel) |
| U6, no slot | **8.1000** | 8.1000 | `pad_geometry.pad_pair_distance` |
| T1 island 28.0 × 8.0 mm | **15.5323** | 15.532 | PR #1155 |
| T1 island 28.0 × 4.0 mm | **13.2655** | 13.265 | PR #1160 |
| U6 island 17.0 × 7.30 mm | **14.8525** | 14.85 | PR #1155 |
| U6 island worst-case | **14.1106** | 14.11 | PR #1155 |

The no-slot rows are the important ones: with the obstacle removed, the solver reproduces the
project's own Rust-backed `pad_pair_distance` **exactly**, which pins the pad geometry, the world
transform, and the path metric independently of the published slot figures it then reproduces.

Pad world positions were derived with the sanctioned **R(−θ)** local→world convention and fed to
`pad_geometry.pad_pair_distance`; the resulting binding-pair and package-maximum figures
(Sec 4) match the task brief's own values exactly, which cross-validates the rotation convention
end-to-end. `scripts/measure_cross_domain_creepage.py` was **not** used (PR #1376's R(+θ)/R(−θ) fix
is unmerged).

Board outline, all 155 footprint courtyards, and all 4 722 trace items were extracted read-only with
`kiutils`.

---

## 4. Per-part findings

Requirement throughout: **12.6 mm PD3 reinforced HV↔SELV**. Not changed, not reinterpreted.

### 4.1 T1 — open slot achievable and cheap; still needs the contested credit

`temper:CST3015` current transformer at `(53.21, 148.91, 90°)`, courtyard `x=[37.96,68.46]`
`y=[136.48,161.34]`.

| pad pair | netclasses | distance |
|---|---|---:|
| pad1 `tank-out` ↔ pad4 `gnd` | HighVoltage ↔ GND | **9.1000 mm** (binding) |
| pad2 `PWR_RTN` ↔ pad3 `I_SENSE` | HighVoltage ↔ FinePitch | 9.1000 mm |
| pad1 ↔ pad3 / pad2 ↔ pad4 | — | **12.4933 mm** (package maximum) |

Package maximum 12.4933 mm < 12.6 mm: **no orientation of these pads clears the bar without a
slot.** Confirmed.

**Is an open, edge-reaching slot geometrically achievable? YES.** Slot body `x=[51.21,55.21]`
(4.0 mm wide, ≥ X = 1,5 mm by 2.7×), `y=[134.91,162.91]` (28.0 mm). The arm turns 90° at either tip
and runs due west to the outline at `x=8`.

- **The westward corridor is clear at both tips.** Occupants of `x<53.21` in the north band
  `y=[132.73,136.73]`: **none but T1 itself**. In the south band `y=[161.09,165.09]`: **none but T1
  itself**. Arm rectangle 43.21 × 4.0 mm.
- **The prior document's 17.96 mm arm length is stale.** It measured against a board whose left edge
  was `x=20`; the outline has since been enlarged to `x=8` (PR #1279's left-column redesign). The
  courtyard-to-edge reach is now **29.96 mm**, and the slot-tip-to-edge reach **45.21 mm**.

**Cost (measured against the real routed board):**

| design | void area (1 layer) | both layers | copper cut |
|---|---:|---:|---|
| island only | 112.00 mm² | 224.00 mm² | 29 segments / 8 nets |
| **OPEN, south arm** | **294.36 mm²** | **587.12 mm²** | **87 segments / 9 nets** |
| OPEN, north arm | 294.36 mm² | 587.12 mm² | 129 segments / 10 nets |

**South is the cheaper arm** (+58 segments over the island, vs +100 for north) — the same ordering
the 2026-08-13 document found, on different absolute numbers. No pad of any footprint is cut by
either arm (the 0.2 mm offsets needed to clear T1's own pad 1 / pad 2 are included above).

**This is a routing change, not a fab change.** The south arm severs 87 committed copper segments
across 9 nets (`OCP2_VREF_2V5` 43, `safety.fault_any_or-a2` 26, `safety.fault_any_or-y2` 12, plus
`i2c_scl_ui`, `safety-line-2`, `safety-line-3`, `PWM_LS`, `fb`, `rtd_pan.r_low_top-inn`). Against
PR #1172's 8 546 mm² total 2-layer channel capacity, the open design consumes **6.87 %** of all
channel area versus the island's 2.62 %.

**Resulting creepage: 13.2655 mm nominal / 12.8296 mm worst-case — identical to the island, and
+0.2296 mm (1.8 %) over 12.6 mm.** Opening the south end moves the governing pair from pad1↔pad4
around the *south* end to pad1↔pad4 around the *north* end; opening the north end moves it to
pad2↔pad3. The number never moves. **Verdict: achievable, affordable, and it does not remove the
Annex L dependency.**

### 4.2 T2 — not evaluable; blocked by placement, unchanged

`temper:CST3015`, same footprint as T1, at `(100, 300, 0°)` — **46 mm south of the board's own
bottom edge (`y=254`)**. T2 is not on the board. Its binding pair (9.1000 mm) and package maximum
(12.4933 mm) are identical to T1's, so T1's geometry transfers *if T2 is ever placed*, along with
T1's identical Annex L dependency. PR #1144's UNSAT courtyard-placement finding is re-confirmed
directly and **this document does not change it**. **Verdict: not evaluable today. "Not obtainable"
is the correct answer here, and it is a placement blocker, not a standards one.**

### 4.3 U6 — open slot achievable but very expensive; still needs the contested credit

`lib:SOIC16W_Isolated` (TI UCC21550BDWK isolated gate driver) at `(85.91, 142.43, 90°)`, courtyard
`x=[80.51,91.31]` `y=[136.48,148.38]`.

Binding distance **8.1000 mm**, attained by six distinct HV↔SELV pad pairs (pad8↔pad9, pad3↔pad14,
pad1↔pad16, pad2↔pad15, pad6↔pad11, pad7↔pad10). Package maximum **11.7145 mm** (pad1↔pad9,
pad8↔pad16) < 12.6 mm: **no slot-free geometry clears the bar.** Confirmed.

**Is an open, edge-reaching slot geometrically achievable? YES, but only via a long detour.** The
slot body must run in **x** between the two pad rows: `x=[77.41,94.41]` (17.0 mm), `y=[138.78,146.08]`
(7.30 mm wide, ≥ X by 4.9×). Its two closed ends are therefore at `x=77.41` (west) and `x=94.41`
(east) — **not north/south**. Measured blockers for a straight arm from each tip:

| from | direction | reach | blockers |
|---|---|---:|---|
| west tip | W | 69.41 mm | **T1**, R20, R36 |
| west tip | E | 94.59 mm | C15, C25, J2, R11, R53, R59, R62, R67, R73, SW2, U20, U26 |
| west tip | N | 122.43 mm | C26, R19 |
| west tip | S | 111.57 mm | K1, R4, R71, U21 |
| east tip | E | 77.59 mm | 12 components (as above) |

No straight arm is clear in any direction. The shortest courtyard-avoiding route is **76.28 mm**, 7
segments, leaving the west tip and detouring **north of T1** through the `y≈132.5` band to `x=8`.

> **Correction to the 2026-08-13 document.** Its §1.3 places U6's slot tip at `y=133.93`, derived as
> `142.43 − 8.5` — applying the slot's **x** half-length to its **y** centre. U6's pad rows are
> separated in `y`, so the slot separating them runs in `x` and its ends are east/west. The
> resulting "4 mm band at `y=[128.91,132.91]`, 2.0 mm clear of T1" description, and the 60.51 mm arm
> length, do not follow from U6's actual slot geometry. The **creepage figures** in that document
> (14.85 / 14.11 mm) are nonetheless correct — reproduced here exactly (Sec 3) — because they were
> computed from the correct slot rectangle. Only the arm-corridor derivation is affected. The
> load-bearing T1/U6 coordination constraint it identified is **real and confirmed here** in a
> different form: the routed U6 arm's `y≈[128.85,136.15]` band overlaps T1's own north-arm band
> `y=[132.53,136.53]`, so **T1 must use its south arm if U6 takes this route**, or the two voids
> merge and touch the outline at two points — which severs the board (Sec 2).

**Cost:**

| design | void area (1 layer) | both layers | copper cut |
|---|---:|---:|---|
| island only | 124.10 mm² | 248.20 mm² | 125 segments / 8 nets |
| **OPEN, west arm** | **717.08 mm²** | **1 434.16 mm²** | **352 segments / 11 nets** |

The open design removes **16.78 %** of the board's entire 2-layer channel capacity (PR #1172's
8 546 mm²) and cuts 352 committed segments across 11 nets — **including `GATE_HS` (16 segments)**,
a gate-drive net. Delta over the island: **+592.98 mm² and +227 segments.** This is a major
re-routing exercise on a board already at 1.31 channel utilisation, not a fab tweak.

**Resulting creepage: 14.8525 mm nominal / 14.1106 mm worst-case — identical to the island.**
Opening the west end moves the governing pair from pad9↔pad8 (around the east end) to pad16↔pad1
still going around the east end; opening the east end mirrors it. **This closes the gap the
2026-08-13 document explicitly flagged as not done** (its §7: *"U6's own creepage figure with the arm
was not independently re-derived via the full visibility-graph computation"*). It is now derived, and
it confirms that document's analytic extension. **Verdict: achievable, expensive, and it does not
remove the Annex L dependency.**

### 4.4 C6 — needs no slot; a compliant replacement is already specified

C6 `power_in.y_cap_pe` currently measures **8.0000 mm** (pad1 `PWR_RTN` HighVoltage ↔ pad2 `gnd`
GND) on the committed board's `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` land.

The replacement is **already landed in source**: `elec/src/modules.ato:1021-1022` assigns TDK
**`B81123C1562M000`** with `Capacitor_THT:C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4`, measured with the
canonical kernel at **20.1000 mm** — clears 12.6 mm by **+7.5 mm**. `docs/hardware/BOM.md:59` carries
it. `docs/evidence/2026-08-13-pd3-land-k1-c6.md` verified the swap alone reproduces the baseline's
DRC category counts exactly across all 20 categories. Only the `pcb/temper.kicad_pcb` resync is
outstanding, and it is expected clean.

**Verdict: no slot needed, open or otherwise. C6 is solved by the part swap.** The open-slot
question does not apply.

### 4.5 K1 — needs no slot; there is no HV↔SELV copper pair to bridge

`temper:Relay_SPST_Omron-G4A-E` at `(90, 222, 0°)`. Its only **copper** pads are A1/A2
(`power_in.bypass_relay-coil1` / `-coil2`, both netclass `Power`) at **4.5500 mm** — a same-domain
pair, not an isolation crossing. Pads 13/14 (`power_in.ntc-no`, `w1_2` — the HV contacts) are
**`F.Fab` only, with no copper layer at all**, confirmed directly this session.

**Verdict: K1 has no HV↔SELV copper pad pair, so no creepage path exists to interrupt and no slot
is applicable.** (K1's separate, open footprint-swap blocker — the `RT33K012` land introducing
electrical shorts, per `docs/evidence/2026-08-13-pd3-land-k1-c6.md` — is a different problem and is
untouched here.)

---

## 5. Would moving the part to the board edge make an open slot trivial?

**Geometrically yes; for the blocker, no — and the second half is what matters.**

Moving a part to the outline shortens or eliminates the arm, which is the *only* thing the arm costs.
It does not change the slot body, the pad geometry, or the governing path, because the closed end is
still there (Sec 2). **The creepage number is unchanged at 13.2655 / 14.8525 mm.** A placement move
buys arm cost, not compliance.

Measured, since the question deserves a measured answer:

- **U6** (courtyard 10.80 × 11.90 mm) — the west margin strip `x=[8,18.8]` is **empty at U6's own y
  band** `y=[136.48,148.38]`, and holds only C23, R5, U7 over the full board height. A west-edge seat
  for U6 exists.
- **T1** (courtyard 30.50 × 24.86 mm) — a west-edge seat `x=[8,38.5]` at T1's y band is occupied by
  **R20, R36, R57**. Not free, though three small passives is a modest displacement.

Both moves are nonetheless **functionally constrained in ways this document cannot clear**: T1 is the
tank current-sense transformer on `tank-out`/`PWR_RTN`, and U6 is the half-bridge isolated gate
driver whose `GATE_HS` / `hb.gate_hs.driver-*` loop inductance is the reason it sits where it does.
Relocating either is a switching-node/EMI question, not a placement question — the same class of
objection `docs/evidence/2026-08-17-pd3-creepage-12-reexamination.md` §4 raised against moving C22
and R26.

**Recommendation: not worth pursuing as a compliance route.** It optimises the cheap term (arm
length) and leaves the expensive one (the Annex L credit) exactly where it was.

---

## 6. What remains unobtainable — and what does not

**Genuinely blocked:**

- **IEC 60335-1 Annex L, pp. 170–172.** Not obtainable; exhaustively searched
  (`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md`). Its content is **not**
  reconstructed anywhere in this document. This blocks the closed-end credit for **T1, T2 and U6
  alike, in both the island and the open design.**
- **IEC 60664-4** — unobtainable, unchanged, not relied on here.
- **T2's placement.** UNSAT under courtyard geometry against the frozen layout; re-confirmed, not
  re-solved.
- **Structural qualification of any slot.** This repo has no FEA/warpage capability. T1's
  solder-joint thermal-cycling question (PR #1160 §4.3(b)) and U6's long-interior-cut flatness
  question are both open. The U6 arm measured here is **76.28 mm**, longer than the 60.51 mm the
  2026-08-13 document already flagged as raising a new structural question.
- **JLCPCB internal corner radius for non-plated slots** — not published; reasoned non-blocking
  (a real router bit can only round an interior corner *outward*, removing more material, which is
  strictly safe for creepage), not sourced.

**Explicitly NOT blocked — do not record these as unobtainable:**

- Whether an open slot is geometrically achievable. **It is**, for T1 (cheaply) and U6 (expensively).
  Measured above.
- Whether an open slot changes the creepage figure. **It does not.** Measured above, both parts,
  nominal and worst-case.
- Whether the groove-width rule is satisfied. **It is**, by 2.7×–4.9×, from primary text.
- Whether C6 or K1 need this at all. **Neither does.** C6 has a landed 20.1000 mm replacement; K1 has
  no HV↔SELV copper pair.

---

## 7. What this changes

- **Retires the open-slot hypothesis as a route around Annex L.** It was already answered on
  2026-08-13; it is now independently confirmed on the current board, for U6 as well as T1, with the
  no-slot baseline cross-validated against the canonical kernel. Anyone proposing it again should be
  pointed at Sec 2 first — the argument is topological and does not depend on this board's layout.
- **Corrects U6's slot-arm geometry** in the 2026-08-13 document (Sec 4.3): its ends are east/west,
  not north/south; the shortest arm is 76.28 mm, not 60.51 mm; and the T1/U6 coordination constraint
  binds T1 to its **south** arm rather than resting on a 2.0 mm clearance in a mis-derived band.
- **Refreshes every arm length for the enlarged outline** (`x=20` → `x=8`). T1's courtyard-to-edge
  reach is 29.96 mm, not 17.96 mm.
- **Closes the U6 visibility-graph gap** the 2026-08-13 document listed as outstanding.
- **Quantifies the open design's routing cost on the real routed board** for the first time: T1
  +58 segments / 6.87 % of channel capacity; U6 +227 segments / 16.78 %, including `GATE_HS`.
- **Does not change** any threshold, DRU, netclass, footprint, or `pcb/temper.kicad_pcb`. 12.6 mm PD3
  reinforced and 10.0 mm HV↔HV functional are untouched.

**The honest bottom line:** T1 and U6 can both be given a compliant-looking creepage number by a
slot, open or island, and neither number is defensible without a document nobody in this project can
get. That is the same place PR #1160 left it. The open-slot idea was a real hypothesis, it was worth
testing, it has now been tested twice, and it does not work — not because slots fail, but because
"open at the board edge" and "no closed end" are not the same thing.

---

## 8. Board integrity

```
before: 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b  pcb/temper.kicad_pcb
after:  26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b  pcb/temper.kicad_pcb
```

Identical, and identical to the main checkout's copy. `git status --porcelain` clean apart from this
document. No slot was cut, no reroute executed, no footprint or threshold touched.

## Files

- This document.
- Read, not modified: `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md`
  (the prior open-slot determination), `2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` (PR #1155,
  primary-source clause text and island baselines),
  `2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` (PR #1170, Annex L negative),
  `2026-08-13-pd3-land-k1-c6.md` (C6/K1 part swaps),
  `2026-08-17-pd3-creepage-12-reexamination.md`, `2026-08-14-certification-lab-package-pd3-and-60664-4.md`,
  `elec/src/modules.ato`, `docs/hardware/BOM.md`, `pcb/temper.kicad_pro`.
- Measured this session, not committed (session scratchpad, never written into `pcb/`): `kiutils`
  courtyard/pad/track extraction; the `shapely`+`networkx` visibility-graph creepage solver; the
  grid Dijkstra arm-corridor router.
