# A70QS50-14F — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

Mersen 14 × 51 mm fuse candidate, functional F2 / compiler reference U66.
Series location: BOOST_DIODE_POSITIVE → fuse → PFC_BUS_PLUS_390V.
The bank, output and bulk bleeders are bank-side; feedback and local 470 nF
are diode-side. No clearing/withstand coordination is demonstrated. The
manufacturer application inquiry remains unsent. No generic AC I²t or
nominal average-current calculation qualifies this capacitor-discharge duty.

Two ETI 006710340 clips are separate assembly parts. The combined footprint
is provisional; see [mechanical assumptions](../../zapote/power-entry/active-rectifier/MECHANICAL.md).
Source/selection trail: parent CLOSEOUT Q1/Q2 and campaign AR-MERSEN/AR-BOUNDS.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
