# Coordinator receipt — AR-BOUNDS attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** The loop R and L now have defensible
*sourced* bounds, and the location of the fault against the screened region is
**INDETERMINATE**, which is the correct answer and not a failure.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`). Evidence ledger passing (26 claims, 4 protection claims,
**0 promotions** — completion was deliberately not advanced). Fault-loop check
passes; the U12 negative control is rejected. 27 files hash-verified.

## A coordinator error the worker caught — the dispatch named the wrong board

The dispatch's `source_bundle` named `pcb/temper.kicad_pcb`
(`sha256 00a27419...`). **That board does not contain the loop nets at all** —
it is the 6-layer product board (`+170V_BUS`, `DC_BUS_RTN`, no boost stage). The
delivered AR-FAULT netlist came from a different board,
`zapote/power-entry/shunt-repair/candidate/section.kicad_pcb`
(`sha256 34e6fba9...`).

The worker found this by looking for the loop net names and finding none, then
derived geometry from the board the netlist actually came from, and recorded the
mismatch in `raw/capture_failures.json`. That is the correct handling: the
*netlist*, not the dispatch's prose, identifies the subject board.

**The coordinator error is mine.** The lesson is the repo's own: a path in a
dispatch is a claim, and a claim about which artefact a model describes has to be
checked against the artefact. Note the failure is silent in the *other*
direction too — had the worker used `temper.kicad_pcb` without checking, it would
have produced a complete, plausible, entirely fictional inductance.

## R bounds

| Term | Value | Kind / direction |
| --- | ---: | --- |
| Copper (geometry-derived, nearest cap, 20 °C) | 10.29 mΩ | **lower bound** (every other term ≥ 0) |
| Fuse (Mersen 11.6 W at 50 A) | 4.64 mΩ | hot figure; upper bound at fault onset |
| Bank ESR (Nichicon LGX, tan δ max @ 120 Hz) | 118.42 mΩ | **upper bound** (ESR falls with frequency) |
| U9 healthy/on Rds_on (25 °C max) | 50.0 mΩ | upper bound **at 25 °C only** |
| Copper at 100 °C | 20.49 mΩ | upper bound |
| **Sourced sub-total of known terms** | **≤ 193.6 mΩ** | |
| U9 failed-short residual | **null** | unsourced |
| U10 failed-short residual | **null** | unsourced |

**No closed upper bound.** The two failed-short residuals are unpublished, and
they are the only terms that can move R across the 0.64013 Ω action screen.
(Threshold: a combined residual above **0.4466 Ω** would put R outside it.)

## L bounds

Copper **75.8 nH – 2815.5 nH** (geometry-derived current-sheet model). The span
**is** the stated return-path assumption: return current directly beneath the
forward path (h = 1.44 mm dielectric) versus horizontally offset by the measured
worst-case 34.5 mm separation. That assumption dominates the result, which is why
it is reported as a range rather than a number.

Bank, fuse and semiconductor-package internal inductances are **null**
(unpublished) and add ≥ 0, so there is no closed upper bound.

## Verdict against the screened region: INDETERMINATE

Against `{400·L ≤ R ≤ 0.64013 Ω}`:

- **Lower boundary** (`R ≥ 400·L`): holds for any total L up to 25.72 µH. The
  copper term's maximum is 2.82 µH — a ~9× margin. But the unpublished internal
  inductances are unbounded, so it is **not closed by sourced data**.
- **Upper boundary** (`R ≤ 0.64013 Ω`): the sourced sub-total is 0.1936 Ω, so it
  passes on everything known — but the two null residuals mean it is **not
  closed**.

So: **inside is plausible on all sourced evidence, the bounds straddle the
region, and no conclusion is forced.** The worker correctly declined to force
one. This is a genuine result, not an evasion: it names exactly one input that
would close it.

## The most important missing input

**The failed-short residual resistance of U9 (STW65N65DM2AG) and U10
(C3D20065D).** Two cautions the worker recorded, both of which matter:

- A healthy/on `Rds_on` is **not** a short residual. U9's 50 mΩ at 25 °C is a
  device parameter, not a failure-mode one. Using it as a short residual would be
  the same class of error as the `GATE_HS` prefix lookup: a value that looks
  right because it is near the right quantity.
- U10's only published figure is a *forward* model (`RT` = 0.055 Ω/leg at 25 °C),
  which is also not a short residual.

One kA-scale pulsed measurement, or a qualified shock-test record, closes this.
Paired second: the bank's 1–100 kHz ESR, which is what would close `R ≥ 400·L`
from above rather than by an unbounded null.

## Also flagged

**F2 (A70QS50-14F) is a bus-side candidate and is not present on the assessed
board.** The protection question is therefore a proposal about an insertion, not
a description of the board as built. CARRIED FORWARD as a standing qualification
on every protection claim in this campaign.

## Milestone

Unchanged: **coordination unestablished.** A plausible cell is a **screen**, not
coordination — it establishes neither melting nor clearing. The manufacturer
packet now carries the real R and L ranges, which is what it was missing.
