# Stage 17 plan: replace R5 (WSK25121L000FEA) with a >= 2 W Kelvin shunt

Planning only (2026-10-12, branch `plan/r5-swap`). No schematic, board, copper, patch or fab file was edited. Everything below is
reproducible from this directory: `python3 screen.py` (writes `screen.json`, asserts the control) and `python3 fit_scan.py`
(writes `fit.json`).

## 0. Why, and the one-line answer

`r5-derating/` FAILS the current R5: 0.864 W at the 29.4 A firmware trip (0.784 W at 28 A) against 0.208 W derated at the
149.16 C B3 pad-cell maximum (1 W part, 100 % to 70 C, 0 at 170 C, ambient axis). DECISIONS item 4 (D-18) already names the
fallback: a >= 2 W four-terminal part. The current part is also **0 stock on JLC and LCSC** (BOM review 2026-10-08), so the swap
removes a procurement blocker as well.

**Recommendation: CSS2H-2512R-1L00F (Bourns, LCSC C4175647), conditional on one go/no-go gate (G6, B3 re-run with its real land
pattern), with BVS-M-R001-1.0 (Isabellenhuette, C466582) as the pre-agreed fallback.** No 1 mOhm Kelvin part clears the 20 %
rule on every reading at the unscaled pad temperature; the table says by how much each one misses or passes. 1 mOhm is kept, so
the OCP divider (R34 12.6 k / R35 11.7 k) does not change (section 2).

## 1. Candidates (screen.py, control asserted)

Pad temperatures are the B3 values of the **WSK footprint** (max 149.16 C, mean 122.74 C; c28, 0.25 mm, h 25, 50 C inlet).
`P_diss` = 29.4^2 x 1 mOhm = 0.864 W. Margin = 1 - P_diss / P_derated at the pad max; the rule is >= 20 % (r5-derating criterion a).
All three derate against **terminal** temperature, which is the physically right reference for the B3 pad cells (the WSK derates
against ambient and gave no terminal rule).

| Rank | MPN | LCSC | JLC stock (2026-10-12) | Rating, derating basis | Derated W at 149.16 C | Margin at 0.864 W | TCR | AEC | Footprint, height |
| --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |
| control | WSK25121L000FEA (Vishay) | C4248455 | **0** | 1 W, ambient axis, 0 at 170 C | 0.208 | **-314.7 % (FAIL)** | +/-250 | no | 2512, 0.64 mm |
| 1 | **CSS2H-2512R-1L00F** (Bourns) | C4175647 | 1482 | 5 W @70 C terminal, linear to 0 at 170 C | 1.042 | **17.1 %** (misses 20 % by 2.9 pt; needs reference <= 148.4 C, i.e. 0.8 K lower) | +/-75 | Q200 | 2512 body, land 7.0 x 3.4 + sense fingers, 0.77 mm |
| 2 | **BVS-M-R001-1.0** (Isabellenhuette) | C466582 | 1607 | 4 W P>100C, flat to 110 C terminal, 0 at 170 C (stability < 1 % curve) | 1.389 | **37.8 %** (needs <= 153.8 C) | 0 +/-50 | Q200 | 3920, land 11 x 6.2, 0.5 mm plate |
| 3 | **CSS4J-4026R-1L00F** (Bourns) | C2076400 | 371 | **8 W** @70 C terminal (Jan-2026 datasheet) vs **4 W** (2020 PDF linked from LCSC) | 1.667 / 0.834 | **48.2 % / -3.7 %** | +/-75 | Q200 | 4026, land 10.6 x 7.3, **2.70 mm** |

Datasheets (downloaded to the scratchpad `dl-r5swap/`, not committed):

- CSS2H: Bourns "Model CSS2H-2512 Series Current Sense Resistor" (bourns.com PDF, created 27-Jan-2026, 5 pp.). p.1 Electrical
  Characteristics (1.0 mOhm / 5 W @70 C terminal; TCR +/-75 ppm/C incl. Cu terminals; AEC-Q200); p.2 Product Dimensions (H 0.77 mm
  max for 1L00x) and Recommended Pad Layout / Recommended Measurements; p.3 "Terminal Temperature Derating Curve" (one curve,
  100 % to 70 C, 0 at 170 C, 130 C marked). The LCSC-linked PDF (2023) agrees. A CERN-hosted copy shows an older two-curve variant
  (5 W @70 C / 3 W @130 C); it is not on the current Bourns or LCSC PDFs and is kept in `screen.json` only as `older_rev_copy`
  (44.7 % margin if it were valid). The LCSC page prints +/-50 ppm; the datasheet says +/-75 (alloy +/-50 only over 20-60 C): use 75.
