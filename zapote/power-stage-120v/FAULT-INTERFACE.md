# Fault-high controller interface

U8 uses SN74LVC1G00DBVR and U9 uses ISO7710DWR (without F).
J4.10 is BUS_FAULT. The NAND output is NOT(OCP_OK_HOT AND OVP_OK_HOT).
Both selected devices retain their previous pad mappings; U9 retains the
8.1 mm high-voltage land pattern.

| Condition | J4.10 | Receiving interlock |
| --- | --- | --- |
| OCP and OVP both healthy, supplies valid | Low | Healthy |
| OCP trips, OVP trips, or both trip | High | Fault |
| HOT input side fully unpowered; controller output supply valid | High after isolator default-output delay | Fault |
| Signal conductor broken; interlock supply/return valid | Power-board output is disconnected; receiving input rises through its 10 kΩ pullup | Fault |

The [interlock](../interlock/INTERFACES.md) expects fault-high, so no polarity
adapter is required. Connect this output to a designated active-high fault
input; the unused fault inputs retain their own integration requirements.
Require the shared controller rail at J4.3 and the interlock supply to remain
within the interlock's 3.135–3.465 V contract. ISO7710 specifies VOH ≥ VCC2−0.3 V
and VOL ≤0.3 V at 2 mA in this supply range. At the lowest allowed rail that
gives ≥2.835 V high; the interlock requires ≥2.7 V high and ≤0.3 V low, with
about 350 µA maximum pullup load. Harness drops/loading must preserve these
levels. Merely meeting the isolator's 2.25 V operating minimum is insufficient.
This truth table does not qualify an open return wire, missing controller
supply, shutdown delay or latch/reset sequencing.

TI SCES212AC §4 gives the NAND's DBV pins A1, B2, GND3, Y4, VCC5.
TI SLLSER9E §7.4 makes the ISO7710 output follow its input when powered and
default high on input-side power loss with the output side powered.
[SN74LVC1G00](https://www.ti.com/lit/ds/symlink/sn74lvc1g00.pdf),
[ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf).

## Brownout remains unresolved

TLV3201 operation is specified only from 2.7 V. ISO7710 requires at least
2.25 V for normal operation and guarantees its powered-down state at ≤1.7 V;
its falling UVLO is 1.7–1.8 V. A collapsing or recovering HOT5 rail therefore has an
unqualified comparator interval. Startup/recovery must independently keep
PERMIT inhibited until the fault detector is valid; falling-supply behavior
also needs a guaranteed shutdown path. Do not
model the isolator's 2.25 V recommended minimum as its falling UVLO.

HOT5 comes from a 78L05 on V15_LS. A regulator fault can lower HOT5 while
V15_LS remains 15 V. The gate drivers monitor their own output supplies, so
their UVLO does not prove shutdown for this fault. A HOT5 supervisor in the
hardware shutdown path, or another independently justified system measure,
is still needed to close this case. Controller-side 3.3 V loss likewise does
not have a guaranteed U9 output and must be evaluated against the complete
interlock/driver supply chain.
[TLV3201](https://www.ti.com/lit/ds/symlink/tlv3201.pdf),
[UCC21550](https://www.ti.com/lit/ds/symlink/ucc21550.pdf).

The source audit enforces the exact NAND/non-F parts, comparator polarity,
output path and header pin. Mutation tests reject the old AND, old F part,
a disconnected header, and added local output loads. These are source checks, not powered tests.
