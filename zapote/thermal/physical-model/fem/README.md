# Bridge lead FEM benchmark

This fixture is a bounded solver and geometry benchmark, not a native-board
qualification model. `input.json` is explicitly marked
`synthetic-benchmark-v1`; the board digest records the comparison context but
does not make the invented dimensions an extraction of the KiCad board.

The Rust CLI emits separate copper, FR-4, solder, plated-barrel and lead
solids, then runs three mesh sizes at two FR-4 domain margins through Gmsh and
Elmer. The copper source is computed from the uniform-path control (`I²R`) and
converted to Elmer's `Heat Source` units (W/kg). Every run retains the Gmsh,
ElmerGrid and ElmerSolver logs in its output directory; replay binds the exact
input bytes and recomputes the geometry/source receipt.

Example invocation:

```text
zapote-lead-fem run INPUT_JSON OUTPUT_DIR GMSH ELMERGRID ELMERSOLVER
```

The first live run after the source-unit fix (`/private/tmp/zapote-lead-fem-live7`)
completed all six cases. The later conforming-fragment run
(`/private/tmp/zapote-lead-fem-live13`) retained a tetrahedral mesh and
external-boundary fluxes, but its physical-material census was incomplete and
is deliberately unqualified. This wrapper is therefore a benchmark harness,
not production board evidence. Package internals, solder wetting, plating
thickness and native pad/trace geometry remain unknown; applicability is
consequently INDETERMINATE.

The next production extension must import the native four-neck geometry,
fragment the solids jointly to preserve conforming interfaces, select only
the package and board cut faces as ports, and couple those port fluxes to the
shared package thermal network.
