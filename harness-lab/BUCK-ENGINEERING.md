# Buck engineering validation

Stages 1–4 are executable software checks. The current reference is **not
engineering-qualified**. Stage 5 always reports `not_run` and
`hardware_validated: false`.

[Implementation checks and four-variant results](evidence/engineering-20260909/README.md)
retain the initial evidence and qualification blockers. The follow-up
[requirements/component audit](audits/buck-20260909/requirements-components.md),
[compact layout candidate](layout-candidates/buck-20260909/README.md), and
[measured behavioral SPICE model](audits/buck-20260909/model-simulation.md)
record subsequent progress. The model is exploratory and remains outside the
approved evidence registry.

The [September 10 closeout ledger](audits/buck-final-20260910/README.md)
records the current exact BOM, source build, waveform tests, corrected v2
fixtures and isolated KiCad 10.0.6 qualification. Use it for current status;
the earlier evidence below describes the historical references.

## Harness implementation and admission

The engineering stages implement validation infrastructure. They do not
complete all of the paper-inspired harness capabilities:

| Paper idea | Current status |
|---|---|
| Persistent traces | Implemented. PCB trials, engineering runs, model decks, logs, hashes, board snapshots, raw waveforms, and failed attempts are retained. Large raw waveforms remain local and Git-ignored; a recorded hash does not make them available in a fresh checkout. |
| External computation | Implemented. Rust judges, KiCad, Atopile, ngspice, native DRC, analytical checks, and independent waveform parsing operate outside the language model. This does not by itself establish physical-model accuracy. |
| Recovery | Implemented bounded act/refine execution and narrowly admitted interruption recovery. Missing or indeterminate native evidence terminates an attempt; it does not trigger an unrecorded replacement trial. |
| Separating harness failures from model failures | Implemented at the validation boundary. Results distinguish pass, fail, blocked, indeterminate, missing/stale evidence, simulator failure, and invalid model receipts. Diagnosis is not yet fully automated. |
| Persistent learned memory/skills | Implemented versioned `notes.md` and `skills.py`, immutable revisions, sandbox loading, and explicit development-to-evaluation inheritance. A live pilot has not yet established effectiveness. |

The [continual harness contract](CONTINUAL-HARNESS.md) describes the implemented
runtime, budgets, recovery, refinement and inheritance. These capabilities remain
distinct from circuit/model qualification and physical validation. Live scoring
requires admitted engineering evidence; software tests cannot supply it.

```sh
make -C harness-lab build check
python3 harness-lab/engineering_host.py harness-lab/runs/engineering-new
```

Use a new output directory every time. Exit 0 means the first four stages passed;
exit 1 means qualification is blocked or failed. The output contains `report.md`,
`report.json`, each raw stage input/result, compiled source exports, native KiCad
DRC reports, board snapshots, artifact hashes, and judge/source identities.

`--variant buck-dev-a|buck-dev-b|buck-res-a|buck-res-b` selects the
frozen fixture context. `--board PATH` evaluates another board within that same
protected context. `--requirements PATH`, `--component-qualification PATH`, and
`--model-manifest PATH` accept reviewed operator inputs. These interfaces are
host tools; they are not editable solver parameters.

## Stage 1: operating requirements

`engineering/requirements.json` contains the source-supported 15 V nominal input
and 3.3 V ±5% output. The source audit also resolves a 13.5–16.5 V input
range, 0.5 A continuous design budget, and product ambient envelope. The September
10 closure revision adopts the 1 A pulse, ripple, startup/transient, efficiency
and thermal targets documented in the requirements manifest. Two component
inputs remain unresolved: effective capacitance and hot inductor saturation.
A source design budget is not a measured maximum.
The regulator's 3 A rating is not a product load requirement.

Rust checks the schema, identities, units, finite values, approval states,
ordered ranges, and required limits. Unknown limits block freezing. Every stage
retains its own findings even when another stage blocks overall admission.

## Stage 2: existing Atopile circuit

The isolated build imports `BuckConverter3V3` from `elec/src/modules.ato` and ties
enable to VIN as production `PowerManagement` does. It copies source dependencies
into the evidence directory and uses pinned Atopile 0.2.69. It does not edit the
production circuit. Atopile must already be available in the local uv cache;
the command uses `--offline` and records unavailable-tool errors.

Rust compares the complete compiled pin partition, authoritative CSV MPNs, native
resolved component values/ratings, and candidate pad assignments. Compiler net
names and reference numbers may differ; connected pin groups must agree exactly.
Atopile's netlist aliases library identities and exports `?` values, so the native
API export supplies resolved attributes and the CSV supplies MPN identity.
Source and compiled artifact hashes must match before those exports are accepted.

The actual build and its voltage/divider assertions pass. This establishes
circuit identity and source assertions, not dynamic performance. Stage 2 remains
blocked pending capacitor DC-bias derating and inductor saturation evidence.

