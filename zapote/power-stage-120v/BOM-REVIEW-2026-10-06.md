# Power-board BOM review: waste and non-standard solutions (native-20 → native-21)

Reviewed: `frozen/default.csv` (native-20: 63 lines, 142 placements), the source
roles (`elec/src/power_stage_120v.ato`), and the adopted native-21 additions
(F6 bias per D-12 ISOLATED-BIAS.md). Ranked by impact. **Decided** items are
recorded in DECISIONS.md 2026-10-06. **Candidate** items need the stated
evidence first.

| # | Finding | Impact | Status |
| --- | --- | --- | --- |
| 1 | **F6 gate bias is over-built.** D-12's isolated-bias proposal uses four RECOM R15C2T25 modules (~45 % assumed efficiency), four TPS7A30 negative LDOs, a rail-window monitor, and a **second 21 W AC-DC (PS2 → IRM-20-15)** to feed them: about **$119** and **~215 purchased parts** per board. Its own sizing shows module heat of 2.32 W at 80 kHz, **above the module's 1.7 W dissipation characteristic** (ISOLATED-BIAS.md). The standard approach is one transformer-driver IC (TI SN6507, 36 V input, or the UCC25800 class built for multi-output gate bias) fed from the **existing SELV 15 V (PS1)**, with reinforced-isolation transformers for three source domains (HS-A on `sw_a`, HS-B on `sw_b`, one LS on `leg_ret`). Each secondary gives a regulated +15 V and a −2 V Zener/shunt split backed by the reservoir capacitors. That **deletes PS2 entirely** (an AC-DC module plus its mains wiring), the four modules, the four negative LDOs, and the bootstrap network. Estimated material **~$15–25**, to be confirmed by sizing. | ~$95 per board, about 150 fewer parts, one AC-DC module removed, ~2 W less heat on the board | **Decided as the D-33 direction**, gated on: PS1 budget, reinforced transformer rating vs D5, and F6 re-simulated with the real bias-source impedance |
| 2 | **MC78L05 for HOT5** (U3) is a legacy regulator with 3.8 mA typ / 6–7.6 mA max ground current. It is the second-largest contributor to the shunt-OCP Kelvin error: 0.75 of 2.13 mV (`02-protection-timing/kelvin/`). A 30 V-input low-Iq LDO (TPS709 class, µA Iq) removes that contribution, raising the band minimum by about 0.8 A. If item 1 lands, HOT5 comes from the LS bias secondary instead and this LDO still applies. | Trip accuracy +0.8 A; same cost | **Decided** for native-21 (part chosen in D-33) |
| 3 | **Bootstrap network** (D1/D2 UF4007, the only THT axial diodes in the gate area, plus C10/C11/C17/C18) is unnecessary once each high side has its own isolated bias. | 6 parts, 2 THT | Follows from F6; D-33 removes them |
| 4 | **Two EMI filters in series.** The board carries a full mains filter (L1 B82726 CM choke 46 × 30 mm, C1/C2 1 µF X2, C3/C4 Y1, RV1, F1), and D-22 added a separate 20 A DM + CM inlet module because the board filter alone fails (−24 dB). Sizing one filter for the whole job, either in the module or on the board, is the standard approach and would remove either L1 (the board's largest part) or the module. | One large choke or one ~$45 module, plus volume | **Candidate**: rerun D-22's model with the board's L1/C1/C2 removed (module only) and with an enlarged on-board filter (no module); keep whichever meets ≥ 6 dB. Added to the D-36 enclosure brief as packaging input |
| 5 | **Five single TLV3201 comparators** (U6/U7 HOT side, U10/U11/U12 CT side) where pairs share supply and domain. A TLV3202 dual for OCP+OVP and another for CT±, plus one single for zero-cross, gives the same performance. | 2 placements | Candidate (low value; do it only if native-21's layout is touched there anyway) |
| 6 | **Off-board DC fuse loop.** J7–J10 (four Würth REDCUBE press-fit terminals) take the bus out to an external Mersen US141 holder with an FWP-10A14F and back (~842 mm of wire, round 4). A PCB-mounted DC-rated fuse would remove four terminals and the harness, **but** FC1's DC clearing is itself unresolved (D-31 part 3). | 4 terminals, a harness, a holder | Candidate, owned by the protection decision: revisit when the vendor DC data for FC1 arrives |
| 7 | **Precision mismatch in the bus divider.** R30 (bottom) is 0.1 % thin film while the four 470 kΩ tops (R26–R29) are 1 % thick film, so the ratio error is set by the tops. Harmless (D-11's target is ±6 %), but the precision buys nothing. | negligible | No change: noted for consistency |
| 8 | **Assembly readiness.** The CSV's "LCSC" column holds MPNs, not LCSC codes, and about 30 placements are THT (TO-247, film capacitors, IRM modules, terminals, fuse clip). Plan mixed assembly: SMT by the fab, THT by hand or selective solder. | Quote and assembly time | Action for native-21 release: map LCSC codes, mark THT placements |

## What is standard and stays

These are reasonable choices that a review should leave alone:
- IPW65R018CFD7 ×4 vertical in one row (one shared sink);
- UCC21550 isolated drivers;
- WSK2512 Kelvin shunt with a TLV3201 OCP and an ISO7710 isolator;
- CST3015 tank CT with a bipolar comparator trip;
- AMC1311 isolated bus sense;
- CDE 942C resonant capacitors;
- TDK film bulk and HF capacitors;
- GBJ2510 bridge on the sink;
- TMOV20RP thermally protected MOV;
- MRT130KP bus TVS;
- the 0.1 % resistors in the OCP threshold and CT trip dividers, where the precision is used.

The ten authored "ReviewOnly" footprints are tracked against manufacturer
drawings in FOOTPRINTS.md and are not a BOM issue.
