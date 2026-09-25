# Temper PFC: campaign findings and next revision

Created: 2026-09-21 (America/Mexico_City)

## Where the project stands

The bounded simulation assessment is complete. It establishes conditional behavior of a custom PFC model and identifies protection and model gaps. It does not establish a build-ready or hardware-qualified appliance.

The product benchmark is the Breville Control Freak's nominal 120 VAC, 60 Hz, 1800 W electrical input class. Neither 1800 W of DC output nor 1800 W delivered to cookware is an established requirement. Power lost in the bridge/PFC, auxiliary supplies, inverter and magnetic coupling must be accounted for. Matching cooking performance also requires defined cookware, heat-up, temperature stability and disturbance-recovery tests.

## What the campaign established

| Area | Evidence and conclusion | Limit |
|---|---|---|
| Cold startup | Complete 650 ms baseline, ending near 383 V with a resistive load | Authored model, three final line cycles evaluated; no long-duration or thermal claim |
| Normal operation | Nine declared points across 108/120/132 VAC passed unchanged electrical screens | About 359–1392 W DC resistive output; discrete points, not a continuous or full-input-power envelope |
| F2 opens | Startup, line-crest and zero-crossing cases passed their exact model screens | F2 opening is prescribed; no physical fuse-clearing or causal current-interruption qualification |
| Diode shorts | Detector response about 3.12 ms exceeded the retained 2 ms window | Failed timing screen; sampled passive current can remain after gate-off |
| Both diode and MOSFET short | Inductor current exceeded the retained 100 A screen; failed-branch current remained despite gate-off | Idealized extreme currents are not credible physical die-current or survival predictions |
| MOSFET alone shorts | Run stopped before the declared endpoint; its own normal prefix was separately accepted | Full fault remains INDETERMINATE, not passing |
| Detector bypassed | Complete trace exceeded the VD 500 V screen, reaching about 651 V; sampled external shutdown stayed absent | This was an intentional negative control, not proof that the unbypassed design lacks a VD detector |

The final assessment, exact receipts and 17 retained archive identities are in:

- [Campaign assessment](../../zapote/power-entry/passive-reva/protection/operating-matrix-07/host/campaign-report-139.md)
- [Reproducibility index](../../zapote/power-entry/passive-reva/protection/operating-matrix-07/host/reproducibility-index-140.json)
- [Parent completion audit](../../zapote/power-entry/passive-reva/protection/operating-matrix-07/host/final-goal-audit-141.md)

A completed assessment includes failed and explicitly incomplete attempts. It does not mean the protection is adequate.

## Timestamp and runtime interpretation

The strict legacy checker rejects repeated timestamps. The later, explicit event-aware policy retains every row and audits equal-time groups, logic observables and relevant integral effects. The earlier strict rejections remain negative evidence. A `first_invalid=true` flag records a legacy non-increasing-time event; it is not by itself the final event-aware electrical verdict. Backward time, nonfinite values, missing payload and incomplete endpoints remain separate defects.

Elapsed campaign time included a queue of long transients and archive analyses. It was not one productive 18-hour simulation. A later live process inspection found two wildcard hash commands blocked on FIFOs and an abandoned export-probe process group. Completion receipts had not caught those older jobs. Eleven processes were terminated, preserving source and raw recordings. About 21 GiB remained free at that inspection.

The [lifecycle incident and repair](../../zapote/power-entry/passive-reva/protection/operating-matrix-07/host/harness-lifecycle-144/incident.md) records the causes, cleanup, and tested future-command guard. Future launches and archive analyses must use explicit timeouts, fresh output receipts, and process-group cleanup. Hash only explicitly enumerated regular files. No broad campaign is needed merely to test the revised command lifecycle.

## Model gaps that still matter

