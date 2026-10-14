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

## Current findings (seed, 2026-10-13: 91 BOM lines, 1 VERIFIED / 24 PARTIAL / 64 UNAUDITED / 2 VIOLATION)
**VIOLATION**
- **J1 1711725**: 24 A is IEC only; cULus group B 15 A, CSA 10 A. Design: 13.5 A regulated (CSA 1.35x), 15 A trip (zero margin), 16.5 A envelope.
- **F2 3403.0171**: 200 A IEC breaking capacity vs 373-3,567 A prospective fault at J11; F1 cannot back it (DECISIONS.md:843).

**UNAUDITED SAFETY/POWER (gate fails until audited)**: R1/R2 1206W4F1003T5E (mains X-cap bleed); C12/C13/C19/C20 GRM31A5C3A102JW01D (1 kV snubbers).

**PARTIAL** (gap in one line)
- F1 KLDR025: overload through J1 not interrupted (25 A fuse vs 15 A terminal); clip datasheet not read.
- BR1 GBJ2510-F: I2t 510 < F1 clearing 1,710 (sacrificial, accepted); Tj not computed.
- Q2/Q3/Q5/Q6: switching loss/dv/dt unmeasured; Tj 128.7 C vs 125 C design on K1 contingency sink; F7 open.
- U1/U2 UCC21550: CMTI 125 vs 95 V/ns is 1.32x (< 1.5x rule); no stock until 2027-06; bypass placement ungated.
- C5/C6 B32676G1905: ripple heating checked only at 22 A (80 %); extrapolation to 26/28 A exceeds the allowance.
- C21-C23/C151/C152 B32654A1104J: 28 A is 4.5 % over the digitised TDK curve (26 A commissioned is inside); third-fault 1,683 V > 1,600 VDC.
- C38-C41 B32652A0104: RMS share unknown (needs measurement).
- RV1 TMOV20RP175E: datasheet not obtained (distributor figures); MCOV margin 0.2 V at 80 %.
- C1/C2 X2: temperature and surge pulse not compared. C3/C4 Y1: exact-MPN datasheet missing; product leakage 0.974 mA vs 0.5 mA (F5).
- L1 B82726S2203A020: no datasheet found; rated voltage and temperature derating unchecked.
- R5 CSS2H: pulse rating vs 71 A trip not compared; shunt current approximated by tank current; zero stock.
- T1 CST3015-200ED: no maker working-voltage/CTI/HF rating at 198 Vpk.
- PS1 IRM-20-15: 11 % margin at a modelled 78 C bay air. PS2 IRM-20-24: derating at real local air unread (model case 98 C vs 85 C ambient rating).
- U41/U42 R24C2T25: datasheet copy is PRELIMINARY (850 Vrms/1.2 kVp functional) vs repo's reinforced claim; thermal and start-up on the bench.
- J3/J11 JST VH: NA UL/CSA file rating not read; J11 sits behind the failing F2.
- J2/J5 Wuerth 74650074: only the 50 A at 20 C docstring; no derating.
- D3/D17 30KPA150CA: no Good-Ark copy; 95 % standoff use at 286 V; plug-in overshoot 384 V exceeds VBR min; lead-bend unchecked.
- ISO7710 (U9, U32-34): CMTI min 85 < 95 V/ns; U9 unfiltered. AMC1311 U4: CMTI 1.05x, datasheet not fetched.
- U36 VOL628A: LED current vs IF max and CTI 275 vs D5 basis unchecked; no CMTI.
- R3/R4, R22-R29 RC1206FR-07: only the 2004 series spec; the current RC_L sheet not read.

VERIFIED: J6 1704004 only (leakage-only PE branch; limits CSA 10 A / cULus 15 A).
