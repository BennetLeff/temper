# Standalone current-sensing / primary OCP unit

The native project is `candidate/section.kicad_pro`, with schematic `candidate/section.kicad_sch` and routed board `candidate/section.kicad_pcb`. The Atopile entry is `elec/src/current_sense_unit.ato:CurrentSenseUnit`. This is a separate 21-component unit, not an integrated cooker board.

The board is 80 × 83 mm with two copper layers. A CST3015 transformer senses AC primary current; a floating burden and biased comparator pair detect either polarity and produce an active-high fault. See [INTERFACES.md](INTERFACES.md) for exact pins, host obligations and qualification steps, and [bom/README.md](bom/README.md) for exact parts and purchasing gaps.

## Build and evidence

- `source-build-04/`: pinned Atopile compilation and exported component/net identities.
- `generated-04/`: strict source-derived native generation at the authored final component poses. Its generated board is an unrouted provenance artifact, not the deliverable PCB.
- `candidate/`: final routed native project and source manifest.
- `poses.json`, `routes-*.json`, `edits-*.json`, `labels-*.json`, `outline-final.json`: explicit agent decisions, replayed through thin native adapters. No placement or routing search algorithm was invoked for this unit.
- `evidence/`: retained failures, native check reports, source equality oracle, renders, footprint review and final validation receipts.
- `circuit/`: Luna's bounded analytical model and supporting proposal documents. The canonical compiled source and [INTERFACES.md](INTERFACES.md) govern final native references; the separately retained `.ato` proposal is not a second build entry.
- `memory/`: actual selected context and reported use for this attempt, plus preparation-only validation of the next reviewed memory revision.

The source manifest describes generation inputs and its generated board hash. It must not be mistaken for the final routed-board hash. The final acceptance receipt binds the routed board, native extraction, model, Rust executable and check results separately.

## What this experiment established

The full Atopile → strict native generation → agent placement/routing → native checks path produced a connected standalone board. Native ERC and DRC/parity reports are retained rather than summarized without inputs. The Rust harness adds source/model binding and explicit geometry/electrical checks with negative controls; the acceptance record states their actual outcome and limits.

The inherited transformer footprint did not match the official land pattern. The corrected local footprint and independent native readback are documented in [the durable learning](../../docs/solutions/logic-errors/cst3015-land-pattern-edge-gap.md). The old full-cooker circuit and shared legacy footprint remain separate migration work.

The inherited bias topology could not establish the claimed midpoint. The standalone design uses a floating burden around a separately bypassed midpoint. Model review then corrected a load-current sign error and included the actual series-resistor tolerance. These are functional findings, not cosmetic routing changes.

## Qualification boundary

The model calculates an approximately 50.12 A nominal trip, with a conditional 46.18–54.16 A corner band. It is a static circuit calculation driven by an ideal transformer transfer relation for an AC waveform; it does not claim that a current transformer senses DC. CT transfer/frequency effects, unspecified hysteresis, hot leakage, startup/brownout, complete shutdown timing, primary termination temperature and assembled insulation remain unqualified. Overall physical acceptance remains INDETERMINATE and all hardware tests are NOT RUN.

This delivers a routed unit and an exercised validation harness. It is not a fabrication or energized-use approval. Exact comparator/clamp availability also remains open. The next physical step is a separately reviewed isolated unit test fixture; full-cooker integration follows individual unit qualification.

The 2026-09-11 [stackup repair](evidence/stackup-fix/README.md) supersedes the original physical stackup: 1.44 mm core / 1.60 mm total, guarded by Rust. The canonical PCB path is unchanged. [Updated 3D render](evidence/stackup-fix/after.png).
