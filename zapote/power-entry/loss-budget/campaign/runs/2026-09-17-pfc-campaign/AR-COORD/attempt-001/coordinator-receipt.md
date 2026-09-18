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
passing (peak against V0/Z0 and V0/R; action against E/R). Those oracles validate
the **RLC calculation**; they do not validate its translation into a
manufacturer's qualification conditions. Melt and clear are separate questions,
and the melt column is a screen, not a melting result:

- **Pre-arcing action screen met** (adiabatic, L-independent): FWP-50A14F
  R ≤ 0.896 Ω; A70QS50-14F R ≤ 0.640 Ω; FWP-25A14F R ≤ 3.855 Ω. The sweep
  establishes where **the constant-resistance model's available action exceeds the
  selected pre-arcing figure**. It does **not** establish actual melting across
  arbitrary pulse durations, temperatures and fuse tolerances. "Melts iff" is
  withdrawn.
- **Peak:** up to 55.2 kA at the R = 5 mΩ / L = 20 nH corner; ≤ 50 kA above
  R ≈ 8.9 mΩ.
- **Clears: FWP is null.** For A70QS50-14F the manufacturer publishes a
  **capacitor-discharge rating of 890 Vdc up to a 2.5 ms time constant** — but the
  cited passage **does not define what "time constant" means**, and the earlier
  claim that "wherever it melts, the manufacturer's condition holds" is
  **withdrawn**.

### The time-constant definition — resolved in the weak sense

Substituting `R·C` for the manufacturer's criterion was not established at the
time, and is now known to be wrong. The captured Mersen catalogue defines the
time constant as **`L/R`** in its high-speed-fuse tables
(`*Time Constant: L/R <=1ms`), and its A70QS capacitor-discharge sentence is
scoped to **890 VDC, 2.5 ms time constant**. That makes `L/R` the
best-supported reading **by context** — the `L/R` statements concern the general
DC ratings and other product lines, not the capacitor-discharge sentence itself,
so this is a supported interpretation, not a manufacturer-confirmed definition of
that condition. What *is* settled is that `R·C` is not it.

At the envelope's peak corner (R = 5 mΩ, L = 20 µH, C = 2240.47 µF):

| Quantity | Value |
| --- | ---: |
| `L/R` — the manufacturer's time constant | **4.000 ms** |
| `2L/R` — oscillation envelope decay | 8.000 ms |
| `R·C` — what the report used | **11.20 µs** |
| **`L/R` : `R·C` — the relevant ratio** | **357x** |

The 714x figure in the earlier draft of this receipt compared `2L/R` against
`R·C`; with the time constant read as `L/R`, the relevant ratio is **357x**.
Either way the point stands: `R·C` is not the manufacturer's time constant, the
damping factor at that corner is 0.0265 (heavily underdamped), and the
"wherever it melts, the manufacturer's condition holds" claim is withdrawn.

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

## Gating inputs, reordered

**The most useful missing input is now the manufacturer's capacitor-discharge
application conditions** for the exact candidate: the definition of the stated
time constant, the applicable waveform and current limits, and clearing or
let-through evidence. Without that definition the existing envelope cannot be
mapped onto their qualification conditions at all — the `R·C` versus `2L/R`
ambiguity is 714x.

Second: **the internal discharge loop's high-current R and L** — U9/U10 short
residual, bank ESR at discharge frequency, fuse resistance and layout. It sets
`E/R`, the peak and the discharge time constant, and so decides which envelope
cells are even physically reachable.

Third: an Eaton capacitor-discharge rating or let-through curve for the FWP class;
startup/inrush and temperature-derated ampacity; a sourced bank/copper withstand
I²t.

## Milestone

**Candidate comparison completed; coordination unestablished.** The nominal RMS
comparison stands as a screening result with startup and derating open. F2
remains a proposal and is not in CAD or BOM.
