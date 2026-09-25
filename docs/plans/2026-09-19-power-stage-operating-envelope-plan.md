# Power-stage operating envelope and integration plan
Created: 2026-09-19

## Outcome and scope

Turn the verified F2 shutdown experiment into a candidate suitable for complete
power-stage evaluation, then consolidate its schematic. The immediate work is
an operating-envelope contract: every limit must say what quantity it constrains,
where it applies, under what conditions, and whether it is a requirement, a
component rating, an assumed model input or a simulation observation.

This plan follows the user's requested sequence: establish limits → evaluate
complete power stage → consolidate schematic. This planning pass delegates and
completes evidence gathering. It does not claim those later implementation or
qualification stages have run. Hardware remains unavailable. Earlier hashed
experiments, including f2-shutdown-04, are immutable.

## Delegated work completed in this pass

| Owner | Subtask | Deliverable |
|---|---|---|
| Luna requirements | Trace product requirements and conflicting legacy values | `operating-envelope-05/research/requirements.md` |
| Luna components | Check exact-part ratings, source conditions and missing bounds | `operating-envelope-05/research/components.md` |
| Luna simulations | Audit exercised dimensions and propose the smallest useful new matrix | `operating-envelope-05/research/sweeps.md` |
| Host | Reconcile authority, integration interfaces and full component scope | `operating-envelope-05/research/integration.md`, envelope contract and this plan |

All evidence paths in the table are relative to
`zapote/power-entry/passive-reva/protection/`. Three Luna agents ran in parallel;
a fourth parallel worker was unavailable because of the agent limit.

## A. Establish the operating envelope

| ID | Concrete substep | Output and completion criterion | Owner / dependencies |
|---|---|---|---|
| A1 | Pin the passive-reva source, retained board, exact parts and accepted shutdown revision; reconcile legacy doubler and stale manifests | One identity/authority table; no340V split-bus or150µH stale-manifest values silently imported | Host + Luna requirements; completed research |
| A2 | Retain108–132VAC and15Arms; distinguish AC-input class from delivered continuous/burst power; define low-line foldback | A voltage-dependent allowed-power curve with explicit PF/efficiency/thermal inputs; no promise of1800W output at108V | Luna requirements with host integration; A1 |
| A3 | Define separate normal, trip and fault limits for VD, VB, VDS, diode reverse voltage and VGS | Node-by-node limits with duration/temperature/tolerance conditions;450V bulk rating is never replaced by the500V provisional VD screen | Luna components; A1 |
| A4 | Bound reachable boost current and stored energy from current-sense tolerance/filter, controller response and L(I,T) | A current/energy envelope over the trajectory; distinguish15Arms line, PCL threshold and instantaneous switch current | Luna components + simulation worker; A1/A2 |
| A5 | Define real15V and5V producers, rail ranges, rise/fall, overvoltage and partial-power behavior; bind ARM/PERMIT ownership | Interface table covering every producer and default state; no tied-healthy missing producer or below-VCC ideal assumption counted as proof | Host with Luna components; A1 |
| A6 | Bind40°C inlet target to assembly losses and component temperatures; define continuous/burst duration only when justified | Thermal/load contract with explicit unknowns; case/junction/PCB/inlet temperatures remain separate | Luna components; A2/A4 |
| A7 | Reconcile the rows and freeze a simulation contract | Each executable test has a sourced limit or explicitly labelled conditional sweep range; unresolved physical inputs remain unknown | Host; A2–A6 |

**Current established baseline:**120VAC nominal,108–132VAC,15Arms,40°C cooling
inlet. Current source configuration is a single389.615V nominal PFC bus,
180µH selected inductor, and16.2kΩ frequency programming (~130kHz design point).
60Hz is an existing calculation assumption. Full allowed bus range, continuous
or burst output rating, hot L(I,T), maximum fault current and complete worst-case
shutdown time are not established by those nominal values.

**A4 decision rule:** derive the allowable current-versus-delay-versus-L/C region
from the chosen voltage/energy ceilings, then compare the actual limiting path
against it. If the controller or magnetics lack an applicable upper/lower bound,
keep the conditional curve and identify the exact missing datum. Resolve that
by applicable vendor evidence or a separately bounded current-limit/magnetic
design; do not turn a51A simulation point into a guaranteed51A cap.

**A5 concrete mismatch:** the older IRM-10-15 proposal's stated overvoltage range
extends to20.25V, while the selected UCC27511A recommends at most18V and has20V
absolute VDD maximum. The fast auxiliary detector is undervoltage-only. The
producer/rail overvoltage disposition therefore needs a real design decision
before calling the supply interface complete.

A2–A6 contain remaining engineering work, not new product facts created by this
plan. The accompanying contract distinguishes inherited requirements from these
open derivations. User choices are needed only if the intended product changes
(e.g. a new mains market or a new power rating), not to reread settled limits.

## B. Evaluate the complete power stage

Proceed in small dependent batches. Reuse the existing fault/supply cases as
regressions when their inputs or source change; do not repeat them as a new
research campaign without a reason.

1. **Create one source-bound integration fixture.** Include rectified AC/source
   impedance, selected bridge/inductor/shunt, diode, local reservoir, F2 and bulk
   bank, actual controller sensing, gate interface, load and real rail ports.
   Confirm source graph and probe directions before numerical work. Use a new
   experiment directory; preserve04.
