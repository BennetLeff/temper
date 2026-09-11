# `zapote-rtd.v1` input contract

The contract is a typed JSON projection of the existing Atopile/export and
native KiCad measurements. `identity` must include nonempty source, board,
suite, and model revisions and 64-character SHA-256 hashes. A missing or
malformed identity makes the run `indeterminate`. The four
`observed_*_hash` fields are computed by the source/board/suite/model adapter
and must equal the claimed hashes; this catches a well-formed but stale digest.
Native adapters set `native_binding_required` and carry
`native_export_sha256`, `native_extractor_sha256`, and the board hash recorded
at extraction. `native_board_sha256` must equal the current `board_hash`; a
stale or hashless native export is indeterminate.

`board.components`, `board.nets`, `board.connections`, and
`board.connectivity_clusters` are required. The latter is native connectivity
evidence and must have `source: "native"`; it cannot be inferred from a
component or net name. Traces carry points, layer, and width. When
`footprint_pads` are present, each pad must carry finite position and positive
size plus copper layers; a native export without those fields is retained as
an explicit geometry coverage gap. `rtd` contains
the exact MAX31865/connector/RREF topology, the upstream and post-ferrite
rail identities, local bypass declarations, authored SPI series bindings,
hardware-fault output, and the shared REF2025 consumers. `rtd.required_local_ics`
enumerates the ADC, reference, two windows, logic,
rail monitor, and fault gate; each must have a decoupling record whose actual
board capacitor has rail and ground `Connection` entries and measured local
coordinates. `firmware` contains the source GPIO map and threshold encoding parameters. ADC
`board.connections[].pin` values are manufacturer pad numbers; the Rust map
is the MAX31865 SSOP-20 map (DRDY=1, BIAS=4, REFIN+=5, REFIN−=6, FORCE+=8,
RTDIN+=10, RTDIN−=11, FORCE−=12, SDI=14, SCLK=15, CS_N=16, SDO=17,
grounds=9/13/18/19, NC3=20). `scenarios` are
independent expected outcomes used to detect model/checker disagreement.

The native binder loads `zapote/rtd/authored-policy.json` for explicit net
domains, sensitive populations, aggressor source-instance paths, topology,
and HV-to-RTD prohibited pairs. It resolves those source paths through the
source manifest and the extractor's explicit reference mapping, then measures
regions from native pad extents. It never infers policy from net-name
substrings. Missing or unresolved model behavior remains a finding or coverage
gap.

The current Temper source mapping is:

| field | source value |
|---|---|
| ADC | `rtd_pan.adc`, `MAX31865AAP+` |
| connector | `rtd_pan.j_rtd1`, pins FORCE+, SENSE+, SENSE−, FORCE− |
| RREF | `rtd_pan.r_ref`, 430 Ω, `ERA-6AEB431V` |
| SPI | SCK 8, SDI/MOSI 11, SDO/MISO 12, CS 10, DRDY 9 |
| threshold words | low 1526, high 45722 |

The harness reports `pass`, `fail`, or `indeterminate`, per-rule findings,
coverage gaps, and the identity/hash evidence. It never upgrades missing
required input, a documented cable blind spot, or missing native geometry to a
pass.
