# Native-06 verification, 2026-09-26

Board SHA-256: `500cdb4b9f3491bfed2535099ad0ed2a59a461f12dd79a7aeedae18014b0f3fe`. These receipts cover the filled, saved
240 × 160 mm four-layer prototype. The board bytes stayed unchanged through
three full DRC repeats and the independent read-only checks. Renewed D4 is
pending; this is not fabrication or powered-operation approval.

| Check | Result | Evidence |
| --- | --- | --- |
| Full KiCad DRC, three runs | 0 copper/clearance/creepage/courtyard findings; 0 schematic mismatch | `drc-1.json` through `drc-3.json` |
| Raw opens | 1, R5 internal current/sense connection; no other split net | `connectivity.json`, raw DRC |
| Source/native identity | 114 MPNs, 313 source pins, 333 copper pads match | `source-parity.json` |
| Saved track/via identity | 560 tracks + 141 vias retain authored nets in five batches | `copper-identity.json` |
| Physical stackup | Four layers, nominal 1.600 mm | `stackup.json` |
| All-layer barrier | 0 hits at the provisional 8.0 mm floor | `barrier.json`, `copper.json` |
| Hardware surface clearance | 0 hits, normal and bring-up | `hardware-surface.json` |
| Mechanical envelope fit | 0 conflicts in both configurations at unchanged native-05 poses | `../../native-05/placement-metrics.json` |
| ERC | 0 errors, 238 warnings | `erc.json` |
| Source audit | 48/48 tests pass | `final49-audit-tests.txt` |
| Board/tool regressions | 43/43 tests pass | `final49-unit-tests.txt` |
| Rust workspace | 325 tests pass | `../../evidence/verification-tools-2026-09-26/final-rust-with-identity.txt` |

`commands.json` preserves the exact validator/DRC invocations and their output.
`final49-replay.txt` and `../route-receipts/` preserve construction. The fill run
uses `--all-track-errors --schematic-parity --severity-all --refill-zones
--save-board`; the three repeat runs omit refill/save. Keep the board's generated
`.kicad_dru`, `.kicad_pro`, library table and libraries with it. A board-only DRC
or one without generated insulation rules is not comparable evidence.

`source-manifest.json` in the parent directory intentionally identifies the
unrouted source-generated placement. Route receipts chain that placement into
the routed board; this verification directory identifies the final saved hash.
The source revision field names the committed parent; the final routes were
uncommitted when measured. Content hashes, rather than a circular self-commit
reference, identify these artifacts.

## Remaining native findings

The 28 library mismatches are retained warnings associated with generated
footprint annotations/metadata; source MPN and copper-pad identity are checked
separately. Three silk overlaps are the L1/J3 outlines. They do not create
copper clearance or body/courtyard violations; clean up production silk before
fabrication. No warning was disabled to obtain the copper result.

The raw LEG_RET open joins the two pad clusters through the four-terminal
WSK2512 resistor internally. R5 pad 1 carries current, pad 2 is the sense pickup.
A PCB bridge between them would defeat the Kelvin connection. The opposite
sense and current terminals are pads 3 and 4. `connectivity.json` retains the
full clusters so this disposition cannot cover another open on the same net.

ERC retains 114 symbol-library warnings, 113 endpoint-grid warnings and 11
isolated-pin-label warnings. The current library environment resolves the
32 footprint-link warnings seen in the earlier 270-warning report.

## Limits

The hardware check uses provisional exposed-metal envelopes and front-surface
copper; measured hardware and 3D assembly fit remain open. The power-path review
is a nominal-width/current-sharing screen, not a thermal or via-current rating.
The shared five-unit check is **indeterminate**, with its existing software,
model, manufacturing and hardware gaps preserved under
`../../evidence/verification-tools-2026-09-26/common-unit-check/`.

The lab/working-voltage review, Coilcraft and module evidence, RCA teardown,
airflow, finished copper/plating, physical overshoot/protection/CT-injection,
thermal/current, leakage, hipot and EMI work have not been completed.