- BVS: Isabellenhuette "BVS (3920)", Issue 24-January-2025 (6 pp.). p.1 technical data; p.2 solder pad dimensions (l 11, w 6.2,
  a 2.7, x 5.6) and mechanical table (L 10, W 5.2, H 0.5); p.3 electrical table (BVS-M-R001: Rthi 15 K/W, TCR 0 +/-50, P70 7 W,
  P>100C 4 W); p.4 "Power derating curve BVS-M-R001" (x = terminal temperature; black curve = stability < 1 %, flat to 110 C, 0 at
  170 C; the green improved-stability < 0.5 % curve reaches 0 W at 140 C and would fail). Element rise at trip = 0.864 W x 15 K/W =
  13 K, so the element sits at about 162 C against the 170 C limit.
- CSS4J: Bourns "Model CSS4J-4026 Series" (bourns.com, created 15-Jan-2026, 5 pp.): p.1 table 1.0 mOhm / 8 W @70 C terminal; p.2
  dimensions (H 2.70 max) and Recommended Pad Layout (10.60 x 7.30); p.3 Terminal Temperature Derating Curve. The LCSC-linked PDF
  (revision created 2020) lists **1.0 mOhm / 4 W**: the rating changed between revisions, and the LCSC listing still says 4 W.
  This is the single largest unknown for rank 3 (needs a Bourns confirmation for the lot actually shipped).

Not ranked: Vishay WSLP25121L000FEA (C844705, stock 5321, 3 W) because JLC lists +/-275 ppm (above the 100 ppm preference) and its
derating axis was not read; the "E" mini-reel variants of CSS2H/CSS4J (stock 0 and 2). Others seen on JLC (Milliohm, Yezhan, TA-I,
Ohmite) were skipped as non-Vishay/Bourns/Isabellenhuette or lacking a downloadable curve. Stock numbers move daily; re-check at order.

Rank key (in `screen.json`): not overloaded on the most conservative datasheet reading, pad <= 160 C, trip floor held; then fit
effort (0 in place, 2/3 re-floorplan); then margin. The 20 % rule is reported (`pass_a_authoritative`) and enforced at G6.
The WSK pad max is a single 0.25 mm hot cell at the board peak, and the mean of the 261 pad cells is 122.7 C (CSS2H margin 63 % at
the mean), so the 20 % rule applied at the max is deliberately harsh. It is still the rule stated in r5-derating, so it stays.

## 2. Resistance and the OCP divider (the math)

With R32 = R33 = 10 k and a 2.5 V reference, `thresholds.py` gives the nominal trip

    I_trip = (2.5 - 2 x th) / R5,   th = 2.5 x R35 / (R34 + R35)

At R5 = 1 mOhm, R34 = 12.6 k, R35 = 11.7 k: th = 1.2037 V, I_trip = 92.59 A (matches the committed 92.593 A). The trip is
inversely proportional to R5, and one E96 step on R34 near 12.6 k moves th by about 12 mV, which is 2 x 12 mV / R5 = 24 A at 1 mOhm
(the committed 11 A per 0.1 k, DECISIONS 2026-10-05, refers to the R34 step with R35 held). So every resistance change is a full
divider re-pick on a coarse grid; `screen.json` -> `retune_if_not_1_mohm` runs it with the exact-corner code:

| R5 | Nominal trip with committed R34/R35 | Best E96 R34/R35 (nominal trip, error) | Band before Kelvin, low after Kelvin bound | Dissipation at trip | Verdict |
| ---: | ---: | --- | --- | ---: | --- |
| 0.5 mOhm | 185 A | 14.3 k / 13.7 k (107.1 A, 14.6 A off) | 63.7-153.2 A, **59.1 A (below 64.17 A)** | 0.43 W | rejected: floor lost, Kelvin sensitivity doubles to 2.07 A/mV, 153 A high edge |
| **1.0 mOhm** | **92.6 A** | **12.6 k / 11.7 k unchanged** | **69.6-116.9 A, 67.4 A** | 0.86 W | **keep** |
| 1.5 mOhm | 61.7 A | 11.8 k / 10.5 k (97.2 A, 4.6 A off) | 80.7-114.5 A, 79.2 A | 1.30 W | no: 1.5x heat, not needed |
| 2.0 mOhm | 46.3 A | 13.7 k / 11.8 k (93.1 A) | 80.2-106.8 A, 79.0 A | 1.73 W | no: 2x heat |

