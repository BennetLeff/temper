# F4: is F2 protected by F1 for a fault at J11?

**Verdict: FAIL.** F1 (Littelfuse KLDR025) does not protect F2 (Schurter UMT 250 3403.0171) for a bolted fault at J11 (blw_l to N_FILT), at any source-impedance corner. F2 melts 19.5x sooner than F1 (226/11.6, at every current) and has to interrupt the fault alone, at a prospective current of about 0.4-3.6 kA against its 200 A @ 250 VAC rating.

Rerun: `python3 -I f2_coord.py` (stdlib only, deterministic, writes `result.json`, exit 0 when the controls flip as required).

## Spec (RESOLUTION-PLAN F4, DECISIONS:629-636)
Pass (fixed in advance): F1 let-through <= F2 breaking rating (200 A @ 250 VAC) OR F1 clearing I2t < F2 pre-arc I2t.

## Inputs and sources
| Item | Value | Source |
|---|---|---|
| Line | 127 V + 10 % = 139.7 V rms, 60 Hz | task; +10 % is the repo's NOM assumption (F1-RECOMMENDATION.md) |
| F1 | KLDR025.TXP, melt (pre-arc) I2t 226.0 A2s, total clearing 1,710 A2s at 200 kA, 200 kA AIR | Littelfuse KLDR datasheet, Revised 06/27/2022, p.6 "Electrical Specifications" (https://www.farnell.com/datasheets/4078688.pdf); exact MPN from `elec/src/parts.ato` MainsFuse25A |
| F1 let-through | 20 A and 30 A columns, "Current-Limiting Effects" table p.6; peak chart p.8 (no 25 A line, so geometric mean of the 20/30 A lines, peak = 2.3 x apparent RMS, calibrated on the 200 kA end of both chart lines, +-15 %) | same |
| F2 | 3403.0171: breaking capacity "IEC: 200 A @ 250 VAC / 100 A @ 125 VDC" (p.4 footnote 2); melting I2t 11.6 A2s at 10 x In typ (p.5 table, 3.15 A row); voltage drop 95 mV typ / 300 mV max at In (-> 30.2 / 95 mOhm) | Schurter UMT 250 datasheet, 5 pages, dated 21.07.2026 (https://www.schurter.com/en/datasheet/typ_UMT_250.pdf) |
| Cord | 14 AWG, 8.286 mOhm/m (20 C); out and back; reproduces the repo's 4.7 / 8.4 kA inlet bounds at 140 V | AWG table; F1-RECOMMENDATION.md s2 |
| L1 | 2 windings x 4.5 mOhm | `parts.ato` Cmc20A (TDK B82726S2203A020) |
| Copper | tracks/vias of l_filt (L1.4 to F2.1), blw_l (F2.2 to J11.1), n_filt (J11.2 to L1.3), 2 oz outer / 1.75 oz inner from `native-21/stackup.json`, 1.72e-8 ohm m; **zones ignored, so 58.8 mOhm is an upper bound** | `native-21/verification/native21s19b-all-copper.json.gz` (board sha b19a4553...) |

Assumptions (labelled in the script): F1 cold resistance 0; source inductance 2-10 uH (the repo's cord + CMC leakage range); every corner is run with the copper counted and with it set to 0 (the real value is between the two, since the zones shunt the tracks).

## Result (rows from `result.json`)
| Corner | Ik rms (Cu counted / Cu=0) | peak | F1 peak let-through | t to F2 pre-arc | t to F1 melt |
|---|---|---|---|---|---|
| C0 stiff, 0 m cord | 1,425 / 3,567 A | 2.1 / 5.1 kA | 804 / 1,093 A | 5.7 / 0.9 us | 111 / 18 us |
| C1 stiff, 1.0 m cord | 1,219 / 2,506 A | 1.8 / 3.6 kA | 763 / 972 A | 7.8 / 1.8 us | 152 / 36 us |
| C2 stiff, 1.8 m cord | 1,092 / 2,022 A | 1.6 / 2.9 kA | 736 / 904 A | 9.7 / 2.8 us | 189 / 55 us |
| C3 15 m branch (0.46 kA at inlet, repo) | 373 / 443 A | 0.54 / 0.64 kA | 514 / 544 A | 83 / 59 us | 1,621 / 1,151 us |

- Criterion 1 fails everywhere: F1's let-through (about 0.5-1.1 kA peak) is 2.5-5x F2's 200 A rating. Even the weakest corner is above 200 A.
- Criterion 2 fails by construction: F1's clearing I2t is at least its melting I2t, 226 A2s (the sheet gives total clearing only at 200 kA, 1,710 A2s), and F2's pre-arc I2t is 11.6 A2s. F1 would need to clear in less than F2's pre-arc energy, a factor of 19.5 below its own melting energy, so it fails at any fault current.
- Timing says the same thing: F2 reaches pre-arc 20x sooner than F1 starts to melt (ratio 226/11.6 = 19.5, independent of current). F2 therefore always opens first. F1 is selective with F2 (F1 never opens for a J11 fault, which is good for nuisance trips) but gives no help to F2's interrupting duty.
- F2's own 200 A @ 250 VAC is exceeded at every corner, by 1.9x to 18x.

Controls (both must flip to PASS, and do): A, source 1.2 ohm (Ik 108 A, F1 let-through 155 A <= 200 A) passes by criterion 1. B, the C1 fault with a fictional F2 whose pre-arc I2t is 3,000 A2s (> F1's clearing lower bound) passes by criterion 2. So the script is capable of returning PASS.

## Caveats
- A bolted fault at the J11 terminals is the governing case; the J11 harness (VHR-3N and wire to PS3) adds impedance that this study does not credit.
- The spec's wording of criterion 1 compares a peak let-through to a RMS-rated breaking capacity; I used the peak (conservative). Even in RMS-equivalent terms (peak/sqrt2: 360-770 A) it fails.
- F1 let-through is a log-log extrapolation of the p.6 table below 5 kA (the sheet's lowest prospective current). Where F2 melts in microseconds the real F1 current is set by F2's arc, so the true value is lower than the table-based number; this does not change either verdict (criterion 2 is independent of it).
- The F2 pre-arc I2t is the 10 x In typical figure; at 400-1000 x In, pre-arc I2t is lower still.

## Replacement (F4 step 2: required because FAIL)
**Littelfuse 02153.15MXP** (215 series, 5 x 20 mm ceramic, T3.15 A, 250 VAC/DC, 1,500 A breaking, "HBC"), cold resistance 28.25 mOhm.
- Availability: LCSC C142723 (7,855 in stock per the LCSC listing seen by search, date not shown); Farnell 1354611, RS 541-4690, Buerklin (15-week lead) listed. DigiKey: not found, check by MPN. Datasheet PDF (littelfuse.com) returned 403 to the downloader, so the 1,500 A figure is from the Littelfuse product page text as quoted by distributors (lioncircuits.com/parts/02153.15MXP, Farnell, LCSC), not read from the PDF: **verify on the Littelfuse datasheet and the approval certificate (breaking capacity differs per agency) before ordering.** Alternates with the same 1.5 kA class: Bel 5HT 3.15-R, Eaton S505H-3.15-R (3.15 A T, 250 V, 1.5 kA; not read).
- Dimensions vs F2: replacement body 5.2 x 20 mm cylinder (Littelfuse page) against F2's 10.1 x 3.0 mm SMD (UMT 250 datasheet p.3). The pinned board's F2 footprint `Fuse:Fuse_Schurter_UMT250` at (266.5, 118.4) has pads 2.0 x 3.75 mm at +-4.25 mm (pad outer span 10.5 mm, gap 6.5 mm), courtyard 11.4 x 4.26 mm (hw-baseline-guard/hardware/native21-stage19b/section.kicad_pcb). **No 5 x 20 fuse fits that footprint**: it needs two PCB clips (e.g. the 5 x 20 clip Littelfuse 01000056Z per the F1 study's distributor listing; unverified here) and a courtyard of roughly 24-26 x 9 mm, with a body about 8-10 mm tall instead of 4.0 mm. This is a layout change at the J11 end of the board (plus the enclosure height check), not a BOM swap. The task's "same footprint" cannot be met by any 5 x 20 HBC part.
- Does 1.5 kA cover the fault? With the copper counted, yes (Ik 0.4-1.45 kA). With the copper treated as 0 the stiff corners reach 2.1-3.75 kA, above 1,500 A (script, `replacement_02153.15MXP`). The real copper has the zones shunting its tracks so the truth lies between; the stiff 0 m corner is within 3 % of 1.5 kA even with the track-only copper. Hence 1,500 A is the right class for a real installation (branch impedance, cord, harness) but gives no margin at a transformer-stiff lab source: the margin must be confirmed on the bench with a short-circuit test at the J11 terminals, or choose a part with a higher rating (none found in 5 x 20 above 1.5 kA at 250 VAC; a 6.3 x 32 HBC 3.15 A T is the next size up).

## Recommendation
1. Record F4 as FAIL in DECISIONS:634; F1 is not a backup for F2.
2. Replace F2 with a 5 x 20 ceramic HBC, T3.15 A, >= 1,500 A @ 250 VAC (02153.15MXP first choice) in clips, at the next copper revision, and rerun fit and height gates; or move the blower tap fuse off the board into a holder at PS3.
3. Alternative that keeps the SMD footprint: protect the tap upstream by sizing, i.e. keep F2 but add a series impedance at J11 so that Ik < 200 A (about 0.6-0.7 ohm total, unrealistic), so not recommended.
4. Ask the certifier (the existing item) whether F2 at 200 A is acceptable as a supplemental fuse behind a branch-protected F1 under UL 248-14 / 62368-1 for this circuit; the answer does not change the physics above.
