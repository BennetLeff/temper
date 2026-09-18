# Coordinator receipt — AR-COORD attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-COORD/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** Coordination remains **UNESTABLISHED**, which
is the correct outcome and is stated as such.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`). Evidence ledger present, passing (29 claims, 5 protection
claims, 2 promotions), 39 files hash-verified.

## Normal current: RMS, and the margin is large

The worst line is 120 V: boost-diode **RMS = 9.0007 A** (108 V 8.5390 A, 132 V
8.5868 A) from the retained waveform model. Eaton's loss correction is a function
of RMS load current, so RMS is the basis, and the earlier 4.5 A average would
have undersized heating by roughly half.

| Candidate | Rated | % of rated | Margin |
| --- | ---: | ---: | ---: |
| FWP-50A14F | 50 A | 18.0 % | 5.56x |
| A70QS50-14F (alt) | 50 A | 18.0 % | 5.56x |
| FWP-25A14F | 25 A | 36.0 % | 2.78x |

Continuous duty is comfortable. **Startup/inrush and temperature-derated
ampacity remain null** — the model is steady-state and no conductor or ambient
derating was captured.

## Fault-impedance envelope, not a resistance window

400 points over R in [5 mΩ, 5 Ω] and L in [20 nH, 20 µH], with model oracles
passing (peak against V0/Z0 and V0/R; action against E/R). Melt and clear are
now separate questions:

- **Melts** (adiabatic, L-independent): FWP-50A14F R ≤ 0.896 Ω; A70QS50-14F
  R ≤ 0.640 Ω; FWP-25A14F R ≤ 3.855 Ω.
- **Peak:** up to 55.2 kA at the R = 5 mΩ / L = 20 nH corner; ≤ 50 kA above
  R ≈ 8.9 mΩ.
- **Clears:** **FWP is null** — no applicable data. For A70QS50-14F the
  manufacturer publishes a **capacitor-discharge rating of 890 Vdc up to a
  2.5 ms time constant**, and its melt region sits inside that condition. That is
  **class guidance, not a demonstrated board coordination**, and the attempt
  labels it as such.

The previous `E/R >= 200 A²s` comparison is correctly relabelled: an ideal
discharge's available action against a pre-arcing figure is a **screen**, not an
interruption criterion.

## Revision reconciled — the review was right

The applicable revision for **FWP-50A14F is 700 Vdc, 50 kAIC at 700 Vdc**
(spec sheet generation 2023-12-04, DS 720025). The retained sheet's 800 Vdc is
**the retained 2011-2014 revision's value, not the ordered part's**. The current
Eaton PDF could not be captured from this host (HTTP/2 `INTERNAL_ERROR`, then an
HTTP/1.1 zero-byte timeout), and the discrepancy was established from the
manufacturer's specification-sheet generation data rather than the retained bytes.
Either way the rating exceeds the nominal 400 V bus, so the candidate's class is
not in question.

## A defect in the coordinator's own gate, found and fixed

The worker flagged that `check_campaign_dispatch.py handback` counted **any
non-null** `result.json.checker_receipt` as a validated run, and worked around it
by leaving the receipt null. That is the same class of error this whole arc has
been correcting — presence standing in for meaning. Fixed: a receipt now counts
only when it explicitly reports a pass (`status: pass` or `passed: true`), with
three regression tests covering a failing receipt, a receipt with no status, and
a passing one. 20 tool tests pass.

## Verdict

**Coordination unestablished.** The completion ladder stays at `part_selected`;
it was not promoted. Candidate part and location remain identified.

## Single gating input

**The internal discharge loop's high-current R and L** — U9/U10 short residual,
bank ESR at discharge frequency, fuse resistance and layout. It sets `E/R`, the
peak and the discharge time constant, and therefore whether any candidate both
melts and stays inside a capacitor-discharge rating. Secondary: an Eaton
capacitor-discharge rating or let-through curve for the FWP class; startup/inrush
and temperature-derated ampacity; and a sourced bank/copper withstand I²t.

F2 remains a proposal and is not in CAD or BOM.
