# F5: leakage / touch-current budget (desk calculation)

Rerun: `python3 -I validation-results/07-conducted-emi/leakage/leakage_budget.py` (writes `result.json`; prints PASS/FAIL; exit 1 = design FAIL).

## Verdict: FAIL (design as specified), not a close call

At 132 V / 60 Hz, +20 % on every Y capacitor, the touch current with the PE open (the UL 1026 test condition) is **0.974 mA per polarity** against a 0.5 mA limit and a 0.25 mA (50 %) budget. The margin is -0.724 mA. The cause is the Y capacitance alone: board Y + D-22 module Y = 9.1 nF/line nominal, which is 0.543 mA at +20 % before any supply is added. The budget allows 5.02 nF per line in total.

Removing the module Y (board Y 2.2 nF only) with typical supply leakage gives 0.163 mA (PASS, +35 % margin), but the module's Y pairs are what the CM filter (D-22 / REC scenarios) relies on, so this trades EMI margin for leakage. That trade is a decision for the owner and the certifier, not made here.

## Limit chosen

**0.5 mA, UL 1026, grounded (3-wire) hand-carried/portable cord-connected appliance.** UL 858 covers ranges and is not applicable. Secondary sources (the standard text is paywalled and could not be read):
- IAEI "UL Question Corner: Leakage current" (https://iaeimagazine.org/columns/ul-question-corner/ul-question-corner-leakage-current/): "cannot exceed 0.5 mA for portable two-wire and three-wire cord and plug-connected appliances" and "0.75 mA for three-wire cord and plug-connected fixed or stationary appliances"; test includes the plug "connected to a power source with an open ground", both polarities. It names no standard or clause.
- AAFES Test Method H-13 (https://www.aafes.com/qualityassurance/TM_H-13.htm): 0.5 mA grounded portable, 0.75 mA grounded stationary/fixed; step 4.2 detaches the chassis ground at the plug. Names no standard.
- A search summary of a forum post (not verified; fetch returned 403) attributes the text to UL 1026 cl. 32.1 with 2.5 mA allowed for the first 5 min for sheath-type heating elements. Another listing places leakage tests in "Section 38". **The clause number is not confirmed.**
A countertop induction cooker is moved by hand, so the portable 0.5 mA class is the conservative reading; the 0.75 mA stationary class is not assumed.

**IEC 60335-1 (reference, cl. 13.2 / 16.2):** 0.75 mA for portable Class I appliances (3.5 mA stationary motor-operated) from a secondary summary; Table 4 text not read. At 0.974 mA the design also exceeds this.

## Inputs and sources

| Item | Value used | Source |
| --- | --- | --- |
| C3, C4 (one per line) | 2.2 nF, Murata DE1E3RA222MA4BP01F, +20 % | `elec/src/power_stage_120v.ato:346-351, 992-993`; `parts.ato:117-123` |
| Inlet module Y (D-22) | 4.7 nF + 2.2 nF per conductor = 6.9 nF, TDK B32021A3472M000 / A3222M000, +20 % | `out-D22/PARTS.md` (Main/HF Y capacitors; "0.437 mA per conductor"); s19b README sec 9.2 |
| PS1 IRM-20-15 (L_FILT/N_FILT), PS2 IRM-20-24 (TCO_L/N_FILT), PS3 IRM-60-15ST (blower, BLW_L) | max 0.25 mA @ 277 Vac each, Class II, no FG pin | MEAN WELL IRM-20-SPEC 2025-11-21 and IRM-60-SPEC 2025-11-21, spec table, PDF p.2, row "LEAKAGE CURRENT: < 0.25mA/277Vac" (https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF, https://www.meanwell.com/Upload/PDF/IRM-60/IRM-60-SPEC.PDF) |
| Blower | DC fan on PS3 15 V output, no extra mains-referred path | `stage16-blower-supply/PLAN-16.md` (fan law, BLW-AC harness to PS3) |
| Coil to PE | 31.0 pF (pan floating) | `DECISIONS.md` item 20, 2026-10-13 update |

Supply scaling: linear in V (132/277), x1.2 because the datasheet gives no test frequency (assumed 50 Hz). Each supply is charged to each line (the datasheet value is a single line-to-output current). Informational "typical" case: Simpex IRM-20-15 test report, 0.015 mA L-FG and N-FG at 240 Vac, one unit (https://simpex.ch/wp-content/uploads/2021/07/IRM-20-15-rpt.pdf); not used for the verdict.

## Scenarios

- **Open PE (governing touch current):** UL tests with the ground open, both polarities. The meter shorts the chassis to earth, so only the hot-side line's capacitance drives the current. The board is symmetric, so both polarities give the same value.
- **Normal, PE intact / open neutral, PE intact:** earthed accessible parts carry about zero touch current; the PE conductor carries both lines (1.95 mA design case, equal for open-N because the floating neutral rises to line potential). Reported for information; it matters for GFCI/outlet nuisance trips, and it is not a UL 1026 pass criterion as far as the secondary sources show.

## Controls

(1) The design plus 10 nF Y per line gives 1.571 mA, FAIL. (2) The board-only variant passes at 0.163 mA and flips to FAIL at 0.760 mA with +10 nF per line; the script's exit status requires that.

## Not included / limits

- Measurement network (UL/IEC 60990 body model, frequency weighting) not applied; capacitive 60 Hz current is taken unweighted, and for HF (60 kHz switch-node) coil-to-PE current no number is claimed. Bench item.
- Mounting-bracket capacitance of the chassis-mounted PS3 and the supplies' actual spread are not in any source. Wiring capacitance and R38 SELV-to-PE bonding paths are not modelled.
- Whether the D-22 module is fitted in the product is taken from the specification ("keep the inlet module").

## Certifier questions to add to outbox section 6

1. Which standard and clause governs: UL 1026 (edition, clause number for leakage current), is a countertop induction cooker "portable" (0.5 mA) or "stationary" (0.75 mA), and does UL 1026 treat it as hand-carried?
2. Is the leakage test run with the PE open (as the secondary sources say) for a Class I plug-in appliance, and is the 2.5 mA / 5 min heating-element exception available to an induction appliance (it is stated for sheath-type elements only)?
3. Does the certifier accept the supply datasheet 0.25 mA @ 277 Vac as a bound, or require measurement? Class II modules with an output bonded to PE (via R38) are in the path.
4. Is the HF (60 kHz) coil-to-PE current included in the measured leakage, and with what network?
