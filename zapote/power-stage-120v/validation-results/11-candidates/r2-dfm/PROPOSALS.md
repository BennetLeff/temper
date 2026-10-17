# R2 DFM: manufacturability, assembly and test proposals (2026-10-13)

Benchmark: accepted stage 20, board SHA-256 `2d5a4b05…`, copper `native-21/verification/native21s20-all-copper.json.gz`,
scorecard `10-benchmark/scorecard-native21s20.json`. Nothing outside this folder was modified; no JLC account, quote or
order was used. Every script reruns with `python3 -I scripts/<name>.py` (needs `shapely`) and writes `results/`.

| Script | Result file | What it computes |
|---|---|---|
| `assembly_cost.py` | `assembly_cost.json` | the 22 hand/consign/THT lines: joints, JLC stock, JLC fee vs in-house labour at 5 and 500 boards |
| `jlc_order_model.py` | `jlc_order_model.json` | JLC assembly fees per order (Standard vs Economic), bare-board sensitivity grid |
| `via_pofv.py` | `via_pofv.json` | via-in-pad census and which vias must stay in the pad |
| `cpl_preview.py` | `cpl_preview.json`, `jlc-rotation-golden.csv` | the 47 NEEDS-PREVIEW lines classed by what a wrong rotation does |
| `board_test_dfm.py` | `board_test_dfm.json` | outline/edge distances, vias over 0.5 mm, test-access coverage per net |
| `panel_nest.py` | `panel_nest.json` | whether the L outline nests 2-up |

## Read this first (what changes the picture)

1. **JLC does through-hole as hand soldering and the fee is small.** JLC's FAQ says parts marked "wave soldering" in its
   library "will be assembled manually"; the price table is **$0.0164 per joint + $3.58 per order** (Standard, 1-10,000
   joints). Our 124 plated joints cost about **$2 per board** at JLC. The expensive items are not the joints: they are
   parts that are not in JLC's library (consign) and the $1.53 feeder fee per BOM line.
2. **The package contradicts itself.** `fab/bom-jlcpcb.csv` already sends 13 THT lines with LCSC codes to JLC
   ("Assembly = JLC (Extended)"), while `PROTOTYPE-LOT.md` says "THT and consigned parts: hand-solder in house". Pick one.
3. **Three lines cannot go to JLC at all:** Q2/Q3/Q5/Q6 and BR1 must be seated in the seat-before-solder fixture on the
   M11 sink before soldering (`owner-items/m11/SINK-DRAWING-NOTES.md`, Acceptance: coplanar 0.05 mm), and F1-CLIP is
   hand-soldered into plated slots. They stay in-house (the 4 TO-247 and BR1 are 16 of 124 joints but most of the labour).
4. **The scorecard metric `hand_or_consign_lines` counts every `Mount == THT` line** (`scorecard.py` line 189), so moving
   a THT line to JLC does not move it. Only deleting a line or making it SMD does. See P4.
5. **POFV cannot be dropped for a saving.** The option is board-wide, and 20 in-pad vias are required (R5 11, U26 9).
6. **Two FAB-NOTE statements are off:** the ten 0.8 mm current vias "stay tented", but JLC tents/fills only up to 0.5 mm
   (P6), and the via census numbers differ between documents (P5).

## Ranked list (by $ and risk)

| # | Proposal | Value | Risk | Effort | Scorecard effect |
|---|---|---|---|---|---|
| P1 | Send 11 LCSC-coded THT lines (80 joints) to JLC manual THT; keep Q/BR1/F1-CLIP in-house | about 106 min/board saved (192 to 86); JLC fee $5.4/board at 5, $1.4 at 500 | low-med | BOM/order note only | none (see P4) |
| P2 | Consign or global-source the 5 no-LCSC THT lines too (S2) | 36 more min/board; fee $26/board at 5 (one-off parcel $85), $3.6 at 500 | med | order process | none |
| P3 | Standard, not Economic, assembly at 5 boards | $13 per order; Standard has no 2-50 limit | low | order choice | none |
| P4 | Split the hand metric (consign/no-LCSC vs THT) | metric honesty; makes P1/P2 visible | low | scorecard | redefines `hand_or_consign_lines` |
| P5 | CPL: 47 lines to 12 designators to check, plus a golden rotation table | prevents a rework of up to 33 SMD parts per lot | low | process + CPL generator | none |
| P6 | Order-note fixes: 0.8 mm vias, via counts, rails | removes ambiguity at JLC review | low | FAB-NOTE | none |
| P7 | Keep POFV and 2 oz inner (considered, rejected to change) | $0 to $2.5/board at stake, not worth any risk | | | |
| P8 | Test: no ICT; flying probe on the loaded board plus the 35 TPs; ask for JLC's full E-test | coverage figures below | low | order option | none |

