# Buck Rev A BOM reconciliation

This receipt binds the generated KiCad BOM and netlist to the purchasing BOM.
The KiCad 10.0.6 default BOM exporter emits reference/value/footprint rows but
does not emit the custom Manufacturer/MPN fields reliably on this project, so
those exact purchasing fields are taken from the generated netlist and checked
against `../../procurement/bom.csv`.

- Generated BOM: `../assembly/schematic-bom.csv`
- Purchasing BOM: `../../procurement/bom.csv`
- Generated netlist: `schematic-netlist.kicadsexpr`
- Populated SMT references: C9, C10, C11, C12, C13, L2, R16, R17, U3 (9)
- Manual THT references: J1, J2 (2)
- Non-purchased copper probes: TP1–TP4; absent TP5
- C11/C12 generated netlist identity: Samsung Electro-Mechanics,
  `CL32B226KAJNNWE`, 22 uF 25 V X7R, `C_1210_3225Metric`
- C11/C12 purchasing identity: DigiKey `1276-3393-1-ND`, observed 770 in
  stock on 2026-09-10; DC-bias behavior remains unverified.

The generated netlist and BOM were produced by `export-release.sh` from the
frozen Rev A schematic. This is a reconciliation receipt, not a claim of
component qualification or hardware testing.
