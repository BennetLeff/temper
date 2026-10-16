# Candidate 23 / stage 38: request to the D-22 inlet-module owner, 2026-10-15

Status: request, power-stage side. Nothing in the module's files (`out-D22/`) is edited from here. DECISIONS 47 items 4
and 5 are the source; this file records what the stage-38 board's leakage and EMI results assume about the module.

## Asked of the module
1. **Remove the four Y capacitors** (main 4.7 nF and HF 2.2 nF per conductor, TDK B32021A3472M000 / A3222M000;
   `out-D22/PARTS.md` "Main Y capacitors", "HF Y capacitors"). Line-to-PE Y is then only the board's C3 / C4, 2.2 nF
   per line.
2. **CM choke TDK 1.6 mH -> KEMET (YAGEO) SCF31X-220-2R1A011JH**: 5.68 mH, 22 A, 500 VAC, 4.39 mOhm, dT max 45 K,
   -40 / +130 C, D 45 x T 42 x H 33 mm max, 91.9 g (YAGEO spec sheet generated 10/15/2026; no pin-pitch drawing for this
   exact part; the sibling SCF31B drawing in KEM_LF0079_SCF-J_JH (09/25) p.4 Fig. 5 gives pitch 17 / 30 mm "reference
   only, not guaranteed"). With the Y at C3 / C4 the module CM choke must be >= 3.6 mH (DECISIONS 47 item 5).
3. Keep D-22's X caps and damping. **DM inductors (stage 52, DECISIONS 74, 2026-10-16): >= 100 uH per line at 21 A DC
   bias**, one per line (was 2 x 41 uH, still without an MPN). The prototype lot fits L1 = TDK B82726S2243A020 (8 uH
   stray against the 2203's 18 uH), and the full EMI margin then needs that DM inductance:
   - with 2 x 41 uH the s19b model gives 6.03 dB nominal and 1.57 dB in the X-caps -20 % sensitivity (INCONCLUSIVE; the
     70 kHz DM line, 2nd harmonic of 35 kHz);
   - with >= 100 uH per line it gives **11.14 dB nominal, 6.95 dB worst sensitivity (PASS)**; 120 uH gives 11.15 / 6.96;
     the DECISIONS 32 part (WE-HCFT 74437636355602, 49.7 uH at 21 A) is not enough (7.06 / 2.62);
   - the model's "module DM 80 uH" sensitivity is -24 % of nominal, so 100 uH nominal covers saturation down to about
     76 uH at 21 A;
   - `11-candidates/b15-proto-alternates/` (`scripts/run_emi_l1.py`, `results/emi-B82726S2243A020_moduleDM100u/`).
   Open: no 100 uH / 21 A DM inductor is selected yet, and its heat against the module allowance (3.6 W for both
   inductors) is unchecked. If the prototype module cannot carry it, the lot runs as a recorded prototype EMI deviation
   (INCONCLUSIVE model margin, pre-compliance on the bench decides). With the production L1 B82726S2203A020 the 2 x 41 uH
   result below still holds.

## What depends on it
- **Leakage (F5):** the stage-38 touch current is 0.2412 mA against the 0.25 mA budget (portable 0.5 mA, 50 %), margin
  8.8 uA (`07-conducted-emi/leakage/result.json`). With the module Y kept it is 0.653 mA and fails.
- **EMI (s19b):** nominal 12.37 dB, every sensitivity >= 8.19 dB with the SCF31X choke and no module Y
  (`07-conducted-emi/s19b/results.json`; board L1 B82726S2203A020, 2 x 41 uH DM; for the stage-52 L1 see item 3). The SCF31X DM leakage is unpublished; the model takes 1 % (56.8 uH). At 0.3 %
  the co-design study's minimum is 6.87 dB, so **please measure the DM leakage of a sample** (open item).

## Sourcing (read 2026-10-15, public pages only)
| Source | Result |
|---|---|
| DigiKey 399-SCF31X-220-2R1A011JH-ND | 68 in stock, 13 weeks standard lead; $12.82 at 1 ... $7.725 at 560 |
| JLC parts API | no listing |
| Mouser | "Access denied" (unread) |
| Farnell | HTTP 403 (unread) |

68 parts cover the prototypes but not a 500-system build (500 chokes for the module alone). Order at the 13-week lead,
or confirm a second channel.

## Not changed on the board
Board L1 for production stays the TDK B82726S2203A020 (`README.md`, "L1"; stage 52 fits the same-drawing
B82726S2243A020 for the prototype lot only, item 3 above): the SCF31X body (45 x 42 mm) does not fit the L1 slot
(47.96 x 32.81 mm between C1, C5, C2 and PS2) without moving C1 / C5 / F1, and DECISIONS 47 item 6 rules out
compaction. The robust variant (SCF31X at L1 as well) stays open for a re-layout.
