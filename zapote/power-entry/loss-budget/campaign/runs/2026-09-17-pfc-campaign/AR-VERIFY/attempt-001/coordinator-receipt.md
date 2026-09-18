# Coordinator receipt — AR-VERIFY attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-VERIFY/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** All four downgraded claims corrected; new
findings below are material.

## 1. Admission

- Dispatch: **ADMITTED** (deadline computed at issue time).
- Handback: **NOT COUNTED AS A VALIDATED RUN** — no checker issued, per
  `ADMISSION.md`. Retained as evidence.

## 2. All four corrections verified

| Claim | Corrected |
| --- | --- |
| per-device thermal power | **1.9501 W typ** (2.2468 W on the 98 % curve) over **four** devices; four-device total 7.764 W. The 3.91 W figure is gone. |
| 98 % worst-bracket saving | **14.05 W at P_bridge = 23 W** (was reported as ~26 W, which is the best bracket point at 35 W) |
| gate factor | `F_VGS_HS` is now derived per point from the digitised `Rds(VGS)` curve; `F_VGS_LS = 1.00` is corrected to 1.00055 at the computed low-side minimum |
| recovery | relabelled a **sensitivity** (typical Qrr × assumed 20 V residual), not a bound |
| voltage table | rebuilt: the MOSFET's required rating follows from the surge-clamped **terminal** voltage; the controller's node stress is derived separately against its own limits |

Independent coordinator arithmetic reproduces the result: `0.5·R·I²` = 1.935 W
per device, four-device total 7.74 W, `P_saved` ≈15.3 / 20.6 / 27.3 W typical.

## 3. Bootstrap — conditional, and honestly labelled

The worst-case high-side gate voltage is **7.592 V with 220 nF**, and the
attempt correctly calls it **conditional, not a bound**: VCC ≥ 10.2 V,
Vd(bs) ≤ 1.3 V and leakage ≤ 12 µA are guaranteed maxima, but the `Qg/Cbs` term
multiplies a **typical** Qg (240 nC, no maximum published). Boundable part:
leakage droop ≤ 0.455 V. Low-side minimum is **9.906 V** at 2.2 µF.

**Capacitor: 220 nF.** Chosen for robustness — it halves the guaranteed leakage
droop (1.000 → 0.455 V) and lifts the conditional worst case above the ~7 V
near-full-enhancement knee. The attempt states plainly that this is not a proof
that 100 nF fails (typical Qg would need ~2.2× to reach UVLO). That is the right
shape of claim.

## 4. Surge and protection — the key new finding

The contract is **assumed** (IEC 61000-4-5, 1 kV L–L / 2 kV L–PE) because no
committed requirement document was found. Under it:

- Protection chain: fuse → MOV → X2 → CMC → Y caps.
- **The power-entry candidate BOM has no MOV. That is a required addition**, not
  an existing feature — the main board carries a V150LA10AP but the candidate
  does not.
- **Assumed clamp ≈ 400 V**, because both LA-series capture attempts returned
  HTTP 403 and the failures are retained.
- The MOSFET's 600 V rating follows from the **surge-clamped terminal voltage**
  (~400 V, 1.5×) — correctly *not* from the controller's 700 V limit. The
  controller's own L/R nodes see the same ~400 V against its 440 V operating /
  700 V limits.
- **New risk:** a boost-switch-short bus fault puts ≈586.7 V across the bridge
  device — only **1.02×** margin on a 600 V part. Flagged, not resolved.

## 5. Revised result

`P_saved = P_bridge − 225·(R_HS + R_LS) − 0.002547 W`:

| Basis (label) | @23 W | @28.30 W | @35 W |
| --- | ---: | ---: | ---: |
| typical | 15.23 | **20.54** | 27.23 |
| 98 % curve — a percentile, **not a max** | **14.05** | 19.36 | 26.05 |
| typical + conditional worst gate | 15.21 | 20.51 | 27.21 |
| 98 % + conditional worst gate | 14.02 | 19.33 | 26.02 |

The nominal moved from 20.48 to **20.54 W**, i.e. the corrections did not
disturb the headline. Recovery (43 mW sensitivity), inrush and EMI remain
**unknown and not subtracted**, so the figures are upper-side estimates, not
bounds.

## 6. Single gating input

**The MOV's clamp voltage at the specified 8/20 µs surge.** It is the one
terminal-voltage number that sets *both* the MOSFET's required rating and the
controller's node stress, and it is currently an assumption (~400 V) behind two
403s.

## 7. Residual uncertainties

Unbounded worst-case gate voltage (typical Qg); the internal bootstrap diode's
reverse leakage while blocking the line (unspecified); operating reverse
recovery; start-up inrush; EMI re-qualification; installed Rcs and airflow.

## 8. Next

Two things now gate a final number, and neither is a bridge measurement:

1. **Capture the MOV's clamp characteristic** (or a measured clamp) at the
   specified surge — sets the voltage rating and confirms or moves the 600 V
   choice.
2. **Resolve the boost-switch-short fault case**, where a 600 V device sits at
   1.02× margin.

The ~20 W nominal opportunity is unchanged and remains the largest found. The
bridge `V_F` measurement stays deferred.
