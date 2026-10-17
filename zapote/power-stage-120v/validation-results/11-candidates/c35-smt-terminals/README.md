# Candidate 35: SMT coil terminals (J2 / J5 → Würth REDCUBE SMT 7466004R)

QUEUE item 35 (DECISIONS 42). The THR coil terminal **74650074** needs a 1.6–2.0 mm board (rev 002.002 p.1). JLC
publishes ±10 % on 1.6 mm, so it cannot guarantee that thickness. JLC also has no published process for the THR part's
reflow step. Candidate 35 changes both coil terminals to the **WP-SMBU REDCUBE SMT 7466004R** (M4 internal through-hole
thread) and keeps everything else of stage 32.

**Verdict: ACCEPT** (draft decision in `DECISIONS-43-DRAFT.md`; the number is assigned at merge).
- Every chain gate is clean.
- The scorecard compare is ACCEPT against s32 and against 19c.
- It is cheaper: $206.44 against $208.08 per board at 500, with one fewer hand / consign line and one fewer THT line.
- Of the two terminals, it is the only one JLC can source and mount on its standard line (section 6).
- Track geometry is identical to s32.

**The one cost is terminal heat.** The copper next to J5 / J2 runs **0.5–3.7 K warmer** than with the THR at every B3
operating point.
- At c28_h25 it is 74.6 / 75.2 °C, against 72.3 / 73.9 °C with the THR. The part is rated to 150 °C.
- The scorecard's B3 metrics are board peaks; the board peak is elsewhere and unchanged, so the scorecard does not
  see this. It is recorded here and in the ledger (check T, a gap).
- I do not read this as "clearly worse". It is the cost of taking the terminal current down through 20 land vias
  instead of four soldered Ø1.85 leads.
- The first s35 chain showed 13–42 K. That was an artefact of how task 04 placed the current sink for a ring pad,
  fixed in section 4.

**Basis:**
- Stage 32 (`native21s32`; copper.json `d6f55dfe…`; board `2fb346dc…`).
- Branch `claude/native21-c35-smt-terminals` from `27e946580`, 2026-10-14/15.
- Stage tag `native21s35`, board `fba59ef3…`.
- Vendor PDFs are not committed; URL, revision, page and sha256 prefix are cited.

| Document | Revision | sha256 prefix |
|---|---|---|
| 7466004R datasheet, `https://www.we-online.com/components/products/datasheet/7466004R.pdf` | 001.003, 2023-07-03, 6 pp. | `e629b5c54c31bd0d` |
| REDCUBE SMD Terminals Design Guide, `https://www.we-online.com/components/media/o153698v410%20BCF_REDCUBESMDDesignGuide_EN.pdf` | 16 pp. | `1d9eb5ae2bdfbb18` |
| 74650074 datasheet (the THR part it replaces; in the ledger) | 002.002 | `fc0cdb43ce6cb534` |

## 1. The part against the THR it replaces

| | THR 74650074 (s32) | SMT 7466004R (s35) | Source |
|---|---|---|---|
| Rated current | 50 A max @ 20 °C | 50 A max @ 20 °C | p.1 of each |
| Derating | the same curve | one curve for "THR 7x7mm & SMD Ø7mm": 44.8 A at 50 °C, 29.4 A at 107 °C ambient | design guide p.11, `results/derating_curve.json` (digitised ±0.5 A) |
| Torque | 1.2 N·m | 1.2 N·m max; breaking ≥ 2.9 N·m | p.1; design guide p.10 |
| Pull | — | through-thread tearing force 300–410 N (5 mm from the board) | design guide p.9 |
| Temperature | −55 to +150 °C | −55 to +150 °C | p.1 |
| Board thickness | **1.6–2.0 mm** | not limited | p.1 |
| Soldering | THR reflow; "wave soldering is not applicable" | SMT reflow; 150 µm paste; MSL 1; tape and reel 500 | p.3 / p.1 |
| Height above the board | 2.5 mm (the KiCad STEP shows 3.7) | 5.0 mm | p.1 |
| Below the board | four pins, 3.0 mm | nothing (the Ø5.0 × 1.0 spigot ends inside the Ø5.2 NPTH) | p.1 |

## 2. Feasibility

**(a) Heat.** See section 4. Copper near the terminal runs +0.5 to +3.7 K. Whole-path resistance is +7 % on res_a and
+4 % on coil_feed. Not clearly worse; recorded.

