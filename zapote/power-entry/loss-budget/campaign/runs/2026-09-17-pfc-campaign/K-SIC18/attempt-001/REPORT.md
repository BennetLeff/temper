# K-SIC18 attempt-001 — source capture: Infineon IMZA65R048M1H

- **Task / attempt**: K-SIC18 / attempt-001 (source-only; `max_solver_invocations = 0`)
- **Changed variable**: none. No solver, no model edit, no CAD/BOM change.
- **Question (full task)**: can an exact Kelvin-source device plus its required
  drive/thermal assembly beat the common reference?
- **Sub-question answered here**: can the exact manufacturer datasheet be
  captured, and can the six `pfc_drive_experiment::Device` parameters plus the
  proposed 18 V gate bias be sourced from it?
- **Outcome**: capture succeeded; 5 of 6 model parameters sourced; `plateau_v`
  is a genuine source gap (null); 18 V gate bias is explicitly source-supported.

## 1. Datasheet identity (captured)

| field | value |
|---|---|
| MPN | IMZA65R048M1H (order code IMZA65R048M1HXKSA1) |
| Manufacturer | Infineon Technologies AG |
| Document | "Datasheet IMZA65R048M1H" (Final datasheet) |
| Revision | Rev. 2.2, 2025-01-20; 16 pages A4 |
| URL | https://www.infineon.com/assets/row/public/documents/24/49/infineon-imza65r048m1h-datasheet-en.pdf |
| HTTP | 200, `application/pdf`, 1,014,353 bytes, 2026-09-17T21:22:17Z |
| PDF SHA-256 | `359a804c4ac29355167fd82205f3020b1949540a597cc83fa9725572aa58e5c1` |
| Path | `raw/infineon-imza65r048m1h-datasheet-en.pdf` |

First attempt on the manufacturer primary succeeded (`%PDF-1.4`), so no mirror
was tried. `raw/` holds the unmodified PDF, the HTTP headers, a `pdftotext`
transcript and page renders used for reading. No HTML was hashed as a datasheet.

## 2. Six model parameters

| Rust field | value | unit | test condition | page / figure | typ / guar. |
|---|---|---|---|---|---|
| `qg_c` | 3.3e-8 | C (33 nC) | VDD=400 V, ID=20.1 A, VGS=0→18 V | Table 7, p.7 (also Table 1, p.1) | typical |
| `qgd_c` | 8e-9 | C (8 nC) | VDD=400 V, ID=20.1 A, VGS=0→18 V | Table 7, p.7 | typical |
| `plateau_v` | **null** | V | not stated; only QGS(pl)=9 nC plateau charge | gap (nearest: Diagram 10, p.10) | not stated |
| `intrinsic_gate_r_ohm` | 6.0 | Ω | f = 1 MHz | Table 5, p.6 | typical |
| `eoss_j` | 1.17e-5 | J (11.7 µJ) | VDS = 400 V (Coss stored energy) | Table 1, p.1; Diagram 16, p.11 | typical |
| `rds_max_ohm` | 0.064 | Ω (64 mΩ) | VGS=18 V, ID=20.1 A, Tj=25 °C | Table 5, p.6 (also Table 1, p.1) | guaranteed max |

Every number above is at VGS = 18 V (or is bias-independent), i.e. the same
gate bias the task proposes. There is no cross-bias transfer.

## 3. The 18 V gate-bias question — explicit source support

**Finding: the exact manufacturer PDF explicitly supports 18 V.** This is not an
extrapolation; 18 V is the recommended turn-on voltage *and* the test bias of the
sourced parameters.

- Table 4, p.5: **Recommended turn-on voltage VGS(on) = 18 V**; recommended
  turn-off VGS(off) = 0 V.
- Table 5, p.6: RDS(on) specified at VGS = 18 V (48 typ / **64 max** mΩ, 25 °C).
- Table 6, p.6: td(on)/tr/td(off)/tf specified at VDD=400 V, VGS=0/18 V,
  ID=20.1 A, RG,ext=1.8 Ω.
