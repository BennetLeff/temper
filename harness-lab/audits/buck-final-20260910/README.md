# Buck closeout — 2026-09-10

The reference and initial harness are implemented, but the buck is **not yet
engineering-qualified**. The live development/evaluation pilot remains blocked
on reviewed component and exact-device model evidence. No powered tests were
performed. The existing production PCB and empty approval registry are unchanged.

The [Luna follow-up review](followup-review.md) records the subsequent startup
protocol correction, transient experiments and tolerance-corner component
review. Test counts and qualification receipts in the original table below
describe the earlier collection; evaluator and requirements changes require
fresh qualification before admission.

## Completed and verified

| Work | Evidence and result |
|---|---|
| Exact BOM and circuit source | [Current nine-component BOM](components/current-buck-bom.md), [source reconciliation](components/README.md), and [real compiled exports](source-build/README.md). Samsung C9 replacement selected; KEMET voltage and Murata tolerance corrected; full project netlist build and BOM reconciliation pass. |
| Waveform instrument | [Tests](tests/README.md): 38 Rust tests, Clippy and Rust formatting pass. The complete 13-case synthetic waveform packet exercises six startup and six load cases plus generic input variation through the real evaluator. It remains rejected for model approval. |
| Corrected reference fixtures | Four [v2 fixtures](../../fixtures/buck-v2/buck-v2-contract.json) derive from the reviewed v5 layout with the exact L2 land pattern and matching library. Original terminal variants and construction constraints are preserved. |
| Native qualification | [36-control receipt](native-tool/qualification/qualification.json): 12 witness passes, 20 intended failures, two indeterminate controls and two operation controls. All four witnesses passed native DRC three times. No new rule suppression was introduced. |
| Native tool fault | [Version comparison](native-tool/version-comparison/README.md) reproduces the 10.0.4 crash and verifies the same missing-route defect produces usable native evidence in isolated official 10.0.6. The installed app is unchanged. |
| Engineering collection | [Current report](engineering/report.md) retains independent stage results. Circuit identity and layout checks run with the selected v2 adapter. Missing component/model approvals still block overall admission. |
| Runtime selection | [buck_v2.py](../../buck_v2.py) selects qualification, engineering and trials consistently. The 10.0.6 adapter delegates to the shared native implementation. Default v1 entry points remain available for historical reproduction. |
| Admission boundary | [Preflight result](preflight/results.json) is blocked before solver execution because engineering qualification is missing. Telemetry is disabled; one blocked preflight claim is retained. |
| Datasheet model development | [Three-case native replay](datasheet-model-development/README.md) uses the current LMR51430X model built by Luna. Nominal mean is 3.315226 V; the load-step model predicts a 2.880473 V dip requiring investigation. All raw captures and hashes were verified. Vendor model access is optional for this development path. |

The [target manifest](../../engineering/requirements.json) records adopted
targets, startup-fixture semantics and two unresolved component inputs. Targets are requirements, not
measured performance. Startup and load protocols verify the actual stimulus,
all VIN/load combinations, both edge directions, slew, holds, output departure
and recovery. Input variation currently checks reviewed generic window/span
limits; it does not claim a fully specified line-transient protocol.

Three Luna agents reviewed component consistency, waveform admission and native
fixture/runtime consistency. The [local review record](review.md) records their
coverage, host corrections and remaining limits. Earlier audit and review
receipts describe earlier source states and are not current qualification.

## What still blocks the milestone

1. **Model accuracy for qualification.** The user selected datasheet-based
   modeling with Luna while retaining LMR51430XDDCR. The
   [model package](../../engineering/models/lmr51430-datasheet/README.md) and
   [development exercises](../../engineering/scenarios/lmr51430-datasheet/README.md)
   provide the development path. TI's terms and sign-in are complete. The signed-in
   [exact design says simulation is not enabled](ti-model-access.md), and its
   Export page offers no simulation model, but a vendor download is no longer
   a prerequisite to development. Establish claim-specific accuracy through
   independent comparison, retaining model, decks and raw results under their
   full hashes. The datasheet model remains unapproved for scored admission.
2. **Effective capacitance.** [The ledger](components/qualification-ledger.md)
   retains exact typical bias/temperature data and transparent sensitivity
   calculations. A numeric input-ripple budget and reviewed combined-condition
   minima are still missing. Typical plots cannot supply guaranteed tolerance,
   aging and temperature floors. Output-capacitor loop/transient requirements
   must be checked with the qualified circuit model.
3. **Hot L2 data.** The selected Bourns part has ample room-temperature ratings,
   but no qualified exact-part hot L(I,T) evidence. The proposed 8.35 A at
   105 °C/20% drop screen is a separate stress assumption; it is not a regulated
   buck operating point. Resolve it with manufacturer evidence or a suitable
   standalone DC-bias inductance test, then review the adopted current margin.

Only after reviewed receipts are pinned in the trusted registry and the
engineering report is eligible should the harness run preflight, four development
slots, freeze inheritance, and run six reserved evaluation slots. No development
or evaluation slots have been consumed in this closeout. Physical validation
remains a later milestone.

## Reproduce and continue

Run from the feature worktree root. The mounted official app is machine-local;
if the volume is absent, mount the retained DMG or select an official 10.0.6
installation explicitly. Do not silently use the installed 10.0.4 app.

```sh
export PATH="/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS:$PATH"
export TEMPER_KICAD_PYTHON="/Volumes/KiCad/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9"
make -C harness-lab build
python3 harness-lab/buck_v2.py qualify harness-lab/runs/new-v2-qualification
python3 harness-lab/buck_v2.py engineering harness-lab/runs/new-v2-engineering
```

The engineering command currently exits 1 because admission is blocked. Once
real reviewed inputs exist, add `--component-qualification PATH` and
`--model-manifest PATH`; their exact identities must also be approved by the
compiled registry. After obtaining an eligible report:

```sh
python3 harness-lab/buck_v2.py trials harness-lab/runs/new-v2-preflight \
  --phase preflight --no-telemetry \
  --qualification harness-lab/runs/new-v2-qualification/qualification.json \
  --engineering harness-lab/runs/new-v2-engineering/report.json
```

Use the same `buck_v2.py trials` prefix for the development/evaluation commands
in the [continual harness contract](../../CONTINUAL-HARNESS.md), retaining
`--no-telemetry`. Current tracing can export complete conversations and project
artifacts; this closeout did not authorize or perform that expanded export.

Every output directory must be fresh. Source, evaluator, contract and evidence
changes invalidate receipts and require recollection. Local changes are
uncommitted; no fabrication package, purchase, vendor message, commit, push or
remote publication was performed.

Collected files are retained byte-for-byte. Some generated reports contain
absolute paths to their original `/tmp/temper-buck-final-*` collection directories;
those paths are machine-local and temporary. Recollect with the commands above
for a portable new admission run rather than editing evidence paths or hashes.
