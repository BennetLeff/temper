---
title: "Qualification exports require clean-build replay"
date: "2026-09-01"
category: best-practices
module: electrical_qualification
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "A qualification package commits generated netlists, schematics, layouts, or manifests"
  - "Generated text embeds checkout-local paths or platform-specific line endings"
  - "Candidate evidence must remain isolated from production design artifacts"
tags:
  - qualification
  - reproducibility
  - atopile
  - generated-artifacts
  - provenance
  - fail-closed
---

# Qualification exports require clean-build replay

## Context

The CT07-T2 and ISO7741 qualification packages initially contained generated
exports that looked credible in review but could not be reproduced from their
Atopile sources. Clean builds exposed two independent problems: component
declarations had hard-coded footprint packages that disagreed with the intended
candidate, and text exports embedded checkout-root paths. Comparing only the
committed files, or rebuilding in the same checkout that produced them, could
not distinguish a real source-derived artifact from a plausible stale one.

Qualification evidence is especially sensitive to this ambiguity. A candidate
package may support a stopped-indeterminate or rejected decision without
authorizing any production change, so its replay tooling must also prove that
the production board and other protected artifacts were not modified as a side
effect.

## Guidance

Treat source-to-export replay as part of the qualification contract:

1. Build the candidate from its declared source in a clean, isolated project
   root with the pinned toolchain.
2. Model package variants explicitly in source. For example, a 0603 resistor
   and a 1206 resistor are distinct component declarations; a caller must not
   relabel an implementation whose footprint is hard-coded elsewhere.
3. Normalize only demonstrated, non-semantic toolchain noise. The shared replay
   helper currently converts CRLF to LF and replaces only the generated
   `<clean-build-root>/src/` prefix with the package's stable root token:

   ```python
   text.replace("\r\n", "\n").replace(
       f"{clean_build_root}/src/", f"{stable_root_token}/src/"
   )
   ```

   Do not sort, rewrite, or broadly canonicalize the export. Those operations
   can hide component identity, connectivity, ordering, or topology drift.
4. Compare every normalized export byte-for-byte with the committed canonical
   set. A match is evidence that the committed artifacts are source-derived;
   schema validity alone is not.
5. Keep verification and publication explicit. Qualification runners expose
   separate `--verify-candidate-build` and `--publish-candidate-build` modes so
   a normal decision replay cannot silently rewrite its own reference inputs.
6. Snapshot the protected production set before publication, write candidate
   outputs atomically, and compare the protected set afterward. Reject symlinks,
   hard-link aliases, path escapes, and files that change during the read.

Tests should use two different temporary build roots containing equivalent
exports, assert identical normalized bytes, introduce one semantic mutation to
prove the comparison fails, and assert protected files remain unchanged during
both verification and publication.

## Why This Matters

A generated file can be syntactically valid, internally consistent, and still
not be the output of the source under review. Clean-build replay binds the
checked-in evidence to that source. Narrow normalization preserves this proof:
it removes known checkout noise without making meaningfully different circuits
compare equal. Protected-set checks separately preserve the authority boundary
between candidate evidence and the production design.

Together these checks turn reproducibility into a construction property rather
than a reviewer assumption.

## When to Apply

- Whenever qualification, compliance, or safety evidence includes committed
  generated text.
- Whenever a generator writes absolute paths, platform-dependent newlines, or
  other known non-semantic data.
- Whenever candidate-only tooling operates in a repository that also contains
  production artifacts it is not authorized to change.
- Do not use broad normalization when the differing bytes have not first been
  shown to be semantically irrelevant.

## Examples

The shared boundary in `scripts/_lib/qualification_replay.py` owns normalization,
atomic publication, secure reads, and protected-set snapshots. Individual
qualification runners own only their export mapping and stable root token. This
keeps the sensitive filesystem mechanics in one tested implementation while
allowing each qualification schema and verdict policy to remain independent.

## Related

- `docs/solutions/tooling-decisions/generated-schematics-from-atopile-netlist-2026-07-15.md`
- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
- `docs/evidence/2026-09-01-ct07-t2-owner-qualification.md`
- `docs/evidence/2026-09-01-iso7741-gate-drive-owner-qualification.md`
