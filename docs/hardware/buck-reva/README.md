# Buck Rev A — bring-up documentation index

Status: **documentation in preparation — no hardware has been powered or measured.**
No physical test is complete. All result fields are empty until an operator runs the bench session.

| Document | Purpose |
|---|---|
| [BRINGUP.md](BRINGUP.md) | Concise operator runbook (first power → 0.5 A → 1 A pulses). |
| [measurement-definitions.md](measurement-definitions.md) | Exact stimulus, capture, and calculation definitions behind the runbook. |
| [equipment.md](equipment.md) | Required capabilities, wiring/probing, and what is unavailable when a capability is missing. |
| [results-template.csv](results-template.csv) | Empty per-operating-point table (to be filled by the operator). |
| [run-record-template.md](run-record-template.md) | Session record: revision, inspection, instrument settings, event log, conclusion. |
| [images/](images/) | Connector/probe map and bench wiring diagram — **PROVISIONAL until the board freeze**. |

## Documentation readiness

- [x] Operator sequence drafted (staged first power, load progression, stop/retry rules).
- [x] Measurement definitions drafted for startup, steps/pulses, ripple, thermal, efficiency.
- [x] Equipment capabilities and degradation paths listed.
- [x] Empty result templates created (no model outputs filled in as bench data).
- [ ] Pinout/probe figures bound to the frozen board — blocked on the board owner's
  `pcb/prototypes/buck-reva/verification/board-freeze.md` and `source-manifest.json`.
  Current figures are labeled **PROVISIONAL — DO NOT ENERGIZE FROM THIS DRAWING ALONE**.
- [ ] Tabletop walkthrough against the frozen schematic/assembly drawing — pending freeze.

## Actual test status

No bench session has been run. Every check below is **NOT RUN**:

- DC regulation (13.5/15/16.5 V × 0/0.05/0.10/0.25/0.50 A) — NOT RUN
- Startup (corners × 0/0.5 A) — NOT RUN
- Load step 0.05↔0.50 A — NOT RUN
- Pulse 0.05↔1.00 A, 10 ms — NOT RUN
- Output ripple (incl. 1 A plateau) — NOT RUN
- Room-temperature thermal screen — NOT RUN
- Efficiency observation — NOT RUN

## Bound revision

No board revision is frozen at the time of writing. Before energizing, the operator must
record the matching release manifest/hash from `pcb/prototypes/buck-reva/verification/board-freeze.md`
in the run record, verify J1/J2 pin numbering and TP1–TP4 silk against the final assembly
drawing, and re-issue these figures. If several revisions exist, refer to the manifest/hash,
not just "Rev A".

## Deferred qualification items (explicit, out of scope for initial bring-up)

- Combined capacitor derating (C9/C10/C11/C12/C13 effective minima under bias/temperature/aging).
- Hot-inductor / fault characterization. The 8.35 A hot-inductor screen is **not**
  a commanded output load for this board; do not drive it through the buck output.
- Environmental qualification (0/40/70 °C ambient corners, validated junction estimation).
- Behavioral-model correlation.
- No mains, inverter, hi-pot, or intentional short-circuit tests belong in this runbook.
  This prototype contains only the 15 V-to-3.3 V buck and bench interfaces —
  no 24 V input, 5 V checks, MCU boot, UART/SPI/I²C, mains, or inverter steps.

## Sources and precedence

- Adopted limits: `harness-lab/engineering/requirements.json`
  (revision `temper-buck-requirements-2026-09-10-startup-compliance`).
- Measurement definitions: `harness-lab/audits/buck-20260910-followup/requirements-proposal.md`.
- Startup stimulus update: `harness-lab/engineering/scenarios/lmr51430-datasheet/` and
  `harness-lab/audits/buck-final-20260910/full-scenario-readiness/README.md`.
- Known limitations: `harness-lab/audits/buck-final-20260910/components/qualification-ledger.md`
  and the margin/transient-resolution reviews.
- Numerical limits here are adopted project targets unless their source says otherwise.
  They are not claims about measured hardware or manufacturer guarantees.
