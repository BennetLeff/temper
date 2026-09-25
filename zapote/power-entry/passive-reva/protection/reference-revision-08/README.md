# Reference revision 08

This revision records the campaign outcome, sets a provisional input-power
budget, selects the next reference architecture, and isolates one feedback
change. It does not qualify a complete converter or change the retained PCB.

## Decisions

- **Power:** use the 1800 W appliance-input benchmark with the existing 15 A
  RMS screen. At assumed PF 0.99, the input ceilings are 1603.8 W at 108 V,
  1782 W at 120 V, and 1800 W at 132 V. With illustrative 95% PFC efficiency
  and 20 W of bus-fed auxiliaries, the corresponding inverter-input budgets
  are 1503.6, 1672.9 and 1690 W. These are allocations, not measurements.
- **Architecture:** retain UCC28180 CCM for this candidate. EVM-573 and
  TIDA-00779 provide same-controller wiring references; neither validates
  this low-line power target. PMP10948 uses a different controller and
  separate 750/550 W stages.
- **Source authority:** the retained 54-part baseline senses VB. VD feedback
  existed in the rejected 133-part experiment, which remains rejected. The
  new simulation candidate moves feedback to VD deliberately.
- **Protection:** keep external bank-voltage observation. F2 remains a
  proposed fuse, not an actuator. Gate inhibition cannot be credited with
  clearing a failed conducting MOSFET; F1/F2 coordination remains open.

## Artifacts

| Artifact | Purpose |
|---|---|
| [Power budget](power-budget.md) / [JSON](power-budget.json) | Assumptions, low-line reduction and downstream allocation |
| [Reference choice](reference-choice.md) / [sources](reference-evidence.json) | Controller choice and reasons to reconsider |
| [Source audit](source-identity.md) / [hashes](source-identity.json) | Baseline versus rejected experiment versus simulation |
| [Protection inventory](protection-revision.md) / [delta](protection-delta.json) | Existing paths, missing model behavior and remaining checks |
| [Candidate](candidate/README.md) | Six-file deck with one electrical line changed, not fully simulated |
| [Feedback fixture](feedback-fixture/README.md) | Short old/new controller OVP test and reproduction details |

The feedback fixture forces VD/VB and compensation pins to isolate the
authored controller's OVP response. It is not the complete converter deck.
Moving feedback to VD gives that controller visibility of local overvoltage;
it also removes its direct visibility of a bank-only excursion, so external
bank protection remains necessary. No full startup, closed-loop stability,
fault-energy or silicon-margin result follows from the fixture.

**Verified result:** the 500 µs fixture completed in 1.321 seconds and retained
35,138 strictly increasing, finite rows. Both controllers switched normally;
the VD-fed controller inhibited its output for the VD-only excursion and
recovered, while the VB-fed controller continued switching. The roles reversed
for the bank-only excursion. Five corrupted-trace/state cases were rejected.
The parent rebuilt the Rust checker with warnings denied and repeated these
checks successfully: [output](feedback-fixture/parent-check.txt),
[guard receipt](feedback-fixture/parent-check.receipt.json),
[parent audit](parent-review.json). The compressed trace is 827,734 bytes.

## Next bounded work

1. Resolve the physical BAT54H connection versus the model's assumed BAV23C
   negative clamp. Bind polarity, location, current-limit interaction and
   temperature-dependent electrical limits before adopting an ECO.
2. Reconcile the reduced gate-protection subcircuit with the retained source;
   reuse existing reset/re-arm evidence where applicable and test only new gaps.
3. Establish source-path/fuse model coverage, without inventing a guaranteed
   clearing time or an ideal disconnect solution.
4. Once those choices are explicit, run a bounded startup/normal experiment
   on the revised feedback topology before selecting another full matrix.

The [plan](../../../../../docs/plans/2026-09-21-pfc-reference-revision-plan.md)
defines this unit's acceptance boundary. The
[campaign closeout](../../../../../docs/evidence/2026-09-21-pfc-campaign-closeout-and-next-revision.md)
preserves earlier successes, failures and incomplete fault attempts.
