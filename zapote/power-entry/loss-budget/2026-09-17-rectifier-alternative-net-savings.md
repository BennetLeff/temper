# Rectifier alternative net savings — what precision changes a decision

Date: 2026-09-17 (revised)
Source: committed candidate screen output
(`zapote/packages/zapote-harness/tests/rectifier_alternatives_probe.rs`,
`zapote/packages/zapote-harness/src/pfc_candidates.rs`). No new model; every
number below is a term the retained screen already computes.

**Revision note.** The first version of this note called several
conduction-only deltas "net savings", treated two evaluated assumptions as the
design space, and asserted a bridgeless result without a current-path model.
Those are corrected below. The screen supports narrower conclusions than it
first did.

## 1. Why this exists

The bridge loss-pinning plan's bar was "pinned tightly enough to rank
rectifier architectures". That phrasing hides the real question: **which
architectures, and would measuring the bridge actually separate them?** This
note asks what the committed screen can actually say about that.

## 2. Committed bridge terms at C1 nominal (120 V)

| Term | Value |
| --- | ---: |
| Passive bridge drop, 2 elements at 1.05 V | **28.30 W** |
| Sensitivity to per-element forward drop | **26.96 W per volt** (2.70 W per 0.1 V) |
| Rectified mean line current (implied) | 13.48 A |
| Conducting devices in the line path | 2 |
| Conduction coefficient, 2 devices | **450 W per ohm** of per-device Rds(on) |
| Active-rectifier conduction, **50 mΩ/device, 25 °C max** | 22.50 W |
| Active-rectifier conduction, **100 mΩ/device, assumed hot** | 45.00 W |
| Active-rectifier break-even per-device Rds(on) | **62.9 mΩ** |
| Parallel-bridge slope term, one bridge / two sharing | 450 / 225 W per ohm of element slope |

50 mΩ and 100 mΩ are **the screen's two evaluated assumptions**, not the
available design space. Nothing in this note bounds what active rectification
could achieve with a different device.

## 3. The governing relation

For the screen's assumed two conducting switches:

```
P_saved = P_bridge − 450 · R_hot − P_additional
```

- `P_bridge` is the passive drop term, itself uncertain across the retained
  1.05 V test point — the committed bracket is **23–35 W** (the 0.85/1.30 V band).
- `R_hot` is the **per-device hot** Rds(on). The retained datum carries a 25 °C
  maximum and an assumed hot value; it carries neither a hot curve nor a device
  choice.
- `P_additional` covers gate drive, rail generation, control, current sensing,
  dead time, fail-off and EMI. **None of it is quantified here.**

**Nominal conduction-only break-even:** `R_hot = 28.30 / 450 = 62.9 mΩ`.
**Across the bridge bracket, before additional losses: 51–78 mΩ**
(23/450 = 51.1 mΩ; 35/450 = 77.8 mΩ). `P_additional > 0` moves the break-even
down, i.e. a real design must beat 51–78 mΩ, not 62.9 mΩ.

## 4. What each alternative's numbers actually support

| Alternative | What the screen supports | What it does **not** support |
| --- | --- | --- |
| **Keep the GBJ as-is** | the reference: 28.30 W nominal, 23–35 W across the retained band | — |
| **Lower-drop passive bridge** | a **conditional** sensitivity: 26.96 W per volt of per-element drop cut. At an assumed −0.05 / −0.10 V this is 1.35 / 2.70 W | a demonstrated ceiling. The value is conditional on the assumed ΔV, and no candidate part has been named or characterized |
| **Parallel passive bridges** | 0 W difference under the constant-drop datum; a **conditional** slope sensitivity of 225 W per ohm of element slope | a demonstrated saving. The public slope value is unverified and current sharing is unmeasured |
| **Active / synchronous** | a **conduction-only** delta: +5.80 W at 50 mΩ/device, −16.70 W at 100 mΩ/device, against a 62.9 mΩ nominal break-even | net saving, or a bound on what active rectification could achieve. The two Rds values are evaluated assumptions; `P_additional` is entirely unquantified |
| **Bridgeless** | nothing quantitative | **unmodeled.** It has a different current path from the active-bridge screen, so the active calculation cannot establish or bound its savings. It needs its own current-path model |

Three corrections to the previous version, stated plainly:

- **The active-rectifier range is a conduction-only difference.** It excludes
  driver, control and commutation losses, so it is not a net saving and must not
  be read as one.
- **The 50–100 mΩ span is two assumptions, not a design space.** It cannot bound
  the opportunity in either direction.
- **The passive 0–4.5 W span is conditional** on the chosen drop and slope
  assumptions, not a demonstrated ceiling across all passive alternatives.

## 5. What precision actually changes a decision

| Decision | Deciding input | Status |
| --- | --- | --- |
| Keep GBJ vs a lower-drop passive part | **two** parts' `V_F(I, T)` on the same basis | no candidate part named |
| Keep GBJ vs parallel bridges | element slope + measured sharing | slope unverified, sharing unmeasured |
| Passive vs active/synchronous | `R_hot` per device for a **chosen** device, plus `P_additional`, against 51–78 mΩ | no circuit, no device, no hot data |
| Bridge ordering vs the switching term | ~0.055 V | **not meaningful** — the switching term's uncertainty exceeds the gap, so no bridge precision settles it |

Forward-drop uncertainty still matters here: it sets `P_bridge`, hence the
break-even. But it is not automatically the binding input — **a sufficiently
favorable candidate device could put `R_hot` far enough below the break-even
that precise bridge measurement is unnecessary to make the decision.**

## 6. The useful next assignment

The screen cannot answer whether there is an opportunity, because no concrete
active-rectifier alternative has been specified. The assignment that would:

1. **Choose one specific active-rectifier circuit** — a named topology and a
   named controller.
2. **Choose the exact MOSFET candidates** — real order codes, package and pinout
   (a Kelvin-source part changes the drive picture).
3. **Obtain their applicable hot Rds(on) data** — at the actual junction
   temperature and gate bias, from primary sources, not a 25 °C maximum.
4. **Quantify `P_additional`** — gate drive and rail generation, controller
   supply, current sensing, dead time and fail-off, and the EMI re-assessment
   obligation.
5. **Compare across the existing bridge bracket**, i.e. against 51–78 mΩ rather
   than a single 62.9 mΩ point.

That establishes whether a worthwhile opportunity exists **before** any
measurement is commissioned. Until those concrete comparisons exist, the
broader architecture search stays open, and the passive alternatives stay
conditional.

## 7. Limits of this note

- Every number is the retained screen's; none is measured. The screen is
  source-bound but derived from a single forward-drop test point, which is the
  defect the plan exists to fix.
- `P_additional` is named but not estimated. It is the reason the active
  alternative is stated as a conduction-only delta rather than a range of net
  savings.
- The passive alternatives assume the candidate part sits in the same position
  with the same thermal path. A different package changes the thermal picture,
  which is the GBJ study's scope, not this note's.
- Nothing here models bridgeless.
