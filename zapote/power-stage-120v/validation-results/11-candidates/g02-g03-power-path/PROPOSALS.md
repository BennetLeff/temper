# G02 dc_link_clamp + G03 bridge_power_stage: power-path proposals (2026-10-13)

Benchmark: stage 19c, board SHA-256 `3d3a2c69…`, copper `native-21/verification/native21s19c-all-copper.json.gz`.
Everything below reruns with `python3 -I scripts/<name>.py` (results in `results/`). Nothing in the repo was modified.
Coordinates are board mm, y down. "Needs the chain" = FEM, DRC, B3 or the F6 decks must confirm it.

## 0. What the copper dump says (verified, not taken from the brief)

1. **The corridor wall is a signal track, not only the n_ha vias.** `leg_a-out_l` (U1.10 to the gate resistors R12/R54) runs 26 mm on In1 at y = 34.7 from x = 56 to x = 82, then jogs to a through via/TP1 at (82.0, 37.0). That track is a wall: it separates the hv_ret plane north of it (R5, the C38-C39 row, x 62-76) from the y 35.2-38.8 ribbon that leads east. The shunt's return therefore detours west of x = 56, south, then east through the ribbon; the pinch is the via at (82, 37) (1.17 mm left between its void and the n_ls track at y = 39.2). Measured at x = 80 the hv_ret In1 ribbons are y 33.6-34.25, 35.15-38.8, 41.2-42.25, 43.75-45.1.
2. **The two n_ha ties at (74.8, 30.7) and (77.86, 30.85)** (B.Cu pour tab to F.Cu tracks) carry 3.2 mm HOT-to-HOT voids on all four layers. On In2 they leave 1.85 mm of bus_p between y = 25.5 (zone edge) and y = 27.35 (void), the 884 A²s neck. n_ha is split into three islands if they are removed, so they cannot simply be deleted (`conn.py` logic, checked).
3. **Clearances the pours keep** (`scripts/clearances.py`): 0.20 mm inside the LOW group (hv_ret, leg_ret, leg_a-out_l, n_ls, v15_ls, v24_raw, ocp_kelvin_*), 3.20 mm between differing HOT groups (bus_p, hv_ret/LOW, SW_A = n_ha/p_ha/sw_a, SW_B). `whatif_lib.repour()` uses exactly these, and with no edit it reproduces the 19c neck (1.172 mm at (82.0, 38.2)) bit for bit. `whatif_lib.necks()` is the unmodified `f1_containment.copper_necks`.
4. **B.Cu is free east of x = 79** (y 27-52), but the n_ha pour (x 58.5-75.5, y 30.6-58.8) and the SW_A/SW_B pours fence it in at 3.2 mm, and F.Cu holds SW_A-group parts (p_ha R71.1 at (75.6, 35.4)), so no outer-layer path crosses x 56-82 for a LOW-group signal. In1/In2 are the only crossing layers.
5. **The rectifier feed is a 108 mm round trip.** BR1.1 (81.7, 4.6) sits 13.6 mm from Q2's drain (68.05, 4.2). Its DC goes east through a 730 mm² In1 rect_p pour to J7 (132.94, 22.43), over the strap to J8, and back west on bus_p. The return runs R5.4 (38.5, 15.2) to J10 (145.94, 9.43), over the strap to J9, through a 297 mm² In2 rect_n pour to BR1.4 (106.7, 4.6). DC resistance by my solver (validated against task 04, below): 1.38 + 3.60 + 6.43 + 0.60 = **12.0 mΩ** (excludes the two strap bars and four screw contacts), 2.70 W at 15 A.
6. **Solver validation** (`scripts/dcnet.py`, 0.25 mm grid, same assumptions as task 04's kit): J8 to Q2 3.73 mΩ vs task 04 3.626 (+2.9 %), J8 to Q5 6.06 vs 5.647 (+7.2 %), R5.4 to J10 6.43 vs 6.373 (+0.9 %).

### A finding that changes the target (SAFETY relevant)

After the corridor is cleared, **the fusing metric cannot reach 2 x F1 at the FET drain pads.** The Q2.2 / Q5.2 drain tongue is 2.56 mm wide on In2 (the pad is 2.5 mm; the neighbouring gate and source pads carry 3.2 mm voids), which the neck calculator reports as terminal-limited, 1,698-1,707 A²s = 0.99 x F1. No conductor change in G02/G03 lifts it: widening the tongue to 3.64 mm is blocked by the 5.45 mm pad pitch less two 3.2 mm voids, and F.Cu/B.Cu bus_p copper cannot reach the drains (SW_A/SW_B pours). The calculator's own "terminal-limited" label says this is the pad land, not a conductor neck; the real current path is the plated barrel (634 A²s alone at 1.5 mm drill, 20 µm) in parallel with the soldered TO-247 lead (copper, ~25 kA²s), neither of which the method counts. **Decision for the lead:** either treat terminal-limited rows as non-governing for `fuse_copper_fusing_ratio`, or accept 0.99 as the best this footprint can score. Also, `l_filt` L1 to BR1 (G01, B.Cu 2.6 mm at (97.5, 11.1), 1,747 A²s) sits at 1.02, so G01's neck is the next limit above the drain pads.

## 1. Ranked proposals

| # | Proposal | Cost (500 boards) | Metrics moved | Interfaces | Risk / effort |
|---|---|---|---|---|---|
| A | Direct BR1 feed, J7-J10 removed from the mains build (bench variant: BR1 DNP, J8+J10 fitted) | -$10.92 per board, -4 THT placements (74650074 line stays for J2/J5) | fuse ratio 0.208 to 0.993 (with C); DC R 12.0 to 3.25 mΩ; DC loss 2.70 to 0.73 W at 15 A; bulk-path L about -4 nH vs B | bus_p, hv_ret, rect_p, rect_n (G01), BR1 pins, ASSEMBLY procedure | med / re-layout of the BR1 zone, SAFETY |
| B | Fallback: keep the straps, clear the corridor (copper only) | none | fuse 0.208 to 0.59 (R5.4 vias) then 0.99; DC R 12.0 to 8.8 mΩ; DC loss -0.72 W | leg_a-out_l (G05), n_ha (G06), bus_p, hv_ret | high / re-layout of G05/G06 signals |
| C | R5.4 via field: 0.8/0.5 mm vias, at least 7 in the pad | about $0 | removes the 1,012 A²s limiter that sits behind A and B | R5 Kelvin (G08) | med / re-layout, G08 check |
| D | Re-quote leads: TVS Brightking 30KPA150CA-B (LCSC C522439), TDK C5/C6 (LCSC C3802167), stud price tiers | up to about -$28 if the listing tiers are real (not claimed) | none | none | low / BOM-only |
| E | Bulk near the FET row, or 80 nF C0G at the drains (from ALT-C5C6 variants D, E) | not costed | F7 die VDS, from the existing decks | G03 loop, B3, enclosure | high, not verified here |

Lines saved: A saves no BOM line (74650074 stays) but 4 placements and 4 hand/THT insertions in the mains build. Zero-stock lines are unchanged: J2/J5 keep the 74650074 line at zero JLC stock.

### Proposal A: direct BR1 feed (P2 in the scripts)

**Change.**
- Nets: merge RECT_P into BUS_P and RECT_N into HV_RET. Delete J7, J8, J9, J10 (74650074 at (132.94, 22.43), (145.94, 22.43), (132.94, 9.43), (145.94, 9.43)) from the mains build. Bench variant (assembled for floating-bus work): leave BR1 unpopulated and fit J8 and J10 as the bench lead landings, still on bus_p / hv_ret. The audit's "RECT nets contain only the BR1 output and the rectifier-side terminal" check and the RECT_P / RECT_N potential groups in `section.kicad_dru` go away.
- In1: delete the rect_p pour (x 82-127, y 0-23). Pour hv_ret in x 60-128, y 0-30 under the rules above. The result is a band y about 9.5-27 across x 77-106 reaching BR1.4 at (106.7, 4.6), 3.2 mm clear of the BR1.1 pad (81.7, 4.6) and of the AC pads BR1.2 (91.7, 4.6), BR1.3 (99.2, 4.6).
- In2: delete the rect_n pour (x 104-128, y 0-13). Pour bus_p in the same window; the band is y about 8-35 at x 77-100, reaching BR1.1.
- The F.Cu/B.Cu rect zones around the BR1 pads (33 mm² each) are renamed bus_p / hv_ret.
- No signal track, n_ha tie, R5 or Kelvin copper moves.

**Mechanism.** The 1.17 mm and 1.85 mm necks and the wall exist only because every DC amp has to go to x = 133-146 and come back through the x 77-84 corridor. With BR1 feeding the planes where it stands, the DC path is 30 mm, not 108 mm, through a band 17-27 mm wide.

**Effect (`scripts/scenarios.py`, rerun `python3 -I scenarios.py`).**

| Metric | 19c | A | Method |
|---|---|---|---|
| DC R (BR1 + bridge + return), mΩ | 12.01 | 3.25 | grid solver, validated above; excludes strap contacts, so 19c is understated |
| DC loss at 15 A, W (scales as I²) | 2.70 | 0.73 | same |
| fusing I²t of the bus_p/hv_ret/leg_ret/rect series path, min over the series | 355 (hv_ret, 1.17 mm) | 1,012 (R5.4 via field), 1,698 once C is applied | f1_containment neck calculator on edited copper |
| bulk-path mirror squares, FET-row side to the C5 pin zone | not defined: the 19c In2 strip (y 25.5-27.35) and In1 ribbon (y 35-39) do not overlap through the corridor | 10.1 sq = 7.1 nH (B: 16.2 sq = 11.4 nH) | `plane_l.py`, screening, 0.705 nH/sq at h = 0.561 mm |

Bulk-path reading: at the ALT-C5C6 slope of 4-7 V/nH, A's advantage over B is about 4.3 nH, roughly 17-30 V on the S4 worst die VDS (490 V against the 520 V target). 19c is worse than B, because its mirrored return is not even connected through the corridor, so its loop is larger than any figure above. All of this is "needs the chain" (a P5-style FEM port, ALT-C5C6 section 7); the model carries no cap ESL, vias or pin loops.

**Interfaces disturbed.**
- G01: BR1.1 / BR1.4 now sit on bus_p / hv_ret, and RECT_P / RECT_N disappear from the isolation list. Spacing to the AC pads stays 3.2 mm functional by construction; run the barrier gate.
- G05/G06: no signal moves. Check the `return_path19` gate: the In1/In2 voids around the signal vias change shape.
- G08: R5 and its Kelvin pair untouched; the In1 split y = 12.65 stays.
- B3: about 1.9 W at 15 A (about 6.6 W at 28 A on a pure I² scaling, not a quoted operating current) leaves the corridor and the studs. Needs B3.
- Isolation numbers that must not move (D5 8.047 mm at n_ha/leg_a-dis (67.46, 42.32), RES_A 12.6 mm): the edit window is x 60-128, y 0-30, so neither lies inside it, and the repour keeps 8.0 mm to any non-HOT net; the chain's barrier gate is still required.

**SAFETY.** This touches fault containment (series copper under F1's 1,710 A²s clearing, DECISIONS 22) and the bench isolation interlock (ASSEMBLY.md: both rails must be open). The mains build loses the removable DC link; the bench path becomes "BR1 not fitted", which is a physical, inspectable open on both rails, and J8 / J10 remain the only bench entry. If a single board must serve both modes, use the AC-side alternative below. Needs certifier review of the interlock wording; D-31's containment wording ("F1 plus copper that survives F1") is not satisfied at the drain pads (section 0) with or without A.

**Alternative A-L (keeps one board for both modes).** Put the removable break on the AC side of BR1 (l_filt and n_filt after the IRM taps) instead of the DC rails, with the same four studs. The existing l_filt pour (B.Cu, x 87-236) and n_filt pour (F.Cu, x 97-288) already pass the present stud rows (x 127-146), so there is no extra detour, and BR1 then floats on the bench with its diodes reverse-biased. It has the same DC copper as A and no BOM saving. Not verified: stud placement and the 3.2 mm voids it adds to those pours; G01 would own it.

**Considered and not chosen: a compact DC link next to BR1** (studs at about x 112-125, y 8-22). The DC round trip would be about 2 x 33 mm; by scaling the 19c rect paths I estimate about 6.5 mΩ against A's 3.25. That figure is a path-length scaling, not a solve; it keeps the REDCUBE parts and two nets, so A and A-L dominate it.

**Risk class** med; effort re-layout of the BR1 zone (copper + netlist + audit/DRU). **Rank** -$10.92 (2.3 % of the $231.94 parts cost), -4 placements, fuse ratio x4.8, DC loss -73 %.

### Proposal B: clear the corridor and keep the straps (S1)

**Change (all coordinates verified legal by `check_clear`, except where noted).**
1. n_ha ties: delete vias (74.8, 30.7), (77.86, 30.85) and F.Cu tracks (74.8, 30.7)-(72.375, 39.6), (77.83, 31.2)-(77.86, 30.85), (77.83, 44.735)-(77.83, 31.2). Add n_ha vias at (73.88, 44.3) (on the existing F.Cu track through C112/C113 at x = 73.88) and (77.83, 42.4); F.Cu track (77.83, 44.735)-(77.83, 42.4); extend the B.Cu n_ha tab to the box (75.0, 41.0)-(78.2, 44.0). The script reports that the new vias sit in other nets' plane voids until the planes are re-poured; the B.Cu tab at x = 78.2 clears v15_ls via (81.8, 41.5) by 3.1 mm (needs the chain's pour check). The n_ha net stays one island only if both ties are placed; `conn.py` shows the three islands without them.
2. leg_a-out_l: delete the In1 tracks (56.0, 31.0)-(56.0, 34.7)-(82.0, 34.7)-(82.0, 37.0), the via/TP1 at (82.0, 37.0) and the F.Cu tracks (82.0, 37.0)-(83.17, 39.9)-(83.175, 46.125). New route on In2: (56.0, 31.0)-(56.0, 46.6)-(83.17, 46.6)-(83.17, 47.3), a via at (83.17, 47.3) and an F.Cu stub (83.175, 46.125)-(83.17, 47.3); TP1 moves to that via. Non-zone DRC: 0.0 mm to a v15_ls via and 1.75-2.85 mm to n_ha on In2 (need 0.2 and 3.2); the F.Cu stub is 7.3-7.95 mm from the U1 signals (SELV-class nets, rule 8.0). So this route does not pass as drawn; it must be nudged by the router, which is why B is the fallback.
3. Re-pour hv_ret In1 and bus_p In2 over x 50-100, y 22 / 25.5 to 50.

**Effect.**

| Metric | 19c | B |
|---|---|---|
| hv_ret neck R5 to J10 | 1.17 mm, 355 A²s | corridor gone; next limit the R5.4 via field, 1,012 A²s |
| bus_p neck J8 to Q2/Q5 | 1.85 mm, 884 | terminal-limited drain tongue, 1,698 |
| DC R, mΩ / loss at 15 A | 12.01 / 2.70 W | 8.80 / 1.98 W |
| mirror squares to C5 zone | disconnected | 16.2 sq, 11.4 nH |

**Interfaces and risk.** G05 (the gate-output line changes layer and reference: `return_path_open_changes` tolerance is 0, so a worse count rejects it), G06 (n_ha pour and ties), plus bus_p / hv_ret. **Risk** high; re-layout. Nothing here is cheaper, so it only scores on the fuse metric and DC loss. I recommend A.

### Proposal C: R5.4 via field (needed by A and B)

The neck calculator finds 6 vias within 6 mm of R5.4 on the 0.6/0.3 mm field, equal sharing, 1,012 A²s. With the drain pads fixed at 1,698 the field only needs to stop being the limiter (`scripts/r5_via_field.py`, Onderdonk at 105 C, 20 µm plating):

| Via drill | n vias to reach 1,698 | n to reach 3,420 |
|---|---|---|
| 0.30 mm | 8 | 12 |
| 0.40 mm | 6 | 9 |
| 0.50 mm | 5 | 7 |

**Change:** replace the in-pad vias with 0.8/0.5 mm (or add vias) so that at least 7 stand in the 3.4 x 1.8 mm pad at (38.5, 15.2). I could not place extra 0.3 mm vias without re-pouring bus_p In2 and sw_b B.Cu around them (3.2 mm voids; the only zone-conflict-free sites are inside the existing void at x 35.4-38.0, y 13.8-15.4), so the bigger-drill route is the one I recommend. Whether JLC fills and caps 0.5 mm in-pad vias is not verified (the board orders epoxy-filled, copper-capped vias, DECISIONS 2026-10-08). **Interfaces:** the Kelvin pads R5.2 / R5.3 (37.43, 11.67 / 13.53) are 1-3 mm from the field: G08 must rerun the Kelvin band (`kelvin_band_low_A` 67.72, tolerance 0.5). **Risk** med.

### Proposal D: sourcing leads (BOM-only, not claimed)

JLC's public part list (queried 2026-10-13) gives LCSC codes the survey lists as "no LCSC code", at prices far below the survey's Digi-Key-based figures; all are stock 0 (`scripts/cost_lines.py`, `results/cost_lines.json`):

| Part | Survey $ per board at 500 | JLC/LCSC listing | Note |
|---|---|---|---|
| D3/D17 30KPA150CA | 19.64 | Brightking 30KPA150CA-B, LCSC C522439, 5.88 each at 100+; a second listing 1.98 at 800 | the survey's own ALT-D3 says Digi-Key $6.727 at 10, so the 9.82 at 500 looks stale; ratings (150 V stand-off, 129.8 A) match the Good-Ark part's, datasheet not read |
| C5/C6 B32676G1905K000 | 12.34 | LCSC C3802167, 1.23 each at 500, 3.28 at 1 | survey lists no LCSC code; 27 wk lead per the survey |
| J7-J10 74650074 | 10.92 | THR terminal listing 1.18 at 100+ | Digi-Key holds 32,606 of it; "zero stock" is a JLC fact only |

Re-quote before counting any of this. The listing tiers could be placeholders. Substituting a different TVS brand needs the owner's approval (DC-LINK-CLAMP no-silent-substitution rule) and a datasheet check of V(BR), Vc at 129.8 A (ALT-D3's 466.8 V) and the hot clamp.

