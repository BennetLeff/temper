# Selected connectivity checker

`check.rs` is a dependency-free Rust checker for the generated KiCad
S-expression netlist. It checks selected compiled endpoint relationships only;
it does not run KiCad DRC, qualify parts, or perform placement.

Build and run it without Cargo or the shared target directory:

```sh
rustc --edition=2021 -D warnings check.rs -o graph-check
./graph-check /path/to/build/default.net
```

The checker requires exactly 131 component records. It tokenizes quoted
strings (including escapes), requires one balanced root form, rejects duplicate
component references, duplicate net codes/names, duplicate or cross-net pin
endpoints, and unknown references. Component instance names are derived from
the suffix after the final `::` in each `sheetpath (names ...)` value. This
keeps checks independent of the temporary absolute source path.

The checker checks the candidate's clamp, shunt return, diode/local-VD and bulk
bank separation, PWM and gate-driver resistor separation, standby enable path, permit
buffer, and the AUX/GND controller-driver rails. `logic5` and `hot_arm` are
kept as named ports with no connector attachment. A successful result says
only that these net endpoints are wired as required; MPN identity is checked
separately from the resolved-components receipt because Atopile 0.2.69's
netlist `libsource` field is footprint-group metadata.

Run the fixture and mutant tests with:

```sh
rustc --edition=2021 --test -D warnings check.rs -o graph-check-tests
GRAPH_FIXTURE=/path/to/build/default.net ./graph-check-tests
```

The checked-in candidate fixture exposes that exporter behavior: its
`libsource (part ...)` for `isense_clamp` and `d_boost` is inherited from
another same-footprint component even though the generated BOM records
`BAV23C-E3-08` and `C3D20065D`. Do not change source footprints to work around
this; verify those identities from the resolved-components receipt.