All three candidates are 1 mOhm, so **no divider, reference or CT-divider change is needed**. What does change is the TCR term
(thresholds.py `SHUNT = (0.001, 0.01, 250e-6)` becomes 75e-6 for CSS2H/CSS4J, 50e-6 for BVS): with the B3 rise at -10/+85 C
ambient and the Kelvin bound shift the low edge goes from 65.49 A (WSK, asserted control) to **67.36 A (CSS2H/CSS4J)** and
**67.63 A (BVS)**, which is 3.2 / 3.5 A above the 64.17 A floor (control: 1.32 A). Hotter 85 C ambient with a fixed 99 K rise is
the same extrapolation as in r5-derating and is kept for comparability.

## 3. Fit on native-21 (fit_scan.py -> fit.json)

R5 today: `(at 38.5 12.6 -90)` on F.Cu, WSK T2.21 footprint (pads 3.3 x 2.03 current, 1.4 x 0.76 sense; courtyard 3.89 x 8.85 mm,
bbox x 36.56-40.45, y 8.18-17.03); body box 3.18 x 6.35 mm, z 1.613-2.248 (enclosure-fit `native21-boxes.json`). Pad 1 LEG_RET
(north), pad 4 HV_RET (south), Kelvin pad 2 (OCP_KELVIN_P) at the LEG_RET end on the west, pad 3 (OCP_KELVIN_N) at the HV_RET end
on the east. Neighbours (courtyards): R13 east (x >= 41.13, 0.68 mm gap), C20 west (x <= 33.03), R58 south-west (y >= 16.73),
Q6 north-west (y <= 7.21), Q3 north-east (x >= 41.8). Patches21 already has R5-specific code (`R5_PADS`, `IN_PAD`, `SWB_CLIP`,
`add_r5`: 0.6/0.3 vias at 0.85 mm pitch inside each current pad, filled and capped).

| Candidate | Courtyard (x, y mm) | In place? | Needs |
| --- | --- | --- | --- |
| **CSS2H** | 5.4 x 7.5, bbox x 35.05-40.45, y 8.85-16.35 | **Yes, 0 courtyard conflicts, 0 foreign-net copper in the new pads +0.2 mm** | New footprint only; no part moves. Smaller along y than the WSK (7.0 vs 8.26 land span), 1.5 mm longer to the west (sense fingers, free space: C20 ends at x 33.0) |
| BVS | 7.3 x 11.5, bbox x 34.55-41.85, y 6.85-18.35 | **No**: overlaps R13 (2.2 mm2), R58 (2.1), Q6 (0.6), Q3 (0.02); no translation within +/-6 mm clears every courtyard; foreign copper leg_b-out_l (R58.2 pad and 3 tracks) in the land | Move R13 (leg A gate R) and R58 (leg B off R): both sit in the F6-qualified gate loops, so re-run the gate-loop/F6 evidence |
| CSS4J | 7.8 x 11.1, bbox x 33.75-41.55, y 7.05-18.15 | **No**: overlaps R58 (3.0 mm2), R13 (1.3), Q6 (0.4); no clearing translation; same leg_b-out_l copper | Same as BVS, plus **2.70 mm** part height (+2.07 mm over the WSK) into the enclosure-fit gate |

CSS2H land pattern is **scaled from the datasheet drawing** (only 3.40, 3.40 and 1.80 are dimensioned): two L-shaped current
pads 1.80 x 3.40 with a 3.40 gap, and two 0.43 mm sense fingers at x = +/-(0.27..0.70) from the centre that leave the pad inner lobes
and run 3.2 mm to one side (1.5 mm beyond the pad edge). BVS Kelvin stubs are my modelling (the datasheet has no sense pads). All
three drawings must be re-measured at footprint creation.

Copper and escape changes for the CSS2H (concepts from patches21: remove, `add_r5`, zone clip, `ESC`/escapes):

1. Footprint with **pad numbers kept**: 1 = LEG_RET, 2 = OCP_KELVIN_P, 3 = OCP_KELVIN_N, 4 = HV_RET. audit.rs asserts these nets and
   `kelvin_plane.py` uses R5.2 as the sink.