**(b) Mechanical and stack height.**
- The lug seat rises from 2.5 to 5.0 mm (+2.5 mm). Nothing protrudes below the board except a screw longer than
  about L = S + 6.6 mm, where S is the lug-plus-washer stack.
- Both go to the enclosure session as a record (`ENCLOSURE-REQUEST.md`): rerun the R26 coil-lead screen 2.5 mm higher,
  and choose the screw length.
- The board-only fit gate is clean: FIT 401 / 0 / 0 / 403 / 0, with a 5.0 mm envelope over the courtyard because the
  part has no 3D model.
- The pull rating (300–410 N) and torque retention on a soldered sample are bench items.

**(c) RES_A 12.6 mm and the 5.0 mm tank rule.** These come from the chain gates and from
`scripts/terminal_spacing.py` → `results/terminal_spacing_s3{2,5}.json`.

RES_A outer creepage: the minimum is F.Cu 20.393 / B.Cu 13.375 mm, unchanged from s32, and the gate passes. The SELV /
PE barrier is 0 violations.

Nearest other-net copper, in mm (s32 THR → s35 SMT):

| Terminal | Layer | Other terminal | Other HOT net |
|---|---|---|---|
| J5 res_a | F.Cu | 5.0 → 5.0 | sw_a 5.0 → 5.0 |
| J5 res_a | In1.Cu | 5.94 → 5.95 | n_ls 5.002 → 5.0 |
| J5 res_a | In2.Cu | 5.94 → 5.95 | ocp_kelvin_n 7.273 → 7.226 |
| J5 res_a | B.Cu | 5.0 → 5.0 | ocp_kelvin_p 6.75 → 6.75 |
| J2 coil_feed | F.Cu | 5.0 → 5.0 | sw_a 2.4 → 2.4 |
| J2 coil_feed | In1.Cu | 5.94 → 5.95 | n_ls 4.47 → 4.475 |
| J2 coil_feed | In2.Cu | 5.94 → 5.95 | n_ls 5.645 → 5.576 |
| J2 coil_feed | B.Cu | 5.0 → 5.0 | n_ls 4.1 → 4.1 |

- The J2 F.Cu sw_a 2.4 mm and B.Cu n_ls 4.1 mm are s32's own copper, not this change; they are DRC-clean under
  rules21.
- The land vias stay inside the 9.2 mm stud lands, so in plan view nothing moved closer to SELV or PE.

**(d) Price and stock** (2026-10-14).

| | 7466004R (SMT) | 74650074R (THR) |
|---|---|---|
| JLC part | C6708126 (also C5523879, 7466004 bulk) | C5118857 |
| JLC stock | 0 | 0 |
| JLC price | 500+ $1.2832 | $1.1772 |
| DigiKey part | 732-5648-1-ND (cut tape) / -2-ND (tape and reel) | 732-74650074R… |
| DigiKey stock | 8,856 | 32,604 |
| Factory lead time | 26 wk | 26 wk |
| DigiKey ladder | $2.64 @1, $2.507 @10, $2.268 @50, $2.03 @100, tape and reel 500+ $1.914 | $4.09 @1, $3.411 @10, $3.007 @50, $2.73 @100, tape and reel 750+ $2.3294 |

- JLC records: `scripts/jlc_fetch.py`, cache in `scripts/jlc-raw/`. Mouser timed out and was not read.
- The scorecard prices both parts at DigiKey: `08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13-addendum-s35.csv`
  and the existing THR row.
- Board parts: $311.47 at 5 boards (s32 $313.28) and $206.44 at 500 (s32 $208.08).

## 3. Design

**Footprint.** `libraries/temper.pretty/Wuerth_REDCUBE-SMT_WP-SMBU_7466004R.kicad_mod`, generated from the p.1 drawing:
- **Copper:** one custom SMD pad, a ring of OD 8.5 mm. The ID is 5.7 mm, against Würth's 5.2: the copper is pulled
  0.25 mm back from the NPTH because JLC removes 0.2 mm of copper round a non-plated hole. This keeps the hole
  unplated (design guide p.7 Fig. 6).
- **Hole:** NPTH Ø5.2.
- **Paste:** four segments, OD 8.3 / ID 5.9, with 1.0 mm webs. The ID is 5.9 against Würth's 5.5, to keep the
  0.1 mm inset from the copper.
- **Other layers:** courtyard r 4.75; F.Fab body Ø7.

