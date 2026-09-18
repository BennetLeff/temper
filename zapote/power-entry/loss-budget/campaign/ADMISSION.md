# Dispatch and handback admission rules

Date: 2026-09-17
Enforced by: `zapote/tools/check_campaign_dispatch.py`
(unit tests: `zapote/tools/test_check_campaign_dispatch.py`)

These rules exist because an attempt was admitted with an expired deadline and
no checker, was reported as a completed run, and had to be quarantined
afterwards. The research was useful; the run was not admissible. Enforce at
admission, not after handback.

## Dispatch admission

```bash
python3 zapote/tools/check_campaign_dispatch.py dispatch <dispatch.json> [--now <iso8601>]
```

A packet is admitted only when:

1. Every required coordinator field is present and non-empty: `campaign_id`,
   `task_id`, `attempt_id`, `absolute_deadline_utc`, `allowed_output_directory`,
   `checkout_path`, `source_revision`, `model_revision_and_sha256`,
   `checker_revision_and_sha256`, `contract_path_and_sha256`,
   `exact_build_or_run_commands`.
2. `absolute_deadline_utc` parses as a UTC timestamp, and
3. it is **after the packet's issue time**, and
4. it is **after now** when `--now` is supplied.

Clause 3 is the failure this file was written for: a packet whose deadline had
already passed when it was written. Issue time is taken from the dispatch file's
mtime, because a packet cannot be issued after its own deadline. Write the
packet and the deadline together; do not reuse an earlier deadline.

A field may be `not_applicable: <reason>` where the task genuinely has no such
input, but the reason is part of the field and cannot be empty.

## Handback admission

```bash
python3 zapote/tools/check_campaign_dispatch.py handback <attempt-dir>
```

- **Counted as a validated run** only when `result.json` carries a non-null
  `checker_receipt`.
- **Not counted** when the dispatch declared the checker `not_applicable`: no
  machine receipt can exist, so the attempt is evidence, not a validated run.
  It may still be cited, with its evidence class stated.
- **Failed** when the dispatch declared a checker and no receipt is present.

"Not counted" is not "discarded". The distinction the campaign needs is between
research that informs a decision and a run the harness validated. Collapsing
them is how an inadmissible attempt becomes a census entry.

## Evidence and completion admission

An attempt that makes an electrical-model claim — a loss, current, stress,
protection arrangement or fault result — must include an **evidence ledger** and
pass:

```bash
zapote-claims <attempt-dir>/claims.json
```

and, where a fault loop is modelled:

```bash
python3 zapote/tools/check_fault_loop.py --netlist <netlist> \
  --loop-nets A,B,C --assignments <assignments.json>
```

Both must exit 0, and their output must be retained under `raw/`. Evidence
references are `{path, sha256}` and are resolved against retained bytes for
**every** collection that carries them — ordinary claims, protection claims and
status promotions — so a non-empty list is not on its own evidence. A failing
ledger is an **admission failure for the claim**, not a note appended to the
report. The ledger records, per claim: whether the value is typical, minimum,
maximum, assumed or measured; its source condition and exact part; its fault
state; whether the assertion is illustrative or qualified; and the completion
status with the evidence supporting it.

**Every claim must also declare its origin** — `source`, `assumption`,
`measurement` or `derivation` — and **a derivation must name its inputs**
(`inputs`, and/or `derived_from`). This is enforced at admission, because
`zapote-claims` rejects a ledger whose claims omit it. The reason it is required
rather than optional: every comparison rule compares a claim against a parent, so
a claim that performed a derivation while naming no parent used to be compared
against nothing and passed every check. Duplicate claim ids, inputs that name no
claim, and dependency cycles are rejected too. Migration of the existing ledgers,
the rule used, and what it deliberately does not fix:
`zapote/power-entry/loss-budget/campaign/migrations/2026-09-18-add-claim-origin.md`.

The campaign's committed ledgers are run through these checks by
`zapote/packages/zapote-harness/tests/campaign_ledgers.rs`, so a ledger that
regresses fails the normal test suite rather than going unnoticed. Procedure:
`zapote/skills/electrical-model-review/SKILL.md`. Incidents and reasoning:
`docs/solutions/best-practices/electrical-model-acceptance-rules-2026-09-18.md`.

A clean run means **no violations were detected by the implemented checks**. It
does not establish derivation soundness in general and does not establish that any
claim is true. It also does **not** catch a calculation that is declared a
`source` instead of a derivation, nor a receipt or packet that restates an
illustrative ledger entry as a bound — both are outside the checks' reach and are
what the review procedure is for.

## Consequences

- An attempt that fails dispatch admission may still be executed if it is useful,
  but its artifacts are recorded with `evidence_class: source_research` and it is
  excluded from the run census.
- A coordinator receipt recording the failure is written beside the attempt, and
  the worker report is never modified.
- Findings from an inadmissible attempt are re-examined before use; they are
  cited with the qualification, not promoted.

## Known gap

This gate covers the two failures observed. It does not yet check that a
declared checker's hash resolves to actual bytes, that the output directory is
unused for the attempt, or that the delivered prompt matches the packet. Those
are in `CHECKER.md`'s admission list and remain unimplemented.
