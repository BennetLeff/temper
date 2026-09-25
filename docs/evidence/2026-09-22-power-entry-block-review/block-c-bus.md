# Bus protection and stored energy: block C

Luna research handback, reviewed and condensed by the parent on 2026-09-22.
Thirty-seven compiled instances: seven bank/filter/bleeder components plus
thirty bus-sensing components. Exact allocation:
[component ownership](component-ownership.json).

## Contract and ownership

C owns c1–c4, c_hf, bleeder1/2; two eight-element VD/VB dividers; reference
and bias; two dual comparators; eight input-isolation resistors; and two
comparator bypass capacitors. D owns the shared health AND package and its
bypass, while D also consumes C's reference for its fast AUX comparator.

Inputs are VD, VB, HOT return and logic5. Four push-pull comparator outputs
feed separate D logic inputs. They must not be wired together as a wired-OR.
Outputs represent two absolute-overvoltage and two mismatch channels, not
proof of fuse continuity.

[Current candidate](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/elec/src/power_entry_pfc_control_candidate.ato),
lines 401–417, puts bank capacitors/filter and the series bleeders on VB.
Local VD reservoir, F2, holder/interconnect and any added local-energy
treatment remain external to the 131-instance graph.
[Integration map](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/integration-map.md).

## Necessity and limits

Local-VD controller feedback does not prove that the external latch sets
before a controller retry. Existing threshold-corner overlap is a reason to
investigate the dynamic behavior, not a trajectory proof.
[Prior architecture assessment](../../../zapote/power-entry/passive-reva/protection/ARCHITECTURE-REDUCTION.md).

Retain the current sensing functions as the comparison baseline. Equal VD
and VB, including equally charged or discharged nodes, cannot distinguish an
open fuse from a closed fuse.

Bank reverse discharge requires a reverse-conducting failed diode and a
conducting MOS. The MOS can be healthy during detection/turn-off delay or
failed-short. A healthy reverse-blocking diode prevents this particular path.
F2 can lie in the bank loop but does not interrupt stored energy already in a
VD-side reservoir. Gate commands cannot clear a failed-short MOS.
[Fault-loop record](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/fuse-coordination.md).

## First decisive simplification check

Compare current four-channel sensing against a specifically defined
absolute-OV/local-VD-feedback alternative that still retains a fault latch.
Exercise F2 opening during startup and established running, both charge
polarities, both nodes initially discharged, and residual-charge restart.
Observe controller retry, latch, actual gate activity and VD/VB energy.

Keep all failures visible. A deletion is justified only if the alternative
preserves required shutdown/restart behavior over the declared envelope,
with applicable timing/error bounds and explicit remaining model limits.
Passing a provisional voltage screen is not component-voltage qualification.
This comparison does not itself qualify F2.

F2 capacitor-discharge waveform applicability, total clearing/let-through,
arc limits and physical withstand remain external data needs.
[Mersen catalogue](https://www.mersen.com/sites/default/files/medias/files/2024-12/HS-High-Speed-Fuses-Mersen-EN.pdf).

## Parent review

The historical 21-part TLV1704 sensing experiment is not a demonstrated
replacement for today's thirty sensing components. The subsequent
[timing audit](../../../zapote/power-entry/passive-reva/protection/f2-timing-02/README.md)
found its applicable maximum delay missing; the present RevB uses TLV3202.
The parent corrected the initial donor-source citation and the overly narrow
“both devices failed-short” description. No component saving is claimed.