## 1. The 22 hand/consign lines

`results/assembly_cost.json` has the full table. Counts: 22 lines = 18 THT BOM lines (38 parts, 124 plated joints) + 3
SMD consign lines (U1/U2, U41/U42, F2) + F1-CLIP. By the BOM: 11 THT lines have an LCSC code (J1, RV1, L1, C3/C4, BR1, Q2-6,
J2/5/7-10, C21-23/151/152, PS1, PS2, J4, J6, C38-41); 9 lines have none (F1, C1/C2, C5/C6, U1/U2, J3/J11, F2, D3/D17,
U41/U42, F1-CLIP).

JLC fees used (jlcpcb.com/help/article/pcb-assembly-price, read 2026-10-13): Standard setup $25.56, stencil $8.21, stencil
storage $4.93, feeder loading $1.53 per line, SMT $0.0016/joint, manual (THT) $0.0164/joint, hand-soldering labour
$3.58/order, fixtures $16.42 (1-29 pcs) / $164.18 (500+), confirm placement $0.45. Economic: setup $8.18, stencil $1.53,
$3.07 per extended line. Consigned/loose parts (jlcpcb.com/help/article/consignment-part-terms-conditions): $0.142 per
piece, $0.017/pin (up to 5 pins) or $0.078 cap per component above 5 pins, agent/customs $45-85 per parcel. These pages
disagree with each other by small amounts (FAQ: $0.0173 per joint, $3.5 labour); I used the price article.

In-house labour is **my assumption, not a sourced number**: 25 s per small joint, 90 s per power joint (TO-247, BR1,
studs, film/bank caps, IRMs, clips), 30 s per part insertion, 8 s per lead trim, $45/h. Edit `LABOUR` in the script. Lead
trim (every THT lead to 2.5 mm below the board, `ASSEMBLY.md`) stays in-house in every scenario because JLC does not
offer it (not found in any JLC page I read).

| Scenario (per board) | Lines to JLC | Joints | JLC fee at 5 / 500 | In-house time | Net saving at 5 / 500 (labour as assumed) |
|---|---|---|---|---|---|
| S0 everything in-house (PROTOTYPE-LOT) | 0 | 0 | 0 | 192 min, $144 | |
| S1 LCSC-coded THT to JLC (P1) | 11 | 80 | $5.39 / $1.35 | 86 min, $65 | $74 / $78 |
| S1s only lines with JLC stock today | 6 at 5 boards, 4 at 500 | 36 / 26 | $3.14 / $0.45 | 153 / 169 min | $26 / $17 |
| S2 plus consigned no-LCSC THT (P2) | 16 | 104 | $26.0 / $3.62 | 50 min, $38 | $81 / $103 |

Stock on 2026-10-13 limits S1 to S1s for now: **zero JLC stock** for J2/J5/J7-J10 (74650074), L1, J6; 6 for the TO-247 and
6 for C3/C4; 288 for C38-C41; unknown for the bank C21-C152. At 500 boards only J1, BR1, PS1, PS2, J4 are stocked deep enough. So
P1 is a prototype-lot lever; at volume it depends on JLC global sourcing or consignment (P2).

Per-line routing:

