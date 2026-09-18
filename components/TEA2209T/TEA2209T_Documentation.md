# TEA2209T/1 — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

NXP active full-wave bridge controller, U1; SOIC-16 3.9 × 9.9 mm, 1.27 mm pitch.
Pins: 1 L, 2 VCCHL, 3 GATEHL, 4 HVS NC, 5 GATELL, 6 VCC, 7 GND,
8 COMP_POL, 9 COMP NC, 10 GATELR, 11 HVS NC, 12 R, 13 VCCHR,
14 GATEHR, 15 HVS NC, 16 VR. GND/COMP_POL reference rectifier negative,
not the downstream side of U12. Bootstrap returns are L/R, not ground.
COMP is left open; HVS pins have no external connection. The candidate uses
220 nF bootstrap and 2.2 µF VCC capacitors. Effective capacitance, startup,
leakage and gate-charge corners remain qualification inputs. Gate disable
cannot disconnect the body-diode mains path.

Source: [NXP datasheet](https://www.nxp.com/docs/en/data-sheet/TEA2209T.pdf).
The retained manufacturer PDF and digest are in the candidate sources manifest.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
