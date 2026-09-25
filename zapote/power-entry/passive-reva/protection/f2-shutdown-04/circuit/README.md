# F2 shutdown revision B circuit contract

This folder records the circuit topology for `PowerEntryF2ShutdownRevB` in
[`elec/src/power_entry_f2_shutdown_revb.ato`](../../../../../../elec/src/power_entry_f2_shutdown_revb.ato).
It is a simulation and compiled-graph candidate (79 physical parts). It is
not an assembled-board change and does not qualify the F2 protection hardware.

The detector retains the prior architecture: two tapped VD/VB dividers,
four TLV3202 comparisons, an SN74HCS21 health gate, and an SN74HCS74 latch.
`health_ok` combines all four bus-voltage comparisons through HCS21 gate1.
`clear_ok` is the second HCS21 output, `health_ok & rails_ok & permit_safe & fast_aux_good`,
and drives the active-low asynchronous clear. The latch D input is logic5 and
CLK is the buffered ARM edge; therefore a held ARM level cannot re-arm after a fault
or rail return. `enable_good` is a separate LVC AND of retained `run` and
`clear_ok`, qualifying the driver boundary as well.

## Supply supervision

Both TPS389001DSER supervisors are powered from logic5. `sup_logic` senses
logic5 with 294 kOhm/100 kOhm (4.53 V nominal falling trip). `sup_aux` senses
aux15 with 1.03 MOhm/100 kOhm (12.995 V nominal falling trip) through a 47 kOhm
SENSE isolation resistor. Each CT pin has a 100 pF capacitor to ground. Using
the TI timing relationship `tPD(r) = C(µF)·1.07 + 25 µs`, this is approximately
132 µs typical reset-release delay; it is a startup hold, not a claimed guaranteed
system latency.

The active-low open-drain RESET outputs are pulled up to logic5 and ANDed in
an SN74LVC1G08DBVR. An explicit 100 kOhm pulldown on `rails_ok` makes the
qualified rail signal low when logic5 is absent. The Ioff-rated LVC device is
the logic-domain boundary: its output is high impedance while VCC5=0 and does
not source a dead logic rail.

An additional TLV3202 channel powered from logic5 senses aux15 through
430 kOhm/100 kOhm against the logic-powered 2.5 V reference. Its nominal
13.25 V falling trip feeds the fourth input of HCS21 gate2, so a
qualifying aux15 loss clears the latch within the comparator/logic propagation
path instead of waiting for the slower TPS3890 reset timer. The host transient
test must exercise an aux15 pulse below 13.25 V for at least 1 us; this path
remains an engineering model pending bench timing characterization.

## Default-off gate-driver interface

The candidate uses TI UCC27511ADBVR rather than relying on the UCC27624 EN
pull-up. UCC27511A IN+ is the PWM input; IN- is a hardware-disable input with
an internal VDD pull-up. A BSS138 N-MOS (1 kOhm gate resistor, 100 kOhm
gate-source pulldown, and explicit 1 kOhm aux15 pullup on IN-) pulls IN- low
only while `enable_good` is high. The pullup is a 1210 part sized for the
approximately 0.324 W worst-case at 18 V. With logic5 absent, the MOSFET is off
and IN- is high, so aux15 cannot enable the output. With aux15 absent, the
driver UVLO keeps both outputs low. Separate 10 Ohm 1206 resistors on OUTH and
OUTL drive the gate path, with a 10 kOhm gate-source pulldown fitted.

The divider sense inputs each include 22 kOhm series isolation and 47 pF
high-node filters. At a charged 500 V bus, a conservative dead-rail bound adds
both full HV-divider currents plus the fast-aux divider and supervisor/Ioff
paths (the comparator current is already bounded by its divider supply): approximately 1.09 mA through the shared 220
Ohm logic5 bleeder, or 0.24 V. ARM and permit cross into the HCS domain
through Ioff-rated SN74LVC1G17DBVR Schmitt buffers with physical pin mapping
2=A, 4=Y, 5=VCC and 3=GND, plus 10 kOhm output pulldowns; PWM has a 1 kOhm
source resistor and 10 kOhm pulldown at IN+.

These are bounded design calculations; the host must still measure unpowered
clamp currents on the selected parts. The LVC Ioff behavior at VCC5=0 and the
buffer output modeled OFF below 1.65 V are fixture assumptions, not guaranteed
partial-power transfer behavior.

## Primary references

- [TLV3202 datasheet](https://www.ti.com/lit/ds/symlink/tlv3202.pdf)
- [SN74HCS21 datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf)
- [SN74HCS74 datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf)
- [TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
- [SN74LVC1G08 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf)
- [SN74LVC1G17 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf)
- [UCC27511A datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf)
- [Nexperia BSS138 datasheet](https://assets.nexperia.com/documents/data-sheet/BSS138.pdf)
