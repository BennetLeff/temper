# Lightweight Requirements-to-Code Traceability Convention

## Overview

Inline `@req(<plan-id>, <req-id>): <note>` comments link source code to plan
requirements. `scripts/check_traceability.py` implements three checks (not
currently wired into any CI workflow — see "CI Wiring" below):

- **R2 (annotation validity):** Every claimed `@req` tag must reference a live
  (non-deferred) requirement in the plan document named by the plan-id, and
  the plan-id must be registered in `docs/traceability-registry.yaml`.
- **R3 (requirement coverage):** Every non-deferred requirement in an active,
  in-scope plan must have at least one `@req` annotation within that plan's
  own declared scope.
- **Registry scope validation:** Every `scope:`/`path:` entry in the
  registry must point to a real, git-tracked file.

**As of the 2026-07-27 scope rewrite** (see
`docs/evidence/2026-07-27-traceability-scope-fix.md` and
`scripts/check_traceability.py`'s own module docstring), the scan universe
is driven directly by `docs/traceability-registry.yaml`: every registered
plan's `scope:` entries (files and directories), unioned together, are what
gets scanned for `@req` annotations. A `TRACEABILITY` sentinel file no
longer gates *whether* a directory is scanned — it only narrows *which
plan-ids* are accepted within the directory it sits in (see "Scoped
Sentinel" below). This replaced an earlier per-directory opt-in model in
which only directories holding a `TRACEABILITY` file were ever examined;
that model gated exactly one directory in the repo's history
(`packages/temper-placer/tests/router_v6/`) and silently skipped every
other plan's coverage check. No mass-annotate pass is required; adoption of
a new plan into the registry's scope is what makes its code eligible for
checking.

## Annotation Format

### Syntax

```
# Python:
# @req(<plan-id>, <req-id>): <optional free-form note>

// C / C++:
// @req(<plan-id>, <req-id>): <optional free-form note>
```

The `@req` keyword, the opening parenthesis, the plan-id, a comma, the req-id,
and the closing parenthesis are **required**. Whitespace between tokens is
flexible. The colon and trailing note are optional.

### Valid Examples

```python
# @req(N4, R4): safety_category fallback with model-first resolution
# @req(N2,R3)
# @req( N2 , R1 ): authority record enumeration -- note
# @req(2026-06-23-004, R3): date-stamped plan-id (see "Plan-ID Shapes" below)
```

```c
// @req(N8, R2): X-macro expansion produces contiguous enum values
// @req(N8,R1)
```

```rust
// @req(2026-06-23-007, R2/K4): the K4 reclaim formula constants.
```

Rust (`.rs`) files use the same `//`-comment syntax as C and are scanned
under the same rule.

### Plan-ID and Req-ID Shapes

Most plans in this repo are named by a date-stamped filename
(`docs/plans/YYYY-MM-DD-NNN-<slug>-plan.md`), not a short code, and
`@req(...)` annotations commonly cite that date-stamped form directly —
either the bare `YYYY-MM-DD-NNN` prefix (`2026-06-23-004`) or, less
commonly, the full filename stem
(`2026-07-09-001-feat-physics-verification-rigor-plan`). A handful of plans
(`N1`-`N10`, `APC1`) are additionally registered under a short alias in
`docs/traceability-registry.yaml`. The plan-id field matches
`[\w-]+` — word characters and hyphens.

Req-ids are not always a bare `R<num>`: real annotations in this repo use
forms like `U8-1`, `R-D5`, and `FR-ADOPT1` (hyphenated), and one dialect
packs two req-ids into a single field with `/` instead of a second comma
(`R2/K4`). The req-id field matches `[\w/-]+`.

**Two dialects the parser does not handle**, found during a 2026-08-12
audit (`docs/evidence/2026-08-12-traceability-regex-fix.md`): an `@req(...)`
with three or more comma-separated fields (`@req(id, R1, R2, R3)`), and a
bare `@req(...)` with no `#`/`//` comment-marker prefix at all (e.g. inside
a docstring body). Both are real, in-use conventions in this repo's code
today, not hypothetical — write new annotations in the two-field,
comment-prefixed form shown above until the parser is extended to cover
them.

### Semantics

- **One line can carry multiple `@req` tags.** A line implementing two
  requirements carries two annotations.
- **One requirement can appear on multiple lines.** A requirement spread across
  several code sites has an annotation at each site.
- **Annotations are informational at the line level** and machine-checked by
  running `scripts/check_traceability.py` (see "CI Wiring" below — this is
  not currently invoked automatically by any GitHub Actions workflow).
- **The plan-id** is either the short form used in plan prose (e.g., `N4`
  for `docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`, one
  of the handful registered under an alias) or the plan's own date-stamped
  id/filename (see "Plan-ID and Req-ID Shapes" above). The mapping from
  short plan-ids to filesystem paths is maintained in
  `docs/traceability-registry.yaml`; a date-stamped plan-id is currently
  only recognized by the R2 gate if it *also* has a registry entry keyed
  under that exact string — most date-stamped plans in this repo do not
  (see `docs/evidence/2026-08-12-traceability-regex-fix.md`).
- **The req-id** is as defined in the plan document (e.g., `R4`).

## Scope Model: Driven by `docs/traceability-registry.yaml`

The scan universe for `@req` annotations is the union of every registered
plan's `scope:` entries (files and directories) in
`docs/traceability-registry.yaml` — **not** "whichever directories happen
to contain a `TRACEABILITY` sentinel file." A file or directory is scanned
if and only if some plan's `scope:` list names it. Coverage (R3) is
additionally scope-precise: an annotation only counts toward a
requirement's coverage if it lives in a file within *that same plan's*
declared scope, so an annotation for a different plan sharing a req-id in
an unrelated file cannot falsely satisfy coverage.

### `TRACEABILITY` Sentinel Files (opt-in *plan-id filter*, not opt-in *scanning*)

A file named `TRACEABILITY` at the root of a directory, if present,
narrows which plan-ids are *accepted* for annotations in that directory
(recursively) — it does not control whether the directory is scanned at
all. A directory with no sentinel anywhere above it is scanned normally if
it falls within some plan's registered scope; there is no unrestricted
opt-out.

### Empty Sentinel

An empty `TRACEABILITY` file means "all active plans' annotations are
accepted in this directory."

### Scoped Sentinel

A `TRACEABILITY` file containing a `plans:` list restricts which plan-ids'
annotations are accepted:

```yaml
plans: [N2, N4]
```

Annotations referencing plans not in the list are flagged as violations
(wrong-directory check).

## Plan-ID Registry: `docs/traceability-registry.yaml`

A committed YAML file mapping short plan-ids to plan document paths and
file-level scopes. Schema:

```yaml
plans:
  <plan-id>:
    path: docs/plans/<plan-document>.md
    scope:
      - path/to/implementing/file.py
      - path/to/another/file.c
```

### Scope Field

The `scope` field lists files and directories that the plan's
implementation touches. It is now the **scan universe itself** — the union
of every plan's `scope` entries is what R2 and R3 look at, not merely where
R3 looks for coverage — as well as, for R3, the boundary that keeps one
plan's annotation from counting toward a different plan's coverage. A plan
author adds their plan to the registry and populates the scope at
plan-implementation time; an omitted or empty `scope` means that plan's
code is invisible to both gates.

A directory-shaped entry ends in a trailing slash
(`packages/temper-placer/tests/router_v6/`) and is recursed; a file-shaped
entry names an exact `.py`/`.c`/`.h`/`.rs` file.

## CI Gates

Implemented in `scripts/check_traceability.py` (a standalone CLI script,
`disposition: utility` in `scripts/manifest.yaml` — see "CI Wiring" below).
There is no `packages/temper-drc/tests/test_traceability_gate.py` or other
pytest entry point; that package was deleted
(`docs/solutions/architecture-patterns/temper-drc-rust-migration-shim-then-delete-2026-08-03.md`).

### R2: Annotation Validity (`--check-annotations`)

Validates every `@req(<plan-id>, <req-id>)` annotation found in the scan
universe against the plan document:

1. Plan-id must be a key in `docs/traceability-registry.yaml` (not merely
   a real plan document — see the plan-id note in "Semantics" above; most
   date-stamped plan-ids are not registered under that exact string today).
2. The referenced plan document must have `status: active` in its YAML
   frontmatter.
3. The req-id must be defined in the plan's "In scope" or "Requirements"
   section.
4. The req-id must not be listed in the plan's "Deferred" section.
5. If the governing `TRACEABILITY` file lists specific plan-ids, the
   annotation's plan-id must be in the list.

Prints one `VIOLATION:` line per failure with file:line and reason, plus a
denominator line reporting how many files were scanned and how many
annotations were found — even on a pass, so a "0 violations" result can be
distinguished from a gate that scanned nothing. Fails closed (exit 1, no
violations printed) if the scan universe is empty.

### R3: Requirement Coverage (`--check-coverage`)

For every plan with `status: active`:

1. Parse all non-deferred requirement IDs from the plan document.
2. For each requirement, check that at least one `@req` annotation for that
   plan exists in a scanned file within *that plan's own* declared scope
   (`_is_file_in_scope`).
3. Print one `UNCOVERED:` line per failure.

Fails closed (exit 1) when zero files were scanned, zero plans are active,
or zero non-deferred requirements were parsed across every active,
in-scope plan — each of those means the gate never evaluated anything,
which must not print the same "passed" message as a gate that evaluated
everything and found no problems.

### Registry Scope Validation (`--check-registry-scope`)

Independent of R2/R3: validates that every `scope:` entry in
`docs/traceability-registry.yaml` actually exists and is git-tracked (a
file-shaped entry must be an exact `git ls-files` match; a directory-shaped
entry must have at least one git-tracked file under its prefix), and that
every plan's `path:` points to an existing document. Prints one
`SCOPE ISSUE:` line per failure.

## Plan Requirement Format (Expected by Parser)

The R2/R3 gates parse requirement IDs from plan documents using the
following heuristics:

- **Requirement definitions:** Lines matching `- R<num>.` or `- R<num>:`
  or `* R<num>` in sections named "In scope" or "Requirements" or
  "Scope Boundaries".
- **Deferred sections:** Sections headed `### Deferred` or `## Deferred`.
  Requirement IDs mentioned in deferred sections are excluded from
  coverage.
- **Plan status:** Read from YAML frontmatter field `status`. Only
  `status: active` plans are gated.
- **Ambiguous requirements:** If a requirement ID appears in both
  "In scope" and "Deferred" sections, it is treated as non-deferred
  (conservative: failures are better than silent gaps).
- **Known gap:** the requirement-definition regex matches `R<num>` only. A
  plan whose units are labeled `U1`-`U4` instead (e.g.
  `docs/plans/2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md`)
  will have real, correctly-cited `@req(N10, U1)`-style annotations flagged
  as "requirement not defined" even though the requirement exists in the
  plan under a different label shape. Not fixed by this document; noted so
  it isn't mistaken for a dangling annotation.

## Developer Workflow

1. **Plan author:** Adds the plan to `docs/traceability-registry.yaml`
   (mapping plan-id to path and scope) as part of implementation. A
   date-stamped plan-id must be registered under that exact string for R2
   to recognize it — adding the plan document alone is not sufficient.
2. **Implementer:** Annotates implementing code with
   `@req(<plan-id>, <req-id>): <note>` using the `#`/`//`-prefixed,
   two-field form. A `TRACEABILITY` sentinel is only needed if the
   directory should *restrict* which plan-ids are accepted there — its
   absence does not exempt the directory from scanning (see "Scope Model"
   above).
3. **CI:** Nothing today — see "CI Wiring" below.
4. **Reader:** Sees `@req(N4, R4)` in code and navigates to the plan
   document via the registry mapping.

## CI Wiring

`scripts/check_traceability.py` is `disposition: utility` in
`scripts/manifest.yaml`, not invoked by any `.github/workflows/*.yml` job.
Running it and reading its output is a manual/local step; a red or green
result today has no effect on whether a PR can merge. See
`docs/evidence/2026-08-12-traceability-regex-fix.md` for the current state
of what the gate reports when run and why it should not yet be wired in as
a hard blocker (a real, separate registry-coverage gap independent of the
regex fix that document addresses).

## Local Development

```bash
# CLI wrapper — run all three checks
uv run python scripts/check_traceability.py --all

# Individual checks
uv run python scripts/check_traceability.py --check-annotations
uv run python scripts/check_traceability.py --check-coverage
uv run python scripts/check_traceability.py --check-registry-scope
```
