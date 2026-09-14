# Bridge physical-model input contract

The versioned `zapote.bridge-physical-model.contract.v1` record describes the
GBU2510A package and the four native bridge lead paths. Every dimension carries
units, provenance, and a nominal/range/status tuple. Native trace and pad
identity is bound by UUID and board SHA-256; a changed hole, net, or package
fails closed.

The model contains one shared package node connected to a cooled sink and to
four lead/barrel/solder nodes. Each lead node is also connected to the
explicit board reservoir (`board_c`), so the package and all four leads are
solved as a single KCL system. The 40 W allowance is a single package design
allowance, not a manufacturer loss rating. It is never copied into each neck.
Neck Joule heat is computed from the PFC branch RMS current and an explicit
lumped screening resistance, then injected once at its lead node; the result
reports package-to-lead, lead-to-board, and package-to-sink flows separately.
That series resistance is only a sensitivity input until the joint-terminal
FEM supplies distributed copper, barrel, solder, and lead electrical paths.

`loss-input.json` records the exact GBU2510A identity and the manufacturer
forward-voltage point used for the diode-loss calculation. The manufacturer
PDF is currently unavailable as a byte archive; therefore the record is
`cached_primary_text` and applicability remains `indeterminate`. A future
byte archive may populate `source_sha256`, but must not change the part or
silently tighten the unknown lead/barrel/solder ranges. Even after a byte
hash check, curve extrapolation and package applicability remain indeterminate.

The point is specified at 12.5 A. If a dynamic resistance is later supplied,
Rust applies it about that reference (`V(i)=Vref+rd*(i-Iref)`) using weighted
waveform first and second moments; it does not add `rd*i²` to a second,
independent voltage intercept.

The PFC waveform is supplied at runtime from
`zapote_harness::pfc_power::Report.waveform`. Its canonical hash is retained in
the assessment. Replay recomputes diode loss and rejects a changed waveform,
branch RMS, contract, board, or summary even when an artifact hash is refreshed.

The result is numerical model evidence only. Package internals, solder wetting,
barrel plating, and chassis cooling are not qualified by this model.
