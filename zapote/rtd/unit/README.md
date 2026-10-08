# Standalone RTD unit

The source-derived, routed 36-part board and matching schematic are in
`candidate/`. Read `HANDOFF.md` for J1/J2 interfaces, evidence scope and future
host obligations; `bom/` contains the exact 36-instance/20-group PCB BOM.

The final native checkpoint (`evidence/native-final-02/receipt.json`) records
three KiCad 10.0.4 DRC/parity passes and one ERC pass, all with zero findings
and unchanged candidate bytes. Rust engineering and circuit-model acceptance
are separate gates. The final 53-test suite passes; its real-board report has
zero failing findings and one explicit local-brownout timing indeterminate.
See `evidence/acceptance-final/receipt.json` and `HANDOFF.md` for the conditional
layout acceptance and later physical/integration obligation.
Physical tests are **NOT RUN**. Full-cooker integration is a later goal.

`profile.json` is the authored standalone validation policy. Source instance
identity remains `rtd_pan.*`; `unit_io` is the additional ten-contact host
connector. `manufacturing-contract.json` defines the four-layer 35 µm minimum
copper board, 0.20 mm minimum spacing/width and 0.70/0.30 mm through vias.
Most supply branches use 0.30 mm. The bound all-state current is 8.448898 mA against 10 mA; external reference
load is limited to 100 µA and 10 nF.

The thin transport adapter is `bind_native.py`:

```text
python3 zapote/rtd/unit/bind_native.py \
  --profile zapote/rtd/unit/profile.json \
  --native <native-unit-export.json> \
  --board-file <matching-board.kicad_pcb> \
  --source-manifest <compiled-source-manifest.json> \
  --extractor zapote/rtd/native_measure.py \
  --model <fault-model.json> \
  --firmware firmware/config.h \
  --firmware-pins firmware/components/hal/include/temper_pins.h \
  --output <unit-input.json>
```

The adapter compares the native export's own board and extractor hashes to the
current bytes and freezes profile, source-manifest, model, firmware, and
export hashes in the envelope. It requires the complete native transport
census and writes `zapote.rtd.unit-input.v1`; Rust owns MPN, pin/net/cluster,
pad geometry, copper width/layer, local decoupling, firmware, and model
findings. Run it with:

```text
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --bin zapote-rtd -- \
  --unit-input <unit-input.json> --output <unit-report.json>
```
