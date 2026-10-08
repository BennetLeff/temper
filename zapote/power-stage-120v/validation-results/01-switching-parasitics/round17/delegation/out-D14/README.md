# D-14 — solver robustness

**The cold aborts are sensitive to the nonlinear iteration allowance: `ITL4=100000` resolves all 25 original aborts without changing 221 comparable results; all 192 decision cases converge from 0.1 to 0.05 ns, while one extra near-threshold hot-screen verdict remains boundary-sensitive.**

## Proposed change

Include [proposed-options.inc](proposed-options.inc) after the existing common
options, or append its single option to a generated deck:

```spice
.options itl4=100000
```

ITL4 controls the transient timepoint iteration ceiling ([ngspice manual,
§11.1.4, p. 325](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf#page=325)).
The original common settings use 200. This proposal changes no component,
model equation, integration method, convergence tolerance, initial condition
or maximum timestep. The shared D2 deck, common options, FEM inputs and board
remain unchanged. It is a proposal for these measured cases, not an automatic
retry policy or a claim that a large iteration ceiling guarantees convergence.
It is the smallest passing **tested** allowance (200, 1000, 10000, 100000),
not a search-derived minimum iteration count.

## Same-step qualification

[final-comparison.csv](final-comparison.csv) and
[qualify-itl100k.json](qualify-itl100k.json) record all 246 pairs/cases. All
25 original aborts reproduce. The proposal completes all 246 cases.
For the 221 pairs where both settings complete, **every parsed printed
measurement is identical**, including the D-6 energy integrals. Off-gate
and die-VDS maximum differences are both zero at printed precision. No
3.0 V screen, 1.9 V screen, VDS, absolute-VGS or ZVS classification changes.
This does not claim bitwise identity of internal solver trajectories.

| Set | Original complete / total | Proposed complete / total |
| --- | ---: | ---: |
| Distinct historical grid aborts | 0 / 14 | 14 / 14 |
| D-6 refinement set | 21 / 32 | 32 / 32 |
| Best-matrix S1/S2/S4 decision set | 192 / 192 | 192 / 192 |
| Nearest off-gate thresholds | 8 / 8 | 8 / 8 |

[recovered-aborts.csv](recovered-aborts.csv) reports the recovered measurements
and each screen separately. Recovery means that a result is available; it
does not mean the circuit passes. For example, the recovered 5 A / 280 V /
DIR1 / ESL20 nH / DT348 ns case has off-gate peak 1.981376 V and incoming
VDS 270.6162 V: it fails the provisional hot screen and does not achieve ZVS.

## Timestep convergence and classification boundary

The final campaign uses the same ITL4=100000 setting at maximum steps
0.2, 0.1 and 0.05 ns for all 192 decision cases and eight near-threshold
cases: **600/600 complete results**, with no aborts. The three values are **maximum adaptive
steps**, not constant internal steps. The original deck ties its nominal
output interval to the maximum step; both are reduced together. ngspice can
use much smaller internal steps at breakpoints and during convergence retries.

Primary comparison tolerances were set before examining the comparisons:
0.01 V off-gate peak and 0.5% die-VDS peak. These are numerical tolerances,
not extra design margin. The 10 mV gate tolerance limits peak movement to
0.53% of the tighter 1.9 V screen, while the 0.5% VDS tolerance limits movement
to roughly 1–2.5 V across these peaks. Neither alone protects a result close
to its screen. All comparisons also test the actual classifications,
so a crossing is reported even if its voltage difference is below 0.01 V.
The eight closest existing off-gate margins include a 2.648 mV separation
from 1.9 V; they are explicitly included rather than inferred from remote
passing cases.

[convergence.csv](convergence.csv) contains all three pairwise intervals.
For the **192 required decision cases**, all 0.1→0.05 ns comparisons satisfy
both numerical tolerances and preserve every classification:

| Maximum-step interval | Pairs | Outside tolerance | Classification changes | Largest off-gate change | Largest VDS change |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.2→0.1 ns | 192 | 0 | 0 | 7.940 mV | 0.4619% |
| 0.1→0.05 ns | 192 | 0 | 0 | 2.084 mV | 0.1667% |
| 0.2→0.05 ns | 192 | 16 | 0 | 10.014 mV | 0.6178% |

Thus the historical 0.2 ns setting is not uniformly converged to the finest
reference at the stated tolerance. Use **0.1 ns maximum step or finer** for
these quantitative peak comparisons with the proposed iteration allowance.
This is a timestep-accuracy recommendation, separate from the cap-only
same-step qualification. No tolerance was relaxed to make the table pass.

The eight additional near-threshold cases are in
[near-threshold-convergence.csv](near-threshold-convergence.csv). Their
0.1→0.05 ns peak movements also meet the numerical tolerances, but one
**1.9 V classification changes**: S3, 170 V, 2 A, DIR0, DT498 ns, ESL10 nH.
Its off-gate peaks are 1.902648, 1.900401 and 1.899797 V at 0.2, 0.1 and
0.05 ns respectively. The finer pair moves only 0.604 mV, yet crosses the
screen. Treat this result as boundary-sensitive, not a robust hot-screen pass.
The screen remains exactly 1.9 V; no hidden acceptance band is applied.
The separately recorded [0.025 ns probe](boundary-probe-itl100k.json) completes
and gives **1.899640 V**, 0.157 mV below the 0.05 ns result and only 0.360 mV
below the screen. The finest two sampled tiers agree on passing the screen,
but that tiny margin does not support a robust pass claim.

Across all 200 cases, 0.2→0.1 ns has three tolerance misses (all additional
near-threshold cases), 0.1→0.05 has none, and 0.2→0.05 has 19. Maximum
coarse-to-finest VDS movement is 0.8899%. Only the boundary case above changes
classification; none of the 192 required decision cases changes.

## Diagnosis and rejected candidates

The logs locate the original failures at node `bus`, at initial transient
steps (~2 ps) and switching breakpoints (2 µs; a D-6 remedy case also fails
at 2.348 µs). They report an initial transient solution and completed dynamic
GMIN stepping; these are not simply missing operating-point runs.
[diagnosis.json](diagnosis.json) retains the per-case evidence.

Changing only the transient iteration budget recovers them. The established
cause class is **numerical iteration-budget sensitivity of the complete
coupled nonlinear deck**. This does not isolate a defect in the driver
B-source, a particular matrix entry or the vendor model. The node named by
ngspice is a convergence location, not proof that a component at that node
is defective. The strict matrix checks and original input hashes are preserved.

An isolated recovery is insufficient qualification. ITL4=1000 recovers the
original grid failures but still fails one D-6 refinement case and additional
fine-step startup cases. ITL4=10000 resolves the full original same-step set
but fails 0.05 ns startup cases at 280 V, DIR1, ESL1.06/20 nH. Both unsuccessful
refinement campaigns were stopped after those failures; their partial rows,
original manifests/logs and exact completed/terminated/unstarted inventories
remain in `convergence-*-partial.json` and `convergence*-stop.json`.
No terminated or unstarted run is counted as complete.

Before the final full campaign, ITL4=100000 passed all 24 finest-step frontier
cases at 280 V: S1, S2 at both 61 and 71 A, and S4, both directions, and
ESL1.06/10/20 nH at DT348 ns. These exact-identity results are reused in the
full campaign. The initial 50-run option screen and bounded later probes
remain in their named JSON/log files. Relaxed ABSTOL/VNTOL alternatives were
explored, but **neither is part of the proposal**.

## Scope and reproducibility

Base: `a5eddd2bec65d0dd026bdd47087947b0b22cbfd6`; ngspice 45.2; Miniforge
Python 3.12. The required vendor fetch verified ZIP SHA-256
`5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d`
and library SHA-256
`02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`.
The sim-kit smoke test passed before the campaign and in the saved final
[smoke.log](smoke.log). The initial fetch output was tool-visible rather than
saved; [vendor-hash-verification.json](vendor-hash-verification.json) is an
explicitly labeled post-campaign check of those fetched files. No licensed
library is part of the deliverable.

The 14 grid cases are the union of ten `grid-best` and six `grid-best-longdt`
aborts, deduplicating the two shared 391 ns cases. The 32 D-6 cases use their
original saved parameters, matrices and decks at 0.1 ns. The 192 decision
cases contain all 32 legacy best-matrix S1/S2/S4 cases at DT307/348 ns and
ESL10 nH, plus ESL1.06/20 nH at those dead times and DT391/443/498 ns.
The eight closest off-gate margins are selected deterministically from both
published grids after deduplication.

`source-inputs.json`, `original-recorder-provenance.json`, the campaign
manifests and `simulator-executable.json` bind the source revision, input
hashes, exact simulator binary and runtime. Immutable recorder source versions
are saved as hash-named `.py.txt` files under `recorder-snapshots/`. Cache reuse
requires matching frozen dependencies, simulator binary/version, parameters,
options, source deck and full generated deck text.

[verification.json](verification.json) records an independent reparse of all
1,770 recorded simulator attempts, including 101 retained unsuccessful attempts.
The verifier confirms the exact 246-case qualification, 600-result convergence
campaign and single boundary probe; it rejects abort, nonzero-exit, missing-endpoint
and truncated-endpoint mutations. It also checks all 221 unchanged measurement
dictionaries and all 192 fine-interval decision verdicts. Ruff passes for the
five maintained Python scripts. The archive verifier checks all 8,874 members.

[deliverable-manifest.json](deliverable-manifest.json) lists the exact files,
sizes and SHA-256 hashes to publish (excluding itself and ignored unpacked raw
files). Include its explicitly listed `.log` receipts even if a repository-wide
ignore rule normally excludes them.

Run from the repository root using the recorded base inputs:

```sh
D14=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D14
D14_PYTHON=/Users/bennet/miniforge3/bin/python
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
$D14_PYTHON zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
$D14_PYTHON "$D14/investigate.py" --mode qualify --options old --label original-reproduction --workers 4
$D14_PYTHON "$D14/investigate.py" --mode qualify --options itl100k --label qualify-itl100k --workers 4
$D14_PYTHON "$D14/investigate.py" --mode convergence --options itl100k --label convergence-itl100k --workers 4
$D14_PYTHON "$D14/investigate.py" --mode convergence --options itl100k --select near_S3_v170_i2_d0_dt498_esl10 --steps 0.025 --label boundary-probe-itl100k --workers 1
$D14_PYTHON "$D14/summarize.py"
$D14_PYTHON "$D14/verify.py"
$D14_PYTHON "$D14/check_baseline.py"
```

When `original-reproduction.json` exists, both the summary and verifier use it
only after checking its complete, unique 246-case inventory and equality of
inputs, completion states and measurements with the frozen baseline. The verifier
also checks its manifest, raw records and logs, retaining the 25 expected aborts.
Missing or changed fresh baseline evidence cannot silently fall back to the old
report. `check_baseline.py` exercises missing/duplicate rows and changed
completion, option, identity and measurement records.

Full raw files remain locally under ignored `raw/`. The committed
[raw-evidence.tar.gz](raw-evidence.tar.gz) preserves every generated deck,
parameter file, simulator initialization file, native log and result record,
including failed and terminated attempts. [raw-evidence-manifest.json](raw-evidence-manifest.json)
records SHA-256 and size for every archive member plus the archive digest.
`bundle.py --verify` checks these hashes and rejects absolute paths, traversal,
symlinks, duplicate members, non-regular files and vendor libraries.

Verify before extracting into a **new, separate** directory:

```sh
$D14_PYTHON "$D14/bundle.py" --verify
D14_EXTRACT=$(mktemp -d)
tar -xzf "$D14/raw-evidence.tar.gz" -C "$D14_EXTRACT"
```

Generated decks retain the original worktree's absolute common-options include;
use the runner to regenerate executable decks in a new checkout. Archive
extraction is for inspection and does not rewrite those recorded originals.

This qualification is at the original **27 °C** simulator temperature. It
does not establish hot-F6 convergence, vendor-model agreement with hardware,
a guaranteed 1.9 V threshold, or guaranteed minimum driver dead time. Those
are separate model/design questions; do not transfer this cold qualification
to D-13's hot generic-diode failures.
