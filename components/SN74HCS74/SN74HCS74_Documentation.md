# SN74HCS74PWR — retained F2 run permission

TSSOP-14 in `elec/src/power_entry_f2_shutdown.ato`. Channel1 uses active-low
CLR1, D2, CLK3, PRE4, Q5, Qbar6; GND7, VCC14. D and CLR receive qualified
health, PRE is high, and raw ARM clocks the flip-flop. Fault recovery alone
cannot generate a clock. Unused channel inputs have defined levels.

[TI datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf); official
[behavioral model](https://www.ti.com/lit/zip/SCEM774) retained in the
`f2-shutdown-03/vendor/` experiment. The independent model fixture checks
retention with ARM held and fresh-edge rearming. It does not qualify power-up:
external rails_ok must hold clear until both supplies and sensing are valid.
