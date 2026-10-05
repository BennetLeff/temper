# Fault-high controller interface

`u_nand` uses SN74LVC1G10DBVR and `u_iso` uses ISO7710DWR (without F).
J4.10 is BUS_FAULT = OR(isolated bus fault, CT_OC_POS, CT_OC_NEG), from
`u_fault_or` (SN74LVC1G332DBVR, 3-input OR, SELV side, powered from J4.3). The isolated
bus fault is the ISO7710 output of NOT(OCP_OK_HOT AND OVP_OK_HOT AND
HOT5_OK_HOT). The HOT5_OK_HOT input comes from a Schmitt-buffered TPS3700
undervoltage detector powered independently from V15_LS. The
tank-CT comparators (`u_ct_pos` and `u_ct_neg`) trip at ≈55 A either
polarity; see tools/ct_detector/README.md.
isolator retains its 8.1 mm high-voltage land pattern. The NAND is now a
six-pin part; its DBV pins are A1, GND2, B3, Y4, VCC5, C6.

| Condition | J4.10 | Receiving interlock |
| --- | --- | --- |
| OCP, OVP and tank-CT healthy, HOT5 above its supervised threshold, supplies valid | Low | Healthy |
| Any of OCP, OVP or tank-CT over-current trips, or supervised HOT5 drops below threshold while V15_LS remains valid | High | Fault |
| HOT input side fully unpowered; controller output supply valid | High after isolator default-output delay | Fault |
| Signal conductor broken; interlock supply/return valid | Power-board output is disconnected; receiving input rises through its 10 kΩ pullup | Fault |

The existing interlock expects fault-high, so no polarity
adapter is required. Connect this output to a designated active-high fault
input; the unused fault inputs retain their own integration requirements.
Its receiver contract was inspected in `ps-oracle` at commit
`fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, in
`zapote/interlock/INTERFACES.md`; that separate circuit is not copied into
this source-candidate package.
Require the shared controller rail at J4.3 and the interlock supply to remain
within the interlock's 3.135–3.465 V contract. ISO7710 specifies VOH ≥ VCC2−0.3 V
and VOL ≤0.3 V at 2 mA in this supply range. At the lowest allowed rail that
gives ≥2.835 V high; the interlock requires ≥2.7 V high and ≤0.3 V low, with
about 350 µA maximum pullup load. Harness drops/loading must preserve these
levels. Merely meeting the isolator's 2.25 V operating minimum is insufficient.
This truth table does not qualify an open return wire, missing controller
supply, shutdown delay or latch/reset sequencing.

TI SCES486E page 1 gives the new NAND's DBV pin map.
TI SCES489E page 1 gives the SN74LVC1G332 DBV pins A1, GND2, B3, Y4, VCC5,
C6; tpd ≤ 4.5 ns at 3.3 V. Its VOH at 3.3 V with the interlock's ≈350 µA load
is near VCC, which meets the ≥2.7 V requirement; re-check VOH at the lowest rail
when the interlock load is qualified.
TI SLLSER9E §7.4 makes the ISO7710 output follow its input when powered and
default high on input-side power loss with the output side powered.
[SN74LVC1G10](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf),
[ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf).

## Brownout correction and remaining boundary

TLV3201 operation is specified only from 2.7 V. ISO7710 requires at least
2.25 V for normal operation and guarantees its powered-down state at ≤1.7 V;
its falling UVLO is 1.7–1.8 V. A collapsing or recovering HOT5 rail therefore has an
unqualified comparator interval. Startup/recovery must independently keep
PERMIT inhibited until the fault detector is valid; falling-supply behavior
also needs a guaranteed shutdown path. Do not
model the isolator's 2.25 V recommended minimum as its falling UVLO.

HOT5 comes from a 78L05 on V15_LS. A regulator fault can lower HOT5 while
V15_LS remains 15 V. `u_hot5_uv` (TPS3700DDCR) is therefore powered from
V15_LS and senses HOT5 through 105 kΩ / 10 kΩ. OUTA is low on undervoltage,
is pulled up to HOT5 through 10 kΩ, and enters a Schmitt buffer before the
three-input NAND. This avoids contention with the two push-pull comparator
outputs and avoids feeding the supervisor's slow open-drain edge directly to
an ordinary logic input. Nominal thresholds are 4.60 V rising and 4.54 V
falling. The source audit pins the independent supply and the full path.

This corrects the missing **steady supervised brownout input**, not the
complete fault-to-current-extinction path. TPS3700's 450 µs maximum
power-on delay means the external interlock must hold PERMIT disabled until
the monitor and controller are proven valid. Its 18 µs fall delay is specified
only for a 5 V supply and 10 mV input overdrive; it is not a guaranteed
maximum across a collapsing HOT5 rail. Test the real regulator collapse,
signal latch, isolator, interlock, DIS, and FET turn-off. Latch the fault
before the logic and isolator supplies leave their operating ranges.
Controller-side 3.3 V loss and shorted-FET interruption remain separate
system tests.
[TLV3201](https://www.ti.com/lit/ds/symlink/tlv3201.pdf),
[UCC21550](https://www.ti.com/lit/ds/symlink/ucc21550.pdf),
[TPS3700](https://www.ti.com/lit/ds/symlink/tps3700.pdf),
[SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).

The source audit enforces the exact NAND/non-F parts, comparator polarity,
HOT5 divider and isolated output path. Mutation tests reject the old AND,
old F part, missing or mispowered HOT5 supervisor, disconnected header,
and added local output loads. These are source checks, not powered tests.
