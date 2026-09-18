# Coordinator receipt — AR-DESIGN attempt-001 (corrected)

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-DESIGN/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL, with claims downgraded.** Eligible for a
conditional comparison; not hardware acceptance.

**This receipt supersedes the first version, which stated "both corrections
closed" and "only a product decision remains". Both of those were wrong, and two
of the errors were the coordinator's, not the attempt's.** The attempt's script
is in several places better than the receipt that described it.

## 1. Admission

- Dispatch: **ADMITTED**.
- Handback: **NOT COUNTED AS A VALIDATED RUN** — no checker issued, per
  `ADMISSION.md`. Retained as source-and-arithmetic evidence.

## 2. Correction A — the thermal calculation, and the receipt's error

The script is **correct** and shares the heatsink across **four** devices:

```python
P_hs  = 0.5 * R_hs * I2 + p_add_dev / 2.0     # one HS device, half the line cycle
P_tot = 2.0 * (P_hs + P_ls)                   # both diagonals, line-cycle average
```

Each MOSFET consequently averages **≈1.95 W** (0.5 · 0.0172 · 225 = 1.935 W),
not the **3.91 W** the previous receipt claimed. The 3.91 W figure came from
dividing a two-device instantaneous total by two instead of four; it was a
receipt arithmetic error, and the "self-consistent" check built on it was
wrong. The script's own arithmetic closes correctly (4 × 1.935 ≈ 7.74 W total,
Tj ≈ 45.4 °C).

**The "~26 W" claim is also withdrawn.** It quoted the 98 % figure at the *best*
bracket point (35 W) as though it were the worst. The 98 % savings are
**13.98 / 19.28 / 25.98 W** at P_bridge = 23 / 28.30 / 35 W, so the pessimistic
worst-bracket figure is **13.98 W**, not ~26 W.

Both temperatures remain **conditional**: `Rsa` is a catalog value at 500 LFM
(typical, not installed airflow) and `Rcs` is assumed at 0.50 K/W (sensitivity
range 0.25-1.0). At `Rcs = Rsa = 1.0` the computed case rises to ≤50.7 °C.

## 3. Correction B — the gate result is partly assumed

`F_VGS_HS = 1.020` is a **fixed constant** with an asserted interval of
1.00-1.07. The script does not recompute Rds(on) from the `Rds(VGS)` curve at
each calculated gate voltage; it applies one factor. The bootstrap VGS values
themselves are computed and defensible (≈8.5 V typ high side, 6.31 V worst
case), but the *resistance correction* is not derived per point.

Two further limits:

- **Typical charge data cannot establish a worst-case bootstrap bound.** `Qg`
  is a typical value, so the 6.31 V worst case is an illustration, not a bound.
- **The low-side minimum is 9.91 V**, which contradicts the script's own comment
  that "LS VGS ~ VCC (>=10.2 V): 10 V data applies" and its `F_VGS_LS = 1.00`.
  At 9.91 V the 10 V data is slightly optimistic, so the low side is not exempt
  either.

Status: **partly assumed.** The direction is right and the effect is small at
220 nF, but it is not the closed derivation the previous receipt claimed.

## 4. Correction C — recovery is a sensitivity, not an upper bound

```python
E_RR_UB = QRR_TYP * 20.0      # J, assuming 20 V residual (generous)
```

Named `_UB`, but it multiplies a **typical** Qrr by an **assumed** 20 V residual
voltage. Neither is a guaranteed maximum, so the 43 mW figure is a
**sensitivity**, not an upper bound, and it must be labelled and propagated that
way. Its operating value remains unknown.

## 5. Correction D — the voltage table mixed component limits with required stresses

The previous receipt's table implied that the controller's 700 V transient limit
"requires" an 800 V MOSFET. That is a category error in both directions:

- A **component limit** (the controller's node rating) is not a **required
  device rating**. NXP's 700 V transient limit does not by itself force an 800 V
  MOSFET.
- Conversely, selecting higher-voltage MOSFETs does **not** protect the
  controller — the controller's node voltage is set by the circuit, not by the
  MOSFET's rating.

The required MOSFET rating follows from the **specified surge** and the
**protection circuit's resulting terminal voltages**. Both are undeclared, so
the correct statement is: the rating question is open, and the 600 V reference
candidate's validity is contingent on a protection design that has not been
specified.

The attempt's substantive conclusion — that a lower-voltage alternative is not
supported by any retained variant and was therefore not screened — survives.

## 6. What survives, and at what strength

| Claim | Status |
| --- | --- |
| Circuit and controller (TEA2209T/1, four-MOSFET synchronous bridge) | retained |
| Actual VGS ≈ 8.5 V HS / ≈10.4 V LS typ, Vregd is VCC not VGS | retained |
| Conduction saving ≈7.8 W; `P_saved` 15.2 / 20.5 / 27.2 W (typ) | retained as typical |
| `P_saved` 13.98 / 19.28 / 25.98 W (98 % curve) | retained; worst-bracket figure is 13.98 W |
| Tj computed, not assumed | retained, **conditional** on assumed Rcs and catalog airflow |
| Gate correction fully closed | **withdrawn** — partly assumed |
| 43 mW recovery as an upper bound | **withdrawn** — it is a sensitivity |
| 600 V valid only under a ≤500 V clamp | **restated** — depends on an unspecified protection design |
| "Only a product decision remains" | **withdrawn** |

## 7. Next: a bounded engineering verification pass

The ~20 W nominal opportunity justifies this; it does not yet establish a final
saving. The pass should:

1. **Correct the four claims above** in the attempt's own numbers, so the
   retained artifact does not carry superseded statements.
2. **Evaluate the selected bootstrap capacitor's actual operating corners** —
   charge, discharge, leakage and droop across the real VGS range, deriving
   Rds(on) per point rather than applying one factor, and stating a worst-case
   gate voltage with its basis.
3. **Define the surge/protection contract** — the specified test level and the
   protection circuit, from which the MOSFET's required voltage rating and the
   controller's node stresses both follow.
