# Round 4 execution record and monitoring handoff

Storage update, 2026-09-28: the owner approved and the coordinator published the [round-4 raw evidence release](raw-evidence/README.md). Its five assets preserve all 12,027 files in the unchanged raw manifest. Local-only statements below describe the original round-4 handback.

**Evidence collected; board validation remains blocked.** This packet follows [ROUND-4.md](../../validation-plan/ROUND-4.md) at PR #1615 revision `829ee9debc08ce239bc2dffe0938c4fec2429545`. A/D are authorized; C evaluates timing only. B remains held. No PCB, component or firmware change was made. Final integration review is recorded in [QUALITY.md](QUALITY.md).

## Read this first

A monitoring agent should read this file, then the linked result for the item it follows. The [master status table](../../validation-plan/00-MASTER-PLAN.md#5-status) is updated with the round-4 outcomes. A finished report does not mean its physical acceptance criteria passed.

| Item | Outcome | Latest evidence |
| --- | --- | --- |
| A | Complete current-limited model grid: 135 cases at each ceiling, all at ≤60 kHz | [A report](../05-resonant-tank-envelope/round4/a-derated/README.md) |
| C1 | Reference-inductance phase complete; board-inductance rerun blocked on D1 | [C1 report](../01-switching-parasitics/round4/c1-zvs/README.md) |
| D1 | Software/extraction blocked; no accepted matrix or SPICE include | [D1 report and next steps](../01-switching-parasitics/round4/d1-extraction/README.md) |
| C2 | Conditional reference-model commutation subtotal complete; total/hot/board loss comparison unresolved | [C2 report](../01-switching-parasitics/round4/c2-losses/README.md) |
| D2 | Legacy replay and finite gate-clamp diagnostic complete; board counterfactuals/full grid unrun | [D2 report](../01-switching-parasitics/round4/d2-switching/README.md) |
| B | Held; no resistor values or hardware change proposed | [Round-4 scope](../../validation-plan/ROUND-4.md) |

## Findings that affect decisions

**A: derating is necessary.** At 42 A, 72 cases retain requested power and 63 are derated; at 40.45 A, 66 retain it and 69 are derated. All 270 cases meet the 60 kHz frequency cap in the ideal tank model. Each ceiling still leaves 73 accepted cases above the static minimum shunt trip. All 270 pass at 25 ns and 133 near-boundary/extreme cases pass at 12.5 ns. Minimum checked current margins are 0.04783 A and 0.04210 A. The earlier near-ceiling handoff was withdrawn after a finer-step crossing; only the [corrected frozen hashes](../05-resonant-tank-envelope/round4/a-derated/outputs/frozen-hashes.json) apply. **42 A is an analysis ceiling; 40.45 A is a command-margin proxy, not a qualified firmware setpoint.**

**C1: longer timing reduces the reference discharge-current requirement.** The 120 V typical strict threshold falls from about 21.5–22 A at 39 kΩ to 10.5–11 A at 51 kΩ. At 10 V the absolute 5% VDS criterion rejects a negative body-diode clamp despite completed discharge; separate signed brackets preserve this distinction. Signed discharge does not establish continuous diode conduction. The six timing corners extrapolate TI's 50 kΩ characterization to 39/51 kΩ and remain ASSUMED, excluding resistor and controller tolerance. Board-L qualification is absent.

**C2: the corrected comparison does not support choosing 51 kΩ from losses alone.** The same-event subset covers 76.64% of events at 40.45 A and 76.93% at 42 A across all six timing corners. The 51 kΩ setting raises the matched 27 °C turn-off + 25 °C diode + residual-Eoss + snubber-proxy subtotal in 105/135 minimum, 110/135 typical and 118/135 maximum-timing cases at each ceiling. Median 42 A increases are about 0.394/0.235/0.286 W. These are conditional subtotals, not total switching loss or a hardware recommendation: low-bus gaps, hot losses, prior-cycle recovery, board inductance and floating-dead-time reversal remain unqualified.

The first C2 join and its approximately 33% coverage are **withdrawn**. It censored waves whose diode still conducted at the saved-window end, incorrectly excluding valid channel/diode sharing after turn-on. The corrected core integrates diode heat from off-command to gate-qualified channel onset; later saved-window heat remains a separate diagnostic. [Twenty external-snubber voltage probes](../01-switching-parasitics/round4/snubber-voltage-check/README.md) preserve all original switching metrics and find a maximum sampled proxy discrepancy of 0.12264 µJ. That sample maximum is not a full-grid bound.

**D1: the blocker is the extraction, not a demonstrated board defect.** Corrected FastHenry wire resistance and plate inductance fixtures pass dimensional checks. Historical `.units mm` decks used `sigma=5.8e7` instead of `5.8e4`, making conductivity 1000 times too high; their numerical results are unqualified. The corrected 0.125 mm leg-A mesh still omits 1,327 narrow links and eight barrel spokes, and its crop cuts active power planes. The finer raster approaches one million nodes before thickness refinement. No accepted board matrix exists; D1's README gives the exact geometry, crop and convergence work needed before C1/D2 may consume it.

The native KiCad audit also found that the historical B3 exporter included **198 distinct net-bearing pad/layer shapes with `FlashLayer=false`**. The apparent Q3.1/In1 overlap is not a physical short. Physical drill voids must also be subtracted after final conductor unions. **Round-3 B3 copper and thermal results require corrected re-extraction and re-solve.** The magnitude and direction of the change are unknown; frozen historical evidence is retained.

**D2: 724 V is not proved to be simultaneous channel shoot-through.** The legacy replay peaks at 723.918 V while off-device die VGS is −2.141 V; its later 7.368 V gate maximum is a different event. The vendor internal channel probe includes avalanche. A delayed finite gate clamp reduces the peak to 598.154 V at the finer step, which shows model sensitivity but does not establish the physical-board cause. The D1-dependent capacitor-ESL/shared-return counterfactuals and full grid remain unrun.

## Next work and scope limits

1. Repair and qualify D1's finite-width contacts, physical holes, current-injection boundaries and crop. Solve two meshes with thickness refinement at 1/10/30 MHz; verify material self/mutual convergence, passivity, orientation and package separation before emitting an include.
2. Re-extract/re-solve the affected B3 copper/thermal analysis with the corrected native geometry. Do not carry its old temperatures into a decision.
3. Only after D1 passes, run the planned board-L C1 and D2 cases and replace C2 reference inputs where applicable. Complete the missing hot/recovery/low-bus and floating-dead-time accounting before using total loss to select timing.
4. Keep B held. The current-limited grid supplies evidence for a future protection decision, not authorization to change it. F4/F5 and capacitor current-rating qualification remain outside this round.

## Identity, workers and evidence storage

Coordinator: `/Users/bennet/.codex/worktrees/ps-r4-integration/temper`, branch `codex/ps-r4-integration`. The five parallel workers used GPT-6-Sol in isolated `ps-r4-a`, `ps-r4-c1`, `ps-r4-d1`, `ps-r4-c2` and `ps-r4-d2` checkouts, handed back uncommitted work, and were reused for bounded independent reviews. The round-3 integration checkout stayed read-only.

Every worker and coordinator restored and verified **3327/3327** round-3 raw files through the local-copy route. [Smoke-test evidence](smoke-test.txt) and [raw-input verification](raw-evidence-check.txt) are retained. Native-15 board SHA-256 is `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`. The licensed Infineon model stays local and must not enter Git or an archive.

Round-4 raw waves/decks/logs remain ignored under each packet's `outputs/runs/` or D1's `extraction/`, with source/output hashes in its manifests. They are present in the coordinator and originating worker checkouts. Reports, scripts and summary outputs are the Git handback. No release publication or remote raw-file availability is claimed; another machine needs those local raw files or a later separately published archive before replay.

[Typical diode/Eoss graph extraction](loss-curve-provenance.json) records the datasheet identity, pages and calibration. These graph readings are not guaranteed device limits. The [C2 handoff constraints](C2-HANDOFF.md) preserve the model-accounting assumptions.

The [round-4 local raw manifest](raw-manifest.json) hashes every retained raw file (including superseded diagnostics and pre-cleanup sources). Verify a local copy from the repository root with:

```sh
python3 zapote/power-stage-120v/validation-results/round4-coordination/verify_raw.py zapote/power-stage-120v/validation-results
```

Python 3.11 or later is required for this verifier. Copy the ignored raw directories with their relative paths intact; the manifest is an integrity check, not a download location.