**Netlist and audit.**
- `elec/src/parts.ato` PowerTerminalM4 (mpn and footprint) changes, then the freeze in `frozen/` and
  `native-21/frozen/` (only J2 / J5 differ).
- `audit.rs`: IDENTITY now names 7466004R, plus a mutation test that putting 74650074 back must fail (82 / 82).
- `native-21/verification/verify_source.py` asserts the MPN and footprint.

**Copper (`patches21.add_stage35`).**
- The base is s32's routed copper, frozen; the only additions are 20 land vias per terminal (`passes35.sh`).
- The vias are 0.85 / 0.3 mm and sit round the Ø8.5 land inside the 9.2 mm stud land: two per half-edge at 4.1 mm,
  plus one per corner.
- They are the design guide's "rivets" (p.7 Fig. 3) and carry the terminal current to In1 / In2 / B.Cu (p.11: 0.3–0.4
  mm vias into the lower layers).
- Barrel wall: 20 × π × 0.3 = 18.8 mm, against the THR's 4 × π × 1.85 = 23.2 mm.

It took three runs:

| Run | Vias | Result |
|---|---|---|
| 1 | 24 × 0.6 / 0.3 | Task 04 topology failed on In1 / In2: a 0.15 mm ring does not resolve on the 0.125 mm grid (`$RUNS/chain1-v06-topology-fail.log`) |
| 2 | 0.85 / 0.3 at 0.85 mm pitch, rings touching | Topology failed: the physical union joins the rings and the grid does not |
| 3 | 20 × 0.85 / 0.3, centres ≥ 1.15 mm apart | Passes clean (0 unconnected, 0 errors, 750 vias); chain CHAIN_DONE |

`incr21.STD_VIA_KEEP` gains res_a / coil_feed so the via cleanup leaves them alone.

**Manufacturing scripts.**
- `apply_lcsc.py` maps 7466004R → C6708126.
- The CPL rotation audit (`extract_kicad.py`, `audit.py`) now handles custom pads. It uses the copper bounding box,
  which matches the CPL generator's pasted-pad rule.
- J2 / J5 come out NEEDS-PREVIEW: JLC has no EasyEDA footprint for them, so the order needs a placement preview check.

## 4. Terminal heat, and the task-04 sink fix

`scripts/terminal_heat.py` measures heat near each terminal from the task 04 and B3 outputs:
- task 04: the res_a (bank → J5) and coil_feed (T1.2 → J2) cases at 18.7 A, scaled to the 29.4 A trip;
- B3: the hottest copper cell within 7 mm of each terminal.

**The artefact.** Task 04 (`round5-native21/run_board.py`) put an equipotential sink node at each physical pad's
exported centre.
- For the THR that is its four leads.
- For the SMT ring pad, the "centre" is the custom-pad anchor at x + 3.55 mm on the ring's east side. All 29.4 A went
  into one point.

The real part is a brass body reflowed over the whole ring, so the ring is close to equipotential.
`scripts/terminal_sink.py` re-solves both cases with run_board's own load_net / solve / sheet_and_heat under four sink
models (`results/terminal_sink_s3{2,5}.json`, 18 µm plating, values at 29.4 A):

| Sink model | J5 R (mΩ) | J5 near-terminal W | J2 R (mΩ) | J2 near-terminal W |
|---|---|---|---|---|
| s32 THR, four leads (every model) | 0.6542 | 0.131 | 0.4099 | 0.068 |
| s35 anchor point (old task 04) | 0.9428 | 0.380 | 0.8015 | 0.406 |
| s35 ring, 8 points | 0.7131 | 0.181 | 0.4465 | 0.100 |
| s35 ring, 24 points (new task 04) | 0.6996 | 0.169 | 0.4257 | 0.083 |
| s35 every copper node under the Ø7 face | 0.6974 | 0.167 | 0.4220 | 0.080 |

**The fix.** `run_board.sink_contacts` sinks a pad that has a hole and no drill (a stud ring land) at 24 equipotential
points on the ring's mid radius.
- This is within 1 % of the full-face model.
- Drilled pads and plain SMD pads keep their centres. On this board only J2.1 / J5.1 qualify.
- So the THR board is unchanged: the s32 rows above are identical under every model.
- Every other task 04 case on s35 is unchanged as well. The largest change is 1e-4 mΩ on sw_a, which is zone-fill
  noise between the two chains.

