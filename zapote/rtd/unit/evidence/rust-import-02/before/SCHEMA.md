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
coordinates plus footprint pads when native geometry is available. Rust checks
the actual capacitor and IC rail and return pads; a global net cluster alone
is insufficient to excuse a long return. Center-to-center locality is only a compatibility fallback for
synthetic inputs without pad geometry; native inputs missing named pad/path
geometry are indeterminate. `firmware` contains the source GPIO map and threshold encoding parameters. ADC
`board.connections[].pin` values are manufacturer pad numbers; the Rust map
is the MAX31865 SSOP-20 map (DRDY=1, BIAS=4, REFIN+=5, REFIN−=6, FORCE+=8,
RTDIN+=10, RTDIN−=11, FORCE−=12, SDI=14, SCLK=15, CS_N=16, SDO=17,
grounds=9/13/18/19, NC3=20). `scenarios` are
independent expected outcomes used to detect model/checker disagreement.

Optional `board.paths` carries source-authored local-escape groups. Each group
has `name`, `nets`, qualified `component_ids`, native `trace_ids`, native
`via_ids`, load-side `terminal_pad_ids`, and native `junction_pad_ids`, plus
finite `max_branch_current_a`,
`copper_thickness_um` (at least the 70 um finished-copper bound), and
`max_route_mm` (at most 3 mm). `uses_buck_or_mcu_trunk` and
`uses_shared_spine` are explicit source memberships and must be false. The
Rust DRC rule admits only SELV_LV groups whose native traces are uniquely
identified on F.Cu/B.Cu, terminate on same-net/same-layer load or junction
copper, form a connected branch, stay within the route limit, and meet the
independent IPC ampacity scalar. Optional `clearance_pad_ids` is a separate
same-IC copper-boundary rule with a 0.20 mm floor; it does not stand in for
branch terminal connectivity. An empty population is an explicit coverage
gap; the thin Python adapter transports native groups without deriving them.

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
| RREF | `rtd_pan.r_ref`, 430 Ω, `RG2012V-431-W-T1`, 0.05%, 5 ppm/C |
| SPI | SCK 8, SDI/MOSI 11, SDO/MISO 12, CS 10, DRDY 9 |
| threshold words | low 1526, high 45722 |

The harness reports `pass`, `fail`, or `indeterminate`, per-rule findings,
coverage gaps, and the identity/hash evidence. It never upgrades missing
required input, a documented cable blind spot, or missing native geometry to a
pass.

The standalone `zapote/rtd/unit/profile.json` uses the typed
`zapote_core::unit::UnitProfile` contract. It binds `RTDUnit` to
the compiled `RTDUnit` wrapper and `RTDSensing` source, records the TPS389001/RREF/divider/filter values,
and fixes the four-layer manufacturing limits. Its ten interface nets have a
stable order with both ground contacts normalized to the physical `GND` net.
The unit envelope additionally carries the native extractor's copper
components/connections/clusters/traces/vias, artifact hashes, parsed firmware
values, and a non-empty fault-model input. `zapote-rtd --unit-input` evaluates
observed MPN/pad/net/cluster/copper/local-decoupling data; source load-budget
and outside-unit aggressors remain explicit indeterminate applicability states
until their source evidence exists. The
profile tests validate source values and reject mutations that turn missing or
deferred evidence into apparent passes; it is not a native board acceptance
result until a matching board/export hash is bound.
