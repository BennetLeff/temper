# Reconciled buck source build

The isolated Atopile 0.2.69 build and resolved attribute export succeeded on
2026-09-10. `collection.json` retains tool commands, source hashes, artifact
hashes and the nine resolved components. `default.net`, `default.csv` and
`resolved-components.json` retain the compiled outputs.

C9 is Samsung CL32B106KBJZW6E. C10/C13 are 100 nF ±10%, 50 V;
C11/C12 are 22 µF ±10%, 25 V. The circuit contract and source now agree on
these exact values and ratings. This build establishes source identity and
compiler assertions, not effective capacitance or transient performance.

The project-wide `make netlist` also completed using pinned Atopile and
regenerated the ignored build outputs and build stamp. Its log is retained.
The BOM/source reconciliation gate passed with zero new findings across 160
BOM rows and 168 source instantiations; its two existing allowlisted backlog
items are unrelated to this buck change.

The first sandboxed build could not access the installed uv cache. The
retained successful build ran with that cache available; the failed attempt
was an environment failure, not a circuit result.
