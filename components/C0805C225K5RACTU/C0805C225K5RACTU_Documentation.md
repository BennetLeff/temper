# C0805C225K5RACTU — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

KEMET 2.2 µF, 50 V, ±10%, X7R, 0805 capacitor candidate; U61.
VCC-to-rectifier-negative controller bypass, not downstream PFC ground.
Nominal capacitance is not an effective-capacitance guarantee at operating
bias and temperature. Startup/control qualification remains open.

Part source: [KEMET X7R specification](https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf).
Package uses locally retained Capacitor_SMD:C_0805_2012Metric. No effective
capacitance or lifetime model is claimed for this checkpoint.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