| Line | Route | Reason / risk |
|---|---|---|
| Q2/Q3/Q5/Q6, BR1 | **in-house** | seat-before-solder fixture on the sink. **SAFETY**: the 12.5 mm HOT-to-PE margin depends on seating and the 2.5 mm trim |
| F1-CLIP, F1 cartridge | in-house | plated slots, cartridge after cleaning (FAB-NOTE) |
| J2/J5/J7-J10 REDCUBE | JLC only if JLC accepts THR reflow (pin-in-paste); else in-house | Würth: THR reflow, wave not applicable; zero JLC stock; 1.6-2.0 mm board needed. Not verified that JLC offers THR |
| J1, RV1, PS1, PS2, J4, J6, C38-41, bank, C3/C4, L1 | JLC manual THT | needs the part flagged as an assemblable THT in JLC's library (not checked per part). Heavy 2 oz pours: JLC publishes no limit; first-article X-ray/visual |
| C1/C2 (X2), C5/C6, J3/J11, D3/D17 | consign to JLC (P2) or in-house | no LCSC code. C1/C2 need leads cut to 4 mm **before** insertion (`ASSEMBLY.md`), which is a hand step anyway |
| U1/U2, U41/U42, F2 (SMD) | consign to JLC | placed by the SMT line; loose-part fee $0.142 each; U1/U2 have zero stock everywhere |
| REDCUBE press-fit | rejected | JLC publishes no press-fit service; Würth THR is the specified part |
| SMD alternatives for the film caps (C38-41), TO-247, IRMs, terminals | rejected | 1 kV X7R MLCC loses most capacitance under DC bias; no SMD at 30 A / 28 A RMS film or at mains terminal ratings. Not a DFM call, and not checked against the chain |

**Interfaces:** none electrically. Mechanical: seat-before-solder fixture and the M11 stack (owner of M11); lead trim
(enclosure R31); nothing in `groups.json` nets. **SAFETY:** trim and seating stay in-house; JLC soldering of the Y and X2
capacitors (C1-C4) and the IRMs is workmanship, not insulation design, but needs first-article inspection and the
creepage check on lead stubs that JLC leaves untrimmed (TO-247 leads reach 14 mm below the board, `ASSEMBLY.md`).
Risk low-med, BOM/order note only. Rank: S1 saves about 106 min of in-house time per board, S2 142 min; no BOM line removed.

## 2. The 47 NEEDS-PREVIEW CPL lines (P5)

`results/cpl_preview.json`. The audit finds 20 (LCSC, footprint) groups in 47 lines (its README counts 24 groups).

| Class | Lines | Why a wrong rotation matters or not | Action |
|---|---|---|---|
| SYM | 9 | C3/C4 (non-polar), RV1, six REDCUBE studs (four same-net pads per stud) | drop from the preview list |
| HAND | 5 | L1, PS1, PS2, J4, J6 are THT, keyed by shroud or pin-1 silk, inserted by a person | pin-1 call-outs on `assembly-drawing.pdf`, first-article check |
| POL | 4 | C126-C129 polarised electrolytic: reversal is a safety and rework item | preview mandatory plus first article |
| SMD | 29 | 28 SOT-23 family (10 LCSC groups, all KiCad 0, fit 180, DB 270) and R5 | one designator per group |

Result: **12 designators to check instead of 47 lines** (10 SOT-23 groups, C2162098, R5).

What I found about the cause: the 28-line SOT-23 conflict is DB (`^SOT-23` = -90) against EasyEDA fit (+180). The DB is
matthewlai/JLCKicadTools at commit 500a9fff; a secondary source lists +180 for SOT-23/-5/-6 (typical, unconfirmed), which
agrees with the fit and not with that DB row. The EasyEDA footprint is what JLC's preview draws at CPL rotation, so the fit
is the better proxy, but the audit's own note (C43368 differs from the other SOT-23-6 parts) says this cannot be trusted
per family. I could not remove the dependency offline, and I did not find a part swap that is clearly better (changing
the 10 SOT-23 parts would trade a known question for unknown ones).

