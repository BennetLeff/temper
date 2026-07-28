# TPS3700 undervoltage monitor

**Selected part:** `TPS3700DDCR` (Texas Instruments, SOT-23-6).

## Temper use

The RTD safety path uses OUTA as an upstream-powered `RTD_RAIL_OK` permission.
`INA+` monitors post-ferrite `RTD_AVDD` through a 619 kΩ / 100 kΩ, 0.1%
divider (`ERA-6AEB6193V`, 0805 -- corrected 2026-07-27 from the fabricated
616 kΩ/`ERA-3AEB6163V`; 616 kΩ is not an E96/E192 value, that MPN does not
exist at any distributor, and 616 kΩ is above the top of Panasonic's
ERA-3A/0603 series range -- see
docs/evidence/2026-07-27-era-resistor-resolution.md). OUTA is pulled up to
`SAFETY_3V3`; it is low at RTD_AVDD undervoltage, which prevents the
post-rail open-drain NAND from clearing `RTD_HW_FAULT`.

The captured circuit uses only the INA+/OUTA undervoltage channel. INB− is tied
to ground and OUTB is unused. This is a threshold monitor, not a claimed
hysteretic supervisor; the computed complete threshold range is 2.777–2.882 V.

## Pinout

| Pin | Signal |
|---:|---|
| 1 | OUTA |
| 2 | GND |
| 3 | INA+ |
| 4 | INB− |
| 5 | VDD |
| 6 | OUTB |

## Reference

[TPS3700 datasheet](https://www.ti.com/lit/ds/symlink/tps3700.pdf)
