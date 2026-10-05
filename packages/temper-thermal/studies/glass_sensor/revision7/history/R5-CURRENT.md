# Current through-glass sensor CAD

**R5 — development dry comparison, not released.** The 6 mm head is the next comparison coupon; the 8 mm head remains its control. Both retain unresolved seal, contact-detection and physical qualification gates.

- [6 mm assembly STEP](revision5/mechanical/R5-D6-rest.step)
- [6 mm cap STEP](revision5/mechanical/R5-D6-cap.step)
- [8 mm reference assembly STEP](revision5/mechanical/R5-D8-rest.step)
- [All motion poses and build details](revision5/mechanical/README.md)
- [R5 report](revision5/report.html) and [evidence ledger](revision5/validation/gaps.json)
- [Exact CAD identities](current-cad.json) and [complete revision provenance](revision5/source-provenance.json)

The full modeled covers, bond films, weld regions, anchor, and four smooth 60 mm wire routes are included. The thermal network reads the corresponding CAD scalar export. Independent cap STEP reimport checks verify its area and volume.

Nominal simulated D6 response is 2.94 s to 90% of the pan step with 2.47°C thermal underread at 200°C. This does not meet the combined <2 s / <2°C whole-system target. All physical tests are NOT_RUN. R1–R4 remain historical records; the separate pressure-reference apparatus is an unconnected dry bench reference, not a sealed cartridge assembly.
