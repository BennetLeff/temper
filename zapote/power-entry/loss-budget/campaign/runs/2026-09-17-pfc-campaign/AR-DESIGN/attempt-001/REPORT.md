# AR-DESIGN attempt-001 — one complete active-rectifier design assessment

Task ID: **AR-DESIGN** · Attempt: **attempt-001** · Campaign: 2026-09-17-pfc-campaign
Kind: design_assessment (source-only, no solver). Contract C1.1 `0accd9bc…a825d6` (matches dispatch).
Dispatch `source_revision` `f7fbb2138…`; HEAD `416792047e…` is that commit **plus** the coordinator's
own admission-enforcement commit. Source-only, so the delta cannot affect any number (recorded in
`inputs.json`).

**Hypothesis / actual changed variable.** A concrete TEA2209T four-MOSFET active bridge, with its
*real* (bootstrap-derived) gate bias and a *computed* junction temperature, beats the passive bridge
across the 23–35 W bracket. The changed variables versus `AR-ACTIVE`: (i) high-side VGS is derived,
not assumed to be Vregd; (ii) Rds(on) is corrected for the real VGS **and** the computed Tj, iterated;
(iii) the voltage rating comes from an explicit transient contract; (iv) the conduction coefficient
keeps R_HS and R_LS separate.

## 1. Circuit and controller

- **Controller:** NXP **TEA2209T/1** (SO16), *Active bridge rectifier controller*, Rev. 1.1,
  2021-04-14 (`raw/TEA2209T.pdf`, sha256 `fb611299…`).
- **Circuit:** four-MOSFET synchronous full bridge at the PFC input (replaces the 1000 V GBU2510A);
  AC into L (pin 1) and R (pin 12); upper MOSFETs VR→L/R, lower MOSFETs L/R→GND; downstream CCM boost
  unchanged. **Two** devices conduct in the line path (one high side, one low side of a diagonal pair).
- **High-side gate-drive path (part 1 of the assignment):** the high-side drivers are powered by a
  **floating supply (VCCHL/VCCHR) referenced to the switching node**, charged by a **bootstrap
  capacitor** (NXP typical config 200 nF; range 100–220 nF) from VCC through an **internal bootstrap
  diode, Vd(bs) = 0.8/1.0/1.3 V** (Table 8). The gate is driven rail-to-rail to VCCHL **relative to L/R**.
  The low side is driven directly from VCC against GND. NXP's own warning: *"Bootstrap capacitors with
  lower value may cause a voltage drop that is too high because of the gate charge losses."*

## 2. Gate supply — the first correction

**Vregd (typ 10.7 V, 10.2–11.2) is the regulated VCC rail, not the MOSFET VGS.** Solving
`VGS = (VCC − Vd) − Qg(VGS)/Cbs − I_leak·T_on/Cbs` self-consistently (T_on = 8.333 ms; IPW60R017C7
Qg = 240 nC; II(VCCHL) = 7 µA typ):

| Node | VGS (V) | Basis |
|---|---:|---|
| High side, Cbs = 220 nF | **8.49** | VCC 10.7 − Vd 1.0 − Qg/Cbs − leakage |
| High side, Cbs = 200 nF | 8.39 | NXP typical-configuration value |
| High side, Cbs = 100 nF | 7.31 | datasheet minimum |
| High side, worst case | 6.31 | VCC min, Vd max, Cbs 100 nF, leak max |
| Low side | 10.41 (9.91–10.91) | VCC minus CVCC (2.2 µF) half-cycle droop |

**Is the 10 V data applicable?** Low side: ~yes (VGS ≥ 10 V, slightly conservative). High side: **no**.
Using IPW60R017C7 Diagram 7 (Tj = 125 °C) the correction at ID ≈ 21 A is
**f_VGS_HS = 1.02 (bound 1.00–1.07)** — small because the C7 die is near-fully enhanced above ~7–8 V.
The correction grows if Cbs is sized at 100 nF, so specify Cbs ≈ 220 nF. Evidence class
`derived_from_manufacturer_datasheet_conditions` / `…figure_digitized`. Nothing here is UNKNOWN.

## 3. Voltage stresses — explicit contract and derived rating

Sourced bounds: line 108/120/132 Vrms → **peak 186.68 V at 132 Vrms** (not 170 V); retained bridge
**1000 V** class (GBU2510A in `BOM.md`; GBJ2510-F VRRM 1000 V) with **no surge clamp/MOV declared**;
TEA2209T node limit **440 V operating / 700 V transient** (max 10 min over lifetime).

Derived required rating **as a function of the (undeclared) clamp**:

| Contract variant | Required class |
|---|---:|
| Line only, ×2 margin (186.7×2 = 373 V) | 400 V |
| NXP 700 V node limit binding | 800 V |
| Added clamp limits node to ≤ 500 V | 600 V |
| Retained-bridge-equivalent, no clamp | 1000 V |

