# Coordinator receipt — AR-BOUNDS attempt-001

Date: 2026-09-18 (revised 2026-09-18 after review)
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL, WITH CLAIMS WITHDRAWN.** The useful results
survive — the board-identity correction, the checker runs, the nulls and the
INDETERMINATE verdict. The **bound** claims do not, and are withdrawn below.

## Admission

Dispatch ADMITTED. Handback **NOT COUNTED AS A VALIDATED RUN** (checker declared
`not_applicable`). Evidence ledger passing (26 claims, 4 protection claims,
**0 promotions**). Fault-loop check passes; the U12 negative control is rejected.
27 files hash-verified.

**A passing ledger is not a true one.** `zapote-claims` checks the properties it
implements — bound direction, conditions, part identity, fault state, assertion
strength, completion rung. It **did not** fire on the four defects below, because
none of them is a *direction* violation at the level it inspects: a mis-derived
"lower bound" is still labelled `lower_bound`, and a subtotal drawing on two
device states is still internally well-formed. This is the repo's own standing
caveat — a clean run means no implemented check fired, not that the claims are
sound — and it is the second time in this campaign that a claim-level defect
survived a green checker.

## The checker does not catch these — and here is precisely why

Reproduced, not asserted. `claims/2026-09-18-arbounds-claims-withdrawn.json`
contains the four entries **as stated**; it **passes `zapote-claims` (exit 0)**.
Measured against the checker's own output, the gap is sharper than "it doesn't
model physics":

**Every condition / part / fault-state / bound-direction rule fires only
*relative to a parent claim*.** They are comparisons between a claim and its
`derived_from`. A claim that makes a derived assertion while declaring
`derived_from: null` has no parent, so **all of those rules are vacuous for it**.

`bank-esr-bank-max` is the worked example. Its own justification performs a
derivation — "0.4737 ohm / 4 = 0.11842 ohm" — but it declared `derived_from:
null`. As shipped it passes. Linking it to its real parent
(`bank-esr-120hz-max`) makes the checker fire immediately:

```
bank-esr-bank-max changes bank-esr-120hz-max's source condition
    with no supported transformation
bank-esr-bank-max changes bank-esr-120hz-max's part
    (LGX2W561MELC50 -> LGX2W561MELC50 x4) with no supported transformation
```

So the defect was **detectable and one field away from being detected**. The
silent default `derived_from: null` is what hides it — and note that `null` is
the *absence* of a declaration, which is indistinguishable from "independently
sourced" unless the schema forces the distinction.