The systematic fix that removes it for every later build is `results/jlc-rotation-golden.csv`: one row per LCSC with
proposed and DB-alternative rotation, status UNCONFIRMED. The owner confirms each in the first lot's preview (cost: 12
checks, plus the CPL Y-sign check the audit flags), the CPL generator (`scripts/bom_cpl_jlc.py`, lead's) reads the table by LCSC,
and no later board is previewed. Value: a rework of one lot: 28 SOT-23 parts x 2 boards at about 3 min each is 3 h, plus
parts. Other cheap checks that already exist: "Confirm parts placement" ($0.45 per order, JLC fee table). Risk low;
effort a few lines in the CPL generator. Scorecard: none.

## 3. Via-in-pad and POFV (P5, P6, P7)

`results/via_pofv.json`: 741 vias of 0.3 mm drill (603 at 0.6 mm pad, 138 at 0.85 mm), 10 of 0.8 mm, 751 total. In pad:
**150 = 72 fully inside + 78 crossing the pad edge** (same-net SMD pads, drill circle against the pad polygon). Classes:

| Class | Vias | Needs to stay in the pad? |
|---|---|---|
| R5 shunt pads | 11 (8 inside) | **yes**: `DECISIONS.md` 2026-10-08, R5.4 has no room outside; g02-g03 proposal C wants 7+ vias there |
| U26 exposed pad (3x3) | 9 | thermal/current for the TPS7A4700; could be unfilled tented vias with a windowed stencil, which is a different assembly risk (solder wicking) |
| C26.1, C106.1 | 2 (edge) | no |
| Test pads TP (bare copper, no paste) | 19 | no: no solder, built that way to avoid routing change |
| Other SMALL pads (passives, IC pins incl. U41/U42 0.65 mm pitch, SOIC pins) | 109 | convention only: DECISIONS 2026-10-08 found 42 of 43 had legal spots then, 15 more by stub trials, and left them |

(The stale FAB-NOTE also lists U27/U28/U35 thermal fields: they do not appear on this stage-20 board. FAB-NOTE says "749 x
0.3 mm vias" and "67 inside, 69 edge"; the dump has 741 and the brief says 71/72. Counts depend on the test. They do not
change the order because the option is board-wide.)

**Cost.** JLC publishes no 4-layer POFV price: its own notices say "POFV for 4-layer PCBs still requires charges" and
that 6-layer and up gets it free (jlcpcb.com/blog/Free-Via-in-Pad-on-6-20-Layer-PCBs-with-POFV). The only public base
price I found is 4-layer $70.6/m2 (jlcpcb.com/news/discount-on-quality-4-layer-pcbs), which for the 290 x 190 bounding box
(0.0551 m2) is a **$3.89 floor** per board before 2 oz and before small-quantity price breaks. The grid in
`jlc_order_model.json` shows what each 10 % POFV adder is worth: **$0.45-0.51 per board, $224 per 500**. Whatever JLC
charges, it is one board-wide option, not per via, so moving the 109 passive/IC-pin vias saves nothing unless **all
20 required vias are also removed**. Reaching zero needs R5's land redesigned and U26's thermal vias unfilled. That is a
re-layout of R5/G08 plus an assembly-risk change, for at most a few dollars a board. **Rejected (P7).**

**The measurement to take, not a guess:** run JLC's instant quote three times on the real specs (4L, 290 x 190, 1.6 mm,
JLC041622-7628, 2 oz/2 oz, ENIG) with POFV on and off, and at 5 and 500: that gives the true POFV and 2 oz deltas. I
could not drive the quote page (browser extension unavailable here).

**P6 order-note fixes (from the data):**
- The ten 1.6/0.8 mm vias (hv_ret, at x 205.6-220.5, y 55.2-72.6, by the J7-J10 studs) are over the 0.5 mm that JLC says it can tent
  or fill: JLC says larger holes "may not be fully covered, and complaints about this are not accepted". Write
  "untented, unfilled" for them. Creepage is measured over copper edges and laminate in the audits; no clearance changes
  from the mask state (**SAFETY**: lead should confirm the D5/barrier/RES_A gates never credit solder mask over these).
- Order note: epoxy fill "for all vias of 0.3 mm", 741 of them, not "749".
- POFV vs creepage: the cap is plated flush with the pad, so no copper outline changes. **No SAFETY impact found.**

## 4. Board level: copper, size, panel, stackup (P3, P7)

- **1 oz inner copper: rejected.** JLC lists inner 0.5/1/2 oz, and 2 oz inner needs a heavy-copper stackup (its pages say
  1.6 mm and 2 oz outer; one summary said 4 layers only). The inner planes carry the bus: In2 is BUS_P and In1 is HV_RET.
  Halving the thickness doubles inner resistance (g02-g03: 12.0 mΩ, 2.70 W at 15 A, with a 6.43 mΩ plane run alone;
  upper bound +2.7 W) and cuts fusing I²t to roughly (30/61)² = 0.24 of the present, so the
  `fuse_copper_fusing_ratio` of 0.208 would fall to about 0.05 (needs the chain to firm up). **SAFETY** (fault containment).
  The 2 oz inner at 61 µm is also the stackup the thermal and Kelvin results were computed on.
- **290 x 190 mm.** Under the 650 cm2 "large size" fee ($57.46, jlcpcb.com/help/article/pcb-assembly-price): the bounding
  box is 551.0 cm2 (outline 451.5). Keep it below 650 cm2 with any rails. Board maximum 4-layer is 350 x 320 mm (Economic) or
  460 x 500 mm (Standard) depending on which JLC page. Fits either way. JLC's capability page says 663 x 593 mm for the PCB itself.
