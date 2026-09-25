# Gate permission and restart: block D

Luna research handback, reviewed and condensed by the parent on 2026-09-22.
Fifty-three compiled instances: forty-seven RevB parts and the six baseline
standby components. [Exact ownership](component-ownership.json).
No component deletion or new protection acceptance is established here.

## Current contract

At valid operating supplies, source implements:

- health_ok = AND of C's four detector outputs.
- rails_ok = AND of the two TPS3890 reset outputs, with a pulldown.
- clear_ok = health_ok AND rails_ok AND permit_safe AND fast_aux_good.
- A rising buffered ARM clocks the latch with D high; clear_ok low clears it.
- enable_good = run AND clear_ok.
- enable_good permits the BSS138 to pull UCC27511A IN− low and separately
  releases the two-FET UCC28180 VSENSE standby clamp.

Fault recovery alone must not re-arm. Missing/invalid supplies, permit loss,
bus faults and a stuck-high ARM need their own temporal cases. These are
intended contracts; arbitrary brownout behavior is not proved by the Boolean
equations. Inputs and outputs remain HOT referenced.

[RevB source](../../../elec/src/power_entry_f2_shutdown_revb.ato), lines
289–532; [standby connection](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/elec/src/power_entry_pfc_control_candidate.ato),
lines 419–434.

## Why apparent duplicates remain

The slow supervisors qualify valid rails and delay reset release. The separate
fast AUX comparator attempts to latch a brief interruption that the supervisor
may filter out. Driver UVLO turns the driver off while supply is inadequate;
it does not provide the retained fresh-arm policy.
[TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf);
[UCC27511A datasheet](https://www.ti.com/lit/gpn/ucc27511a).

Likewise, direct gate blocking and controller standby have different effects.
The latter changes controller state through VSENSE. Removing it requires
checking compensation, restart and standby behavior, not just observing a
low MOS gate. The external driver's split gate resistors are intentional
turn-on/turn-off paths; the duplicate baseline pair was already removed.

The power-off-tolerant LVC gates/buffers specify Ioff at zero supply. This does
not define HCS latch/AND behavior or the entire analog path during intermediate
supply voltages. The existing fixture models low-voltage behavior as off/reset;
that remains an assumption.
[Fixture limits](../../../zapote/power-entry/passive-reva/protection/f2-shutdown-04/fault-tests/README.md).

## Next bounded simplification unit

Take E's declared rail waveforms and B/C's shutdown-energy envelope as inputs.
Compare the current rail/enable path with one concrete consolidation candidate.
The replacement must retain supply qualification, necessary fast fault capture,
direct disable, controller standby, and fresh-arm behavior unless a requirement
is explicitly shown unnecessary.

Start with isolated loaded-gate fixtures, including rail order, rail return,
ARM/PERMIT held high, each bus fault, and a successful fresh-arm positive
control. Require complete traces, real pre-fault gate activity where relevant,
and retained shutdown until the actual new ARM edge. Keep nominal model
screens separate from guaranteed hardware bounds. Exploration pulse widths
are not automatically product requirements.

There is no justified lower component count yet. More nominal simulations
cannot establish unspecified intermediate-supply silicon behavior.

## Parent review of historical findings

The worker initially treated old fault-review findings as current defects.
The parent and worker inspected the current extractor and resolution record.
The dead LATE_FAULT parameter, truncated absent-rail acceptance and fresh-ARM
coverage findings have been resolved. They are not reopened here.

Current evidence: [resolution](../../../zapote/power-entry/passive-reva/protection/f2-shutdown-04/review-resolution.md);
[extractor](../../../zapote/power-entry/passive-reva/protection/f2-shutdown-04/fault-tests/extract.rs),
full-span/gap checks at 70–120, fresh-arm checks at 141–171, regression cases
at 508–587. This pass read those checks; it did not rerun the simulations.
