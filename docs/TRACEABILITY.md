# Lightweight Requirements-to-Code Traceability Convention

## Overview

Inline `@req(<plan-id>, <req-id>): <note>` comments link source code to plan
requirements. Two CI gates enforce consistency:

- **R2 (annotation validity):** Every claimed `@req` tag must reference a live
  (non-deferred) requirement in the plan document named by the plan-id.
- **R3 (requirement coverage):** Every non-deferred requirement in an active
  plan must have at least one `@req` annotation in opted-in source code.

The system is opt-in per-directory via a `TRACEABILITY` sentinel file. Only
directories containing a `TRACEABILITY` file are scanned for annotations.
No mass-annotate pass is required; adoption is incremental.

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
```

```c
// @req(N8, R2): X-macro expansion produces contiguous enum values
// @req(N8,R1)
```

### Semantics

- **One line can carry multiple `@req` tags.** A line implementing two
  requirements carries two annotations.
- **One requirement can appear on multiple lines.** A requirement spread across
  several code sites has an annotation at each site.
- **Annotations are informational at the line level** and machine-checked at
  CI time.
- **The plan-id** is the short form used in plan prose (e.g., `N4` for
  `docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`). The
  mapping from short plan-ids to filesystem paths is maintained in
  `docs/traceability-registry.yaml`.
- **The req-id** is as defined in the plan document (e.g., `R4`).

## Opt-In Model: `TRACEABILITY` Sentinel Files

A file named `TRACEABILITY` at the root of a directory signals that files
under that directory (recursively) participate in traceability. Only
directories containing a `TRACEABILITY` file are scanned for `@req`
annotations.

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

The `scope` field lists files that the plan's implementation touches. It
is used by the R3 gate to determine where to look for coverage annotations.
A plan author adds their plan to the registry and populates the scope at
plan-implementation time.

## CI Gates

### R2: Annotation Validity (`test_req_annotations_valid`)

Validates every `@req(<plan-id>, <req-id>)` annotation against the plan
document:

1. Plan-id must be in the registry.
2. The referenced plan document must have `status: active` in its YAML
   frontmatter.
3. The req-id must be defined in the plan's "In scope" or "Requirements"
   section.
4. The req-id must not be listed in the plan's "Deferred" section.
5. If the `TRACEABILITY` file lists specific plan-ids, the annotation's
   plan-id must be in the list.

Violations are hard CI failures with file:line and reason.

### R3: Requirement Coverage (`test_req_coverage_complete`)

For every plan with `status: active`:

1. Parse all non-deferred requirement IDs from the plan document.
2. For each requirement, check that at least one `@req` annotation exists
   in an opted-in file within the plan's scope.
3. Flag uncovered requirements as hard CI failures.

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

## Developer Workflow

1. **Plan author:** Adds the plan to `docs/traceability-registry.yaml`
   (mapping plan-id to path and scope) as part of implementation.
2. **Implementer:** Places a `TRACEABILITY` sentinel in the directory
   (if none exists) and annotates implementing code with
   `@req(<plan-id>, <req-id>): <note>`.
3. **CI:** Catches invalid annotations and uncovered requirements.
4. **Reader:** Sees `@req(N4, R4)` in code and navigates to the plan
   document via the registry mapping.

## Local Development

```bash
# Run both gates locally
uv run pytest packages/temper-drc/tests/test_traceability_gate.py

# CLI convenience wrapper
uv run python scripts/check_traceability.py --all

# Individual checks
uv run python scripts/check_traceability.py --check-annotations
uv run python scripts/check_traceability.py --check-coverage
uv run python scripts/check_traceability.py --check-registry-scope
```
