# B3 probe rows for the rail monitors, and the unrated-part sweep (2026-10-15)

OPEN-ITEMS S16 (integration DECISIONS 60). Board s42 (9e075b4b), hot-copper BASIS (`../hot-copper-2026-10-15`).

The S16 study had to assume an 85 °C local temperature at the monitor ICs, because B3 had no rows there. They now have
gated rows, read from the hot-copper field.

```
python3 ../run_basis.py --workers 3                 # BASIS; run files now carry "probes" (body_runs probes=True)
python3 -I scripts/monitor_sweep.py                 # -> monitor-sweep.json (monitor rows + the sweep below)
python3 ../test_b3_hot_copper.py                    # probe-row tests (9 gated rows, self-heat, refusals)
```

## Rows

`body_runs.run_case(probes=True)` records the pad-copper temperature of every footprint on the board (393 refs): the
maximum over all pads on the mounting layer, on both meshes. `b3_ratings_gate.probe_rows` turns them into rows. Each row
uses the gate's estimator, Q(0.25) + 3·|Q(0.25) − Q(0.5)| + (bay − 50).

| Refs | Part (s42 BOM) | Row | Limit | Self-heat P·RθJA |
|---|---|---|---|---|
| U17 / U19 / U21 | TL431AIDBZR | gated | TA 85 °C (TI SLVS543S 6.4 p.5, TL43xxI) | 16.7 mW × 206 K/W = 3.4 K |
| U29 / U30 / U31 | LM339BIDR | gated | TA 85 °C (TI SLCS006Z 6.4 p.6) | 28.2 mW × 111.2 K/W = 3.1 K |
| U16 / U18 / U20 | TLVH431BQDBZR | gated | TA 125 °C (TI SLVS555N 5.3 p.5, TLVH43x_Q) | 6.2 mW × 206 K/W = 1.3 K |
| 42 divider / reference resistors on the monitor and split nets | RT0603 / ARG03 thin film, RC1206 / 0603WAF thick film | advisory | terminal derating line 155 − 85·P / (0.8·P_rated) | in the line |

The s42 board carries TL431**A**IDBZR. The S16 re-centre's TL431**B**IDBZR is the same I grade, so the limit is the same.

**Pad temperature is the die and local-ambient proxy.** In still air at these powers, the air beside a part is cooler
than the copper it sits on, so the pad is conservative for TA. Adding P·RθJA on top double-counts the board spreading
that RθJA already contains, which is also conservative.

**Self-heat** is computed from the BOM operating point (`elec/src/f6_bias.ato`) at V_PN = 17.0 V + 3 %:
- **TL431 reference:** K = REF, fed by 2.2 kΩ from P, less the 20 kΩ halfref divider. I_K = 6.70 mA at 2.495 V.
- **LM339B:** I_Q ≤ 1.6 mA (SLCS006Z 6.7 p.7, 36 V, −40 to 85 °C) at V_PN, plus four outputs sinking the 10 kΩ / 5 V
  pull-up at V_OL ≤ 0.4 V.
- **TLVH431 split shunt:** at most the whole 4.99 kΩ bleed at 2.01 V. This is static only; any dynamic imbalance of the
  gate-drive return is not modelled.
- **RθJA:** SLVS543S 6.3 p.5 DBZ; SLCS006Z 6.6 p.6 D; SLVS555N 5.4 p.5 DBZ.

**Refusals.** A monitor ref that no longer carries its pattern net stops the gate (`monitor(_ls)?-ref`, `-good`,
`split-fb` / `bias_ls-fb`). So does a resistor on a monitor net whose role pair is not in the topology table, and so do
hot run files without probes. Cold-copper controls keep the pre-S17 rows: `--copper-tcr 0` still reproduces the
ff921e889 `margins.json` byte for byte, through the new gate.

## Result: the monitors fail at the release case

Estimates in °C. In each margin cell, the first value is against the as-built grade (85 °C) and the second against the
125 °C grade of the same pinout: TL431BQDBZR (SLVS543S p.4, 6.4 p.5 TL43xxQ) and LM2901BIDR (SLCS006Z 6.4 p.6, LM2901B
TA −40 to 125).

| Ref | c18 @ 61 (release) | margin | c22 @ 55 | margin | c28 @ 55 | margin |
|---|---|---|---|---|---|---|
| U29 LM339B (LS) | 102.9 | **−17.9** / +22.1 | 100.0 | −15.0 / +25.0 | 106.0 | −21.0 / +19.0 |
| U31 LM339B (HB) | 101.5 | **−16.5** / +23.5 | 97.9 | −12.9 / +27.1 | 102.5 | −17.5 / +22.5 |
| U30 LM339B (HA) | 96.6 | **−11.6** / +28.4 | 91.5 | −6.5 / +33.5 | 94.2 | −9.2 / +30.8 |
| U17 TL431A (LS) | 92.7 | **−7.7** / +32.3 | 89.3 | −4.3 / +35.7 | 94.8 | −9.8 / +30.2 |
| U21 TL431A (HB) | 85.5 | **−0.5** / +39.5 | 81.2 | +3.8 / +43.8 | 84.5 | +0.5 / +40.5 |
| U19 TL431A (HA) | 81.9 | +3.1 / +43.1 | 77.5 | +7.5 / +47.5 | 80.8 | +4.2 / +44.2 |
| U16 TLVH431BQ (LS split) | 101.2 | +23.8 | 98.3 | +26.7 | 104.8 | +20.2 |
| U20 TLVH431BQ (HB split) | 83.6 | +41.4 | 79.0 | +46.0 | 81.7 | +43.3 |
| U18 TLVH431BQ (HA split) | 80.2 | +44.8 | 75.7 | +49.3 | 79.0 | +46.0 |