### Proposal E: leads taken from ALT-C5C6 (not re-run)

ALT-C5C6 shows that moving the bulk to the trunk (variant D, trunk 2 nH) cuts worst die VDS by 46-56 V, and 80 nF C0G at each drain (variant E) takes the worst VDS to 425-427 V from 466-482 V, at the cost of off-gate rising from 0.53-0.78 V to 0.89-1.18 V (screen 1.9 V). After A the freed zone x 108-150, y 0-35 could host one bulk cap, but the cap is 42.6 x 33.6 mm and 48.4 mm tall against a sink at 133-150 W: needs enclosure R33 and B3. I did not evaluate these.

## 2. Considered and rejected

- **Moving the In1 leg_ret/hv_ret split at x 42.8-53 (leg A source neck 2,080 A²s).** The neck just becomes the Q3.3 pad tongue (2.87 mm, 2,130 A²s): +2.4 %, no value.
- **Single 30KPA300CA instead of two 30KPA150CA.** Already rejected in ALT-D3 (table row X). No new data.
- **MOSFET alternatives (G03).** Searched JLC's list on 2026-10-13: IPW65R041CFD (C528753, 720 in stock, 41 mΩ class, older CFD): about 2.3 x the Rds(on) of the 18 mΩ part, which adds conduction loss to a sink budget already at 133-150 W (DECISIONS 15); IPW60R024CFD7 (C537444, 64 stock, 600 V): its 80 % derating limit is 480 V against S4 worst die VDS of 466-490 V; STW65N023M9-4 (6 in stock, $26.8) no better than the 6 we have; CoolSiC IMZA65R027M1H (C536297, 1,480 in stock, 650 V, 34 mΩ max in the RS listing) would help Qrr and S4 but needs a gate-drive, bias and CMTI redesign (G05/G06/G07, 18 V drive) and was not sourced beyond listings. IPW65R018CFD7 itself: 106 A, 18 mΩ max, Qg 234 nC (RS listing); numeric Qrr, Qoss, Eoss not found without the Infineon PDF. **No equal-or-better stocked drop-in exists.** SiC is a separate project.
- **DC-field partial-inductance screen** (`scripts/bulk_path_l.py`). Its control (a straight strip pair of known L) came out at 0.40-0.64 of the analytic value depending on block size, so it cannot give absolute nH; kept only to document the failure. The mirror-image plane model (`plane_l.py`) is what the table uses.
- **Moving bulk by repouring only** (no part change): the bulk path is limited by the corridor and the cap ESL; see E.

## 3. What I could not verify

- DRC, barrier, B3, Kelvin band and the F6 decks for any edit: no chain run, by the rules.
- Route feasibility of B's leg_a-out_l re-route (fails 3 clearances as drawn).
- The 0.2 mm seam at y = 27 in my first A pour disappears with a 30 mm window; A's numbers above use that window. Real pours also need thermal relief and zone priority, which the dump does not hold.
- Whether the mirror-plane model fits the real current at 20-100 MHz; the absolute nH figures are +-50 %.
- Stud / strap contact resistance, and the current basis: 15 A is task 04's experiment current, not a quoted operating point.
- Datasheet Qrr, Qoss, Eoss for the FETs (RS and JLC listings only), and every TVS / TDK price (listing tiers, stock 0).

## 4. Files

- `scripts/pp_common.py`, `dcnet.py` (solver and validation), `whatif_lib.py` (re-pour and neck engine), `scenarios.py` (BASE, S1, S1_ub, P2), `plane_l.py`, `r5_via_field.py`, `clearances.py`, `cost_lines.py`, `bulk_path_l.py` (failed control).
- `results/scenarios.json`, `r5_via_field.json`, `cost_lines.json`.
