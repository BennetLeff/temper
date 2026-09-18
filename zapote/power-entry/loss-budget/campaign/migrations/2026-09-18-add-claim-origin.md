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

## How origins were assigned in v1 (superseded — see the v2 section below)

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

**Known imprecision, and why v1 was replaced rather than annotated.** A claim whose
value is a *computation over* source documents but whose `value_kind` is a maximum
— e.g. `fuse-action-screen` — was labelled `source` by rule 3 rather than
`derivation`. The v1 response was to record that imprecision; that was not enough.
`value_kind` does not establish origin at all, and v2 replaces the rule outright.
See **v2 — the `value_kind` rule was wrong** below.

**The v1 per-ledger table that followed is retained as the record of what v1
produced.** The current hashes and origin counts are in the v2 section.

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

## v2 — the `value_kind` rule was wrong, and its errors are corrected

**v1 assigned origins from `value_kind`**: typical/minimum/maximum → `source`. That
is unsound. `value_kind` describes the *value* — bounded, typical, assumed,
measured — and says nothing about whether the value was **read from a record** or
**computed**. It produced a concrete error: AR-PROTCKT's `bank-stored-energy` was
labelled a `measurement` while citing a computation and a netlist. Recording the
imprecision in prose did not make that provenance accurate.

**v2 rules** (`2026-09-18-claim-origin-v2-provenance-fix.py`):

| Rule | Condition | Origin |
| --- | --- | --- |
| 1 | `derived_from`/`inputs` present | `derivation` |
| 2 | `value_kind == assumed` | `assumption` |
| 3 | an explicit reviewed override | as stated |
| 4 | otherwise | `source` |

`value_kind` appears only in rule 2, and only in the one direction that is safe: a
claim asserting its **own** value is assumed is an assumption. Nothing follows from
`maximum` — that is what rule 3's reviewed table is for, because deciding it needs
the claim's meaning.

**Computations corrected to derivations.** Each names the claims it consumes:

| Claim | Ledger | Now | Computes |
| --- | --- | --- | --- |
| `bank-stored-energy` | AR-PROTCKT (+ARC: see below) | derivation, `inputs=[bank-capacitance]` | `E = 0.5·C·V²` |
| `fuse-resistance-hot` | AR-BOUNDS (attempt + canonical) | derivation, `inputs=[fuse-watts-loss-rated]` | `R = P/I²` |
| `fuse-action-screen` | AR-BOUNDS (attempt + canonical) | derivation, `inputs=[a70qs50-pre-arcing-i2t-max]` | `R ≤ E/I²t` |
| `bank-esr-bank-max` | AR-BOUNDS attempt | derivation, `inputs=[bank-esr-120hz-max]` | `ESR/4` |
| `a70qs50-fuse-resistance-estimate` | AR-MERSEN | derivation, `inputs=[a70qs50-watts-loss]` | `R = P/I²` |

Two input claims were **added** where a computation had no claim to name, sourced
from artifacts the attempt already retained — not invented:

- `bank-capacitance` (AR-PROTCKT) ← `raw/netlist_fault_loop.json`.
- `a70qs50-pre-arcing-i2t-max` (AR-BOUNDS, both ledgers) ← the Mersen catalogue.

An input that is a **document** rather than a claim is carried as `evidence` and
described in `justification`; the schema's `inputs` names claim parents only. This
is now stated in the `ClaimOrigin` documentation.

**AR-PROTCKT `bank-stored-energy` — before and after**

```
before: origin=measurement  inputs=[]                    vk=measured
after:  origin=derivation   inputs=[bank-capacitance]     vk=typical
        condition_transformation: evaluated at the 400 V bus setpoint
```

**ARC's `bank-stored-energy` is `source`, not `derivation`** — it is taken from
AR-FAULT's retained coordinator receipt, and the ARC ledger contains no claim it
was computed from. "Read from a record" is what makes a claim a source; that is
why the `ClaimOrigin::Source` doc now says "retained document … or a prior
attempt's retained record" rather than "external document".

## v2 per-ledger state

