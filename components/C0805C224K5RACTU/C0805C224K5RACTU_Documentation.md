# C0805C224K5RACTU — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

KEMET 220 nF, 50 V, ±10%, X7R, 0805 capacitor candidate; U59/U60.
Each is connected between its high-side floating supply and that leg's L/R
node. Nominal 220 nF implements the selected bootstrap target; it does not
prove effective capacitance under bias/temperature or a minimum VGS.

Part source: [KEMET part specification](https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf).
Package uses locally retained Capacitor_SMD:C_0805_2012Metric. Bias curve and
operating corner qualification remain open; no fitted effective-capacitance
model is claimed.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
