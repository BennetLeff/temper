# D-30: connector power direction

J9 now receives controller power instead of claiming to generate it; the new nine-board validator rejects the original defect, and all PCB bytes are unchanged.

## Source fix and ERC

Base: `codex/power-stage-120v-build` at `841a66d9408e16b3fcd71d9e46131b62df00bb65`.
Work branch: `codex/ps-r17-d30-connector-direction`.

The round4 capture supplies the original `JCTRL` rows. The round5
[partition source](../../../../../prototype-closure/round5/boards/partition.rs)
now applies the correction before reference renumbering: J9.1 `CTRL_3V3` is
`power_in`; J9.2 `CTRL_GND` is `passive`, matching the connector-map return
contract. Round4 remains immutable. The generated table, embedded schematic
symbol and symbol library were regenerated; connectivity and copper did not
change.

Removing the false sources exposes the actual external dependencies.
`render_central.py` now labels two external ERC boundaries: controller supply
via J9.1 and controller return via J9.2. They describe required incoming
connections, not onboard producers. The Rust validator independently requires
those exact connector endpoints, nets and types; power flags never qualify as
sources in its audit.

| Central ERC state | Errors | Existing ground warnings | Evidence |
|---|---:|---:|---|
| Original J9 pins, both `power_out` | 0 | 9 | [Before](before/central-erc.json) |
| Corrected types, before external controller boundary flags | 2 | 9 | [Intermediate](central-erc-without-controller-boundary.json) |
| Corrected types and explicit external boundaries | 0 | 9 | [After](after/central-erc.json) |

Both intermediate errors are `power_pin_not_driven`: J9.1 on `CTRL_3V3`, and
U98.5 on `CTRL_GND`. The nine `ground_pin_not_ground` warnings remain visible;
no ERC exclusion or severity change was added.

## Class audit

Only two connector pins in the starting tables claimed an output without an
onboard source. There were no additional instances requiring a design choice.
All paths below are under
`zapote/power-stage-120v/prototype-closure/round5/boards/`.

| File:line | Pin / net | Before | After | Source relationship |
|---|---|---|---|---|
| `central/generated/pins.tsv:1129` | J9.1 / CTRL_3V3 | power_out | power_in | External controller supply |
| `central/generated/pins.tsv:1130` | J9.2 / CTRL_GND | power_out | passive | External controller return |

The complete [before audit](before/power-direction.tsv) and
[after audit](after/power-direction.tsv) include file:line, onboard typed source
and joined supply/boundary for every connected connector pin and every power
input. [Before findings](before/power-direction.txt) contain two direction
contract violations and two missing-onboard-source violations, all referring
to the same two pins. [After findings](after/power-direction.txt) are empty.

| Board | Table pins | Connector pins, including NC | Power-input pins after fix | Audit result |
|---|---:|---:|---:|---|
| central | 1411 | 98 | 253 | J9 pair corrected; all inputs have declared sources |
| catch | 60 | 8 | 5 | No class defect |
| bus | 60 | 8 | 5 | No class defect |
| line | 52 | 8 | 5 | No class defect |
| pre | 52 | 8 | 5 | No class defect |
| out | 52 | 8 | 5 | No class defect |
| tank | 68 | 8 | 5 | No class defect |
| iproof | 11 | 2 | 0 | Passive burden/signal interface |
| iline | 11 | 2 | 0 | Passive burden/signal interface |

Counts and input hashes are recorded by [capture.py](capture.py) in
[evidence.json](evidence.json). The audit covers 1777 table pins, eight explicit
harnesses with 40 conductors, and five external supply/return endpoints.
The six voltage cards receive POD_3V3 from central U1.2 (source reference REG3)
and AUX_0V through their harnesses. Their internal DCDC/HLDO/LDO supply inputs
trace to local typed device outputs. Central AUX_24V/AUX_0V enter via J_AUX24;
POD_5V enters from the external converter via J_REG5.3. CTRL_3V3/CTRL_GND enter
via JCTRL. Equal net names on unrelated boards do not establish a connection.

## Validator and checks

[power_direction.rs](../../../../../prototype-closure/round5/boards/power_direction.rs)
is a standalone, standard-library Rust executable wired into `boards/check.sh`.
It rejects unsupported connector outputs, undriven power inputs, and joined
`power_out` connector pins, including transitive harness joins. It rejects
missing/malformed tables and changed harness/boundary endpoints. It distinguishes
signal drivers from power producers and excludes connectors and flags as
producers. Explicit NC component outputs are allowed.

[All 20 tests pass](after/power-direction-tests.txt). Negative controls restore
each original J9 type separately, remove the actual central regulator, remove
the controller boundary, connect two driven harness outputs, and try to use a
flag, signal output, another connector or an unrelated board's identically
named rail as a power source. The actual baseline tables fail under the final
validator, as [reproduce.txt](reproduce.txt) records.

[After native checks](after/verification-summary.json) show all 27 DRC samples
(three per board) with zero violations, opens or schematic-parity differences.
All eight sensor schematics have zero ERC violations. The
[native oracle](after/native-pin-oracle.json) confirms exact table/XML/native-pad
nets, footprint identity, original source conservation and eight harness pinouts.
It now also compares every connector pin type against the actual KiCad XML and
rejects an intentionally wrong type. This catches stale embedded symbols that
net-only parity cannot detect.

[Before PCB hashes](before/board-hashes.json) equal
[after PCB hashes](after/board-hashes.json) for all nine boards.
[The central XML export](after/central-netlist.xml) contains the corrected
J9 types. The [root](root-review.png) and [CONTROLLER_1](controller-review.png) drawing pages were visually inspected;
external boundary labels and connections remain readable.

## Replay

From the repository root, with KiCad 10.0.4 and `rustc` available:

```sh
sh zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D30/reproduce.sh
```

This regenerates the central source partition and schematic, executes the
existing ERC/DRC/parity checks plus the new validator, captures current receipts,
and runs the validator against pin tables extracted from the exact base commit.
It expects the baseline to fail on J9.1 and J9.2. The original before ERC/DRC
receipts were captured with the base revision's `boards/check.sh` before editing;
the intermediate ERC receipt was captured after the partition correction and
before adding the two external controller flags.

Repository gates also passed: import boundary (5 contracts kept, 0 broken),
`make regen`, and `make regen-check`. Their logs are in [gates](gates/).
The import gate used a temporary environment with import-linter/PyYAML and
`--no-sync`, with this checkout's `packages/temper-placer/src` on PYTHONPATH.
No Rust workspace, native bridge or shared extension was built.

## Limits

This is a connector metadata and source-reachability check. It trusts component
pin types and the explicitly declared external supply interfaces; it does not
establish supply capacity, voltage compatibility, backfeed behavior or physical
controller availability. Native component symbols can carry more detailed types
than the source tables; the added type-parity assertion is for connectors.
Existing product qualification holds remain in force. No root `pcb/`, root
`elec/`, power-stage `native-*`, `frozen/`, or mit-product-guidance worktree was
modified.
