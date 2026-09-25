# SN74HCS21PWR — F2 health combining logic

TSSOP-14 dual four-input AND in `elec/src/power_entry_f2_shutdown.ato`.
Gate 1: inputs1/2/4/5, output6. Gate 2: inputs9/10/12/13, output8.
VCC14, GND7; pins3/11 NC. All inputs are Schmitt inputs.

Gate1 combines four detector outputs; gate2 combines that result, external
aggregate rails_ok, permit and tied-high logic5 to release the latch clear.
It does not gate ARM or independently generate run permission.
[TI datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf), retained in
`zapote/power-entry/passive-reva/protection/f2-timing-02/sources/`.
22 ns at 4.5 V/50 pF is fixture-specific; supplied rail qualification is external.
