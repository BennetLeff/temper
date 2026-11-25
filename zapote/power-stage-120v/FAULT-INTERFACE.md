# Fault-high controller interface

`u_nand` uses SN74LVC1G10DBVR and `u_iso` (U9) uses Chipanalog CA-IS3720HW
(H suffix: default output high; TI ISO7710DWR until stage 31, DECISIONS 34).
J4.10 is BUS_FAULT = OR(isolated bus fault, CT_OC_POS, CT_OC_NEG), from
`u_fault_or` (SN74LVC1G332DBVR, 3-input OR, SELV side, powered from J4.3). The isolated
bus fault is the U9 output of NOT(OCP_OK_HOT AND OVP_OK_HOT AND
HOT5_OK_HOT). The HOT5_OK_HOT input comes from a Schmitt-buffered TPS3700
undervoltage detector powered independently from V15_LS. The
tank-CT comparators (`u_ct_pos` and `u_ct_neg`) trip at 73.19 A nominal either
polarity, band 67.36–79.32 A (stage 54, DECISIONS 81; COMMISSIONING B9). The 55 A model in
tools/ct_detector/README.md is the 1:100 / 1.5 Ω detector this replaced.
Since stage 30 the isolated bus fault (U9.13) reaches the OR through R134 1 kΩ / C167 100 pF,
which filters ns-wide CMTI upsets (DECISIONS 33). Since stage 55 the RC node drives U47
(SN74LVC1G17 Schmitt buffer, C179 decoupling), and U47.Y drives U13.A. The LVC1G332 input is
not a Schmitt input and is limited to 10 ns/V (SCES489E p.3); the RC edge is 93–133 ns/V.
The buffer switches at VT+ ≤ 1.92 V plus tpd ≤ 6.5 ns, so the slow-corner trip delay through
the RC is 107.0 ns (107.7 ns at stage 54). A full-swing upset shorter than 52 ns is rejected
(25 ns at stage 54). Source: DECISIONS 82, `validation-results/11-candidates/c55-findings/results/u13-edge.md`.
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
within the interlock's 3.135–3.465 V contract. U9 does not drive J4.10: U13 does, so the
interlock's ≥2.7 V high / ≤0.3 V low at about 350 µA is U13's to meet (below). U9 only has to
switch U47: CA-IS3720 specifies VOH ≥ VDDO−0.4 V and VOL ≤ 0.4 V at 2 mA (v1.05 s.7.8, 3.3 V
table), i.e. ≥2.735 V at the lowest rail against U47's VT+ ≤ 1.92 V. Harness drops/loading must
preserve the J4.10 levels. Merely meeting the isolator's 2.375 V operating minimum is insufficient.
This truth table does not qualify an open return wire, missing controller
supply, shutdown delay or latch/reset sequencing.

TI SCES486E page 1 gives the new NAND's DBV pin map.
TI SCES489E page 1 gives the SN74LVC1G332 DBV pins A1, GND2, B3, Y4, VCC5,
C6; tpd ≤ 4.5 ns at 3.3 V. Its VOH at 3.3 V with the interlock's ≈350 µA load
is near VCC, which meets the ≥2.7 V requirement; re-check VOH at the lowest rail
when the interlock load is qualified.
CA-IS372x v1.05 Table 9-1 makes the H-suffix output follow its input when powered and
default high on input-side power loss (or an open input) with the output side powered.
[SN74LVC1G10](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf),
[CA-IS3720](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2404091718_Chipanalog-CA-IS3720LW_C2890049.pdf).

## Brownout correction and remaining boundary

TLV3201 operation is specified only from 2.7 V. CA-IS3720 requires at least
2.375 V for normal operation; its UVLO is 1.95–2.375 V rising and 1.88–2.325 V falling, and its
output is undetermined between the two (v1.05 s.7.3, Table 9-1 note 3). A collapsing or recovering HOT5 rail therefore has an
unqualified comparator interval. Startup/recovery must independently keep
PERMIT inhibited until the fault detector is valid; falling-supply behavior
also needs a guaranteed shutdown path. Do not
model the isolator's 2.375 V recommended minimum as its falling UVLO.

HOT5 comes from a 78L05 on V15_LS. A regulator fault can lower HOT5 while
V15_LS remains 15 V. `u_hot5_uv` (TPS3700DDCR) was therefore powered from
V15_LS and senses HOT5 through 105 kΩ / 10 kΩ.

**Stage 48 (B13 H1, c48-ldo-en-ref-watch): U14 VDD and its cap C48 are on
HOT5.** U14's second channel is now the REF25 watchdog (INB− on a 63.4 k /
11.7 k tap of REF25, OUTB wired to OUTA on HOT5_UV_RAW), and INB− (pin 4)
sits next to VDD (pin 5): on V15_LS a pin 4–5 short would put ~15 V on a 7 V
abs-max input (SBVS187G 6.1 p.5). On HOT5 it puts ≤ 5.5 V there and drives
OUTB low (a fault, not a silent loss). The UV detection still covers a
regulator that sags: VIT± are specified unchanged from VDD 1.8 V to 18 V
(6.5 p.6), below UVLO OUTA is driven low (note 3 p.6), and below V(POR)
0.8 V the HOT5 pull-up of OUTA, the Schmitt buffer and U9 side A are
unpowered together (U9 defaults high). A regulator that fails high (IN–OUT
short, HOT5 → V15_LS ≤ 15.46 V) stays inside U14's 18 V VDD range.

OUTA is low on undervoltage,
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
[TPS3700](https://www.ti.com/lit/ds/symlink/tps3700.pdf),
[SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).

The source audit enforces the exact NAND / default-high isolator parts, comparator polarity,
HOT5 divider and isolated output path. Mutation tests reject the old AND,
old F part, missing or mispowered HOT5 supervisor, disconnected header,
and added local output loads. These are source checks, not powered tests.