**The line range alone does not settle the rating.** The 600 V reference candidate satisfies only the
added-clamp variant, and that clamp is **not in the retained BOM**. **A lower-voltage alternative is not
supported** by any retained variant and was not screened for performance (a representative 500 V-class
part, IPW50R280CE, is named in `inputs.json`; its datasheet capture failed and the failures are retained
in `raw/capture_failures.json`). No rating was assumed.

## 4. Commutation and start-up losses (each with condition + evidence class)

| Term | Value | Evidence class |
|---|---:|---|
| Controller + gate drive | **2.5 mW** | datasheet prose + calculated (line-frequency gate drive) |
| Dead-time body-diode conduction | null, bound 2.7 µW | derived bound (td ≤ 2.5 µs about the zero crossing) |
| Line-commutation reverse recovery | null, **over-bound 43 mW** | unknown; Qrr 18 µC is rated at 58.2 A/400 V, not at the zero crossing |
| Start-up inrush body diode | **null** | unknown (NTC-limited; no capture, no bench) |
| EMI re-qualification | **null** | unknown (obligation) |

No term is zero-filled. Quantified P_additional ≈ **2.5 mW**.

## 5. Coupled thermal estimate — the second correction

Proposed assembly (reusing the selected bridge-cooling concept `thermal/bridge-cooling.md`): Wakefield
395-1AB + 2× Sunon fans + Al spreader + SIL PAD; **Ta = 40 °C** (design inlet), **Rsa = 0.50 K/W**
total (typical catalog @500 LFM), **Rjc = 0.28 K/W max**, **Rcs = 0.50 K/W per device ASSUMED**. Iterating
`T_sink = Ta + P_total·Rsa`, `Tj = T_sink + P·(Rjc+Rcs)`, `Rds(Tj)` from the digitised Diagram 8:

| Basis | T_sink | **Tj** | R_HS | R_LS | P_cond |
|---|---:|---:|---:|---:|---:|
| typical | 43.9 °C | **45.45 °C** | 17.56 mΩ | 17.21 mΩ | 7.82 W |
| 98 % curve (percentile, not a max) | 44.5 °C | 46.29 °C | 20.25 mΩ | 19.84 mΩ | 9.02 W |
| Rcs 1.0, Rsa 1.0 K/W | — | 50.70 °C | 18.16 mΩ | — | 8.09 W |

**Tj is an output, not an input**, and it converges to ~45–51 °C. No typical hot value is presented as
a bound; the 98 % curve is labelled a percentile, and no guaranteed hot maximum exists.

## 6. Comparison across the bracket

`P_saved = P_bridge − 225·(R_HS + R_LS) − P_additional`, i.e. the dispatch's `450·R_hot`
form with **R_hot ≈ 17.4 mΩ/device** (225·(R_HS+R_LS) = 450·R_hot when R_HS = R_LS).

| Basis | @23 W | @28.30 W | @35 W |
|---|---:|---:|---:|
| **typical** | **15.17 W** | **20.48 W** | **27.17 W** |
| 98 % curve | 13.98 W | 19.28 W | 25.98 W |

Effective hot Rds ~17.4 mΩ/device (typ) vs the 51–78 mΩ break-even — a large margin. **Residual
uncertainty:** P_additional beyond ~2.5 mW (inrush, EMI, real recovery) is unknown and subtracts from
every row; the 98 % row shows the device spread; and the **voltage-rating condition gates the whole
result** (no declared clamp).

## 7. Case counts, controls, checker

- Case census: expected 1; attempted 1; **valid 1**; failed 0; unsupported 0; unrun 0.
- Controls reproduced/anchored: 23–35 W bracket, I_rms 15 A, reference IPW60R017C7; the digitised
  Diagram 8 reproduced the p.5 table (0.01517 vs 0.015 at 25 °C; 0.03363 vs 0.033 at 145 °C).
- **Checker:** `not_applicable` by dispatch (G0 unimplemented) → **no checker receipt**; per ADMISSION.md
  this attempt is **not a validated run** and is retained as evidence only.
- Unresolved findings: (a) voltage rating unsupported without a clamp; (b) slow reference body diode
  (Qrr 18 µC) may force a fast-diode device with higher Rds; (c) inrush/EMI unknown; (d) Rcs assumed;
  (e) no guaranteed hot Rds maximum.

## 8. Accounting

- Solver invocations **0**; model/CAD/BOM edits **0**; bench work **none**. Primary sources **2** (+3
  retained AR-ACTIVE captures referenced), capture failures **4 new** in `raw/capture_failures.json`.
- Touched files: only this attempt directory (`raw/`, `inputs.json`, `result.json`, `REPORT.md`,
  `manifest.json`). No commits, no stash.
- Wall time ≈ 20 min. Deadline `2026-09-18T06:26:17Z`; handback well before it.

---

**The single most important missing input:** the product's **real input transient/surge contract** —
the test level and whether a front-end clamp is fitted. It is the one input that decides whether a
600 V-class device may be used at all. The loss result is already robust and favourable (~15–27 W saved
at a computed 45–46 °C junction), but with a 1000 V-class retained bridge and no declared clamp, the
reference candidate's 600 V rating is unsupported and every lower-voltage alternative is excluded.
