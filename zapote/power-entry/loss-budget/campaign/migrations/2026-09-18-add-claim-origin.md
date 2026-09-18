# Migration record — explicit claim origins

**Date:** 2026-09-18
**Issue:** #1606
**Script:** [`2026-09-18-add-claim-origin.py`](2026-09-18-add-claim-origin.py) (idempotent, `--check` to dry-run)
**Schema owner:** `zapote/packages/zapote-erc/src/evidence_claims.rs`

## What changed and why

`zapote-claims` now requires every claim to declare an **origin** — `source`,
`assumption`, `measurement` or `derivation` — and requires a derivation to
**name its inputs**.

The gap this closes: every comparison rule in `unsound_derivations` compares a
claim against a **parent**, and the only way to name a parent was `derived_from`,
whose absence was a silent default. A claim that performed a derivation while
declaring no parent was therefore compared against nothing, and passed.
Observed on AR-BOUNDS: `bank-esr-bank-max` computed `0.4737 ohm / 4` in its own
justification, declared `derived_from: null`, and passed every check. Declaring
its real parent made the source-condition and part checks fire immediately — it
was one field away from detection.

Full analysis: `runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/coordinator-receipt.md`.

## How origins were assigned

Read from what each claim already declared. Nothing was inferred from prose and
nothing was invented:

| Rule | Condition | Origin |
| --- | --- | --- |
| 1 | `derived_from` is set | `derivation`, `inputs = [derived_from]` |
| 2 | else `value_kind == measured` | `measurement` |
| 3 | else `value_kind` ∈ {typical, minimum, maximum} | `source` |
| 4 | else | `assumption` |

`value_kind` is the discriminator because it is the claim's **own** existing
declaration: the worker already recorded per claim whether the value was read
bounded from a document (typical/minimum/maximum) or is a model result
(`assumed`). Rule 3 reads a field the claim already carries rather than guessing
at meaning.

**Known imprecision, deliberately not papered over.** A claim whose value is a
*computation over* source documents but whose `value_kind` is a maximum — e.g.
`fuse-action-screen`, an action screen built from a catalogue I²t and a computed
`E/R` — is labelled `source` by rule 3 rather than `derivation`. Refining those
to derivations with named inputs is follow-up work, and the checker cannot detect
the difference in any case. Rule 4 is the weakest honest label: a claim with no
bounded or sourced value establishes nothing.

## Per-ledger effect

| Ledger | Origins assigned | Pre-migration sha256 (prefix) | Post-migration sha256 |
| --- | --- | --- | --- |
| `runs/.../AR-BOUNDS/attempt-001/claims.json` | assumption 17, derivation 1, source 8 | `bbf054d774678dda` | `061c0453672d66df0e46b3e33aa433c7a052e591ea3a071def1d58e0a3f90fc0` |
| `runs/.../AR-COORD/attempt-001/claims.json` | assumption 18, derivation 1, source 10 | `69b1c9fc670c2913` | `1d0a505e24b2f0e1d86de7edc527453b6003eeafbbe8ca431263a12a6b9dd87f` |
| `runs/.../AR-MERSEN/attempt-001/claims.json` | assumption 16, source 7 | `467e2b0e9538c1d5` | `8c8c9b695a9e82fcc2728d6148eaf660d60ab1e3af248e3aa34d9f117ada7342` |
| `runs/.../AR-PROTCKT/attempt-001/claims.json` | assumption 6, derivation 1, measurement 1, source 7 | `64135a3a1117a3ee` | `ac9c41545d712927779a1dbbd79daabe2d56c0f993f1e82574071942d8d35a7b` |
| `claims/2026-09-18-arbounds-claims-withdrawn.json` | assumption 3, source 1 | `e0197559fd4e685c` | `6d53f3ef2530599c9b1241d4667499184bc061587a5efc96a0453d9abd719218` |
| `claims/2026-09-18-arbounds-claims.json` | assumption 16, derivation 2, source 7 | `1a7bbed90e04d2cd` | `c41fda788a7433242ecc978f2e7662b4172cc2568b17a56b24502764280e82d9` |
| `claims/2026-09-18-arc-claims-withdrawn.json` | assumption 1, derivation 3, measurement 1, source 1 | `979ccbf94dfbb9a1` | `6b42904f8db5b4aeb1ca287ac87864b4be54a173a130e8a8c9fa9b9577d22608` |
| `claims/2026-09-18-arc-claims.json` | assumption 3, derivation 1, measurement 1, source 1 | `62884b587c553318` | `5064a7ab8f10a8e2e52e34cf2cc4ab60e2c88e39e3c7a43ba31844531682c0a7` |

## Hash drift — recorded rather than hidden

Migrating a ledger changes its bytes, and several artifacts record the old ones:

- the four `attempt-001/manifest.json` files list `claims.json` with its hash;
- `AR-COORD` and `AR-PROTCKT` `raw/checker/checker_receipt.json` record
  `claims_json_sha256`;
- `AR-PROTCKT/attempt-001/inputs.json` records the canonical ARC ledger's hash.

**Those records were deliberately left unchanged.** Each one is a true statement
about the bytes that existed when it was written, and rewriting it would claim a
checker was run on bytes it never saw. Nothing in the repository verifies them,
as `grep` for `claims_json_sha256` outside the receipts confirms — they are
records, not gates. The drift is stated here instead.

## Residual gap, still open

Two of the four AR-BOUNDS defects are **not** addressed and cannot be by this
schema:

1. `2026-09-18-arbounds-claims-withdrawn.json` still **passes**. Its
   `bank-esr-bank-max` performs a derivation while being declared a `source`.
   Detecting that needs the meaning of the prose, not its shape. The regression
   `the_documented_residual_gap_is_still_open` asserts this, so that closing the
   gap fails a test rather than passing silently.
2. A receipt or packet that restates an `illustrative` entry as a **bound** is
   outside the ledger entirely. That is how the AR-BOUNDS defect reached the
   manufacturer packet. Closing it needs report-to-ledger consistency: generated
   tables inheriting evidence strength and conditions from the ledger rather than
   restating them, with prose upgrades caught in review.