- Table 7, p.7: QG / QGS(pl) / QGD specified at VGS = 0→18 V.
- Table 2, p.3: IDM = 100 A and the VGS=18 V reverse-drain row also use 18 V.

Gate-voltage domains (all from the PDF):

| domain | min | max | source |
|---|---|---|---|
| Recommended turn-on / turn-off | 0 V (off) | 18 V (on) | Table 4, p.5 |
| Operating range incl. undershoots | −2 V | 20 V | Table 4, p.5 |
| Absolute max, static | −5 V | 23 V | Table 2, p.3 |
| Absolute max, transient (tp ≤ 1 % duty/fsw) | −7 V | 25 V | Table 2, p.3 |

Caveats: the recommended **off** bias is 0 V, not −5 V; a −5 V off-bias is
inside the static absolute maximum but **outside** the Table 4 operating range
(−2 V lower bound). Table 4's notice warns that exceeding the operating range can
push RDS(on)/VGS(th) past the datasheet maximum at end of life, and Infineon
recommends ≤ 80 % of maximum ratings for lifetime. The datasheet publishes
**switching times only — no Eon/Eoff energy row** — so there is no −5/+18 V
energy figure that could be mis-applied at another bias.

## 4. Package / pinout / ratings

- Package **PG-TO247-4** (PG-TO247-4-U02), 4-pin TO-247 **with Kelvin source**.
- Pins (p.1 device view): **1 = Drain + tab; 2 = Power Source; 3 = Driver
  Source (Kelvin source); 4 = Gate.** Infineon note: "the source and driver
  source pins are not exchangeable. Their exchange might lead to malfunction."
- VDS = 650 V. ID(DC) = 40 A @ Tc=25 °C, 28 A @ Tc=100 °C; IDM = 100 A @ 25 °C,
  VGS=18 V. ISDC = 40 A (VGS=18 V)/26 A (VGS=0 V); ISM = 100 A. Ptot = 150 W
  @ Tc=25 °C; Tj −55…175 °C; Rth(j-c) = 1.0 °C/W; EAS = 171 mJ; dv/dt = 200 V/ns.
- Lifecycle (web page, not the PDF): product status "not for new design"
  (2026-09-17); procurement observation only, not device performance.

## 5. Missing inputs / uncertainty

- **`plateau_v` (null)**: the manufacturer states no numeric Miller plateau
  voltage. Table 7 gives plateau *charge* QGS(pl)=9 nC. Diagram 10 (p.10,
  VGS=f(QG), VDD=400 V, ID=20.1 A) shows a **sloped** plateau region ≈ 7.5–9.5 V,
  but it is a graphic with no stated value and a sloping plateau, so promoting a
  digitized point would be an unsupported value. Nothing was fitted.
- **No hot RDS(on) maximum**: the only guaranteed max is 25 °C (64 mΩ); the
  175 °C value (67 mΩ) is typical only, so no hot maximum is recorded.
- **No switching-energy source**: only times are published, so the follow-on
  numerical task cannot use a datasheet Eon/Eoff.
- Assembly terms (driver rail producer, gate loop, bridge/diode, magnetics,
  shunt, ESR, EMI, cooling) remain untouched — `total_loss_w` stays null.

## 6. Status and evidence

- Source-only: `numerical_status = NOT_RUN`; `hardware_qualification =
  NOT_PERFORMED`; `physical_applicability = INDETERMINATE`.
- No checker receipt (G0 checker unimplemented per the dispatch).
- Unresolved finding: `plateau_v` gap (above). No source or tool failures.

## 7. Next observation

Measure the assembled VGS at the Kelvin-source pin at the 18 V bias to obtain
the real Miller plateau; alternatively obtain it from Infineon's M1 simulation
model or app note AN_1907_PL52_1911_144109.

## 8. Accounting

- Wall time ≈ 281 s; solver invocations 0/0; deadline 2026-09-17T22:30:00Z met.
- Touched files: this attempt directory only (`raw/`, `inputs.json`,
  `result.json`, `REPORT.md`, `manifest.json`). No commit, no stash, no model,
  CAD or BOM edits.