The script change changes the task 04 and B3 model key, so both re-ran in the final chain.

**Result** (`results/terminal_heat_s32.json`, `results/terminal_heat_s35.json`). Hottest copper cell within 7 mm, °C,
B3 at 1.0 mm pitch:

| Operating point | J5 THR | J5 SMT | J2 THR | J2 SMT | Board peak (both) |
|---|---|---|---|---|---|
| nominal_h25 | 62.1 | 63.3 | 63.5 | 64.2 | 129.0 |
| nominal_h10 | 78.2 | 79.7 | 79.8 | 81.2 | 162.1 |
| c28_h25 | 72.3 | 74.6 | 73.9 | 75.2 | 135.0 |
| c28_h10 | 100.5 | 103.5 | 100.8 | 102.9 | 192.3 |
| extreme_h25 | 81.6 | 84.3 | 76.2 | 76.7 | 190.3 |
| extreme_h10 | 123.6 | 127.3 | 114.8 | 116.0 | 247.1 |

Task 04 at 29.4 A, 18 / 12 µm plating:
- J5 path 0.700 / 0.785 mΩ, against 0.654 / 0.730 for the THR.
- J2 path 0.426 / 0.427 mΩ, against 0.410 / 0.410.
- Largest land-via current is 2.57 A (J5, 18 µm). The THR's largest lead current was 10.4 A.

Neither terminal has a heat-source row in B3, so contact and lug heat are outside the model for both alike. Würth puts
both parts on one derating curve. The terminal temperature at 28 A on a lugged sample is a bench item, and it is in
the ledger as check T: 103.45 / 150 = 0.69 at c28_h10, a gap.

## 5. Chain and scorecard

The final chain (`chain.sh native21s35`, SPINE_OWNER unset) gave **CHAIN_DONE** on board `fba59ef3…` (Gerber ZIP
`b950c360…`).

| Gate | Result |
|---|---|
| Connectivity, DRC | unconnected 0; DRC errors 0 |
| Barrier and creepage | barrier 0 violations; RES_A outer 0 (F 20.393 / B 13.375 mm) |
| D5 | 8.047 / 8.507 |
| Rust audit | 0 |
| DFM | PASS, 750 vias |
| SPINE_LOCK | PASS (owner none) |
| Bypass / return path / PI | PASS |
| FIT | 401 / 0 / 0 / 403 / 0 |
| Kelvin band | 67.77–116.44 A |
| Task 04 | 39 / 0 failed; bus_p span 2.835 % |
| B3 | c28_h25 135.0, nominal_h10 162.1, c28_h10 192.3, extreme_h10 247.1 |
| CPL audit | 349 / 349 |
| BOM / CPL designators | PASS |

- **Necks** (`shoot-through-f1/s35_necks.json`): min ratio 0.993, same as s32.
- **OCP pickup** (`coil-pickup/s21b/result-s35.json`, default depth basis): pan-60 stack 4.17 A, same as s32.
- **Scorecard:** `validation-results/10-benchmark/scorecard-native21s35.json`; the compare lines are in
  `results/compare.txt`.
  - `ACCEPT native21s35 vs scorecard-native21s32.json`: cheaper parts_usd_at_500 and hand_or_consign_lines; better
    nothing.
  - `ACCEPT native21s35 vs scorecard-native21s19c.json`: cheaper parts_usd_at_500, placements, hand_or_consign_lines,
    consign_lines and zero_stock_lines; better return_path_open_changes, kelvin_band_low_A, b3_c28_h25_peak_C,
    b3_nominal_h10_peak_C, cmti_gate_ratio_min, fuse_copper_fusing_ratio, bank_ratio_tdk_28A_40k / 35k and
    ocp_pickup_stack_pan60_A.
- **Changes against s32** (scorecard fields): hand_or_consign_lines 21 → 20; tht_lines 19 → 18; parts_usd_at_5
  313.28 → 311.47; parts_usd_at_500 208.08 → 206.44; vias 710 → 750. zero_stock_lines stays 8, because both terminal
  rows are JLC-zero.
