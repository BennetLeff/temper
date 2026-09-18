# 006710340 — active-rectifier candidate

2026-09-18. Exact part selected for the experimental power-entry revision.

ETI CH14-PCB clip; two clips per U66 fuse assembly. The retained Green
Protect catalogue PDF p34 / printed p36 supplies the clip dimensions.
It is a clip drawing, not a manufacturer PCB land pattern. Assembly spacing,
slot allowances, leg orientation and Mersen cartridge engagement require
mechanical verification. Its stated CH gPV application rating is not a
qualification of this combined Mersen assembly.

Source: [ETI catalogue](https://files.eti.si/levels/en-GB/4309_TD.pdf), retained
with SHA256 in the candidate sources directory. See candidate MECHANICAL.md.

This is a construction candidate, not an approved production substitution.
No stock/price, assembly fit, interruption, installed cooling or hardware
qualification is asserted. See [validation](../../zapote/power-entry/active-rectifier/VALIDATION.md) and the
[parent qualification handoff](../../zapote/power-entry/CLOSEOUT.md).
Local KiCad footprints are vendored with the candidate; no global library
resolution is required. The [authored source](../../elec/src/power_entry_active_unit.ato)
and [BOM](../../zapote/power-entry/active-rectifier/bom.csv) are the implementation references.
