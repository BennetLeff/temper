# IPW60R017C7 — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

Infineon 600 V MOSFET, U55–U58, TO-247-3 vertical. Pin 1 gate, 2 drain,
3 source; metal tab is drain. Upper drains join rectifier positive; upper
sources and lower drains form L/R; lower sources join rectifier negative.
A shared heatsink requires engineered electrical isolation because the drain
tabs have different potentials. 600 V is a candidate class, not a completed
surge/fault rating decision. Typical hot-resistance/gate curves from the prior
campaign do not establish a guaranteed production maximum or survival.

Retained source: `AR-VERIFY/attempt-001/raw/reused_sources/Infineon-IPW60R017C7.pdf`
under `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/`.
Its SHA256 is retained in the candidate sources manifest.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
