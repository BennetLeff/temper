# LCSC sourcing for native-21 (survey 2026-10-08)

> **Stale for the board of record (2026-10-15):** this survey describes the 2026-10-08 BOM and still names superseded parts (UCC21550, ISO7710, CST3015-100ED, B32656G0275J000, 74650074R). For s43, use `../PROTOTYPE-LOT.md` and `SNAPSHOT-2026-10-15.csv` (s43 rows).

`lcsc-map.csv`: every one of the 92 BOM lines looked up on jlcpcb.com/parts and lcsc.com product
pages (URL per line in `Source_URL`; no C-number guessed). `../scripts/apply_lcsc.py` writes the
result into `../fab/bom-jlcpcb.csv`.

| Result | Lines |
| --- | ---: |
| Exact LCSC match | 84 |
| Fixed by a source change (DECISIONS.md 2026-10-08) | 2 |
| Accepted JLC substitute (equivalent spec) | 1 |
| Consign or hand-assemble | 5 |

**Source changes this survey forced** (value/MPN only, same footprints; native-21 rebuilt, parity 0):
- **R83, R101, R116** `RT0603BRD077K62L`: 7.62 kΩ is not an E192 value and no 0.1 % part exists.
  Changed to **RT0603BRD077K68L (C375517)**. The monitor's negative-rail OV edge moves from −2.198 to
  −2.206 V (+0.35 %), inside the TL431's ±0.5 % and the LM339's offset.
- **R51, R52, R55, R56** `RC1206FR-070R68L`: Yageo's RC series starts at 1 Ω, so this MPN does not
  exist. Changed to **RL1206FR-070R68L (C728510)**, Yageo's low-ohm series: 0.68 Ω, 1 %, 0.25 W.

**Accepted substitute (to stage 42):** C12/C13/C19/C20, Murata GRM31A5C3A102JW01D (not on LCSC) → Yageo
CC1206JKNPOCBN102 (C113872): 1206, 1 nF, 5 %, 1 kV, C0G. GRM31A5C3A102JW01D is not a Murata part at all (the
GRM31A5C3A list ends at 100 pF), so from stage 43 the source MPN is CC1206JKNPOCBN102 itself and the BOM line is a plain
JLC Extended line (`apply_lcsc.py`, `STOCK-2026-10-13-addendum-s43.csv`, `study-2026-10-15/snapshot/s43/`).

**Consign or hand-assemble:**
- C5/C6 B32656G0275J000;
- U1/U2 UCC21550**BDWK**R. LCSC has only the DW variant, a different package and creepage, so it is
  not a substitute;
- T1 CST3015-100ED; T2/T3 750320775;
- R34 RT0603BRD0710K6L. The 0.1 % alternate TNPW060310K6BEEN had zero stock.

**Zero stock at survey (exact matches, needs a buy plan before ordering):**
- R463N410000N1M (C1, C2);
- B82726S2203A020 (L1);
- WSK25121L000FEA (R5);
- 74650074R (J2, J5, J7–J10);
- 942C12P22K-F / 942C12P1K-F (C21–C23);
- ISO7710DWR (U9, U32–U34);
- 0430451612 (J4), MRT130KP295CV (D3), 1704004 (J6);
- SN6507DGQR (U35), VOL628A-3X001T (U36);
- RT0603BRD076K12L (6.12 kΩ);
- RT0603BRD07133KL (133 kΩ; in-stock drop-in Viking ARG03BTC1333, C1509631, noted not applied).

**Thin stock:**
- IPW65R018CFD7: 6 in stock, 4 per board;
- DE1E3RA222MA4BP01F: 6, 2 per board;
- 6SVPC220M: 13, 4 per board.

Only AO3400A is a JLC Basic part; every other line carries JLC's Extended-part fee. The 19 THT
lines assemble at JLC only if in library and in stock (hand or wave soldered, extra fee).
