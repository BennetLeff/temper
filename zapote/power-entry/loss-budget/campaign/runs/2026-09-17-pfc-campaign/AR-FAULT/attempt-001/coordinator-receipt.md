# Coordinator receipt — AR-FAULT attempt-001 (corrected)

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-FAULT/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL, with one modelling claim withdrawn.** The
586.7 V refutation stands; the discharge distribution does not.

**This receipt supersedes the first version, which claimed a discharge
distribution the retained netlist does not support.**

## 1. Admission

- Dispatch: **ADMITTED**.
- Handback: **NOT COUNTED AS A VALIDATED RUN** — no checker issued, per
  `ADMISSION.md`.

## 2. Withdrawn: the discharge distribution

The first receipt reported **~34 J into the shunt, ~7.7 kA peak and τ ≈ 116 µs**.
All three are **withdrawn**. The retained netlist evidence shows the current-sense
shunt **U12 is not in the internal discharge loop**:

| Element | Nets | Terminals on the loop |
| --- | --- | --- |
| U12 (shunt) | `PFC_BUS_MINUS`, `minus` | **1** — cannot conduct in the loop |
| U9 (switch) | `PFC_BUS_MINUS`, `a1`, `q_boost-g` | 2 power terminals |
| U10 (boost diode) | `PFC_BUS_PLUS_390V`, `a1` | 2 |
| U36-U40, U52 (caps) | `PFC_BUS_PLUS_390V`, `PFC_BUS_MINUS` | 2 |

U9's source and the capacitor negatives share `PFC_BUS_MINUS`, so the loop is
**capacitors → shorted U10 → U9 → capacitors**, bypassing U12. The shunt sits
between `PFC_BUS_MINUS` and the bridge return (`minus`), which the loop never
reaches. A model that puts current in the shunt is a **wiring error, not a
tolerance**.

**What survives:**

- **179.24 J stored** in the 2240.47 µF bank at 400 V. Unchanged.
- The refutation of 586.7 V. Unchanged.
- The internal loop's **existence** and the fact that **nothing on the board
  interrupts it**. Unchanged.
- The **distribution** of that energy: **null, requiring a corrected model.**

## 3. F1's data is available, and it does not close interruption

Schurter publishes for the 0034.3129: **1,638 A²s typical melting I²t at 10×
rated current**, and **160 A breaking capacity at 250 VAC**. These do **not**
establish safe interruption of this fault's prospective currents. Coordination
needs **total clearing behaviour at matching test conditions** — not a direct
comparison of unmatched I²t figures, and not a melting I²t against a breaking
current.

Interruption therefore remains **unclosed**: F1 is in the line-fed loop, its
coordination is unestablished, and the internal loop has no interrupting element
at all.

## 4. The 350 A / 510 A²s figures cannot qualify the active bridge

Those are the **GBJ passive bridge's** survival ratings. The proposed active
bridge is a different device with a different fault path, so it needs **its own
fault-path and device-survival assessment**. Using the passive part's ratings to
qualify its replacement is exactly the substitution this campaign keeps catching.

## 5. OCP, a crowbar and a fuse are not interchangeable

- **Gate shutdown cannot interrupt a transistor that has already failed short.**
- A **crowbar** needs a coordinated interruption or energy-handling path; it is
  not self-sufficient.
- The **existing shunt cannot directly sense the internal discharge loop** — see
  §2. A protection scheme that depends on it would be blind to this fault.

Any recommendation must name which of these is proposed and why it can act on
*this* loop.

## 6. Status of the voltage conclusion

**600 V remains a candidate rating, not a completed qualification.** The
refutation removes the 586.7 V driver, but qualification still depends on the
single-fault blocking case, the protection design, and the coordination above.

Line impedance is **not the sole remaining input**; so are F1's total clearing
behaviour, the active bridge's own survival ratings, and the internal loop's
interruption method.

## 7. Enforcement added

`zapote/tools/check_fault_loop.py` (6 tests) rejects a discharge model that
assigns current to an element which cannot conduct in the declared loop: an
element qualifies only when at least two of its terminals lie on the loop's nets.
Run against the real netlist and the erroneous model:

```
FAULT LOOP INCONSISTENT
  - U12 carries 34.0 but only 1 of its terminals ['PFC_BUS_MINUS', 'minus']
    lie on the declared loop ['PFC_BUS_MINUS', 'PFC_BUS_PLUS_390V', 'a1']
```

## 8. Two bounded follow-ups

1. **Corrected fault-loop and protection assessment.** Distribute the 179.24 J
   through the actual loop, establish F1's total clearing behaviour at matching
   conditions, assess the active bridge's own survival, and name a protection
   element that can act on the internal loop.
2. **MOV data capture** against the proposed surge conditions — independent of
   the fault, now unblocked on its own terms.

The ~20 W nominal opportunity is unchanged and still the largest found.
