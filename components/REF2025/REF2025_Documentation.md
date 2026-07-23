# REF2025 precision reference

**Selected part:** `REF2025AIDDCR` (Texas Instruments, SOT-23-5).

## Temper use

The RTD hardware-fault window uses the 1.25 V `VBIAS` output as the source for
two 0.1% threshold dividers. It is powered and enabled from upstream
`SAFETY_3V3`, rather than post-ferrite `RTD_AVDD`, so thresholds remain defined
while the RTD analogue rail is being declared unsafe.

`VREF` is intentionally unused in this design. The local 100 nF bypass
capacitor is a placement requirement for the `VIN` supply pins.

## Pinout

| Pin | Signal |
|---:|---|
| 1 | VBIAS (1.25 V) |
| 2 | GND |
| 3 | EN |
| 4 | VIN |
| 5 | VREF (2.5 V) |

## Reference

[REF2025 datasheet](https://www.ti.com/lit/ds/symlink/ref2025.pdf)
