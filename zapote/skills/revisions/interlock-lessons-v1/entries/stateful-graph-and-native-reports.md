# Verify stateful behavior on the actual graph and read native findings correctly

Portable procedure; no interlock part value or electrical threshold transfers
to a different unit without fresh evidence.

An early interlock evaluator computed permission from the present reset input,
so it modeled a pulse instead of stored permission. A subsequent evaluator
read an aggregate input instead of the flip-flop's clear pin. Both appeared
plausible when checked only against hand-written inputs. The accepted evaluator
propagates the compiled physical-pin graph and compares its output to a separate
requirement oracle. Mutations bypass the actual clear, clock and NAND pins,
ground D, and exchange Q/QBAR. Stateful traces require reset, healthy operation
without another edge, fault, recovery while reset is held, and a fresh reset.

Use package-specific datasheet pin maps and inspect the rendered schematic.
A copied symbol template can show the wrong pin names despite correct netlist
parity. Exact source/native connectivity does not validate a mistaken device
definition shared by both representations.

Read native report schemas rather than trusting a worker's summary. KiCad ERC
stores findings under `sheets[].violations`; DRC uses root-level `violations`
and separate `unconnected_items`. Reading a missing root ERC field as an empty
list manufactured a zero while stdout and the sheet reported 25 off-grid
warnings. The retained rejected final-native-01 report demonstrates this;
final-native-02/03/04 demonstrate the corrected grid and actual zero counts.
Require the expected schema fields; absence is not an empty result.

A model can verify its declared static boundary while device timing and
power-off behavior remain INDETERMINATE. A local input pullup does not establish
remote power-off isolation, and an invented SENSOR_LIVE signal is not an
implemented liveness producer. Preserve these obligations at integration.

Evidence: `zapote/packages/zapote-harness/tests/interlock.rs`,
`zapote/interlock/evidence/rust-final.json`,
`zapote/interlock/evidence/final-native-01/erc.json`,
`zapote/interlock/evidence/final-native-summary.json`,
and `zapote/interlock/ACCEPTANCE.md`.
