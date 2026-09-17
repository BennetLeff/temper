# K-SIC15 attempt-001 — source extraction: onsemi NTH4L060N065SC1

Task: K-SIC15 (source-only). Attempt: attempt-001.
Question: can an exact Kelvin-source device plus its required drive/thermal
assembly beat the common reference?

## 1. What was asked

Verify that the already-retained datasheet is the genuine onsemi manufacturer
PDF, hash both in-repo copies and confirm identity, then extract the six values
consumed by `pfc_drive_experiment::Device` (`qg_c`, `qgd_c`, `plateau_v`,
`intrinsic_gate_r_ohm`, `eoss_j`, `rds_max_ohm`), with unit, test condition and
page/figure. No solver run, no model edit.

## 2. Identity

- MPN: **NTH4L060N065SC1**, onsemi. Package **TO-247-4LD** (CASE 340CJ).
- Document: `NTH4L060N065SC1/D`, **Rev. 3, January 2023**, 8 pages.
- Both retained copies are **byte-identical**:
  - `.../options/architecture-comparison/sic/sources/NTH4L060N065SC1-Rev3-2023-01.pdf`
  - `.../options/replacement-pair/sources/NTH4L060N065SC1-Rev3-2023-01.pdf`
  - SHA-256 (both): `e1063468f3c85e75c1830382be534ad8d7647d7f69ba8d4fe4c4dc31b004f8c4`
- Genuine-PDF evidence: `%PDF-` header, `file` = "PDF document, version 1.4,
  8 pages", PDF metadata Author=`onsemi`, Creator=`BroadVision, Inc.`,
  Producer=`Acrobat Distiller 22.0`, CreationDate 2023-01-30.
- A byte-identical copy is retained at `raw/` in this run directory.

## 3. The six model parameters

| Field | Value | Unit | Condition | Page / figure | typ or guaranteed | Applicability |
| --- | ---: | --- | --- | --- | --- | --- |
| `qg_c` (QG(TOT)) | 74 | nC | VGS=-5/18 V, VDS=520 V, ID=20 A | p2 Table 2 (Q charges) | typical | **SOURCE_CONDITION_MISMATCH** |
| `qgd_c` (QGD) | 23 | nC | VGS=-5/18 V, VDS=520 V, ID=20 A | p2 Table 2 | typical | **SOURCE_CONDITION_MISMATCH** |
| `plateau_v` | **null** | V | not published | p2 Table 2 (absent); p5 Fig. 7 (curve only) | not specified | NOT_SPECIFIED |
| `intrinsic_gate_r_ohm` (RG) | 3.9 | ohm | f = 1 MHz | p2 Table 2 | typical | APPLICABLE |
| `eoss_j` | **null** | J | not published (only Coss=133 pF) | p1 Features; p5 Fig. 8 | not specified | NOT_SPECIFIED |
| `rds_max_ohm` | 0.070 (70 mΩ) | ohm | VGS=18 V, ID=20 A, TJ=25 C | p2 Table 2 (RDS(on) max); p1 | **guaranteed** | **SOURCE_CONDITION_MISMATCH** |

Associated RDS(on) rows (all p2 Table 2): 60 mΩ typ at 15 V/20 A/25 C (no max),
44 mΩ typ at 18 V/20 A/25 C, 50 mΩ typ at 18 V/20 A/175 C (no max).

## 4. Gate-bias mismatch — the load-bearing finding

Task gate bias: **0/+15 V unipolar (15 V swing).**
Datasheet switching test point: **VGS=-5/+18 V bipolar (33 V swing).**

The published switching energies are measured at the bipolar point:

- EON = 45 µJ, EOFF = 18 µJ, Etot = 63 µJ, typ, at
  VGS=-5/+18 V, VDS=400 V, ID=20 A, RG=2.2 Ω, inductive load, TJ=25 C
  (p2 Table 2, SWITCHING CHARACTERISTICS).

These are recorded and labeled **SOURCE_CONDITION_MISMATCH**; none is
transferred into a 0/+15 V energy or gate-loss figure. `qg_c`/`qgd_c` carry the
same -5/+18 V mismatch (their charge is swing-dependent), and the only
*guaranteed* RDS(on) maximum (70 mΩ) is an **18 V** number — at the proposed 15 V
only a 60 mΩ **typical** exists, with no maximum and no guaranteed hot point.

Gate limits captured:
- Recommended VGS operation: **-5/+18 V** (p1 VGSop; p2 VGOP).
- Absolute maximum VGS: **-8/+22 V** (p1 Maximum Ratings).
The 0/+15 V proposal sits inside both, but the source switching data does not.

## 5. Package / Kelvin / ratings

- Pinout: **G, D, S1 = Kelvin Source, S2 = Power Source**; the device has a
  separate Kelvin source pin (p1, p7 mechanical outline).
- VDSS 650 V (guaranteed min); ID 47 A at TC=25 C, 33 A at TC=100 C, IDM 152 A;
  PD 176 W at TC=25 C; body-diode IS 35 A; RθJC 0.85 °C/W (p1, p2).

## 6. Missing inputs (explicit nulls — not zero)

- **`plateau_v`: null.** No Miller plateau voltage is stated. Only p5 Figure 7
  (VGS vs QG) shows a plateau; reading it off the curve is digitization/fitting,
  which is forbidden here.
- **`eoss_j`: null.** No Eoss value or test condition is published. The part
  gives Coss = 133 pF at VDS=325 V and a Coss-vs-VDS curve (Fig. 8); computing
  Eoss would require digitizing and integrating over the actual 400 V bus.
  Coss is not substitutable for stored energy.
- Not inferred: current-transfer charge from QG−QGD; 0/+15 V energy from the
  -5/+18 V rows; hot/15 V RDS(on) from the 25 C or 18 V values.

## 7. One next observation

The single missing measurement most likely to change the decision is a
**matched double-pulse switching-energy capture of this exact device at
0/+15 V, RG = 2.2 Ω, 400 V bus, over the instantaneous drain currents present
at the PFC switching instants, at 25/100/125 C**, stating whether Eoss is
already included. Until then the candidate's switching loss at the proposed
bias is unknown, and no loss advantage over the common reference can be
claimed. (Fallback source-only option: a manufacturer or onsemi-authored
0/+15 V Eon/Eoff/Eoss dataset or a validated SPICE model; none is retained.)

## 8. Budget / accounting

- Solver invocations: 0 of 0 (source-only).
- Sources retrieved: 1 primary PDF, verified in two paths. Retrieval failures: 0.
- Files produced: `raw/NTH4L060N065SC1-Rev3-2023-01.pdf` (+ `.sha256`),
  `raw/datasheet-layout.txt`, `inputs.json`, `result.json`, `REPORT.md`,
  `manifest.json`.
- Source revision: `1e0d8132d66e16027bbe4f6b21844b2d208b87d2`. No model, board,
  BOM, CAD or acceptance rule changed.
