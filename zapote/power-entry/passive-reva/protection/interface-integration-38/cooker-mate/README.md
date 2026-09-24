# Rev38 cooker-board mating-port derivative

This Atopile candidate imports the existing `elec/src/main.ato:Top` and adds
one Molex 43045-1612 16-contact header to **that** cooker's ESP32-S3 and SELV
3.3 V rail. It does not change the canonical cooker source or PCB. A native
cooker board with this header, its layout, and a qualified harness remain to
be made.

| Header pad | Cooker connection | ESP module pad |
| ---: | --- | ---: |
| 1, 9 | Existing SELV `+3V3` | 2 (supply) |
| 2 | `SOURCE_STOP_N`, GPIO13 | 21 |
| 3 | `SOURCE_VALIDATED_HEARTBEAT`, GPIO21 | 23 |
| 4 | `SOURCE_PERMIT_SET_REQUEST`, GPIO48 | 25 |
| 5 | `SOURCE_PREWATCHDOG_OK`, GPIO18 | 11 |
| 6 | `SOURCE_COMMAND_TX`, GPIO40 | 33 |
| 7 | `SOURCE_RESPONSE_RX`, GPIO41 | 34 |
| 8, 13, 16 | Existing SELV ground | 1 (modeled) |
| 10 | `SOURCE_START_N`, GPIO42 | 35 |
| 11, 12 | Existing GPIO38/39 I²C, with the cooker's 4.7 kΩ pull-ups | 31, 32 |
| 14 | `SOURCE_RESET_GOOD`, buffered supervisor RESET | Cooker-side TPS389001 output |
| 15 | `SOURCE_INTERLOCK_N`, gated inverse of latched SHUTDOWN | Cooker-side LVC logic |

The Rev38 board has local 10 kΩ pull-downs on `SOURCE_RESET_GOOD` and
`SOURCE_INTERLOCK_N`. This derivative now joins a cooker-side supervisor,
buffer, inverter and AND gates to pins 14/15. The reset request is shared
with GPIO14 and must be high-Z/open-drain in firmware. The source task has a
guarded, queued one-shot reset candidate, but no operator caller or target pin
capture; authorization remains locked out. See
[`SOURCE-RESET-INTERLOCK.md`](../SOURCE-RESET-INTERLOCK.md) for the reset
truth table and unmeasured startup/partial-power gates. The present cooker
`SafetyInterlock.shutdown` is an active-high fault; the inverter and reset
qualification provide the high-to-allow polarity at pad 15.

The cooker MCU's modeled ground is module pad 1; physical WROOM-1 ground
pads 40/41 are not represented in that existing component and need a package
review before native layout. The shared GPIO38/39 I²C bus and the GPIO40–42
JTAG tradeoff also need cooker-system and target-board checks.

Build with Atopile 0.2.69 from this repository:

```sh
ATO_BIN=/path/to/ato ./build.sh
```

`build.sh` stages the canonical cooker source with this derivative in a
temporary project because Atopile 0.2.69 cannot export a netlist when a
project imports files outside its project directory. It compiles and runs the
shared Rust exact-pin audit against the generated netlist and BOM, then prints
their paths. The audit checks the selected cooker ESP, connector, I²C pull-ups,
every used header pad, the existing 15 V module and buck input/output/return
chain, separation of port functions and power rails, exact members on each
control net, including the new reset/interlock producer path. In the
2026-09-24 build, the exported BOM had one
`ESP32-S3-WROOM-1-N8R8` and one `43045-1612`; the netlist joined all listed
signal pads to the module pads above, tied pads 1/9 to the existing `+3V3`
net, tied pads 8/13/16 to SELV ground, and joined pads 14/15 to their
candidate producer outputs. This is source connectivity evidence, not a native-board, rail-load,
startup, timing, or harness qualification.

`../tools/build_cooker_mate_source.py` also creates a persistent, pinned
source snapshot. The current `../cooker-source-01` netlist, BOM, resolved
export and hashes are linked to the Rev38 snapshot by
[`COOKER-ASSEMBLY-SOURCE.md`](../COOKER-ASSEMBLY-SOURCE.md). This digital
connector check does not constitute native PCB or physical cable evidence.

## Native cooker-board readiness

`native_probe.py` checks the frozen `cooker-source-01` receipt, resolves the
compiled BOM and footprint names against the same `pcb/libs` and KiCad stock
roots used by the strict native bridge, and compares connected pin numbers to
available footprint pad numbers. Its retained result is
[`evidence/native-readiness-01.json`](evidence/native-readiness-01.json): 189
references, 42 resolved footprint types, and no connected pin absent from a
resolved footprint. It is a source/footprint diagnostic, not a native export.

Three package inputs block a credible native cooker board:

- `F1` (`cooker.power_in.fuse`) references
  `Fuse:Fuse_Holder_5x20mm`, and `RT1` (`cooker.power_in.ntc`) references
  `Resistor_THT:R_Disc_D15.0mm_W7.0mm_P7.5mm`. Neither exists in the strict
  bridge's local or installed stock footprint roots. The embedded shapes in
  the canonical PCB are marked `generator stub`, so they are not released
  library footprints.
- The local `lib:ESP32-S3-WROOM-1` footprint contains pads 1–39 only.
  [Espressif's ESP32-S3-WROOM-1 datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
  identifies ground contacts 40 and 41, which are also absent from the
  current Atopile component model. Reconcile both source and land pattern
  against the selected `ESP32-S3-WROOM-1-N8R8` package before layout.
- No reviewed 189-reference poses, board outline, or HOT/SELV spacing plan
  exists for this derivative. The `temper-design-bundle` extension currently
  fails the repository freshness gate, so strict native projection has not
  run on this snapshot.

Reproduce the static diagnostic from the repository root:

```sh
.venv/bin/python zapote/power-entry/passive-reva/protection/interface-integration-38/cooker-mate/native_probe.py
```

After those inputs are resolved, `build_native.py` invokes the existing
strict bridge with `CookerMate38` as the entry and `pcb/libs` as local
libraries. It requires complete reviewed poses and outline, and refuses an
existing output directory. Do not project this derivative onto the canonical
`pcb/temper.kicad_pcb`.
