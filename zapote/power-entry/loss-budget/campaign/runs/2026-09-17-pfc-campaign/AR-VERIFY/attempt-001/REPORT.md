# AR-VERIFY attempt-001 — bounded engineering verification of the TEA2209T + IPW60R017C7 candidate

Task ID: **AR-VERIFY** · Attempt: **attempt-001** · Campaign: 2026-09-17-pfc-campaign · Kind: engineering_verification.
Contract C1.1 `0accd9bc…a825d6` (matches dispatch). Dispatch `source_revision` `d94b2b8f0…`;
HEAD `ecc52f3f6…` is that commit plus the coordinator's own "correct the receipt / add AR-VERIFY" commit.
Source-and-arithmetic only, so the delta cannot affect a number.

**Hypothesis / actual changed variable.** The candidate survives correction, but only as conditional
values: the four downgraded claims are fixed, the gate correction is re-derived per point and comes out
smaller than the assumed constant, and the voltage rating stays conditional on an assumed MOV clamp.
Changed variables: (i) per-device power stated over four devices; (ii) the worst-bracket saving stated at
23 W; (iii) `F_VGS_HS`/`F_VGS_LS` replaced by a per-point Rds(VGS) ratio; (iv) recovery relabelled a
sensitivity; (v) the voltage table replaced by a terminal-voltage derivation; (vi) the bootstrap
capacitor justified from its operating corners.

## 1. The four downgraded claims, corrected

| Claim | Superseded | Corrected (label) |
|---|---|---|
| (a) per-device thermal power | 3.91 W | **1.9501 W** at the computed hot Rds, `0.5·R·I_rms²` over **four** devices (typical) |
| (b) 98 % saving at the worst bracket (23 W) | ~26 W | **14.05 W** — the ~26 W was the **best** bracket point (35 W) |
| (c) `F_VGS_HS = 1.020` assumed / `F_VGS_LS = 1.00` invalid | constants | **derived per point**: HS 1.0088 (8.49 V), 1.0141 (7.59 V), 1.0291 (6.31 V); LS 0.99955 (10.41 V) … 1.00262 (9.55 V) |
| (d) 43 mW recovery "upper bound" | `E_RR_UB` | **sensitivity** (typical Qrr × assumed 20 V residual) |
| (e) voltage table | mixed controller limit and device requirement | MOSFET rating from the **surge-clamped terminal voltage**; controller stress separately from the **same terminal voltages** vs its own limits |

(a) follows from 225·(R_HS+R_LS) = 7.764 W total over four devices; each device conducts half the line
cycle, so each averages 0.5·R·I_rms². (b) is the same bracket arithmetic with the correct endpoint;
AR-DESIGN's 13.98 W refines to **14.05 W** once the per-point Rds is used. The coordinator's ~1.95 W
per-device figure is confirmed (1.9501 W typical).

## 2. Bootstrap operating corners (charge / discharge / leakage / droop)

Base constants from the captured TEA2209T Rev 1.1 (Table 8, Sec 12): `VCC/Vregd` 10.2/10.7/11.2 V;
`Vd(bs)` 0.8/1.0/1.3 V; `II(VCCHL)` 4/7/12 µA at `VL = 200 V`; floating-supply UVLO max 5.0 V; bootstrap
range 100–220 nF. Device `Qg = 240 nC` is **typical only** (no maximum published). `T_on = 8.333 ms`.

| Cbs | HS VGS typ | HS VGS conditional worst (guaranteed VCC/Vd/leak, **typical Qg**) | leakage droop (bound) |
|---:|---:|---:|---:|
| 100 nF | 7.302 V | 6.305 V | ≤ 1.000 V |
| 200 nF | 8.382 V | 7.474 V | ≤ 0.500 V |
| **220 nF** | **8.491 V** | **7.592 V** | **≤ 0.455 V** |

- **Worst-case gate voltage: 7.592 V with 220 nF — CONDITIONAL, not a bound.** VCC ≥ 10.2 V, Vd ≤ 1.3 V
  and leakage ≤ 12 µA are guaranteed maxima; the Qg/Cbs term multiplies a **typical** Qg, so it cannot be
  bounded. Bound only what is boundable: leakage droop ≤ 0.455 V, Vd ≤ 1.3 V, VCC ≥ 10.2 V.
- **Low side:** VGS = VCC − (2·Qg + I_bias·T_on)/CVCC = 10.406 V typ, **9.906 V min** (2.2 µF), 9.553 V
  (1.0 µF). The 1.00 factor was invalid at the minimum; the derived ratio is 1.00055 there — small but nonzero.
- **Chosen capacitor: 220 nF.** Top of NXP's range and essentially its 200 nF typical configuration.
  It halves the guaranteed leakage droop and lifts the conditional worst case above the ~7 V
  near-full-enhancement knee. This is a **robustness** choice, not proof that 100 nF fails: typical Qg
  needs ~2.2× (100 nF) or ~5.8× (220 nF) to reach the 5.0 V UVLO. Recharge is not binding (RC ≪ half-cycle).
- **Unbounded term:** the internal bootstrap diode's **reverse leakage while it blocks the line** is not
  specified in the captured datasheet; it would add discharge and is not bounded.

## 3. Per-point Rds(on) from the digitised Rds(VGS) curve

`Rds(Tj,VGS) = Rds10(Tj) · [Rds(VGS)/Rds(10 V)]`, where the ratio is the digitised **Diagram 7** family at
ID = 30 A, Tj = 125 °C (5.5/6/6.5/7/10/20 V → 1.054/1.035/1.025/1.018/1.000/0.989). **Assumption:** the
ratio is temperature-independent over the 45–51 °C range (Diagram 7 is published only at 125 °C) — labelled,
not derived. The ID = 21/15 rows digitised only five strokes (merged curves); they are carried as a
sensitivity (ratio band ~1.009–1.042 across ID for the points used), not as the primary.

