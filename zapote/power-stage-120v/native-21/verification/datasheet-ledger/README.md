# Datasheet ratings ledger (native-21)

One entry per BOM line (keyed by MPN) recording the manufacturer datasheet, its ratings **with their approval basis**
(IEC vs cULus vs CSA, temperature, derating curve), the repo's worst-case stresses with file:line, the derating rule, the
computed stress/limit ratio, and which layout guidance is enforced by a gate or is `UNCHECKED`. Created 2026-10-13 after
the outside review found J1 rated 24 A IEC but 15 A cULus / 10 A CSA (FINDINGS #4).

## What the gate checks (`gate.py`)
Fails (exit 1) on: a BOM MPN missing from the ledger; designators that drifted from `native-21/frozen/default.csv`;
a malformed or self-inconsistent entry; any `VIOLATION`; any SAFETY/POWER-class line still `UNAUDITED`.
Self-consistency: the gate recomputes every `checks[].ratio = stress / limit`; a failing `violation`-severity check forces
`VIOLATION`, a failing `gap`-severity check forces `PARTIAL` or worse; `VERIFIED` needs a datasheet url or repo copy, rated
limits with a source page, stresses with evidence, at least one passing check and no gaps; `PARTIAL` must list its gaps;
every `path[:line]` cited in stress evidence or layout guidance must exist in the unit. `--strict` fails on any non-VERIFIED.
SIGNAL-class `UNAUDITED` lines only warn. Prints counts by status and class; writes `ledger-report.json`.

    python3 -I native-21/verification/datasheet-ledger/gate.py [--strict]
    python3 -I native-21/verification/datasheet-ledger/tests/test_gate.py     # negative controls

## Adding or changing an entry
Edit `ledger.json` (`seed_ledger.py` produced the first seed; do not rerun it, it overwrites). Fields: `mpn`, `designators`
(must equal the BOM), `class` (SAFETY | POWER | SIGNAL), `function`, `status`, `datasheet {url, revision, fetched | repo_copy}`,
`ratings [{parameter, datasheet_limit, unit, basis, source}]`, `stresses [{parameter, worst_case_value, unit, condition,
evidence}]`, `derating_rule`, `checks [{id, rating, stress, max_ratio, severity, rule, ratio}]` (ratings and stresses are
referenced by `parameter`, same unit, numeric), `layout_guidance [{item, enforced_by}]` (`enforced_by` is a repo gate path
or starts with `UNCHECKED`), `gaps`, and `finding` (required for VIOLATION). When a BOM line is added or an MPN changes, add
the entry in the same commit or the gate fails.

## Current findings (after stage 28, 2026-10-14: 92 BOM lines, 2 VERIFIED / 28 PARTIAL / 62 UNAUDITED / 0 VIOLATION; the gate PASSES)
Stage 38 (2026-10-15): 93 BOM lines, 3 VERIFIED / 31 PARTIAL / 59 UNAUDITED / 0 VIOLATION; PASS. PS1 IRM-20-15 removed, IRM-20-24 -> MPM-20-24.
Stage 40 (2026-10-15, candidate 30a): 92 BOM lines. CA-IS3720LW removed (U44 is now the second ISO6721FBDR); D20 joins
BAT54S-7-F (its reverse stress is D18's), R135 joins 0603WAF1002T5E and C168 joins CC0603KRX7R9BB104. The one VIOLATION is
IPW65R018CFD7 (DECISIONS 49), unchanged.
Stage 42 (2026-10-15, candidate 39, DECISIONS 54): 93 BOM lines, 3 VERIFIED / 31 PARTIAL / 58 UNAUDITED / 1 VIOLATION.
R10/R12/R18/R20 RS-06L8R20FT -> 25121WF680JT4E (68 ohm 2512, new POWER entry) and C55/C56/C62/C63 leave
C0603C102J5GACTU for GRM1885C1H472JA01D (4.7 nF C0G, new SIGNAL entry, PARTIAL). IPW65R018CFD7 VIOLATION -> PARTIAL: the
S4 diode limits are met at typical Qrr (49.7 V/ns, 244 A/us); the maximum-Qrr basis is its open gap (D-8 bench). The one
VIOLATION is now **25121WF680JT4E**: at the 22 A c22 ceiling (bay 55 C) its B3 terminal is 138.1 C, where 0.217 W is 109 %
of the derated power against the 80 % rule; the gated still-air ceiling with this network is 20.0 A
(validation-results/11-candidates/c39-gate-network).
Batches A/B merged on s42 (2026-10-15, 27 lines, DECISIONS 56 stress basis: thermal ratings at the release case c18_h10 /
bay 61 C from b3-ratings/margins.json, with c22/c28 overruns as `owner: airflow route (c22/c28)` gaps; electrical ratings
at s42's 49.7 V/ns S4 edge, maximum Qrr a D-8 gap): 3 VERIFIED / 32 PARTIAL / 58 UNAUDITED / **0 VIOLATION**; PASS.
25121WF680JT4E clears at c18 (0.217 W = 0.775 of the 131.2 C-terminal curve, rule 0.8), and so do batch A's R5 and bank
(28 A rows) and batch B's ISO6721FB / 2EDR8259X CMTI (2.0x / 3.0x at 49.7 V/ns). The B3 gate's C5/C6 advisory limit is
now TDK's 105 C (B3267* p.13).
Stage 43 (2026-10-15, candidate 43, track cleanup + source MPN fix): 93 BOM lines, 3 VERIFIED / 32 PARTIAL / 58 UNAUDITED /
0 VIOLATION; PASS. C12/C13/C19/C20 re-keyed GRM31A5C3A102JW01D -> **CC1206JKNPOCBN102** (the source now names the ordered
Yageo part; the source-MPN owner gap is closed). GRM1885C1H472JA01D's temperature re-cited from the c22 FET-row value
(133.5 C) to the release case, 122.1 C <= 125 C, with the c22 overrun (132.6 C) an `owner: airflow route (c22/c28)` gap.
Every margins.json citation follows the s43 rows (line numbers and values); the c22 worst R_on is now R12 (136.1 C
terminal, 0.976 of the derated power). validation-results/11-candidates/c43-cleanup/README.md section 5.
History: seed 1 / 24 / 64 / 2. Stage 27 replaced J1 (VIOLATION -> PARTIAL); R1/R2 and the snubber caps were audited
(UNAUDITED -> PARTIAL). Stage 28 replaced F2 (VIOLATION -> VERIFIED) and added its limiter R130 (PARTIAL). `ledger.json` is the record from here on; `seed_ledger.py` reproduces only the first seed.
**VIOLATION**: none.

**UNAUDITED SAFETY/POWER**: none.

**Resolved:** F2 3403.0171 (UMT 250, 200 A IEC vs 373-3,567 A at J11) was replaced at stage 28 by the UMT-H 3403.0279.23
(1500 A UL @ 277 VAC) with R130, a 0.15 ohm AC05 limiter: the J11 fault is bounded at 980 A (65 %; c28-f2/bounds.py).
J1 1711725 (24 A IEC only; 15 A cULus / 10 A CSA) was replaced at stage 27 by 1714971, MKDS 5/2-9,5 (UL/cUL
and CSA group B 30 A, 300 V): 45-55 % across 13.5-16.5 A, 83 % at F1's 25 A.

**PARTIAL** (gap in one line)
- R130 AC05000001507JAC00: pulse 0.54 of capacity on the current-limiting clearing estimate, 0.94 on 3x melting; F2's clearing I2t is unpublished, so a bench short at J11 settles it.
- J1 1714971: ratings from Phoenix catalog extracts (2017; a 2010 copy agrees on 30 A, prints 600 V UL/cUL); UL Product iQ, database.ul.com and Phoenix all 403 on 2026-10-13, so E60425 / CSA 13631 still unconfirmed.
- R1/R2 1206W4F1003T5E: 44 % of continuous working voltage, 58 % of the 5 s overload in a surge (RV1 455 V clamp); no maker pulse rating.
- C12/C13/C19/C20 CC1206JKNPOCBN102 (source MPN GRM31A5C3A102JW01D until stage 43; not a Murata part): 490 V die VDS at 49 % of 1 kV (50 % rule, modelled); Yageo sheet read, no ripple/pulse rating published.
- F1 KLDR025: overload through J1 not interrupted (25 A fuse vs 15 A terminal); clip datasheet not read.
- BR1 GBJ2510-F: I2t 510 < F1 clearing 1,710 (sacrificial, accepted); Tj not computed.
- Q2/Q3/Q5/Q6: switching loss/dv/dt unmeasured; Tj 128.7 C vs 125 C design on K1 contingency sink; F7 open.
- U1/U2 UCC21550: CMTI 125 vs 95 V/ns is 1.32x (< 1.5x rule); no stock until 2027-06; bypass placement ungated.
- C5/C6 B32676G1905: ripple heating checked only at 22 A (80 %); extrapolation to 26/28 A exceeds the allowance.
- C21-C23/C151/C152 B32654A1104J: 28 A is 4.5 % over the digitised TDK curve (26 A commissioned is inside); third-fault 1,683 V > 1,600 VDC.
- C38-C41 B32652A0104: RMS share unknown (needs measurement).
- RV1 TMOV20RP175E: Littelfuse 2017 sheet (distributor copy; littelfuse.com 403). MCOV 79.8 % (80 % rule), 750 A = 7.5 % of 10 kA single and 57 % of the digitised 100-pulse 1.31 kA; Vc 455 V @ 100 A confirms the ALT-D3 model. Gaps: local ambient (85 C rating), newer revision, UL 1449 file unread.
- C1/C2 X2: temperature and surge pulse not compared. C3/C4 Y1: exact-MPN Murata spec found (Y1 300 V / X1 440 V, UL E37921, VDE 40043033): 47 % at 139.7 V. Product leakage (F5) passes at stage 38, 0.2412 mA vs the 0.25 mA budget (s35: 0.974 mA), contingent on the D-22 module Y removal and PS3 = MPM-65-15ST.
- L1 B82726S2203A020: TDK sheet 5/26 read: 250 V AC (56 %), IR 20 A at TR 60 C, Lstray 18 uH. 15 A meets 80 % only up to 67.7 C local air (IR itself to 85.3 C); L1 air is unmeasured, exhaust side of the 50 C duct. No UL/CSA recognition listed.
- R5 CSS2H: pulse rating vs 71 A trip not compared; shunt current approximated by tank current; zero stock.
- T1 CST3015-200ED: no maker working-voltage/CTI/HF rating at 198 Vpk.
- PS2 MPM-20-24 (stage 38, was IRM-20-24; PS1 IRM-20-15 deleted): MPM-20-SPEC 2024-10-30 read. 9.59 W is 44 % of 21.6 W and stays within 90 % of the p.3 derating curve up to 70.3 C local air (unmeasured); Vin 53 % of 264 VAC; touch current < 80 uA / 264 VAC; approvals IEC 60601-1 (2 x MOPP) / IEC 60335-1, no UL file listed (certifier item).
- U41/U42 R24C2T25/R: claim resolved. The current /R sheet (Rev. 1-2024) gives 5 kVAC reinforced, 1.4 kVp, 1000 Vrms, 1.4 kVDC, matching f6_parts.ato; the 'preliminary 850 Vrms' copy was the non-/R series. Barrier 37 %. 1.71 W holds to 85.6 C local air (90 % rule); air, start-up and EMI are bench items.
- J3/J11 JST VH: NA UL/CSA file rating not read; J11 sits behind the failing F2.
- J2/J5 Wuerth 74650074: only the 50 A at 20 C docstring; no derating.
- D3/D17 30KPA150CA: no Good-Ark copy; 95 % standoff use at 286 V; plug-in overshoot 384 V exceeds VBR min; lead-bend unchecked.
- ISO7710 (U9, U32-34): CMTI min 85 kV/us confirmed (SLLSER9E). U32-34 pass on the 10 us filter (5.47 ns event vs 5.95 us). U9 is unfiltered all the way to the controller latch: **new finding, availability only** (below).
- AMC1311 U4 (SBAS786C read): CMTI 100 min = 1.05x; VIORM 2120 V (13 %); VSENSE 1.65 V at 198 V (82.5 % of the 2 V FSR); 2.38 V at 286 V is above the linear range (240 V) but below clipping (302 V). Firmware flags over-range at 231 V, and OVP is the TLV3201.
- U36 VOL628A: LED current vs IF max and CTI 275 vs D5 basis unchecked; no CMTI.
- R3/R4, R22-R29 RC1206FR-07: only the 2004 series spec; the current RC_L sheet not read.

**Datasheet-gap pass 2026-10-13 (RV1, L1, C3/C4, U4, U41/U42, ISO7710, J1; derived numbers: `scripts/datasheet_gap_calcs.py`)**
- **NEW, U9 ISO7710 CMTI (availability, not safety).** U9.OUT -> U13 OR -> J4.10 BUS_FAULT -> controller interlock (LVC14 -> HC30 -> LVC14 -> LVC1G74 CLR_N) has no RC anywhere. A HIGH upset trips the permit latch, which turns all drivers off until firmware sends a reset edge: a nuisance trip in the safe direction. A LOW upset during a real fault can only delay detection by the upset width (event 5.47 ns, against a 0.85-1.16 us OCP chain), because OCP, OVP and HOT5 faults are held levels. Fix options: a 1 k / 47 pF RC at U13.A (+57 ns) at the re-spin, or a controller debounce. First, bench-probe BUS_FAULT at hard S4/S5 edges.
- **Resolved, RECOM isolation claim:** see U41/U42 above. The ledger had read the wrong product (non-/R RxxC2Txx).

VERIFIED: J6 1704004 only (leakage-only PE branch; limits CSA 10 A / cULus 15 A).