A component qualification JSON identifies `artifact_path`, `artifact_sha256`,
`reviewed_by`, `source`, and `source_sha256` (the report's current source identity).
Its `capacitors` map has entries `c_in`, `c_boot`, `c_out1`, `c_out2`, `c_out_hf`,
each with numeric `effective_min_uf` and `required_min_uf`. It also records
`inductor_saturation_a` and `required_peak_a`. These are reviewed engineering
inputs, not inferred datasheet ratings; the host verifies the retained artifact.

## Stage 3: qualified simulation

The current development path is the [reusable LMR51430X datasheet model](engineering/models/lmr51430-datasheet/README.md)
with [native ngspice exercises](engineering/scenarios/lmr51430-datasheet/README.md).
The user selected this path on September 10: build a model from the selected
part's datasheet and use it for engineering work, with Luna implementing it.
Do not require a vendor download or replace the part solely because that
download is unavailable. Atopile owns the circuit and exact parts; the SPICE
package records the pin mapping and models their electrical behavior.

Development simulations can proceed before Stage 3 approval. Record their
assumptions and use them for sensitivity studies, circuit debugging and bench
test planning. Qualification is a separate claim about predictive accuracy:
either a self-authored or vendor model needs evidence appropriate to that claim.

No exact, independently qualified LMR51430XDDCR model is supplied. The old
`LMR51430_avg.lib` uses a 0.8 V reference and is rejected. The required variant
has a 0.6 V reference, 500 kHz switching, and PFM operation. A new
[datasheet-derived model](audits/buck-20260909/sources/model/README.md) now runs
startup, line/load steps, a TI example, and EN restart in ngspice. Its assumed
compensation and missing device calibration prevent qualification; the audit
runner does not issue admission receipts.

The host runs fixed ngspice commands in fresh scenario directories and retains
stdout, stderr, decks, exact model bytes, and ASCII rawfiles. Rust parses the
rawfiles, checks named signal types, sample counts, monotonic finite time,
duration/resolution, and computes windowed voltage, ripple, overshoot, settling,
input variation, and load variation metrics. Caller-supplied scores are ignored.
The three scenario types are startup, input variation, and load variation.
The adopted protocol requires six startup cases (three VIN corners and two
loads), six load cases (three VIN corners and two profiles), and input variation.

The [simulation manifest contract](engineering/scenarios/README.md) describes
the operator input. The checked-in RC waveform is an instrument control only:
it tests the parser against actual ngspice output and an analytic RC response.
It cannot qualify the buck. Simulation is schematic-only (`layout_sensitive:
false`); none of these measurements claims layout-specific EMI, temperature,
protection, or physical performance. Reuse checks bind model, circuit,
requirements, and settings; parasitic reuse additionally requires the same board.

## Stage 4: layout and presentation

The new checks retain U1's protected context, full native DRC, and connectivity
checks, then measure endpoint-connected copper path lengths, power trace widths,
SW/FB copper edge separation, and visible label bounds/heights. A via located at
a capacitor pad no longer proves a short ground return.

The 20 mm connected-path limit, 0.5 mm trace minimum, 1 mm SW/FB separation,
and 0.8 mm label height are explicit experiment proxies. They are not numerical
TI specifications or ampacity guarantees. The graph supports straight segments
joined at endpoints, same-layer intersections, T-junctions, and through vias. Zone/arc geometry and paths that
cannot be established by this graph are indeterminate, never assumed good.
Centerline path length is not a copper polygon loop-area or field simulation.

The original development reference has about 43.7 mm of ground-return routing and no
visible reference/value labels. It therefore fails the new layout checks.
Missing 3D model declarations are reported separately; the current collector
does not resolve every model-file path, and missing models do not alter
electrical status. The preliminary boards and their original qualification
artifacts remain unchanged. The separately retained v4 candidate passes the
layout and presentation judges with an 11.2875 mm ground-return path and
visible labels. Its L2 footprint was a stub. The current v5-derived v2
fixtures carry the reviewed SRP1265A land pattern and matching local library.
Their four terminal variants preserve the original construction challenges.
These fixture boards do not constitute a production PCB or physical validation.

## Scope and next admission gate

The report is the admission boundary for full buck trials. The continual
solver/refinement runner is implemented and software-tested. Its live pilot
remains unrun because component and model qualification are missing. Supply
reviewed evidence, pin its exact identities, and obtain an eligible engineering
report before running the development/evaluation pilot. Production PCB
qualification and bench validation remain separate milestones.

External qualification also requires an exact receipt pin in the compiled
`engineering/approved-evidence.json` registry. Both registries are currently
empty. Only an externally reviewed receipt with an explicit `id`, `status:
"pass"`, and `synthetic: false` can be pinned. Each ID maps to the full SHA-256
of canonical sorted-key compact JSON for the receipt (excluding the host-only
`verified_artifact` field). Changing any source, model, numeric margin, or
review metadata invalidates the pin. Software fixtures are not registered.
The registry is a trusted operator artifact, never a solver-editable input.

Model/deck/evidence paths must be relative and resolve inside the repository,
including after symlink resolution. Component evidence paths follow the same
rule. The selected manifest itself is an explicit operator-selected local file.
The source identity binds the Atopile source, wrapper, and circuit contract;
tool and registry changes are separately retained through the source inventory
and compiled judge hash, avoiding circular receipt identities.

When resolving requirements, `load_step_endpoints` uses `min` and `max` current
in A, with distinct endpoints. `efficiency_operating_points` uses a nonempty
`points` array of `{vin_v, iout_a, min_efficiency_percent}`. These are operating
conditions and acceptance limits, not single placeholder numbers.
