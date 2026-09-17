# Power-entry architecture decision - 2026-09-16

> **Corrective experiment (2026-09-17):** The earlier `4.468 W` output-
> capacitance number was invalid: ST's 456 pF `C_oss eq.` is time-equivalent,
> not energy-equivalent. The corrected DS11178 Rev 2 Figure 8 interpolation is
> 2.397 W ±0.078 W typical at the retained bus/frequency. The current GBJ
> assembly evidence is conditional (Wakefield 392-120AB/Sanyo 9RA1212E1001;
> nominal 84.35 °C, weak 117.82 °C, fan-loss 118.64 °C), so the old GBU
> bridge-cooling margin is not applicable. See
> [the corrective experiment](CORRECTIVE-EXPERIMENT-2026-09-17.md).

This is the decision the retained power-entry evidence supports today. It
replaces the earlier five-board-variant framing. It does not claim the
electronics are qualified: no powered measurement has been performed. A
reproducible Rust event model now bounds the switching term; physical waveform
and thermal qualification remain open.

## Decision

**Keep the passive bridge and give it a real thermal path, and optimize the
boost stage in parallel (candidates 1 and 5). Do not pursue the active
rectifier or parallel bridges at this point.**

The two chosen candidates attack the two things the evidence actually names,
they are electrically compatible, and neither needs a new topology. The
alternatives are not rejected on principle; they are deferred because the
numbers that would justify them are not the numbers that currently dominate.

**This is a priority decision, not a ranking.** Nothing here says candidate 1 or
5 is the lower-loss architecture by measurement — the boost overlap is pursued
*because it is unmeasured*, and the bridge is pursued *because it is the
assembly constraint*, not because either was scored against candidates 2, 3 or
4. The screen that feeds this still promotes nothing and ranks nothing. What the
decision does say is which unknowns are worth buying first, and it is reversible
on the evidence listed under "What would change this decision".

## What was resolved in this pass

**The boost-switch identity.** The authored and native order code is now
`STW65N65DM2AG`; the physical package marking remains `65N65DM2`. The retained
ST datasheet's Device summary binds those two strings. The board, source
manifest, native census and manufacturing receipt carry the same AG identity
and board hash, so the switch terms below are attributed to a real part.

**The output-capacitance and switching terms.** The earlier 4.468 W calculation
was invalid: ST's 456 pF `C_oss eq.` is time-equivalent. Digitizing the official
DS11178 Rev 2 Figure 8 gives **2.397 W ±0.078 W** typical at 389.615 V and
129.107 kHz. Gate drive (`Qg` 120 nC at 10 V) is **0.155 W**. The Rust event
model includes UCC28180 1.5/2 A source/sink limits, 10 ohm external plus 3.3
ohm intrinsic gate resistance, Miller plateau, 10 nH loop inductance and
current-dependent VDS transitions. Its nominal 120 Vrms/10 V/25 C case reports
**43.943 W switching overlap**, **11.261 W conduction**, **0.155 W gate** and
**2.397 W Eoss**. Eoss is counted once on turn-on and remains separate from a
measured Eon that already includes Coss discharge. These are typical bounded
model results; waveform, hot RDS(on) and diode qualification remain open.

**The bridge thermal path.** The current GBJ study is conditional evidence,
not an installed cooling qualification. It keeps the bridge a constraint until
the Wakefield 392-120AB/Sanyo 9RA1212E1001 assembly and airflow are measured.

## The five cases

| Case | State | Evidence |
| --- | --- | --- |
| Nominal (120 V) | modelled | Ideal CCM screen; 28.304 W bridge drop at the 1.05 V test point |
| Low line (108 V) | modelled, and it fails the requirement | Needs 16.658 A inside a 15 A ceiling; 179.3 W short at 1,617.1 W reachable |
| High line (132 V) | modelled | Meets the requirement; bridge drop falls to 25.730 W because less current carries the same power |
| Hot / degraded cooling | modelled for the bridge, by a different instrument | `bridge-thermal-02` joint FEM and the 20-case `thermal/bridge-cooling` study |
| Startup / fault | **not modelled** | No CCM operating point exists; no loss term is computed and none is claimed |

