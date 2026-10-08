# Validation and replay

Run from the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --bin zapote-interlock -- zapote/interlock/candidate/source-manifest.json zapote/interlock/evidence/native-final.json zapote/interlock/interface-contract.json
```

The interlock CLI exits nonzero on FAIL **or INDETERMINATE**. The construction milestone permits zero hard failures alongside explicit qualification gaps; it does not translate INDETERMINATE into PASS. Common saved-board checks are registered in the Zapote Makefile. They are not full electrical qualification.

The Rust validator checks 25 exact source/native component identities and source values; complete physical pin-net sets including four intentionally unused outputs/pins; strict pin-map uniqueness and coverage; and exactly one native connected cluster per net. The gate evaluator reads actual compiled physical nets. It propagates both inverter packages, the eight-input NAND and AND, then resolves the flip-flop's actual clear, preset, D and clock before reading PERMIT/QBAR at J2. All 4,096 fault/live/watchdog/Q/old-reset/new-reset vectors are compared with an independent requirement oracle.

The conditional open-input calculation uses each source resistor's maximum value and the reviewed leakage budget. Shared Rust checks validate saved-board document binding, native stackup, 0.15 mm copper clearance and all six bypass locations. Native geometry and connectivity are supplied by KiCad extraction; these checks do not independently prove all properties of the KiCad extractor. A saved-board digest is checked by the shared stackup gate, while component/pad/trace/via representation is checked by native document binding.

The mutation suite uses real source and native fixtures. It reroutes the actual clear/clock/NAND/D/Q pins, changes component values, splits a native net into two clusters while retaining every node, connects an NC pad, removes strict pin-map coverage, alters contract assumptions and supplies stale or contradictory board evidence. Stateful traces cover all seven fault channels, missing live and watchdog reset, retained permission, held reset during recovery and deliberate rearming. Native truth tables do not measure watchdog elapsed time or recovery/removal timing.

## Native construction

`tools/build_source.py NEW_DIRECTORY` compiles Atopile 0.2.69. `source-build-01` is historical, using the rejected 10 kΩ WDI bias; `source-build-02` uses the TI-recommended 1 kΩ. Preserve its captured `.net`, `.csv`, layouts and manifest despite general `build/` ignore rules.

`tools/build_native.py NEW_DIRECTORY` consumes source-build-02, explicit poses and outline using the existing strict source bridge. It produces a skeleton, whose historical board metadata can describe the generator defaults. The accepted candidate is separately initialized to two layers, populated with original library footprints, source-field synchronized, and routed. Final evidence, not a skeleton's board section, describes the manufactured stackup.

Original library refresh and field synchronization use the existing shared/current-sense adapters. `zapote/rtd/apply_routes.py` transactionally applies explicit route vertices and native vias/zones. The final recipe is `routes-08.json`; `tools/finish_board.py` applies authored labels. Fill ground zones through native `pcbnew.ZONE_FILLER`, save, then extract with `zapote/current-sense/tools/extract_current_sense_native.py`. `tools/draw_schematic.py` emits the readable source-bound schematic with package-specific pin names and explicit NC markers.

Routes 04–07 and their failing reports are retained. Early worker attempts and the unreadable/wrong-pin-name schematic were rejected during coordinator review. Original footprints exposed 0.15 mm DFF pad spacing; the final low-voltage fabrication floor is documented in MODEL.md. No new placement or routing search algorithm was added.

Native final checks use KiCad 10.0.4 with all severities, all track errors and schematic parity. Three final runs and rendered inspection are required before freeze. ERC alone is not proof of semantic circuit correctness. The source/schematic netlist oracle must also agree on every physical pin.

## Unpowered-load bench sequence — NOT RUN

Use a current-limited 3.3 V supply and logic stimulus/measurement equipment, with the heater and gate drive disconnected. Verify actual J1/J2 pin continuity first. Check disabled startup; assert LIVE and each healthy input; issue one reset pulse; verify PERMIT persists when reset returns high. Assert each fault independently, then clear it while reset stays low: PERMIT must remain low until a fresh reset edge. Repeat for LIVE removal and watchdog RESET. Stop WDI falling edges and measure timeout; disconnect the host WDI conductor and repeat. Qualify supply ramp/brownout behavior, reset timing and downstream receiver power loss separately. No result is populated as measured by this digital build.