2. Remove stage-16 R5 vias and F.Cu stubs that fall outside the new current pads: of the 5 LEG_RET and 7 HV_RET in-pad vias, 5 and 4
   stay in the new pads; the rest (and the pad-adjacent HV_RET vias at (35.8, 13.9), (37.1, 13.68), (38.6, 13.68), 0.08-0.2 mm from the
   new SB finger) must go, then `add_r5` re-places up to R5_MAX filled vias on the new pad outlines. Current density: the new pads are
   6.1 mm2 each against 6.7 mm2, so the in-pad via count and the coherent-return check (REVIEW m11, up to 18 A through one via) must be
   repeated.
3. Kelvin: both fingers sit 0.54 mm apart on the **west** side, so the pair leaves as a tight pair (better than today's opposite
   ends). Today's OCP_KELVIN_N exits east (39.77, 16.03) -> via (41.3, 15.2) and OCP_KELVIN_P exits north-west to a via at
   (36.0, 8.0); both stubs short to the new current pads and must be removed, and the pair re-routed west from x about 35.3, then onto
   the existing In1 dead-end notch toward C40/C38 (FLOORPLAN: Kelvin pair In1 then In2, one notch per plane). Re-check
   the HV_RET/LEG_RET F.Cu pour carve (zone refill) around the fingers and the 0.2 mm 2 oz clearance; the fingers are 0.43 mm wide.
4. The SW_B clip `SWB_CLIP = (34, 12, 42, 18)` stays valid (new courtyard inside it).
5. Sense-point question for Bourns: the fingers branch from the current pad's inner lobe, so the sense tap includes the lobe copper.
   Confirm with the vendor where the part's sense terminals contact (datasheet "Recommended Measurements" gives probes 2.68 mm apart).
   Gate G7 quantifies the lobe copper with the Kelvin plane solver.

For BVS/CSS4J a re-floorplan of R13/R58/Q6 and a new Kelvin escape on a 11 mm land would be needed; that is a stage like 15b, not a patch.

## 4. Gates the stage must rerun

| # | Gate | What changes / pass condition | Where |
| --- | --- | --- | --- |
| G1 | KiCad DRC + source-to-native parity | Zero new violations; parity needs the new footprint name in the source manifest and `frozen/default.net` | `tools/check_native_parity.py`, native-21 build chain, DRC rule file `section.kicad_dru` |
| G2 | Barrier gate and D5 audit | HV_RET/LEG_RET/Kelvin geometry changed; barrier and creepage must stay at the D5 basis | `native-21/layout/barrier_gate21.py`, `verification/barrier-gate-rust.json`, `verification/d5_audit.py` |
| G3 | JLC DFM and Gerber review | 0.43 mm fingers/0.54 mm gap on 2 oz, filled-and-capped in-pad vias (POFV note), new paste apertures, pads vs JLC rules (jlc_dfm_check limits PTH 0.254, via ring 0.15) | `tools/jlc_dfm_check.py`, FAB-JLCPCB.md, Gerber render of the R5 box |
| G4 | Enclosure fit (height) | CSS2H 0.77 mm vs WSK 0.64 mm: R5 box z 1.613-2.38 (+0.14 mm); BVS 0.5 mm plate; CSS4J 2.70 mm would be z 4.31 | `validation-plan/enclosure-fit/` (`body_collisions.py` with an envelope for parts without a 3D model; check for a vendor STEP) |
| G5 | Kelvin plane re-solve and budget | New R5.2/R5.3 positions on the plane; e_th at the all-at-max-transfer bound must keep the low edge >= 64.17 A (today 2.198 mV, -1.037 A/mV; screen predicts 67.36 A with the new TCR before any change in e_th) | `02-protection-timing/kelvin/kelvin_plane.py EXPORT TAG`, `kelvin_budget.py` |
| G6 | **B3 thermal at 28 A, h 25** (go/no-go) | Re-run `r5_derating.py` with the new part's land pattern and heat row (0.864 W at the trip, rating row and curve from section 1); pass: P_diss <= 0.8 x derated at the new pad max (CSS2H needs max <= 148.4 C, today 149.16 C), pad <= 160 C, trip floor held. Add the part's own thermal resistance (BVS: Rthi 15 K/W; Bourns gives none, ask) | `r5-derating/r5_derating.py`, `b3/thermal.py`, `native-21/verification/*-all-copper.json.gz` |
| G7 | OCP band | No divider change at 1 mOhm. Update thresholds.py R5 tuple (tolerance 1 %, TCR 75 or 50 ppm) and its comment/MPN label, and `calc_protection_bands.py`/`ocp_bands.py`; band must stay >= 64.17 A | `02-protection-timing/round3/thresholds.py`, `stage15-28A/ocp_bands.py` |
| G8 | Commutation-loop evidence | R5 sits in the commutation loops (placement_metrics, FLOORPLAN M11); the land span shrinks 8.26 -> 7.0 mm; confirm the loop inductance and the F6 cases on the provisional matrices are unchanged | FEM evidence of FLOORPLAN M11 |
| G9 | Source identity (verify_source / audit.rs) | `IDENTITY` entry `("r_shunt", "WSK25121L000FEA")` at audit.rs:300; the hard-coded footprint check (audit.rs:772-775, "r_shunt footprint must be the 1mOhm T2.21mm variant") and its test (`wrong_low_ohm_shunt_footprint_fails`, audit.rs:1191-1195); pin/net expectations audit.rs:733-736 stay if pad numbers are kept. Rust edits are stage-17 work; this plan did not build the workspace | `audit.rs`, `elec/src/parts.ato` (`Shunt1m`: mpn, footprint), `native-21/frozen/{default.csv,resolved-components.json,default.net}` |
| G10 | BOM / CPL | New MPN and LCSC number in `bom-jlcpcb.csv`, `sourcing/lcsc-map.csv`, `positions-kicad.csv`; R5's CPL rotation is already "NEEDS-PREVIEW" (audit row: no DB rule) and the new part needs its own JLC preview check; extended-part fee as before | `validation-results/08-manufacturing-package/native-21/` (`cpl-rotation-audit/`, `fab/`, `owner-items/order/`) |
| G11 | Records | DECISIONS item 4 (D-18) gate "local ambient <= 100 C" is too loose (r5-derating item 3) and item 14's "0.86 W at 28 A" is the trip value; record the swap and the vendor answers | `DECISIONS.md` |