The balance sheet is therefore four of five cases with a modelled treatment and
one, startup and fault, genuinely open. The hot case is not "untested": it is
modelled, and what it says is uncomfortable.

## Why the hot case matters to the decision

The retained `bridge-thermal-02/assessment.json` reports nominal-fine whole-
joint peak **84.35 °C** / hottest GBJ node **80.22 °C**, weak-assembly
**117.82 °C** / **95.95 °C**, and fan-loss **118.64 °C** / **119.53 °C**.
The weak and fan-loss cases exceed the 110 °C local screen. The 100 CFM
catalog calculation (59.64 °C) is a conditional reservoir calculation, not
installed airflow evidence. No GBU2510A/Wakefield 395-1AB margin transfers to
this GBJ assembly.

Two consequences:

1. The passive bridge remains the baseline, but cooling applicability is
   **INDETERMINATE** until installed airflow, contacts and fan-fault behavior
   are measured.
2. The weak-contact and fan-loss sensitivity is the evidence-backed cooling
   change required for closure; further nominal mesh refinement is not.

## Candidate disposition

| Candidate | Disposition | Reason |
| --- | --- | --- |
| 1. Keep bridge, improve thermal path | **pursue** | The constraint the evidence actually identifies; compatible with 5 |
| 5. Boost-stage optimization | **pursue** | Largest single lever: the overlap term spans tens of watts and is unmeasured |
| 2. Larger / lower-drop bridge | defer | Worth 2.696 W per 0.1 V of forward drop; a part-sourcing question with no authored part to score |
| 3. Parallel passive bridges | defer, not rejected | The constant-drop model has no slope term, so it cannot express sharing; needs a forward-slope curve first |
| 4. Active rectifier | defer | 62.9 mΩ is a conduction-only screen against the unread hot curve; drive, commutation, protection and EMI costs are missing, so it is not an architecture decision |

The ordering follows from one asymmetry: the bridge drop is 28.304 W of a
1,796.4 W input, about 2%, and is bounded to roughly a 2:1 band by the forward
drop; the boost overlap is unbounded and can exceed the entire bridge loss on
its own. Reducing a bounded 28 W is worth less than resolving an unbounded
term of the same size.

## What would change this decision

- **Measured overlap energy well below the band.** If the real transition is
  fast at the actual 10 ohm gate network, the boost lever shrinks and the
  bridge architecture becomes proportionally more interesting.
- **A bridge neck improvement that cannot close the 2.14 K local margin.** At
  which point candidate 2 or 4 earns a real evaluation, because the assembly,
  not the silicon, is what fails.
- **A lower-drop orderable bridge.** Candidate 2 becomes scorable immediately:
  multiply its forward-drop reduction by 2.696 W per 0.1 V and compare against
  the heatsink work it would save.
- **A hot `RDS(on)` curve.** That single number decides candidate 4, because
  the break-even threshold is already computed and the 25 °C maximum sits just
  below it.

## Not decided here

- No total loss and no cooling margin. Missing terms are named, never zeroed.
- No delivered-output efficiency. The 1,796.4 W requirement is the ideal CCM
  model's *input* power, not pan power.
- No claim about startup, inrush, precharge, shutdown or fault behaviour.
- No acceptance of the existing bridge neck geometry, and no fabrication or
  energize authorization.
- Physical qualification of the switching model, hot RDS(on), diode recovery,
  installed cooling and startup/fault behavior remain open. The current board
  geometry and routing were preserved.

## Provenance

| Item | Where |
| --- | --- |
| Switch datasheet, order code and marking | `sources/STW65N65DM2AG.pdf` (pinned by hash in `pfc_loss_budget.rs`) |
| Loss screen and bounded switch terms | `zapote/packages/zapote-harness/src/pfc_candidates.rs`, `pfc_loss_budget.rs` |
| Reproducible switching model and raw result | `loss-budget/PFC-SWITCHING-MODEL.md`, `loss-budget/evidence/pfc-loss-simulation-2026-09-17.json` |
| Bridge joint model | `shunt-repair/bridge-thermal-02/assessment.json` |
| Bridge cooling study, 20 cases | `thermal/bridge-cooling.md`, `thermal/evidence/bridge-cooling-2026-09-14/` |