What remains genuinely outside the checker is defect 1 (the physical claim that a
single-path figure bounds a network) and defect 3 (the arithmetic direction of an
upper-bound subtraction in prose). Those need either a soundness rule about
parallel conductors, or a human. **The gap is filed as a follow-up rather than
fixed here** (issue **#1606**), because changing the ledger schema is a design
decision plus a Rust change plus migration of existing ledgers, and it is not
required to correct the packet.

## Claims withdrawn

**Attribution first, because it matters.** The AR-BOUNDS ledger itself labelled
these entries `value_kind: "assumed"` and `assertion: "illustrative"` — the worker
was notably more cautious than the documents built on top of it. It was **the
coordinator's receipt and the manufacturer packet that promoted them to "bounds"
and to "R >= 10.29 mOhm"**. Two of the defects are worker-side
(`copper-loop-resistance-lower`'s `bound_kind: "lower"` field, and
`bank-esr-bank-max` being marked `assertion: "qualified"`); the other two are mine.
Both are corrected.

Recorded machine-readably in `withdrawals.json`. The affected entries are
`copper-loop-resistance-lower`, `known-components-loop-r-upper`,
`bank-esr-bank-max`, `loop-inductance-bounds`; `withdrawals.json` also names
which entries **survive unchanged**.

### 1. "R >= 10.29 mOhm" is not a lower bound — the direction is wrong

The copper figure traces a single least-resistance *path* per capacitor and
**excludes other conductors, including the return-side `PFC_BUS_MINUS` B.Cu
zone**. Parallel paths can only *reduce* effective resistance, so the
extracted-path figure sits **above** the true network value. It is an estimate
that tends to over-state, and it cannot bound the network from below.

The same defect propagates: the dependent `R >= 400*L` margin and the
"25.7 uH" boundary figure lose their basis, because both were computed from a
quantity that was never a lower bound.

### 2. The 193.6 mOhm subtotal mixes incompatible device states

It sums bank ESR + fuse + **U9's healthy on-resistance** + copper, and then
treats **U9's failed-short residual** as an additional unknown. Those are
different scenarios: when U9 is shorted, its healthy `Rds_on` does not apply, and
no published figure replaces it. The subtotal is incoherent and is withdrawn.

### 3. The 0.4466 ohm crossing threshold does not follow

The reasoning was `0.64013 - 0.19355 = 0.44658`, so "a residual above 0.4466 ohm
crosses the screen". But `0.19355` is an **upper** bound on the known terms, so
the residual required to cross is `0.64013 - (known)`, which is **larger** than
0.4466 when the known terms are smaller. A residual of 0.5 ohm with known terms
of 0.05 ohm gives R = 0.55 ohm — below the screen. **The threshold does not
establish what it claims.** Establishing it needs a *lower* bound on the known
terms, which does not exist here.

### 4. The ESR figure is not a broadband bound

It uses **nominal capacitance** although the parts carry a ±20% tolerance, which
alone moves the derived ESR by roughly a quarter (a 20% low part gives ~25% more
ESR). And it extends a **120 Hz** loss-angle specification to the discharge
waveform with no evidence that the specification holds at that frequency.
Nichicon states the capacitance and loss-angle conditions explicitly; the
corresponding figures for the discharge regime were not obtained. So this is a
120 Hz nominal estimate, not an upper bound at the fault.

**The inductance range is likewise an estimate, not a pair of limits** — it spans
two return-path assumptions rather than bounding the geometry between them.

## Recommendation withdrawn

The attempt recommended "one kA-scale pulsed measurement of a failed-short
residual, which closes the only term that can move R across 0.64013 ohm". That
is **withdrawn**: a single specimen would *characterise that specimen's* failure
mode, not bound the population's failed-short behaviour. Device-to-device and
failure-mode-to-failure-mode variation is exactly what is unknown, so one
measurement would produce a number, not a bound — and the temptation to treat it
as one is the error this whole campaign keeps finding.

## What survives

- **The board-identity correction.** The dispatch named `pcb/temper.kicad_pcb`
  (`00a27419...`), which contains **none** of the loop nets; the AR-FAULT netlist
  came from `zapote/power-entry/shunt-repair/candidate/section.kicad_pcb`
  (`34e6fba9...`). The worker found this by looking for the net names and found
  none, derived geometry from the board the netlist actually came from, and
  logged the mismatch. **The coordinator error is mine**, and had the worker used
  the named board it would have produced a complete and fictional inductance.
- **The checker runs and the negative control** (U12 rejected for having one
  terminal on the loop nets) — these are connectivity results, unaffected.
- **The nulls**, which are the most valuable output: **U9 and U10 failed-short
  residuals are not published**, and U10's only published figure is a *forward*
  model, not a short residual. A healthy `Rds_on` is not a short residual.
- **The verdict: INDETERMINATE** — reachable directly from the nulls without any
  of the withdrawn bounds, and still correct.

## Fault states — corrected here too

The protection scenario this feeds requires **both devices shorted**: **U10 (the
boost diode) failed short** is what connects the bus to `a1`, and a healthy U10
is reverse-biased and blocks the discharge entirely; **U9 (the boost switch)
failed short** completes the loop and removes U9 as an interrupter. **F2, a
proposed series fuse, is then the only element that can act.** This matches what
AR-FAULT and AR-PROTCKT already recorded ("a bare boost-switch short does NOT
discharge the bank"; "U9 cannot be turned off; F2 is the only element that can
act") and is now stated the same way in the manufacturer packet.

## Milestone

Unchanged: **coordination unestablished; location indeterminate.** The packet
now goes out as an **inquiry carrying the R–L sensitivity envelope and clearly
labelled estimates**, which is what the manufacturer needs and all the evidence
supports.
