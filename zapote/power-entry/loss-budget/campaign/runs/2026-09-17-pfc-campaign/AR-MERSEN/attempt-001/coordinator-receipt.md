# Coordinator receipt — AR-MERSEN attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** The envelope is now mapped onto the
best-supported reading of the manufacturer conditions, and **coordination remains
unestablished**, correctly.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`). Evidence ledger passing (23 claims, 4 protection claims,
2 promotions), 31 files hash-verified. Both checkers run, both negative controls
fail as designed.

## The applicable condition

**890 VDC** for capacitor-discharge applications (A70QS French Cylindrical,
catalogue p.20 / HS 20). The capacitor-discharge sentence states a limit of
**2.5 ms time constant**, which we read as `L/R` — but that reading is
**supported by context, not established by the capacitor-discharge passage
itself.**

The basis for reading it as `L/R`: the catalogue's DC tables state
`*Time Constant: L/R ≤ 1ms`, and the A70QS page uses `L/R ≤ 10 ms` and
`10 ms time constant` interchangeably. What that does **not** do is define the
time constant *inside the capacitor-discharge sentence itself* — those `L/R`
statements concern the general DC ratings and other product lines. So `L/R` is
the **best-supported interpretation**, not a manufacturer-confirmed definition of
this condition, and the receipt must not claim the stronger thing.

What is established regardless: **`R·C` is not the manufacturer's time
constant**, because no part of the catalogue defines it that way. The candidate
condition to confirm with the manufacturer is `890 VDC, L/R ≤ 2.5 ms`; the
700 VDC / `L/R ≤ 10 ms` figure on the same page is the general DC rating, and the
1 ms figures belong to other product lines.

## A number of the coordinator's, corrected

The AR-COORD receipt quoted a 714x gap between the two readings. That compared
**`2L/R`** against `R·C`. With the time constant read (by context) as **`L/R`**,
the relevant ratio is **357x** (4.000 ms against 11.20 µs). The conclusion is
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
- Voltage passes everywhere. Peak passes (`max 55.23 kA`) — but only against the
  **general 100 kA DC rating**, which is a different condition from capacitor
  discharge.

**142 of 400 cells pass the selected screens: `{400·L ≤ R ≤ 0.64013 Ω}`.** They
are **not qualified operating points.** The capacitor-discharge current limit is
recorded as **unknown**, and the screens used a general DC figure in its place;
that unknown remains an **unresolved gate**, not a passed one.

The cell count is still the finding, because it corrects a mapping error: under
the withdrawn `R·C` reading all 144 action-met cells would have been admitted, so
the error would have passed two cells that the real (best-supported) condition
excludes.

This is a **conditional model-screen intersection, not a board location, and not
coordination.** The real discharge occupies one unknown cell in it.

## Clearing: not demonstrated for any candidate

**A70QS50-14F** has a class condition that some cells pass, but **no
DC/capacitor-discharge let-through I²t is published** (only 1500 A²s at 700 VAC),
and the bank/copper withstand I²t is unsourced. **FWP** candidates have no
capacitor-discharge condition at all — a mapping that is **undefined, not
empty**, which is worth distinguishing: absence of a stated condition is not
evidence of failure.

Completion stays at **`part_selected`**. It was not promoted.

## Gating inputs, and why no further sweep closes them

The remaining unknowns are **manufacturer application conditions**, not
computational ones. Another envelope sweep cannot supply them, and no additional
harness capability is needed for this step.

1. **A manufacturer application review for A70QS50-14F** — the primary route. It
   must ask, with the bank energy and the R–L envelope supplied: does the
   capacitor-discharge time constant mean `L/R` or something else; what current
   limit applies *to capacitor discharge* (as distinct from the general 100 kA DC
   rating); the minimum breaking current in this application; and any
   capacitor-discharge let-through or clearing evidence.
2. **Defensible bounds for the board's high-current R and L** at the fault —
   U9/U10 short residual, bank ESR at discharge frequency, fuse resistance,
   layout — developed alongside the packet so the questions carry real numbers
   rather than a bare range. They decide **which cell the real discharge
   occupies**, and so whether it lands in the screened region at all.
3. **A sourced bank/copper withstand I²t.** With (1)'s let-through figure, this is
   what would let "clears" stop being null.

A capacitor-discharge-specific peak-current limit, the candidate's MBC, and
startup/inrush plus temperature-derated ampacity ride along in the same request.

## Milestone

**A candidate with relevant manufacturer guidance and a reproducible conditional
screen; coordination unestablished.** The nominal RMS comparison stands as a
screening result with startup and derating open. F2 remains a proposal and is not
in CAD or BOM.
