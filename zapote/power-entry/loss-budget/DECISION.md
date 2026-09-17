# Power-entry architecture decision - 2026-09-16

This is the decision the retained power-entry evidence supports today. It
replaces the earlier five-board-variant framing. It does not claim the
electronics are qualified: no powered measurement has been performed and the
overlap term below is still unmeasured.

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

**The boost-switch identity.** The authored `STW65N65DM2` is ST's *marking*
form, not an order code. The retained ST datasheet's own Device summary prints
`Order code STW65N65DM2AG` against `Marking 65N65DM2`, so the orderable part is
`STW65N65DM2AG`. The datasheet is now a hash-pinned source
(`sources/STW65N65DM2AG.pdf`), which is what allows the switch terms below to
be attributed to a real part instead of to an unnamed device. The earlier
framing treated `STW65N65DM2AG` and `STW63N65DM2` as unapproved substitutions;
that is settled — `STW63N65DM2` is a different orderable device, and the
authored string resolves to the AG order code.

**The output-capacitance term.** It was previously excluded outright. The
datasheet's equivalent output capacitance (`C_oss eq.` 456 pF, `VDS` 0 to
520 V) bounds it at **4.468 W** for the 389.615 V bus at 129.107 kHz. Gate
drive (`Qg` 120 nC at 10 V) is **0.155 W**. Both are single-condition typicals
and are reported as estimates, not guarantees.

**The bridge thermal path.** The practical heatsink question now has a
source-bound FEM answer rather than an open item, and the answer is that the
bridge is a *constraint*, not a formality (below).

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

The retained bridge cooling study selects a Wakefield 395-1AB sink and two
Sunon MF80251V1 fans and runs 20 FEM cases, against a **40 W bridge dissipation
allowance** rather than the 28.304 W constant-drop estimate — the study is
conservative about loss on purpose. At the design requirements the four bridge
necks land at **100.48-107.86 °C** against a 110 °C local PCB ceiling and a
125 °C junction ceiling. That is compliant, but the tightest local margin is
**2.14 K** and the series budget leaves **5 K** of junction margin. With the fan
stopped the same budget reaches **150 °C**, i.e. **-25 K**, and
`failed_fan_budget_compliant` is false.

At quarter contact conductance the necks run **125.09-147.77 °C**. The
independent joint model (`bridge-thermal-02`) agrees on the shape: the hottest
lumped GBJ diode node is 80.22 °C at the nominal 60 °C sink reservoir, 95.95 °C
in the weak-assembly case, and 119.53 °C at the 100 °C fan-loss reservoir, with
mesh and fine differences under 0.044 K.

Two consequences:

1. The passive bridge is feasible, but only with a real sink, real airflow and
   low-resistance bridge connections. It is not a PCB-only part, and "feasible"
   here means a few kelvin of margin at the design requirements with the fans
   running.
2. The margin is committed by the assembly and the connections, not by mesh
   refinement. That is why the recommended work is to improve the bridge
   connections and establish the actual lead/barrel/solder heat paths.

## Candidate disposition

| Candidate | Disposition | Reason |
| --- | --- | --- |
| 1. Keep bridge, improve thermal path | **pursue** | The constraint the evidence actually identifies; compatible with 5 |
| 5. Boost-stage optimization | **pursue** | Largest single lever: the overlap term spans tens of watts and is unmeasured |
| 2. Larger / lower-drop bridge | defer | Worth 2.696 W per 0.1 V of forward drop; a part-sourcing question with no authored part to score |
| 3. Parallel passive bridges | defer, not rejected | The constant-drop model has no slope term, so it cannot express sharing; needs a forward-slope curve first |
| 4. Active rectifier | defer | Break-even is about 62.9 mOhm hot per device against a 50 mOhm 25 °C maximum, i.e. it turns on the unread hot curve, and it adds control, protection and EMI complexity |

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
- **The authored identity has not been edited.** `elec/src/power_entry_unit.ato`,
  the BOM and the native board still read `STW65N65DM2`. In this repository
  that correction forces a native regeneration, and routing is applied rather
  than replayed, so it belongs with the next board revision. It is queued, not
  forgotten.

## Provenance

| Item | Where |
| --- | --- |
| Switch datasheet, order code and marking | `sources/STW65N65DM2AG.pdf` (pinned by hash in `pfc_loss_budget.rs`) |
| Loss screen and bounded switch terms | `zapote/packages/zapote-harness/src/pfc_candidates.rs`, `pfc_loss_budget.rs` |
| Bridge joint model | `shunt-repair/bridge-thermal-02/assessment.json` |
| Bridge cooling study, 20 cases | `thermal/bridge-cooling.md`, `thermal/evidence/bridge-cooling-2026-09-14/` |