| Ledger | n | Origins | sha256 |
| --- | ---: | --- | --- |
| `AR-BOUNDS/attempt-001/claims.json` | 27 | assumption 17, derivation 4, source 6 | `95b7371e6356d58ab412c2e3e1f3f4fca600ef0356c2158c594fa977bf6a3124` |
| `AR-COORD/attempt-001/claims.json` | 29 | assumption 18, derivation 1, source 10 | `1d0a505e24b2f0e1d86de7edc527453b6003eeafbbe8ca431263a12a6b9dd87f` |
| `AR-MERSEN/attempt-001/claims.json` | 23 | assumption 15, derivation 1, source 7 | `fe5f36f02fab2635874842b8ebb4687e6ba00bc86e16e9b815b89355038aef55` |
| `AR-PROTCKT/attempt-001/claims.json` | 16 | assumption 6, derivation 2, source 8 | `db4d70ec3daf063566f3b6db88ed479ee56366ac69d17c59bf22d267c478ea7b` |
| `claims/2026-09-18-arbounds-claims-withdrawn.json` | 4 | assumption 3, source 1 | `80b7ecde5acfd83db126026b8eb7ac115c720df12f9b03bdc162c4d5fd249391` |
| `claims/2026-09-18-arbounds-claims.json` | 26 | assumption 16, derivation 4, source 6 | `ea5cdcc4a88bdcc817a8fbefc99174b0add279167f0b1f7e5b567b68d95b67c7` |
| `claims/2026-09-18-arc-claims-withdrawn.json` | 6 | assumption 1, derivation 3, source 2 | `ddcef49444b11f71db0ef6107c4213329ceea91bf3f854887043205a96c86b32` |
| `claims/2026-09-18-arc-claims.json` | 6 | assumption 3, derivation 1, source 2 | `d70363fdf083975e7dc9e02a526b3b4111bf82b510f419b56589769598100f9f` |

The as-stated (`*-withdrawn.json`) fixtures are deliberately **not** overridden and
are reset to the provenance they were originally stated with, so they keep
recording the defect instead of being silently corrected.

## Hash drift — resolved, not hidden

**Historical receipts are retained untouched.** Each `raw/checker/checker_receipt.json`
records the bytes that existed when it ran; rewriting one would claim a check that
never happened.

**Fresh verification records are issued for the migrated bytes**
(`2026-09-18-issue-post-migration-verification.py`):

- `runs/*/AR-*/attempt-001/raw/checker/verification-post-migration.json` — the
  current `claims.json` sha256, the exact command, its exit code and output, and a
  pointer to the historical receipt it supersedes.
- `claims/verification-post-migration.json` — the same for the canonical ledgers.

**Manifests are reconciled.** Each attempt `manifest.json`'s `claims.json` entry now
carries the current hash plus a `post_migration_note`; the pre-migration hashes for
the v1 pass are in the table above. The manifest is the artifact-identity authority
for the tree as it stands, so leaving it pointing at bytes that no longer exist
would have been the disagreement, not the reconciliation.

`AR-PROTCKT/attempt-001/inputs.json` records the canonical ARC ledger as an *input*
at its pre-migration hash. It is left as-is for the same reason as the receipts: it
is a record of what that attempt consumed. The drift is noted here.

## Residual gaps, still open

Three things this work does **not** fix, kept explicit:

1. `2026-09-18-arbounds-claims-withdrawn.json` still **passes**. Its
   `bank-esr-bank-max` performs a derivation while being declared a `source`.
   Detecting that needs the meaning of the prose, not its shape. The regression
   `the_documented_residual_gap_is_still_open` asserts this, so closing the gap
   fails a test rather than passing silently.
2. A receipt or packet that restates an `illustrative` entry as a **bound** is
   outside the ledger. That is how the AR-BOUNDS defect reached the manufacturer
   packet. Closing it needs report-to-ledger consistency: generated tables
   inheriting evidence strength and conditions from the ledger. Tracked separately.
3. Origins were assigned by a reviewed rule plus an explicit override table, claim
   by claim over ~120 claims. Claims neither computed nor explicitly `assumed` are
   `source` by rule 4; an author who disguises a calculation as a document read is
   still not detectable, which is gap 1 restated.

