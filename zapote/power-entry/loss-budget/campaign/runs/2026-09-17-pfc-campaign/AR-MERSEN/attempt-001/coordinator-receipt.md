# Coordinator receipt — AR-MERSEN attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** The envelope is now mapped onto the real
manufacturer conditions, and **coordination remains unestablished**, correctly.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`). Evidence ledger passing (23 claims, 4 protection claims,
2 promotions), 31 files hash-verified. Both checkers run, both negative controls
fail as designed.

## The applicable condition

**890 VDC, `L/R ≤ 2.5 ms`** for capacitor-discharge applications (A70QS French
Cylindrical, catalogue p.20 / HS 20).

The basis is the catalogue's own definition: its DC tables state
`*Time Constant: L/R ≤ 1ms`, and the A70QS page uses `L/R ≤ 10 ms` and
`10 ms time constant` interchangeably. The sentence explicitly scoped to
capacitor discharge is the 890 VDC one; the 700 VDC / `L/R ≤ 10 ms` figure on the
same page is the general DC rating, and the 1 ms figures belong to other product
lines. **`R·C` is not the manufacturer's time constant.**

## A number of the coordinator's, corrected

The AR-COORD receipt quoted a 714x gap between the two readings. That compared
**`2L/R`** against `R·C`. With the definition now confirmed as **`L/R`**, the
relevant ratio is **357x** (4.000 ms against 11.20 µs). The conclusion is
unchanged — `R·C` was the wrong quantity — but the figure is corrected, and the
AR-COORD receipt now records the resolution rather than an open ambiguity.

## The joint mapping

Melt and clear cannot be screened on the same axis: the pre-arcing **action** is
L-independent (`E/R`), while the manufacturer's **condition** is L-dependent
(`L/R`). Evaluated jointly, with `V ≤ 890 V` and `peak ≤ 100 kA`:

- Action screen met (`E/R ≥ 280 A²s`, the catalogue's maximum pre-arcing figure):
  `R ≤ 0.64013 Ω` — 144 cells.
- Of those, **2 fail** the `L/R ≤ 2.5 ms` condition: `(R = 5 mΩ,
  L = 12.62 µH)` at 2.52 ms and `(R = 5 mΩ, L = 20 µH)` at 4.00 ms.
- Voltage and peak pass everywhere (max 55.23 kA < 100 kA).

**142 of 400 cells qualify: `{400·L ≤ R ≤ 0.64013 Ω}`**, and the cell count is the
finding. Under the withdrawn `R·C` reading all 144 action-met cells would have
been admitted, so the mapping error was not cosmetic — it would have qualified
two cells that the real condition excludes.

This is a **model-screen intersection, not a board location, and not
coordination.** The real discharge occupies one unknown cell in it.

## Clearing: not demonstrated for any candidate

**A70QS50-14F** has a class condition and some cells meet it, but **no
DC/capacitor-discharge let-through I²t is published** (only 1500 A²s at 700 VAC),
and the bank/copper withstand I²t is unsourced. **FWP** candidates have no
capacitor-discharge condition at all — a mapping that is **undefined, not
empty**, which is worth distinguishing: absence of a stated condition is not
evidence of failure.

Completion stays at **`part_selected`**. It was not promoted.

## Gating inputs, in order

1. **The internal discharge loop's high-current R and L** at the fault — U9/U10
   short residual, bank ESR at discharge frequency, fuse resistance, layout. It
   decides **which cell the real discharge occupies**, and so whether it lands in
   the qualifying region at all.
2. A **DC/capacitor-discharge let-through I²t** for the exact candidate, and a
   sourced **bank/copper withstand I²t** — without both, "clears" stays null.
3. A capacitor-discharge-specific **peak-current limit** and the candidate's
   MBC; startup/inrush and temperature-derated ampacity.

## Milestone

**Candidate comparison completed; coordination unestablished.** The nominal RMS
comparison stands as a screening result with startup and derating open. F2
remains a proposal and is not in CAD or BOM.
