# D23 — TI driver-model compatibility gate

**INDETERMINATE: the available TI UCC21550B-Q1 proxy did not produce a transient result in ngspice 45.2, so this attempt cannot validate native-18/19 gate timing or change any D2 verdict.**

## What was obtained and tested

Base `c09244caa7588bb72d786a8b1b884390003a5caf`, branch `codex/ps-r17-d23-vendor-driver`; all writes are confined to this output directory. [Provenance](provenance.json) records input and harness hashes. [Runtime](runtime.log) identifies the executable.

TI's [UCC21550 catalog page](https://www.ti.com/product/UCC21550) did not expose a model in the inspected design-resources listing. The [UCC21550-Q1 listing](https://www.ti.com/product/es-mx/UCC21550-Q1) provides **UCC21550B-Q1 PSpice Model, SLUM881**. The [download](https://www.ti.com/lit/zip/slum881) contains an unencrypted `ucc21550-q1.lib`, whose header identifies **Rev. A, 2023-10-19**. This is an automotive B-Q1 model; no inspected TI source establishes equivalence to the board's catalog **UCC21550BDWKR**. It is a proxy, not a selected-part qualification.

| Download | SHA-256 |
|---|---|
| SLUM881 archive | `a78cde1efc300da2758bb2e2ff8ce9d6a115acea7b2d5336e1b32a2152a2ab5e` |
| TI library | `4355b47c5ee17cd416075f86f3b80e76b013125f9539fe9ac04b077136ea2b22` |
| Infineon CFD7 library, smoke test only | `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b` |

[fetch_models.sh](fetch_models.sh) downloads and verifies both models. All vendor bytes and smoke caches stay under ignored `vendor/`; no licensed models are part of this deliverable. This conservative treatment does not claim the TI archive explicitly forbids redistribution. [Hash checks](model-fetch.log) and the unchanged upstream kit [smoke test](smoke.log) pass. [smoke.py](smoke.py) changes only the model-cache and temporary-output locations; no Rust build or shared model directory is used.

## Compatibility result and stop condition

The model was included unchanged with `set ngbehavior=psa`, ngspice's [documented PSpice compatibility mode](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf). DIS is grounded, both output supplies are ideal 12 V, VCCI is 3.3 V, RDT is 50 kΩ and both output loads are 1.8 nF. No bootstrap/power-stage model was introduced before this gate.

| Probe | Outcome | Evidence |
|---|---|---|
| Initial fixture, A initially high; 200 ns input gap; requested stop 24 µs | Manually terminated while initializing; no measured transient | [Deck](driver_fixture.cir), [log](runs/fixture-first/run.log), [status](runs/fixture-first/result.json) |
| Both inputs initially low, then A pulse and B edge with 200 ns gap; requested stop 4 µs | **INDETERMINATE**, 60-second process timeout; no measured transient | [Executed deck](runs/fixture-low-start/probe.cir), [log](runs/fixture-low-start/run.log), [status](runs/fixture-low-start/result.json) |

Both logs report failure of dynamic gmin stepping, true gmin stepping and source stepping, then stop progressing at `Transient op started`. Neither reaches the end-of-transient measurement. The initial high-input operating point was removed in the second diagnostic fixture; that did not resolve initialization within the bounded attempt. This identifies an observed convergence blocker, **not proof that every possible ngspice configuration is incompatible**. Its internal root cause remains unresolved.

The parser also warns that `TD` is ignored on four UVLO switch models. Those parameters are `TD=0` in the pinned library, so these warnings alone do not establish a timing error or explain the initialization failure. The vendor source was not changed to suppress warnings or force convergence. The packaged PSpice result is not evidence that this ngspice run completed.

Per D23 step 1 (“if it does not, say exactly why and stop”), integration stopped here. The initial fixture is diagnostic preparation, not a claim of a completed datasheet-characterization suite.

## Requested characterization and comparison disposition

Reference: [TI UCC21550 SLUSE89C, August 2024](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), printed p.10 and §§7.4.2, 8.2.2.8, pp.25–26,33. Datasheet numbers below are specifications/typicals, not simulation output.

| Quantity | Datasheet min / typ / max | D23 model result |
|---|---|---|
| Unloaded propagation, either edge | 26 / 33 / 45 ns | Not measured |
| Rise, 1.8 nF, 20–80%; fall, 90–10% | — / 8 / — ns each | Not measured |
| Programmed dead time, 20 kΩ | 167 / 185 / 203 ns | Not run after compatibility stop |
| Programmed dead time, 50 kΩ | 399 / 443 / 487 ns | INDETERMINATE |
| Longer of programmed/input gap | Longer interval controls | 200 ns fixture did not complete |

TI defines programmed dead time from the outgoing output's 90% falling crossing to the incoming output's 10% rising crossing. That is not automatically MOSFET VGS-threshold dead time; p.33 explicitly distinguishes external gate-network behavior. No 391–498 ns gate-crossing window is established here.

| Requested downstream evidence | Disposition |
|---|---|
| Vendor-driver D2 variant with 49.9 kΩ, bootstrap and selected supply returns | Not constructed after step-1 stop |
| Approximation baseline replay against `grid-best-longdt` | Not run; no fresh baseline reproduction claimed |
| Native-18/19 S1/S2/S4, both directions, ESL 1.06/10 nH, best matrix | Not run |
| Off-gate 3.0 V / 1.9 V screens, die VDS, ZVS and changed verdicts | No new conclusion; existing results remain approximation-based |

## Source identity and next action

[Identity excerpts](identity-excerpts.txt) show frozen BOM and native-19 agreeing on R9/R17 **RT0603BRD0749K9L**, and U1/U2 **UCC21550BDWKR**. `DECISIONS.md` identifies the resistor as 49.9 kΩ ±0.1% and the controller gap as 200 ns. Frozen netlist R9/R17 entries instead have value `?` and a generic `R100R0603` library identifier. That is stale/non-authoritative symbol metadata, **not evidence that the fitted resistors are 100 Ω** and not an established electrical contradiction. No design files were changed.

To reopen D23: establish TI-supported applicability to the catalog B device and qualify a supported simulation configuration against the datasheet fixture. A PSpice execution is a possible next investigation, not an already-validated substitute. Only after that gate should the requested baseline and D2 variant be run. No hardware or firmware decision is justified by this failed initialization.

## Reproduce

From this directory:

```sh
zsh fetch_models.sh
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 smoke.py
/Users/bennet/Miniforge3/bin/python3 probe_model.py
# Expected on the recorded environment: timeout, INDETERMINATE, exit 2.
# Optional bounded replay of the initial high-input fixture:
/Users/bennet/Miniforge3/bin/python3 probe_model.py --first
/Users/bennet/Miniforge3/bin/python3 record_evidence.py
```

The probe hashes the vendor libraries before running, retains failures, and requires a complete transient plus required measurements before calling a future run completed. A future completed run still needs the full characterization and applicability review. Syntax compilation of the three Python harness files and `git diff --check` passed. No broad repository tests were needed for this simulation-evidence-only change.