- **Panelization.** JLC's assembly pages "recommend keeping panel dimensions within 250 x 250 mm" and for orders over 30
  pieces cap panelized boards at 250 x 250 mm. A 1-up 290 x 190 mm board exceeds that on one side; ask JLC in the
  order note whether a single board counts as a panel (unresolved). 29 SMD pads are within 3 mm and 43 within 5 mm
  of the outline (closest 1.09 mm, U31 and C140), so assembly rails are needed: Standard assembly supplies them
  ("Assembled boards ship with manufacturing rails attached by default"). Rails and tabs on the L outline will need a
  review from JLC; no cost found.
- **Nesting two L outlines** (`panel_nest.py`): 290 x 332 mm panel, 12.6 % less bounding box per board (about $0.5/board if JLC
  bills the bounding box), but 962.8 cm2 passes the 650 cm2 fee, exceeds 250 x 250 and needs breakaway tabs near
  the HOT/SELV barrier. **Rejected** at both 5 and 500.
- **Standard vs Economic assembly** (`jlc_order_model.json`, 84 JLC lines, 61 extended): at 5 boards Standard is
  **$203.23** against Economic **$216.57** because Economic charges $3.07 per extended line against Standard's $1.53 per
  line of any kind. Economic is also single-sided only and limited to 2-50 boards. Use Standard. At 500 Standard is
  $1,891 ($3.78 per board). Each extended line removed by other agents' proposals is worth **$1.53 once** (never per board).
- **Price at 5 and 500, what is known:** assembly service per board $40.65 / $3.78 (above); bare board $3.89 floor
  with the grid in `jlc_order_model.json` (heavy-copper adder 15-30 % is a third-party figure, POFV adder unknown). The
  parts costs are the scorecard's $333.45 / $234.83. So at 500 the order is dominated by parts (about 98 %), and
  every DFM lever here is small beside one part swap.

## 5. Test and bring-up (P8)

`results/board_test_dfm.json`: 141 nets with two or more pads. **26 have a board-only test pad** (35 TPs, 18.4 %), 49 have a TP or a
THT lead on the bottom (34.8 %), and all 141 have at least one top SMD pad with a 0.5 mm or larger smallest side (100 %,
generous: it does not check for bodies over the pad). Vias are tented and bare copper only exists at TPs, so vias are not
probe points.

- **ICT: not realistic.** Assembly is top-only but the bottom is covered with THT leads trimmed to 2.5 mm, vias are tented,
  and a bed-of-nails fixture for a 290 x 190 mm board with 8 mm HOT/SELV spacing is not justified at 5 or 500 boards.
- **Flying probe on the loaded board:** reachable (all nets have a top pad), but HOT nets must use isolated probes
  (`BRINGUP-PROBES.md`). Not a JLC service I could price.
- **Bare board:** JLC's free E-test is a sample; a full test costs extra (jlcpcb quote page, as reported by search; the FAQ
  says multilayer is 100 % flying-probe tested and the two statements disagree). Ask for the full test for the prototype lot:
  inner 2 oz copper opens/shorts cannot be seen otherwise. Fee not published.
- The 115 nets without a TP are covered by component pads; for production at 500, add TPs only for the nets the
  functional/hipot test needs (rails, PWM, PERMIT, DIS, BIAS_BAD).

## Considered and rejected

- Dropping POFV (section 3), 1 oz inner (section 4), nesting 2-up (section 4), SMD film caps / MLCC replacements (section 1),
  press-fit studs (section 1), ICT (section 5), Economic assembly (section 4), 6-layer (POFV free, but JLC's pages say 2 oz
  inner is a 4-layer offer, and it adds two layers of cost).

## What I could not verify

- Any JLC bare-board price for this spec, the POFV and 2 oz adders, and the full E-test fee (quote page not reachable).
- Whether each LCSC THT part is flagged as assemblable THT in JLC's library, whether JLC does THR reflow for the REDCUBE studs, and
  the JLC consignment fee for these 9 no-LCSC lines (the pages disagree).
- JLC size limits for a 1-up 290 x 190 board in Standard assembly (pages quote 350 x 320, 400 x 500, 460 x 500, 470 x 500).
- In-house labour numbers are assumptions; the JLC fees are the published table, read 2026-10-13.
- The SOT-23 rotation truth (only a JLC preview settles it).
