# SN74LVC1G08 single AND gate

**Selected part:** `SN74LVC1G08DBVR` (Texas Instruments, SOT-23-5).

## Temper use

The gate combines the RTD window comparator outputs into
`WINDOW_OK = LOW_OK AND HIGH_OK`. It is powered from post-ferrite `RTD_AVDD`
and receives its own local 100 nF bypass footprint. Its output is only a
permission input to the downstream default-high fault stage; loss of this
post-rail logic cannot clear `RTD_HW_FAULT`.

`simulation/models/SN74LVC1G08_ngspice.lib` is the portable static model used
by the full RTD ngspice deck. Its high-impedance invalid-supply state is
resolved by the schematic's 100 kΩ `WINDOW_OK` pull-down.

## Pinout

| Pin | Signal |
|---:|---|
| 1 | A |
| 2 | B |
| 3 | GND |
| 4 | Y |
| 5 | VCC |

## Reference

[SN74LVC1G08 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf)
