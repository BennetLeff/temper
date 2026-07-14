# SN74LVC1G38 open-drain NAND gate

**Selected part:** `SN74LVC1G38DBVR` (Texas Instruments, SOT-23-5).

## Temper use

This is the sole device permitted to pull the active-high `RTD_HW_FAULT` net
low. Its inputs are `WINDOW_OK` and upstream-powered `RTD_RAIL_OK`; its output
sinks only when both permissions are high. A 10 kΩ pull-up to upstream
`SAFETY_3V3` therefore asserts the fault on a short, open, brownout, or total
post-ferrite rail loss.

The selected LVC family’s partial-power-down (`Ioff`) behavior is required:
an unpowered `RTD_AVDD` device must not back-power the net or hold it low. Add
the local 100 nF bypass footprint adjacent to the VCC/GND pins.

## Pinout

| Pin | Signal |
|---:|---|
| 1 | A |
| 2 | B |
| 3 | GND |
| 4 | Y (open drain) |
| 5 | VCC |

## Reference

[SN74LVC1G38 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g38.pdf)
