# Buck Rev A export visual review — C11/C12 replacement binding

Reviewed 2026-09-10 from outputs generated with KiCad CLI 10.0.6 after the
approved C11/C12 substitution to Samsung CL32B226KAJNNWE.

- Front/back copper, mask, silk and Edge.Cuts SVGs are present for visual
  review. Paste is present as Gerber output for stencil manufacture; the
  exporter does not emit paste SVGs. Matching Gerbers and the job file are in
  the fabrication ZIP.
- The one-page assembly drawing was rasterized and visually inspected. The
  50 × 40 mm outline, four isolated M3 holes, U3/L2/capacitor placement,
  J1/J2 positions, TP1–TP4 labels and front silk are present. J1/J2 are
  excluded from SMT positions and listed for manual installation.
- Plated and non-plated drill-map PDFs were opened; NPTH shows the four M3
  holes and PTH shows the connector holes.
- `positions-full.csv` has 11 footprints and `positions-smt.csv` has 9; the
  exact difference is J1/J2. No TP5 footprint is present.
- The ZIP was opened and checked: eight Gerbers plus job file, two Excellon
  files and two drill maps, with no docs or procurement files mixed in.

This inspection does not imply fabricated or powered hardware. The nine
unfilled via-in-pad joints still require the manual solder and magnified
inspection treatment in `docs/assembly-notes.md`.
