# G04 resonant_tank and G09 ct_zc_detect: proposals (2026-10-13)

Benchmark: native-21 stage 19c (`../../10-benchmark/`). G04 is $12.60 and G09 is $14.29 at 500 (`../GROUPS.md`). Nothing here edits the board, a script outside this folder, or a committed result. Every number below comes from a datasheet I read (cited) or a script in `scripts/` that reruns with `python3 -I`. Outputs are in `results/`; raw JLC API replies are in `raw/`.

Reruns (all deterministic, a few seconds):

    python3 -I scripts/bank_options.py            # results/bank_options.json
    python3 -I scripts/double_fault_variants.py   # results/double_fault_variants.json (imports the 02 study read-only, controls assert)
    python3 -I scripts/ct_options.py              # results/ct_options.json
    python3 -I scripts/line_zc_opto.py            # results/line_zc_opto.json
    python3 -I scripts/jlc_query.py "<kw>"        # JLC public part search, caches in raw/
    python3 -I scripts/jlc_detail.py C50132500    # price ladder, stock, library type

Datasheets (not saved in the repo): TDK `MKP_B32651_658.pdf` 6/26, SHA-256 `c32e3754…afdd3` (identical to the 02 study's, retrieved again 2026-10-13); Coilcraft Document 1608-1 rev 09/08/25, SHA-256 `0da51f0e…bd5f`, <https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf>; Vishay VOL628A rev 1.9, <https://www.vishay.com/docs/82401/vol628a.pdf>.

## Ranking

| # | Proposal | Parts cost at 500 | Lines / flags | Metric effect | Touches | Risk | Effort |
|---|---|---|---|---|---|---|---|
| P1 | T1 CST3015-100ED to **-200ED** (1:200), R39 1.5 to 3.0 ohm | up to **-$4.12** (T1 $11.43 to $7.31; channel-dependent, see below) | hand/consign -1, lines 0, ext lines 0 | trip amps unchanged by construction; T1 volt-time 7.2 % to 5.3 % of limit; burden loss halves | sw_a/coil_feed (same pads), J4.13/14 (same V per A), audit.rs identities | **med** (protection input) | BOM + one value (+ audit.rs strings) |
| P2 | U36 VOL628A-3X001T to **-2X001T** (same package, same VDE option) | +$0.13 (LCSC ladder) | zero-stock -1 | pulse widens by 1.6x (moves away from the firmware's 300 us minimum) | barrier part U36, J4.16, audit.rs | **low-med** | BOM only (+ audit.rs strings) |
| P3 | Bank 5 x B32654A1104**K** to **J** (+-5 %), LCSC C3794777 | about +$1.48 (LCSC ladder; DK price not captured) | hand/consign -1 | bank at 28 A: 1.105x to **1.022x** the TDK curve (40 kHz); allowed tank current 24.8 to 26.8 A at 35 kHz; double-fault 1702.4 to 1682.7 V | C21-C23/C151/C152 only | **low** | BOM only |
| P4 | U10+U11 (2 x TLV3201) to one TLV3202AIDR | -$0.30 (benchmark estimate) to -$0.67 (JLC ladder) | placements -2, lines +1 | none | CT lobe layout | low-med | re-layout of the CT lobe; not worth it alone |

P1 and P2 do not interact. P1+P2+P3 together: hand/consign lines -2, zero-stock lines -1, parts cost about -$2.6 on the LCSC basis. F3 stays closed by the firmware floor (DECISIONS 13); none of these closes it in hardware, and I found no hardware fix that beats that (see the rejected list).

---

## P1. T1 to CST3015-200ED with a 3.0 ohm burden

**Change.**
- T1: `CST3015-100ED` to `CST3015-200ED` (Coilcraft; JLC/LCSC **C50132500**, Extended, SMT, stock 64, ladder $7.7113 at 1, $7.5368 at 10, $7.3052 at 90+; fetched 2026-10-13 from the JLC part API; <https://www.lcsc.com/product-detail/C50132500.html>). Same CST3015 series, so the same pins (1-2 primary, 3-4 secondary) and the series' one dimension drawing (Coilcraft 1608-1, p.2). Footprint `temper:CST3015` is unchanged.
- R39 (`r_ct_burden`): 1.5 ohm `RC1206FR-071R5L` (C137360) to **3.0 ohm `RC1206FR-073RL`** (Yageo, **C137279**, Extended, stock 1019, 1206, 250 mW, 1 %). Same footprint, same net names.
- Nothing else changes: not the 1 k series, not the BAS116H clamps, not the 100 nF C0G burden shunt, not the 2.21k/10k references, not the TLV3201s.

**Mechanism.** Volts per primary amp is burden / N. 1.5/100 = 3.0/200 = 0.015 V/A (asserted in `ct_options.py`). So the comparator trips (`(3.3 x 10/12.21 - 1.65) / 0.015 = 70.18 A`, the schematic's "about 70 A"), the CT_MON scale (1.32 V at 88 A, inside the 1.65 V bias) and CT_ZC are identical in amps. Coilcraft's terminating-resistance column says the same (RT = 1 ohm for -100, 2 ohm for -200 at 1 V per 100 A).
What changes, computed from the 1608-1 table (L 3.2 to 12.8 mH, volt-time 638 to 1276 V-us, secondary DCR 1.54 to 5.94 ohm; `results/ct_options.json`):
- Secondary volt-time at the 118.74 A shunt-band top and 25 kHz: 46.0 V-us, 7.2 % of limit, becomes 67.6 V-us, **5.3 %**. (The 100ED figure reproduces the 46 of 638 V-us in DECISIONS 13, which is the control for the method.)
- Magnetising error at 25 kHz with L at -25 %: 0.81 % becomes 0.59 %. Phase lead 51 ns becomes 38 ns.
- Burden dissipation at 28 A rms: 0.118 W becomes 0.059 W. R39 is one of the B3 heat sources at 0.13 W, so B3 sees less.
- The CT stays terminated on the board, so the open-secondary spike analysis of `06-controller-interface` does not apply.

**Effect on the scorecard.**
- `parts_usd_at_500`: up to -$4.12. Caveat: the benchmark's $11.43 is Coilcraft direct (a web-search summary, `STOCK-2026-10-13.csv` row T1). JLC lists no -100ED at all (C50132500, -300ED and -400ED only). The $7.31 is the LCSC channel for the -200ED at 64 pcs. At 500 boards the 64 pcs of stock do not cover the build, so the buying channel is Coilcraft direct, and I have no Coilcraft quote for the -200ED. **Needs a quote**: if Coilcraft prices the series flat, the cost saving is zero and the benefit is only the assembly one below.
- `hand_or_consign_lines`: -1 (T1 is consign today; C50132500 is a JLC SMT part). `bom_lines`, `placements`: 0. `jlc_extended_lines`: +1 only if the consign line was not counted extended (T1 line is `consign`); zero-stock lines unchanged.
- `b3_c28_h25_peak_C`: needs the chain; R39 heat falls by 0.06 W, so it cannot rise.
- Everything else (D5, RES_A, return path) is unchanged: same footprint, same pads, same routes.

**Interfaces disturbed.**
- sw_a / coil_feed: T1 primary pads and primary DCR (0.1 mohm max, both parts) are unchanged. Checker: G03/G05 owners need nothing.
- J4.13 (ct_zc) and J4.14 (ct_mon): same volts per amp, so no controller change. F11 is neither helped nor hurt.
- Safety-interlock chain: CT band 64.55-76.09 A is a function of the dividers and the V per A, so it is unchanged. OCP band (G08) and bank OV (F3) are untouched.
- `audit.rs` lines 260, 341 and 343 pin `t_ct` to `CST3015-100ED` and `r_ct_burden` to `RC1206FR-071R5L`: the lead updates those strings. `parts.ato` `CST3015_100E` (mpn, docstring "88 A") likewise.

**Safety and certification.** **SAFETY** (T1 straddles the barrier and feeds a protection input).
- Insulation: the 1608-1 first-page bullets give 5000 Vrms one minute and "designed to meet reinforced insulation, at least 8 mm creepage/clearance" for the whole series, the same statement DECISIONS 757 relies on for the -100ED. No working voltage, CTI or HF/PD figure is published for either, so DECISIONS 757's "HF rating stays a Coilcraft question" is unchanged. Not made worse.
- Protection: CT trip current is unchanged in amps; the independence from the shunt OCP is unchanged (same comparators, same OR into BUS_FAULT). The ratio accuracy of the -200ED is not published (neither is the -100ED's). The D4 condition-2 bench step (inject primary current, check the trip near the design point; `DECISIONS` D4 note) must be run on whichever T1 is built, so the incremental bench cost is zero.
- **Open, MAG-11/MAG-27:** the primary-to-secondary capacitance C_ww is not published for either part. The 100 nF C0G burden shunt absorbs a switching-edge charge, so the pickup in equivalent primary amps is dV / 0.015 with dV = C_ww x 198 V / 100 nF. That is **independent of N and of the burden**, so the -200ED is no worse than the -100ED for equal C_ww: 0.26 / 0.66 / 1.3 / 2.6 A for 2 / 5 / 10 / 20 pF, to be read against the 3.0 A pickup allowance in the trip floor (DECISIONS 13). The -200ED has twice the secondary turns, so its C_ww may be larger; the burden time constant doubles (150 to 300 ns), which only lengthens the decay. Ask Coilcraft (cst@coilcraft.com) for C_ww of both parts and measure it at bring-up. I could not verify either number.

**Risk and effort.** Risk **med** (a protection input device changes; the physics above says nothing moves in amps, the bench confirms). Effort: BOM and one value, plus the audit identity strings.

**Rank.** Cost up to $4.12 (unquoted), 1 hand/consign line, 0 lines.

---

## P2. U36 VOL628A-3X001T to VOL628A-2X001T

**Change.** `VOL628A-3X001T` (C17618137: JLC/LCSC stock 0, 28 wk) to `VOL628A-2X001T` (**C145344**, Extended, stock 172, ladder $0.6117 at 1, $0.3409 at 500; both fetched 2026-10-13). Same LSOP-4 package and VDE option 1: Vishay's ordering table (rev 1.9, p.2) lists X001T for the VDE option in bins -2 and -3. The footprint, the 8.0 mm creepage/clearance, VIORM 1050 V, VIOTM 8000 V, VISO 5000 V, CTI 275 and DTI >= 0.4 mm are the family's safety table (p.4), identical for both bins. Everything else on the net list stays.
Not chosen, and why:
- `VOL628A-3T` (C118058): same die, but the ordering table gives it no VDE option; JLC stock is also 0 (the survey's DK 12,262 is for the -3T, not the X001T).
- `VOS628A-3T` (C143059, stock 2,367 per search): a different package (SOP-4, not the long-creepage LSOP-4); not an 8 mm part. Rejected.

**Mechanism.** Only the CTR bin changes: 100-200 % to 63-125 % at IF = 1 mA (p.3). Saturation still holds: the 33 k pull-up needs 0.1 mA, and VCEsat is tested at IC = 0.32 mA for bin 2 (p.3), 3.2x that. At 120 V rms the LED string (4 x 16.5 k) carries 2.5 mA peak.
The firmware window is `min_width_us = 300`, `max_width_us = 4000` (`firmware/components/power/n21_binding.c`). `line_zc_opto.py` computes the output pulse width against CTR(sub-mA)/CTR(1 mA) = g, which the datasheet does not give (the ECO already says so). Pulse width at 120 V, 60 Hz:

| g | bin -3 (benchmark) | bin -2 |
|---|---|---|
| 0.1 | 462-917 us | 724-1449 us |
| 0.2 | 245-471 us | 375-732 us |
| 0.3 | 173-323 us | 259-497 us |
| 1.0 | 71-117 us | 97-168 us |

So bin -2 sits at 1.6x the width. If the real g is above about 0.2, the benchmark's bin -3 pulses fall below the firmware's 300 us qualification and the bin -2 pulses are closer to it; **this is a benchmark risk worth a bench look whichever bin is built.** The pulse centre does not move with CTR (both edges shift together); only the width does.

**Effect on the scorecard.** `zero_stock_lines` 10 to 9 (U36's line; JLC 172 pcs covers about 34 five-board lots, not 500 boards, where Mouser stock is the route: aggregator listing, about 6,143 at Mouser, undated, **not verified**). `parts_usd_at_500`: +$0.13 on the JLC ladder ($0.3409 vs $0.2072, both fetched). Lines, placements: 0. `single_source_lines`: unchanged.

**Interfaces disturbed.** J4.16 line_zc: same electrical function, different pulse width. Barrier at U36: same package, same 8.0 mm. `audit.rs` lines 265 and 544 pin the MPN.

**Safety and certification.** **SAFETY** (a mains-to-SELV optocoupler). Insulation ratings are the family table, unchanged. No CMTI is published (`06-controller-interface/cmti`: OPEN), same as the benchmark. I make no claim beyond "the datasheet's safety table does not distinguish the bins".

**Risk and effort.** Risk **low-med** (the pulse width and its firmware window need a bench look). Effort: BOM only, plus audit strings.

---

## P3. Bank 5 x B32654A1104K000 to B32654A1104J000

**Change.** Same TDK part, +-5 % (code J) instead of +-10 % (K): `B32654A1104J000`, JLC/LCSC **C3794777**, Extended THT, stock 104, ladder $0.9705 at 1 to $0.5513 at 520, $0.522 at 1040. For reference the K part now has an LCSC code too, **C3811101** (stock 0, ladder $0.2561 at 520). The BOM and the survey record no LCSC code for the K part; that appears to be stale. The two ladders look inconsistent with the survey's $1.41 at 500 (DK basis), so I do not trust the K figure; the J/K ratio of about 2.2x on the LCSC ladder is the only like-for-like comparison I have (+$0.30 per cap, +$1.48 per board). **Needs a DK/Mouser price.**

**Mechanism.** The round-6 bank margin is set by the worst share: one part at +tol and the others at -tol (`common6.worst_share`). At 5 x 0.1 uF the worst part carries 23.4 % of the tank current at K and 21.7 % at J, 7.4 % less. `bank_options.py` reuses round 6's digitised TDK p.57 curves and reproduces its 24.8 / 25.3 / 26.1 / 27.3 A at 35 / 40 / 45 / 50 kHz (asserted), then gives J:

| | K (benchmark) | J |
|---|---|---|
| tank current at the TDK 85 C curve, 35 / 40 / 45 / 50 kHz | 24.8 / 25.3 / 26.1 / 27.3 A | **26.8 / 27.4 / 28.2 / 29.5 A** |
| bank ratio to the curve at 28 A, 40 kHz | 1.105 | **1.022** |
| bank ratio at the 29.4 A firmware trip, 40 kHz | 1.160 | 1.073 |
| loss at 28 A, ESR typ 100 kHz (nominal C) | 3.03 W | 3.03 W |

(DECISIONS 21 and the round-6 README quote 1.12x at 28 A; that is the worst frequency, 35 kHz, where J gives 1.04x.) A narrower C tolerance also narrows the f_res spread the CT, OCP and double-fault studies use (0.45-0.55 uF today). `double_fault_variants.py` reruns the committed 02 study with C +-5 % (its controls assert first and the base row reproduces 1702.4 / 1688.8 / 1494.8 / 1178.4 V):

| variant | governing V | no-floor steady | time-domain F1 | fw floor (35 kHz) steady | time-domain F2 |
|---|---|---|---|---|---|
| base K | 1702.4 | 1702.4 | 1688.8 | 1178.4 | 1494.8 |
| J | **1682.7** | 1662.4 | 1682.7 | 951.0 | 1392.7 |

So J cuts the exceedance from 6.4 % to 5.2 % over 1600 V and does **not** remove it. I found no like-for-like part that fits the slot and does (below).

**Also enumerated:** every bank of 2-5 parts from the TDK 1600 V values (47, 100, 150, 220 nF) at 0.45-0.55 uF, K and J (`results/bank_options.json`). Nothing beats five 100 nF at the same tolerance on allowed current, and every other combination moves C off 0.50 uF, which moves the tank (f_res, trips, yield). The best 4-part option (100 + 3 x 150 nF, 0.55 uF) is 2.9 W loss but changes the tank, so it is not a drop-in.

**Effect on the scorecard.** `hand_or_consign_lines` -1 (the five caps become a JLC THT line; stock 104 covers 20 boards, not 500, so the zero-stock/low-stock flag moves from consign to LOW_JLC_STOCK). `parts_usd_at_500` about +$1.48 (see above). Bank margin is not a scorecard metric; B3 peak is unchanged (the bank is not the board peak).

**Interfaces disturbed.** None electrical: same footprint, same pitch (27.5 mm), same body. G09: the CT band does not move. G08: none. Controller: none.

**Safety and certification.** None touched. A tighter C tolerance only narrows the corner set the protection studies already bound.

**Risk and effort.** Low; BOM only.

---

## P4 (optional, low value). U10 + U11 to one TLV3202AIDR

U10/U11 are the positive and negative CT over-current comparators (TLV3201, two SOT-23-5, 2 x 100 nF). One dual TLV3202AIDR (SOIC-8, **C129325**, stock 7,399, $0.5954 at 500, JLC ladder) does both. Placements -2 (U11 and one 100 nF), lines +1 (the TLV3201 line stays for U12 and G08), parts cost -$0.30 on the benchmark's $0.45 estimate or -$0.67 on the JLC ladder ($0.6312 per TLV3201, $0.5954 for the dual). It needs the CT lobe re-routed (SOIC-8 land, new pin order). **SAFETY**-adjacent: the two polarity trips share one die. The shunt OCP (G08) is a separate chain, so the second trip path stays independent as long as the dual is **not** shared with any G08 comparator; do not merge them. I rank it last: $0.30 and a re-layout of a congested SELV lobe, with one more BOM line.

---

## Considered and rejected

1. **Higher-voltage bank (B32654A2104, 2000 V DC / 700 V AC, 100 nF) to remove the 1702 V exceedance.** Does remove it (1702.4 / 2000 = 0.851) and is strictly better thermally (IRMS 10.0 A vs 7.3 A, ESR 12.6 vs 19.3 mohm at 100 kHz, TDK p.23: -35 % loss). **Rejected**: the body is 22.0 x 36.5 mm against 14.0 x 24.5 mm; five in the existing row need 112.5 mm against the 81.8 mm slot (round-6 README); and price/lead time are worse (Avnet snapshot: $3.29 at 640, 42-week lead, via search, not fetched; LCSC C3808641 ladder $1.5087 at 500 against $0.2561 for the K part, stock 0 for both). It is a re-layout of the bank row (bank pitch, R22-R25 and J2/J5 move) for about +$6 (LCSC ladder, 1.5087 vs 0.2561 per cap) to +$9 (Avnet 3.29 vs the survey's 1.41) per board, to close a third-fault scenario DECISIONS 13 already accepted. If TDK answers the single-event question with >= 1.1 x V_R, the question disappears without any part change.
2. **Series/parallel arrangements for voltage.** Series strings need twice the parts for the same C and double the current-share problem; the 1250 V B32654 parts are below the double-fault figure. No enumerated arrangement beats 5 x 100 nF.
3. **Resonant-node clamp (TVS pair) across RES_A and SW_B.** The 02 study sizes it at conduction from about 1.3 kV, about 0.65 J (bank) to 0.88 J (coil), not conducting at 483.7 V peak. A stack of high-voltage bidirectional TVS adds a part on RES_A, which carries the 12.6 mm outer-layer creepage rule (`res_a_outer_min_mm` 13.375 today), plus leakage and a failure mode (a shorted TVS shorts the bank) for a third-fault case. No stocked part verified. Rejected.
4. **A hard timer floor in hardware (a retriggerable one-shot on the PWM edges).** The firmware already refuses `f_min < 35 kHz` in `tank_freq` and refuses retimes below it in `n21_binding` (DECISIONS 13). That floor brings the double fault to 1494.8 V (time-domain) and 1178.4 V (steady) in the committed study, and 1392.7 / 951.0 V with J caps in mine. A hardware one-shot guards a third fault (corrupted timer) that DECISIONS 13 puts outside the one-fault analysis and that stays under the 2560 V proof level; it adds parts on G05/G07's PWM path. Rejected.
5. **Bank voltage sense for a second independent trip.** Needs a 1.6 kV divider from RES_A across the 8 mm barrier. Rejected on creepage alone.
6. **Remove or replace the CT detector with a shunt or bus-voltage detector.** The CT is the second trip path (DECISIONS 13: hardware CT band 64.55-76.09 A vs the shunt OCP's 66.30-118.74 A). The 02 double-fault study shows what the shunt alone gives: 1702.4 V at 118.74 A vs 1164.5 V at the CT's 76.09 A. A single polarity comparator (dropping U11) delays the trip by up to a half cycle: 14.3 us at 35 kHz at up to di/dt = 198 V / 66.5 uH = 3.0 A/us, about +42 A beyond the trip, which lands at the shunt band. All of these weaken protection (**SAFETY**) and are rejected.
7. **Delete the line zero-cross string and derive zero crossings from the bus.** The firmware takes half-cycle boundaries from LINE_ZC only (`n21_binding.c`, DECISIONS 2026-10-06), and burst mode needs the crossing while the tank is stopped. In a burst-off interval the DC link is held by C5/C6 (19 uF) and R3+R4 (440 k): tau = 8.4 s against an 8.3 ms half cycle, so the bus does not track |v_line| and gives no crossing. Rejected.
8. **Line ZC string 4 x 16.5 k to 2 resistors, or dropping U24/C89.** Saves $0.04 and $0.44 respectively. The four-resistor string keeps each 1206 under 200 V working voltage (ECO: 0.074 W each at 140 V); two would see up to 250 V on a 500 V surge (the RV1 clamp level, not computed here). U24's Schmitt buffer drives J4.16, a pin in the F11 signal-integrity item. Rejected.
9. **Bleed string R22-R25 (4 x 470 k) to fewer or one resistor.** Each 1206 sees about 160 V peak at 640 V peak across C_res (parts.ato docstring); three would see about 219 V, over the 200 V working voltage of the 1206 part. A single HV resistor is an Extended line at the same cost, and the string is the only discharge path for a bank left at about 250 V after an OCP trip (the ato comment). Saving: $0.04. Rejected.
10. **Cheaper film caps (KYET KP104J1600VP22, C2857952, 986 in stock, 22.5 mm pitch).** Different pitch, and no ripple-current or dV/dt datasheet figure for 35-60 kHz at 5.6 A each; not verified. Rejected.
11. **Würth 74650073R (M3, C6848497, stock 1,996) for J2/J5.** It is the M3 sibling of the M4 74650074 (which has 0 JLC stock; the survey shows DK stock 32,606 and 26 wk). An M3 thread changes the coil lug and probably the footprint; not verified. If G02 removes J7-J10, J2/J5 stay as the line's only users. Left for the G02 owner; I do not propose it.
12. **Other CT sources.** No SMT CT with 8 mm reinforced insulation, 5 kV and 80 A besides CST3015 turned up (TDK B82801 and B7841x are 2.4 kV basic insulation or lower current). CST3015-050ED, -300ED, -400ED have 0 stock at JLC.

## What I could not verify

- Coilcraft prices for the -200ED (P1's cost saving), and C_ww for either T1 (MAG-11/MAG-27 stay open); no insulation working-voltage figure exists in 1608-1.
- DK/Mouser price and stock of B32654A1104J000 and K, and the 500-piece price on the channel the board will actually buy from. The LCSC ladder for the K part (C3811101) looks too low against the $1.41 survey figure.
- Whether C3811101 (K) and C3794777 (J) are genuine in-stock-able THT assembly lines at JLC: stock 0 and 104.
- Mouser stock for VOL628A-2X001T (aggregator figure only).
- CTR at the actual sub-mA LED current (the `g` factor). The 300 us firmware minimum is a benchmark risk I flag, not a measurement.
- Whether JLC will place a 16.7 g T1 (Coilcraft weight 16.6-16.9 g) reliably; C50132500 is listed as SMT.
- TDK's single-event over-voltage rating (the DECISIONS 13 owner question); nothing in P1-P3 changes that need.
- J4 signal integrity (F11): no proposal here touches it, and I did not model it.