2. **Replace synthetic PWM with applicable UCC28180 behavior.** Validate current
   limiting, normal regulation, VSENSE standby, startup, stop and retry against
   manufacturer reference behavior. The existing100kHz/55%-duty F2 pulse source
   is not the source's ~130kHz closed-loop operating point. A declared behavioral
   controller is acceptable for conditional studies only after independent
   functional checks; unresolved dynamics stay explicit.
3. **Establish normal operating points first.** Start with108/120/132VAC and
   low/mid/maximum permitted load (nine conditional points), at the existing60Hz
   assumption. Set maximum load from A2, not1800W at every voltage. Record steady
   ripple, RMS/peak current, losses, bus voltage, controller state and startup.
   Stop a branch that cannot reach a physically consistent operating point.
4. **Apply the fault state matrix.** Begin with F2 opening during established
   run and during startup; both nodes charged, both discharged and residual-
   charge restart. Include healthy switches, switch short, diode short and both
   short as separate graph states. A gate command receives no interruption
   credit when the switch is short. Include controller OVP-before-external-latch
   and continuing/repeated mains input; these are absent from the fixed-PWM proof.
5. **Exercise interactions.** Combine adverse line/PWM phase, current-limit
   delay, physically consistent L(I,T), minimum effective local capacitance,
   capacitor ESR/ESL, loop/interconnect inductance, hot device parameters,
   threshold offsets and real supply transitions. Start at source-supported
   endpoints and a small set of witnesses; refine around event-order changes.
   An arbitrary finite grid is not a continuous-envelope proof. Keep correlated
   device parameters consistent or justify an explicit conservative bound.
6. **Check each relevant waveform and retained state.** Record VD, VB, VDS,
   VGS, inductor/channel/body/fuse current, fault output, Q, enable, controller
   state and load permit. Check node-specific voltage/time limits, no unintended
   rearm, source work and local energy accounting. Keep passive ringing separate
   from controlled current cessation. Refine time step at limiting cases and
   verify negative controls still fail.
7. **Review and disposition.** Report minimum margin and the condition causing
   it, with model applicability separate from numerical convergence. For a real
   failure, change the responsible circuit/interface and rerun affected cases;
   do not widen a limit to manufacture acceptance. Missing fuse-arc, magnetic or
   partial-power evidence remains a named conditional boundary.

**B completion:** a reproducible integrated fixture, exact scenario definitions,
strict regression/negative-control outcomes and a reviewed margin table. This
is the simulation milestone. Installed physical qualification is a later,
separate requirement in `passive-reva/MILESTONE.md`.

## C. Consolidate the buildable schematic

1. **Count the whole implementation.** Map the retained54-part power stage and
   standalone79-part protection experiment into retained/replaced/new/offboard
   parts. Include5V/15V producers, isolation, F2 holder/interconnect, reservoir and
   system-control interfaces.79 is not an integrated-board part count.
2. **Review functions before substitutions.** Audit duplicated bias/filter/bypass
   and support networks; compare combining rail monitors and fast auxiliary
   loss detection, or reducing logic packages. Preserve required bandwidth,
   injection limits, power-off behavior and local decoupling. No part-count
   reduction is accepted merely because an integrated device exists.
3. **Compare at most two concrete alternatives.** Show exact parts, conditions,
   physical pin mapping, full installed BOM and which requirement each fulfills.
   Keep both OV channels, mismatch detection, direct disable and fresh-arm latch
   unless the integrated fault matrix proves a function unnecessary. Sequencing
   may move only to a real implemented producer.
4. **Implement one candidate and reverify.** Compile its source, check graph and
   package/ratings, rerun the established fault/supply/driver suite and the new
   controller-coupled limiting cases. Refresh source/model binding; never relabel
   the old79-part evidence as proof of the new circuit.
5. **Prepare layout and bench handoff.** Freeze the accepted electrical interfaces
   and assumptions, then perform the required native/Rust saved-board checks.
   Carry specific remaining measurements into the bench plan. Layout readiness,
   simulation completion and hardware protection qualification are separate gates.

## Execution order and stop conditions

A2/A3/A5 can proceed in parallel; A4 and A6 exchange current/loss/temperature
bounds. A7 freezes the inputs before B's broad matrix. B1/B2 may begin with
explicit conditional inputs while A4 is being resolved, but cannot claim a
qualified envelope from them. C1 census can run alongside B; C2–C4 follow the
controller/fault conclusions so we do not simplify away a function still needed.

Use Luna workers for bounded evidence/model/circuit units with disjoint files.
The host owns the canonical source, integration and final acceptance. Every
numerical implementation uses existing Rust rule owners and source-bound
fixtures; no generic harness rewrite is a dependency. Stop and report the exact
missing input or contradictory result rather than inventing a rating, repeatedly
retrying downloads, or adding unrelated protection functions.

## Research confidence and next executable slice

High confidence in inherited mains/current/inlet requirements and the scope of
04's observed simulation results. The manufacturer tables are condition-specific;
research reports record uncertain part variants and thermal-footnote ambiguity.
Confidence in a physical maximum-current/turnoff/thermal envelope remains low
until A4–A6 are resolved.

The next bounded execution slice is **A3–A5 plus B1/B2**: derive node limits,
resolve current-limit/magnetic inputs and rail-overvoltage behavior, then build
the actual-controller integration fixture. This addresses the main missing
behaviors before further component-count optimization.