- The controller is a host-authored UCC28180 functional surrogate, not TI's transient silicon model. Available TI assets have not been correlated with it.
- The simulation's assumed BAV23C clamp lacks a guaranteed low-current forward-voltage envelope over temperature and production spread. It is also a different part, polarity and node from the BAT54H connection in the retained physical source. Authored hot-temperature loading fixtures fail their engineering screens. The saved ISENSE scan also crosses the strict recommended positive-voltage boundary and does not exercise peak-current limiting.
- The fixed inductor model lacks validated saturation, DC bias, core loss and thermal behavior.
- MOSFET, diode, capacitor and auxiliary models do not establish real SOA, switching loss, ripple heating or supply behavior.
- Physical F1/F2 clearing and coordination must be established separately. A scripted switch opening is not a fuse model.

## Reference-design correction

PMP10948 is a useful 120 VAC benchmark but uses UCC28063 interleaved transition-mode controllers and separate 750 W and 550 W PFC stages. Its headline 1300 W is not a drop-in UCC28180 implementation or a single output stage rating to scale blindly.

UCC28180EVM-573 and TIDA-00779 use the current controller family. The former is a 360 W wiring reference; the latter's stated full-power range is 190–270 VAC. Neither establishes a qualified 120 VAC / 1800 W appliance design. Reference topology, compensation, current sensing, magnetics, drivers, bias and inrush paths require explicit comparison; efficiency cannot simply be inherited.

## Authorized next work

The source audit found a material authority trap: source-build-07 is the
**rejected 133-part supervisor experiment**, not the retained 54-part baseline.
Its local-VD feedback must not be described as already installed. The restored
root source and accepted SPICE both use bank-VB feedback; the new revision
tests moving the simulation's feedback to VD as a deliberate candidate change.
See the [source identity audit](../../zapote/power-entry/passive-reva/protection/reference-revision-08/source-identity.md).

F1 exists upstream in the retained source, but its clearing dynamics are absent
from the model. F2 remains a proposed offboard fuse, not a controllable
precharge switch. Gate-enable default-off/re-arm behavior must not be assigned
to an invented F2 actuator. The existing authored external VD/VB detectors are
retained; the negative-control result does not justify duplicating them.

The user authorized documenting these findings and proceeding through a reference-based revision, with bounded Luna tasks and parent verification:

1. Establish a provisional whole-appliance power budget and low-line derating rule, labeling every efficiency/auxiliary assumption.
2. Select a reference architecture for the next simulation candidate and record reasons and change triggers.
3. Reconcile existing protection before changing it. Separate missing model behavior, missing physical coordination, and a justified circuit change.
4. Implement and run small focused tests for the chosen change, preserving the old campaign. A passing functional fixture must not be promoted to complete converter or hardware validation.

Execution artifacts for this revision live in [reference-revision-08](../../zapote/power-entry/passive-reva/protection/reference-revision-08/). The next full matrix is gated on those focused results, a source-bound revised candidate, and a specific decision it will resolve.

## Completed next-revision unit

Luna agents drafted the budget, reference comparison and protection inventory,
built the small feedback fixture, and independently reviewed the result. Parent
review corrected the source authority, F2 actuator misconception, auxiliary
allocation assumptions and checker coverage before acceptance.

The selected next candidate retains UCC28180 and changes only feedback from VB
to VD. At illustrative PF 0.99, the 15 A screen and 1800 W input cap imply
1603.8/1782/1800 W input ceilings at 108/120/132 V; those are planning limits,
not measurements. The assumed conversion and auxiliary budget is recorded
separately and must not be read as pan output.

One 500 µs functional fixture completed in 1.321 seconds. It shows the modeled
controller inhibits PWM for an excursion on its selected feedback node and
recovers afterward. Selecting VD leaves bank-only overvoltage to independent
bank protection. The parent verified 35,138 finite, strictly increasing rows
and five rejected negative mutations with the rebuilt Rust checker.

The complete changed converter deck has not been simulated. Current-sense
clamp/source fidelity, integrated protection, fuse coordination, closed-loop
startup/load behavior, thermal limits and hardware qualification remain open.
