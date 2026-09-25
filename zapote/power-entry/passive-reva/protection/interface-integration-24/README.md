# Revision 24: power-entry interface handoff

Date: 2026-09-22. This revision closes a **review and preparation** work package,
not the electrical integration or hardware qualification. Revision 11 remains
the latest compiled full candidate (136 components). Revisions 16 and 19 are
native clamp/reset fixtures; Revisions 20–23 are isolated dynamic investigations.
No PCB, production schematic, part approval or measured hardware result changed.

## Work completed

| Record | Result |
| --- | --- |
| [AUX source decision](source-decision.md) | Reconciles the direct IRM-10-15 proposal, historical IRM-10-24/LDO path, Rev19 LT4363 clamp and separate TPS26601 cutoff option. Selects **IRM-10-15 → Rev19 LT4363** only as the first isolated fixture graph. Sets a safe latched-shutdown/deliberate-re-arm target and documents the missing source fault and load contract. |
| [Bench capture protocol](bench-capture.md) | Defines a low-voltage, isolated startup/fault measurement with synchronized AUX, buck, gate, sense, driver and temperature channels; stimuli, evidence format, uncertainty and stop conditions. **No physical run occurred.** |
| [Control integration audit](control-audit.md) | Maps Rev11 ports and Rev16 reset/control pins, identifies the corrected Rev19 clamp net table, records 17 existing boundary ERC findings and the bindings required before a native candidate build. No new full graph is compiled. |
| [Wider PFC gates](wider-pfc-gates.md) | Keeps ISENSE diode and F1/F2/local-capacitor interruption requirements distinct, with the missing manufacturer and physical bounds stated. No supplier contact or fuse test occurred. |

The initial source recommendation from the delegated review substituted a
TPS26601 cutoff for the LT4363 clamp. Parent review corrected this because a
substitution would change the circuit tested in Revisions 20–23. TPS26601 is
retained as a separate topology to evaluate if interruption is allowed. Parent
review also replaced the Rev16 clamp pin-map reference in the control audit
with the corrected [Rev19 expected pin map](../interface-dynamics-19/clamp-expected.tsv):
R7.1 and D1.2 are on `GATE_DRV`, D1.1 stays on `CG`.

## Decision queue

1. Confirm the intended AUX producer/protection topology and bound the
   recommended **safe latched shutdown with deliberate re-arm** response to a
   source fault. The selected Rev19 LT4363-1 model latches off in the declared
   35 V / 50 ms fixture. Actual switch/relay turn-off and no-restart behavior
   remain unverified.
2. Provide the actual source voltage/current/impedance and fault/restart
   envelope, complete buck and AUX load waveforms, exact assembled capacitor
   population, and hot FET SOA bound. The Mean Well rating and the synthetic
   0.5 Ω source are not replacements for those inputs.
3. Build or identify a physical low-voltage prototype and test equipment. Then
   execute the bench protocol and compare the raw driver-pin rail, startup,
   fault, recovery and FET stress with stated product limits. No such article
   was available during this work.
4. Choose the control interface, identify the Rev11 latch/enable instances,
   and insert Rev19 protection ahead of every AUX consumer in a fresh
   authoritative source candidate. Follow
   [the audited build order](control-audit.md#bounded-native-candidate-build-order-after-bindings-are-fixed)
   and [Revision 25 feasibility report](../interface-integration-25/README.md).
5. Obtain application-specific diode/fuse bounds and repeat the full PFC
   campaign only after a single integrated candidate and its fault envelope
   are fixed.

Manufacturer questions already exist in
[Revision 09](../reference-revision-09/manufacturer-questions.md); they have not
been sent. Neither model output nor a drafted question is supplier evidence.

## Verification scope

The four records were reviewed for topology consistency and local links.
Source electrical numbers are tied to the primary manufacturer data sheets
linked in the individual records. The Rev19 pin-map correction was checked
against the actual `clamp-expected.tsv`. This revision adds documentation only:
there is no fresh ERC, simulation, measured waveform, FET SOA approval or
fuse-coordination result. Working files remain uncommitted in the power-entry
worktree.
