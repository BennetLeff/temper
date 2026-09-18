# Rectifier alternative net savings — what precision changes a decision

Date: 2026-09-17
Source: committed candidate screen output
(`zapote/packages/zapote-harness/tests/rectifier_alternatives_probe.rs`,
`zapote/packages/zapote-harness/src/pfc_candidates.rs`). No new model; every
number below is a term the retained screen already computes.

## 1. Why this exists

The bridge loss-pinning plan's bar was "pinned tightly enough to rank
rectifier architectures". That phrasing hides the real question: **which
architectures, and would measuring the bridge actually separate them?** This
note answers that by comparing the *achievable net saving* of each alternative —
its gross loss reduction less the losses and complexity it adds.

## 2. Committed bridge terms at C1 nominal (120 V)

| Term | Value |
| --- | ---: |
| Passive bridge drop, 2 elements at 1.05 V | **28.30 W** |
| Sensitivity to per-element forward drop | **26.96 W per volt** (2.70 W per 0.1 V) |
| Rectified mean line current (implied) | 13.48 A |
| Active-rectifier conduction, 50 mΩ/device, 25 °C | 22.50 W |
| Active-rectifier conduction, 100 mΩ/device, assumed hot | 45.00 W |
| Active-rectifier break-even per-device Rds(on) | **62.9 mΩ** |
| Parallel-bridge slope term, one bridge / two sharing | 450 / 225 W per ohm of element slope |

## 3. Net saving per alternative

| Alternative | Gross saving | What it adds | Net saving | Deciding input |
| --- | --- | --- | --- | --- |
| **Keep the GBJ as-is** | 0 | — | **0** | — |
| **Lower-drop passive bridge** | 26.96 W per volt of per-element drop cut: **1.35 W at −0.05 V, 2.70 W at −0.10 V** | a part change only; no drive, no control | **~1–3 W** | the candidate part's `V_F(I, T)` on the same basis as the incumbent's |
| **Parallel passive bridges** | **0 W** under the constant-drop datum; 225 W per ohm of element slope if the slope is real: **1.1 W at 5 mΩ, 4.5 W at 20 mΩ** | a second bridge, a second thermal path, unverified current sharing | **~0–4.5 W, unproven** | the element's forward slope and measured sharing |
| **Active / synchronous rectification** | bridge drop replaced by conduction: **+5.80 W at 50 mΩ**, **−16.70 W at 100 mΩ** | gate drive, rail generation, control, current sensing, dead time, fail-off, EMI | **−16.7 W to +5.8 W** | the **hot Rds(on) curve** — the screen reports a 62.9 mΩ break-even and the datum carries neither the hot curve nor a max |
| **Bridgeless** | the same conduction lever as active rectification — the drop is replaced by switch conduction, not removed | the active-rectifier additions plus common-mode and line-polarity control | **≈ active rectifier's, at materially higher complexity** | same hot Rds(on) curve, plus a topology model that does not exist |

Two corrections to the intuition this analysis started with:

- **The bridge's 28.30 W is not the reducible prize.** For every passive
  alternative the reducible amount is 0–4.5 W. Only active rectification has a
  large lever, and its sign depends entirely on a curve the datum lacks.
- **Bridgeless does not save the bridge drop.** It replaces a diode drop with
  switch conduction, so its gross saving is bounded the same way active
  rectification's is — not by the 28.30 W.

## 4. What precision actually changes a decision

| Decision | Precision needed | Is it obtainable? |
| --- | --- | --- |
| Keep GBJ vs a lower-drop passive part | ~0.05–0.10 V per element (1.3–2.7 W) | Yes, by DC bench sweep — but **only if the candidate part is characterized too**, on the same basis and at the same temperature |
| Keep GBJ vs parallel bridges | the element slope and measured sharing | Not by a single-device sweep; needs a sharing measurement |
| Passive vs active/synchronous | **not a forward-drop question at all** — it is the hot Rds(on) curve against a 62.9 mΩ break-even | No: the curve is absent from the retained datum |
| Bridge ordering vs the switching term | ~1.5 W, i.e. ~0.055 V | **Not meaningful** — the switching term's own uncertainty is larger than that, so no bridge precision settles it |

The last row is the plan's revised R10, confirmed numerically: a bridge
measurement precise to 0.055 V would still not order the bridge against the
switch, because the switching term is uncertain by more than the gap.

## 5. Conclusion — the measurement changes a decision only under a condition

Pinning the incumbent bridge's forward drop is **necessary but not sufficient**.
It tells you the size of the passive prize (1–4.5 W across the passive
alternatives). It cannot by itself capture that prize, because every passive
saving is a *difference between two parts' curves*, and it cannot touch the one
large lever (active rectification), which is gated on the hot Rds(on) curve.

So the condition on "does the measurement change a decision" is:

- **Yes**, if a specific candidate bridge part is named and characterized on the
  same basis — then the 1–3 W passive comparison becomes decidable, and the
  precision target is ~0.05 V per element.
- **No**, if the incumbent is characterized alone — the output is the size of a
  prize no alternative has yet been shown to win, and the screen's own
  conservative output already brackets it (23–35 W) tightly enough for that.
- **Not applicable**, for the active/synchronous and bridgeless decisions, which
  need the hot Rds(on) curve instead. That is a different input, cheaply
  identified and currently absent, and it is the one that gates the largest
  lever.

**Recommendation:** before commissioning any bridge V_F measurement, name the
candidate passive part. If none exists, the higher-value next input is the hot
Rds(on) curve for the active-rectifier screen, not bridge forward-drop
precision.

## 6. Limits of this note

- Every number is the retained screen's; none is measured. The screen is
  source-bound but derived from a single forward-drop test point, which is the
  defect the plan exists to fix.
- "What it adds" is qualitative. Gate drive, control, sensing and EMI for active
  rectification are named but not estimated; they are the reason its net saving
  is stated as a range rather than a number.
- The passive alternatives assume the candidate part is used in the same
  position with the same thermal path. A different package changes the thermal
  picture, which is the GBJ study's scope, not this note's.