- **Track geometry** (the integration branch's `track_geometry.py` on `native21s35-all-copper.json.gz`): right-angle
  corners 104, acute corners 206, fold-backs 44, any-angle 704.4 mm. This is identical to s32; stage 35 adds vias only.

## 6. JLC sourcing and mounting, both terminals

The owner wants JLC to fabricate and assemble the whole board, so whether JLC can assemble a part is a feasibility
criterion. Pages were read on 2026-10-14/15, read-only, with no cart and no account.

**Getting the part to JLC.**
- Both parts are JLC-zero (C6708126 SMT, C5118857 THR).
- `https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction`: Global Sourcing parts are bought by JLCPCB from
  global distributors into the order's private library, with a lead time of 9–15 days. Consignment (shipping our own
  parts) is also offered, and the two can be mixed in one order.
- So for either part: Global Sourcing from DigiKey (SMT 8,856 in stock, cut tape or tape and reel; THR 32,604), or
  consign from the same stock.
- The SMT part comes on 500-piece tape and reel. For 5 boards (10 parts), a cut-tape strip may need a leader for the
  feeder; JLC's file review decides.

**Mounting at JLC.**
- **7466004R (SMT):** a reflow part on tape and reel, MSL 1, so it goes on JLC's standard SMT line like every other
  SMD part. Two items are open for JLC's file review:
  - Würth's 150 µm paste. The board's stencil thickness is not chosen; a step stencil or a larger aperture may be
    needed.
  - The 5.0 mm body height and the brass mass on the pick-and-place.
  - The CPL rows for J2 / J5 are NEEDS-PREVIEW: there is no EasyEDA footprint, so the order preview must be checked.
- **74650074R (THR): unsupported / unverified.**
  - `https://jlcpcb.com/capabilities/pcb-assembly-capabilities` says "THT components are assembled using wave
    soldering" and says nothing about through-hole reflow or pin-in-paste.
  - Würth forbids wave soldering for this part (rev 002.002 p.3).
  - JLC's blog post "Pin-in-Paste: Through-Hole Reflow With a Stencil"
    (`https://jlcpcb.com/blog/pin-in-paste-through-hole-reflow-stencil-guide`) is general guidance, not an orderable
    service.
  - `https://jlcpcb.com/help/article/98-PCB-Assembly-FAQs`: parts that cannot be wave soldered are soldered by hand,
    for a labour charge plus a per-joint fee and one extra day. Hand-soldering a brass 7 × 7 mm block with four leads
    into 2 oz pours is unverified.
  - On top of that, the THR needs a 1.6–2.0 mm board, which JLC's ±10 % does not guarantee (DECISIONS 42).

**On this criterion the SMT part passes and the THR part does not.**

## 7. Open items

1. **Enclosure** (`ENCLOSURE-REQUEST.md`, a record only; no one was contacted):
   - lug seat +2.5 mm, so rerun the R26 coil-lead screen;
   - screw length against the lug stack;
   - the pull load.
2. **Bench:**
   - lug pull and torque retention (1.2 N·m) on a soldered sample;
   - terminal temperature at 28 A with the real lug and Litz lead.
3. **JLC order:**
   - stencil for 150 µm paste at J2 / J5;
   - CPL preview of J2 / J5 (NEEDS-PREVIEW);
   - Global Sourcing or consignment for both terminals (JLC-zero; DigiKey stock above).
4. **If the terminal heat matters at the bench:** larger land-via drills. Würth allows 0.3–0.4 mm; 0.4 mm gives
   25.1 mm of barrel wall, more than the THR's 23.2. This was not done here because `route21.via` has no per-via drill
   and the board uses one 0.3 mm via drill.
5. **Not this change:** `native-21/verification/datasheet-ledger/tests/test_gate.py` fails at `27e946580` already. Its
   case 4 looks up `ISO7710DWR`, which stage 31 replaced. `gate.py` itself passes.

## Files

**Scripts** (all `python3 -I`, run from this folder):
- `scripts/terminal_heat.py LABEL TASK04_OUTPUTS B3_OUTPUTS --json OUT`
- `scripts/terminal_sink.py POWER_COPPER.json.gz --json OUT`
  - s32 input: `git show 27e946580:zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/inputs/power_copper.json.gz`
  - s35 input: the committed `inputs/power_copper.json.gz`
- `scripts/terminal_spacing.py LABEL BUILD/copper-dump.json --json OUT`
- `scripts/derating_curve.py`
- `scripts/jlc_fetch.py`

**Passes:** `passes35.sh` (frozen s32 base plus stage 35).

**Results:** `results/*.json`, `results/compare.txt`.

**Runs directory:** `$RUNS` = `worktrees/runs-native21/s35`, outside the repo. Kept: `b4` (the accepted build) and
`p3/j1` (the pass).
