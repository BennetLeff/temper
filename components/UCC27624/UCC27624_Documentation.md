# UCC27624D — isolated F2 gate-disable interface

SOIC-8 in `elec/src/power_entry_f2_shutdown.ato`: ENA1, INA2, GND3, INB4,
OUTB5, VDD6, OUTA7, ENB8. AUX15 powers VDD; retained latch Q drives ENA,
PWM drives INA. INB/ENB are grounded. OUTA drives the retained 10 Ω/1206
gate resistor, with a 10 kΩ gate-source pulldown and local 1 µF/100 nF bypass.

[TI datasheet](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) and official
[PSpice model](https://www.ti.com/lit/zip/SLUM884). The exact model is retained
in `zapote/power-entry/passive-reva/protection/f2-shutdown-03/vendor/`.
Its loaded-output check is conditional on the authored gate-capacitance load;
it is not an exact STW65N65DM2AG current-turnoff model.

ENA has an internal pullup whose resistance is specified typically. The
external 2.2 kΩ pulldown improves nominal default-low margin, but unpowered
logic/back-power behavior and worst-case pullup strength remain unqualified.
