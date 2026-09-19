# Passive Rev A native checkpoint

`source-build-01` is the unmodified Atopile exporter output. Its generic
builder staging board is not the authoritative candidate and may carry the
builder's six-layer metadata.

`section.kicad_pcb` here is deliberately the retained routed GBJ2510-F board
from `shunt-repair/candidate`, whose saved bytes declare only `F.Cu` and
`B.Cu`. The replacement is recorded in `validation.json`; no route or
protection change is implied. ERC and DRC were run against these exact bytes.

The Rust source-to-native binding receipt uses the existing
`zapote_erc::source_circuit::Circuit` implementation. Protection remains
conditional; F2 is not present in this baseline.