## 5. Risks

1. **Margin on paper is 17.1 % for the recommended part** (needs the pad reference 0.8 K lower; BVS 37.8 %, CSS4J 48.2 % only on
   the 8 W revision). The B3 pad temperature depends on the new pad area (CSS2H current pads are 9 % smaller than the WSK's) and on
   the model's missing body-to-air path (pessimistic, per round 5). Mitigation inside the budget: more in-pad vias, a wider same-net
   F.Cu pad extension, then fall back to BVS.
2. **Sense semantics of the CSS2H** (2-terminal part, Kelvin on the land): lobe copper in the sense path and current crowding.
   G5/G7 plus a vendor question settle it; a native 4-terminal part (CSS4J) avoids it but does not fit.
3. **Datasheet revision drift**: CSS4J 4 W vs 8 W on the same MPN; CSS2H two older curve variants; LCSC TCR text +/-50 vs datasheet
   +/-75. Order against the printed current Bourns datasheet and get a written rating statement from Bourns.
4. **Stock**: CSS2H 1482, BVS 1607, CSS4J 371 on 2026-10-12 (all "extended"); the control part is 0. Re-check at order time.
5. **Land pattern dimensions are scaled from drawings** (CSS2H partly undimensioned); a wrong finger geometry costs a re-spin of the
   footprint, not of the board, if found at G1/G3.
6. Hotter-than-modelled element: BVS element at about 162 C at trip (8 K to the 170 C limit); Bourns gives no element rise.
7. If the owner insists on a native 4-terminal part, the plan changes to a floorplan stage (R13/R58/Q6 move, F6 re-evidence) with
   CSS4J's height gate (+2.07 mm) as the first check.

## 6. Estimated scope (CSS2H path)

One stage (17), local to a 12 x 10 mm box, no other part moves: (1) footprint + STEP/envelope and `Shunt1m` component edit (parts.ato,
frozen files, audit.rs strings); (2) a patches21 delta: remove R5 vias/stubs, `add_r5` on the new pads, Kelvin pair re-route and zone
refill; (3) rebuild, DRC/parity, barrier, D5; (4) B3 re-run (about 3 min), Kelvin plane re-solve, band check; (5) DFM/Gerber and
CPL preview; (6) DECISIONS and BOM/lcsc-map updates. About one agent-day plus the B3/Kelvin runs, plus one vendor email (Bourns:
rating basis, sense-terminal contact, element thermal resistance). If G6 fails: stage 17b with the BVS floorplan (about 2-3x the
work: R13/R58 moves, F6 and loop re-evidence, 11 x 6.2 mm land, new Kelvin escape).

## Reproduce

```sh
cd zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/stage17-r5
python3 screen.py      # control asserted against ../r5-derating/results.json; writes screen.json
python3 fit_scan.py    # courtyard / copper conflicts from committed stage-16 copper; writes fit.json
```