- **Five of the nine monitor ICs fail at c18 @ 61.** U29 binds the release gate at −17.9 K. On the 125 °C grades, every
  monitor row passes in every BASIS case: the worst is U29, +19.0 K at c28 @ 55.
- **The heat is not tank current.** U29 sits 10.7 mm from U26 (TPS7A4700, the LS 17 V span regulator, 0.90 W) and 8.6 mm
  from U37. U30 / U31 sit about 14 mm from the RECOM modules U41 / U42 (1.03 W each).
  - At bay 61, U29's row is −13.3 K at c8 (8.4 A trip), −14.7 K at c12, −16.7 K at c16 and −17.9 K at c18
    (`../hot-copper-2026-10-15/margins-bay61.json`).
  - So no tank ceiling passes at bay 61 with the 85 °C parts. That is a property of the bay and the bias heat, not of the
    tank copper.
- **Mesh term.** The gate's mesh term adds 3·|Δ| for these small pads. U29's 0.25 mm pad maximum alone is 83.8 °C at
  50 °C, so 94.8 °C at bay 61, plus 3.1 K of self-heat: still −12.9 K without the mesh term.
- **Dividers (advisory) pass.** The worst is the 2.2 kΩ RC1206 reference feed R59, which carries 0.103 W of its 0.25 W:
  +24.2 K at c18 @ 61 and +22.5 K at c28 @ 55. The 0603 dividers and pull-ups are all ≥ +67 K.

## Sweep: BOM semiconductors with no B3 row (report only, no gating)

The script covers every U / Q / D / BR / PS on the s42 BOM (`native-21/frozen/default.csv`, which matches the s42 c42b
schematic values) that has no B3 row. For ratings, it uses the ledger's temperature ratings first (read only), then a TA
grade read this session from the TI / Infineon text in `runs-native21/s16-monitor-dl` (MANIFEST sha256). Pad estimates
use the gate's estimator with no self-heat.

**Rated ≤ 105 °C:**

| Ref | MPN | Rating | c18 @ 61 pad | margin | c28 @ 55 pad | margin |
|---|---|---|---|---|---|---|
| PS2 | MPM-20-24 | 85 °C working temperature (ledger, p.2) | 112.2 | **−27.2** | 120.7 | **−35.7** |
| U5 | LM4040A25IDBZR | TA 85 °C (SLOS456Q 6.3 p.5, I grade) | 89.5 | **−4.5** | 104.5 | **−19.5** |

- **PS2** is heated (0.67 W into the board) and has a body model, but no rating row. Its 85 °C rating is the module's
  working ambient, and its pin pads carry its own heat, so the pad proxy is pessimistic for this part. A −27 K margin is
  still not a pass.
- **U5** has a 125 °C grade: LM4040xxxQ, SLOS456Q 6.3 p.5.

**Excluded because their ratings are above 105 °C:**
- Q2 / Q3 / Q5 / Q6: Tj 125 °C design, ledger;
- BR1: TJ 150 °C, ledger;
- U1 / U2: 2EDR8259X, TA 125 °C, Rev 1.7.

U26 / U41 / U42 and the nine monitors already have rows.

**No rating in the ledger or in the datasheets read (36 parts).** The full list is in `monitor-sweep.json`, hottest first.
The hottest at c18 @ 61, with the c28 @ 55 estimate in parentheses:
- D6–D9 PMEG6030EP: 113–119 °C (140–166 °C);
- U43 / U44 ISO6721: 110 °C (114 / 118 °C);
- U3 TPS70950: 107 °C (124 °C);
- U14 TPS3700: 101 °C (116 °C);
- U37 TPS70950: 100 °C;
- D18 / D20 BAT54S: 99 °C (123–124 °C);
- U8 SN74LVC1G10: 94 °C (111 °C);
- U7 / U6 TLV3201AI: 90 / 89 °C;
- U15 SN74LVC1G17: 90 °C (112 °C).

Their ledger entries are UNAUDITED or PARTIAL, with no temperature rating. Any of them with an 85 °C grade fails.

## Not done here

- No ledger edits.
- The 125 °C grades are a BOM decision (DECISIONS), not taken here. They clear the monitor rows but not the R10 row (see
  the hot-copper README).
