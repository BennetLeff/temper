# TLV3202IDR — isolated F2 detector

Two SOIC-8 dual comparators provide four separate push-pull health outputs in
`elec/src/power_entry_f2_shutdown.ato`. Pins: 1 OUT1, 2 IN1−, 3 IN1+, 4 GND,
5 IN2+, 6 IN2−, 7 OUT2, 8 VCC. Supply is externally regulated HOT 5 V.
Outputs must not be tied together.

[TI datasheet](https://www.ti.com/lit/ds/symlink/tlv3202.pdf), retained under
`zapote/power-entry/passive-reva/protection/f2-timing-02/sources/`.
Its full-temperature 55 ns limit applies to specified overdrive/load conditions;
it does not establish this circuit's ramp response. Charged-bus input injection
with logic unpowered remains unqualified. No production PCB integration.