## 4. Surge / protection contract

- **Test level (ASSUMED product contract):** IEC 61000-4-5, **1 kV L–L / 2 kV L–PE**, 1.2/50 µs–8/20 µs.
  Source: `docs/architecture/induction_curriculum.md:2112`; second source IEC 60335-1 OVC II 1500 V
  (`docs/evidence/2026-08-13-mains-selv-barrier-derivation.md`). This is a checklist item, **not** a
  committed requirement document.
- **Protection circuit:** fuse → **MOV across L–N** → X2 → CMC → Y caps. The main board carries the MOV
  (`V150LA10AP`, 150 V rms MCOV, `docs/hardware/BOM.md:46`); the **power-entry candidate BOM does not** —
  adding it is required for this derivation.
- **Assumed clamp:** `V_clamp ≈ 400 V`. Both capture attempts for the LA-series datasheet returned
  **HTTP 403** (retained in `raw/capture_failures.json`); the repo's own audit also marks the part
  UNVERIFIED. What would settle it: a captured V–I/clamp curve at 8/20 µs, or a measured clamp.
- **MOSFET required rating:** from the terminal voltage it must block = `V_clamp ≈ 400 V` (1.5× on a 600 V
  device). Steady line peak is 186.7 V (3.2×); a boost-switch-short bus fault is ~586.7 V (1.02×, marginal).
- **Controller node stresses:** L/R/VR see the **same MOV-clamped ~400 V** against their own 440 V
  operating limit (and 700 V transient). **A higher-rated MOSFET does not lower that node voltage, and the
  controller's 700 V limit does not force an 800/1000 V device.** L–PE common mode is not clamped by the
  L–N MOV and is INDETERMINATE.
- **Retained-BOM variant:** without a MOV the terminal voltage is INDETERMINATE → no rating derivable.

## 5. Revised result

`P_saved = P_bridge − 225·(R_HS + R_LS) − P_additional`, `P_additional = 2.547 mW` (IC 2 mW + gate 0.544 mW
+ dead-time bound 2.7 µW):

| Basis (label) | @23 W | @28.30 W | @35 W |
|---|---:|---:|---:|
| **typical** | **15.23 W** | **20.54 W** | **27.23 W** |
| 98 % curve (**percentile**, not a max) | 14.05 W | 19.36 W | 26.05 W |
| typical, conditional worst gate | 15.21 W | 20.51 W | 27.21 W |
| 98 % + conditional worst gate | 14.02 W | 19.33 W | 26.02 W |

Previous nominal 20.48 W → revised **20.54 W**. Per-device power 1.95 W typ / 2.25 W (98 %); Tj 45.4 °C typ,
46.2 °C (98 %), 50.6 °C at the Rcs = Rsa = 1.0 K/W contact corner. **Residual uncertainty:** `P_saved` is an
**upper-side** estimate — the 43 mW recovery sensitivity, inrush and EMI losses are unknown and are **not
subtracted**; the device basis is typical (no guaranteed hot max); and the whole result is gated by the
assumed MOV clamp. A concluded smaller-or-conditional saving is accepted; the ~20.5 W figure is not protected.

## 6. Accounting

- Case census: expected 1; attempted 1; **valid 1**; failed 0; unsupported 0; unrun 0.
- Controls reproduced: 23–35 W bracket, I_rms 15 A, reference IPW60R017C7; the digitised Diagram 8
  reproduces the p.5 table (0.01517 vs 0.015 at 25 °C; 0.03363 vs 0.033 at 145 °C).
- **Checker:** `not_applicable` by dispatch (G0 unimplemented) → **no checker receipt**; per ADMISSION.md
  this is **not a validated run** and is retained as evidence only.
- Unresolved findings: (a) MOV clamp uncaptured → voltage rating conditional; (b) Qg has no maximum →
  bootstrap worst case conditional; (c) slow reference body diode (Qrr 18 µC); (d) inrush/EMI unknown;
  (e) no guaranteed hot Rds max; (f) L–PE common-mode stress indeterminate; (g) the product's released
  surge test level is not a committed requirement (curriculum checklist only), and the requirements doc's
  "MOV 275 V" conflicts with the committed 150 V MCOV part.
- Evidence pointers: `raw/compute_ar_verify.py`, `raw/compute_result.json`, `inputs.json`, `result.json`,
  `raw/capture_failures.json`, `raw/reused_sources/` (both datasheets, digitisation, figures).
- Solver invocations 0; model/CAD/BOM edits 0; bench work none; primary sources reused 2; capture
  attempts this attempt 2 (both failed, retained). Touched files: only this attempt directory.
  No commits, no stash. Wall time ≈ 25 min; handback well before `2026-09-18T06:43:31Z`.
- **Recommended next observation:** capture or measure the `V150LA10AP` clamp voltage at the 8/20 µs surge,
  then re-run the terminal-voltage derivation. That single number moves the 600 V device from
  "adequate with margin" to "insufficient" or confirms it.

---

**The single most important missing input:** the **MOV's clamp voltage at the specified surge waveform** —
a captured `V150LA10AP` LA-series 8/20 µs V–I characteristic, or a measured clamp. It is the one
terminal-voltage number from which both the MOSFET's required rating and the controller's node stress are
derived, and it is currently assumed at ~400 V because both capture attempts returned HTTP 403.
